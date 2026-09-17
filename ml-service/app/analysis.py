from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import numpy as np
import shap

from .baseline import Baseline, BaselineManager
from .config import Settings
from .data_client import SkyGuardDataClient, reading_is_faulty
from .ml_placeholders import MlDetector, StatisticalDetector, SensorDiagnosticDetector, FeatureEngineer
from .calibrated_multivariate import CalibratedMultivariateDetector
from .calibrated_fusion import CalibratedScoreFusion
from .alert_state import AlertStateManager
from .aws_analysis import AwsAnalysisEngine
from .sensor_mode import SensorMode
from .models import AnalyzeResponse, AnomalyResult, DetectorResult, EngineeredFeatures, EventDetectionMetrics, EventLatency, EvaluationMetrics, EvaluationResponse, GroundTruthEvent, MlServiceStatus, SensorReading, ShapContribution

logger = logging.getLogger(__name__)


def calculate_metrics(truth: Sequence[bool], predictions: Sequence[bool]) -> EvaluationMetrics:
    if len(truth) != len(predictions):
        raise ValueError("Truth and prediction sequences must have the same length")
    tp = sum(actual and predicted for actual, predicted in zip(truth, predictions))
    fp = sum(not actual and predicted for actual, predicted in zip(truth, predictions))
    tn = sum(not actual and not predicted for actual, predicted in zip(truth, predictions))
    fn = sum(actual and not predicted for actual, predicted in zip(truth, predictions))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return EvaluationMetrics(true_positives=tp, false_positives=fp, true_negatives=tn, false_negatives=fn, precision=precision, recall=recall, f1_score=f1)


def calculate_event_latencies(events: Sequence[GroundTruthEvent], results: Sequence[AnomalyResult]) -> list[EventLatency]:
    ordered_results = sorted(results, key=lambda result: result.timestamp)
    latencies: list[EventLatency] = []
    for event in sorted(events, key=lambda item: item.start_timestamp):
        first = next((r for r in ordered_results if r.timestamp >= (event.end_timestamp or event.start_timestamp) and r.is_anomaly and (event.fault_type != "MISSING_DATA" or r.fault_type == "MISSING_DATA" or "missing_data" in r.reasons)), None)
        if event.fault_type != "MISSING_DATA":
            first = next((r for r in ordered_results if r.timestamp >= event.start_timestamp and (event.end_timestamp is None or r.timestamp <= event.end_timestamp) and r.is_anomaly), None)
        normal = next((r for r in ordered_results if event.end_timestamp and r.timestamp > event.end_timestamp and not r.is_anomaly), None)
        latencies.append(EventLatency(fault_type=event.fault_type, affected_variable=event.affected_variable, start_timestamp=event.start_timestamp, end_timestamp=event.end_timestamp, detection_latency_seconds=(first.timestamp - event.start_timestamp).total_seconds() if first else None, recovery_latency_seconds=(normal.timestamp - event.end_timestamp).total_seconds() if normal and event.end_timestamp else None))
    return latencies


def calculate_event_metrics(events: Sequence[GroundTruthEvent], latencies: Sequence[EventLatency]) -> dict[str, EventDetectionMetrics]:
    by_key = {(item.fault_type, item.start_timestamp): item for item in latencies}
    output: dict[str, EventDetectionMetrics] = {}
    for fault_type in sorted({event.fault_type for event in events}):
        fault_events = [event for event in events if event.fault_type == fault_type]
        items = [by_key[(event.fault_type, event.start_timestamp)] for event in fault_events]
        detected = [item for item in items if item.detection_latency_seconds is not None]
        recovered = [item for item in items if item.recovery_latency_seconds is not None]
        total = len(items)
        output[fault_type] = EventDetectionMetrics(total_events=total, detected_events=len(detected), missed_events=total-len(detected), detection_rate=len(detected)/total if total else None, mean_detection_latency_seconds=sum(i.detection_latency_seconds for i in detected)/len(detected) if detected else None, mean_recovery_latency_seconds=sum(i.recovery_latency_seconds for i in recovered)/len(recovered) if recovered else None)
    return output


class AnalysisEngine:
    def __init__(self, client: SkyGuardDataClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.baseline_manager = BaselineManager(settings.baseline_size)
        self.feature_engineer = FeatureEngineer(settings.rolling_window)
        self.readings: list[SensorReading] = []
        self.events: list[GroundTruthEvent] = []
        self.baseline = Baseline((), settings.baseline_size)
        self.last_error: str | None = None

    @staticmethod
    def normalize_mode(sensor_mode: str | None) -> SensorMode:
        try:
            return SensorMode((sensor_mode or SensorMode.FULL).upper())
        except ValueError as error:
            raise ValueError("sensor_mode must be FULL or AWS") from error

    async def refresh(self, limit: int | None = None) -> bool:
        try:
            readings, events = await asyncio.gather(self.client.fetch_readings(limit), self.client.fetch_ground_truth())
            self.readings = sorted(readings, key=lambda reading: reading.timestamp)
            self.events = sorted(events, key=lambda event: event.start_timestamp)
            self.baseline = self.baseline_manager.build(self.readings, self.events)
            self.last_error = None
            return True
        except Exception as error:
            self.last_error = str(error)
            logger.exception("Unable to refresh Layer 1 analysis data")
            return False

    def _run_detectors(self) -> list[AnomalyResult]:
        features = self._engineered_features()
        baseline_features = self._baseline_features(features)
        ml_detector = MlDetector(threshold=self.settings.anomaly_threshold)
        ml_detector.fit(baseline_features)
        statistical_results = StatisticalDetector(threshold=self.settings.anomaly_threshold).detect(features)
        ml_results = ml_detector.detect(features)
        # Explain only the latest point. The dashboard requests the latest
        # result, while calculating SHAP for thousands of historical rows on
        # every refresh is unnecessary and can make TreeSHAP fragile/slow.
        ml_results = self._attach_shap(ml_detector, features, baseline_features, ml_results)
        diagnostic_results = SensorDiagnosticDetector(frozen_consecutive=self.settings.diagnostic_frozen_consecutive, frozen_tolerance=self.settings.diagnostic_frozen_tolerance, expected_interval_seconds=self.settings.diagnostic_expected_interval_seconds, threshold=self.settings.anomaly_threshold).detect(features)
        multivariate_detector = CalibratedMultivariateDetector(threshold=self.settings.multivariate_threshold)
        multivariate_detector.fit(baseline_features)
        multivariate_results = multivariate_detector.detect(features)
        fused_results = CalibratedScoreFusion(statistical_weight=self.settings.statistical_weight, ml_weight=self.settings.ml_weight, threshold=self.settings.anomaly_threshold).fuse(statistical_results, ml_results, diagnostic_results, multivariate_results)
        return AlertStateManager(clear_after_normals=3).apply(fused_results)

    @staticmethod
    def _attach_shap(
        detector: MlDetector,
        features: Sequence[EngineeredFeatures],
        baseline_features: Sequence[EngineeredFeatures],
        results: Sequence[DetectorResult],
    ) -> list[DetectorResult]:
        """Attach TreeSHAP to the latest FULL-mode Isolation Forest result."""
        if not results:
            return list(results)

        latest = results[-1]
        latest_feature = next(
            (feature for feature in features if feature.timestamp == latest.timestamp),
            None,
        )
        if latest_feature is None or not latest_feature.valid_for_scoring:
            return list(results)

        try:
            feature_names = tuple(EngineeredFeatures.feature_names)
            target_matrix = np.asarray([latest_feature.vector()], dtype=float)
            background_matrix = np.asarray(
                [feature.vector() for feature in baseline_features[-60:] if feature.valid_for_scoring],
                dtype=float,
            )
            if background_matrix.size == 0:
                background_matrix = target_matrix

            feature_count = target_matrix.shape[1]
            if len(feature_names) != feature_count:
                raise ValueError(
                    f"FULL SHAP feature mismatch: model has {feature_count} columns, "
                    f"but {len(feature_names)} feature names are defined"
                )

            # Supplying a small normal baseline makes the SHAP background
            # explicit and avoids explaining thousands of historical rows.
            explainer = shap.TreeExplainer(
                detector.model,
                data=background_matrix,
                feature_perturbation="interventional",
            )
            expected = np.asarray(explainer.expected_value).reshape(-1)
            base_value = float(expected[0]) if expected.size else None
            values = np.asarray(
                explainer.shap_values(target_matrix, check_additivity=False),
                dtype=float,
            )

            if values.ndim == 3:
                if values.shape[1] == feature_count:
                    values = values[:, :, 0]
                elif values.shape[2] == feature_count:
                    values = values[:, 0, :]
                else:
                    raise ValueError(f"Unexpected FULL SHAP shape: {values.shape}")
            elif values.ndim == 2 and values.shape[1] == feature_count:
                pass
            elif values.ndim == 1 and values.size == feature_count:
                values = values.reshape(1, -1)
            else:
                raise ValueError(f"Unexpected FULL SHAP shape: {values.shape}")

            row_values = values[0]
            row = latest_feature.vector()
            contributions = [
                ShapContribution(
                    feature=name,
                    value=float(row[index]),
                    shap_value=float(shap_value),
                    direction=(
                        "increases_anomaly"
                        if float(shap_value) < 0
                        else "decreases_anomaly"
                    ),
                )
                for index, (name, shap_value) in enumerate(zip(feature_names, row_values))
            ]
            contributions.sort(key=lambda item: abs(item.shap_value), reverse=True)

            output: list[DetectorResult] = []
            for result in results:
                if result.timestamp == latest.timestamp:
                    output.append(
                        DetectorResult(
                            timestamp=result.timestamp,
                            score=result.score,
                            is_anomaly=result.is_anomaly,
                            reasons=result.reasons,
                            shap_base_value=base_value,
                            shap_contributions=tuple(contributions),
                        )
                    )
                else:
                    output.append(result)
            return output
        except Exception:
            logger.exception("Unable to calculate FULL-mode SHAP explanations")
            return list(results)

    async def get_status(self, sensor_mode: str | None = None) -> MlServiceStatus:
        mode = self.normalize_mode(sensor_mode)
        await self.refresh()
        if mode == SensorMode.AWS:
            aws = AwsAnalysisEngine(self.settings)
            aws.refresh(self.readings, self.events)
            initialized, progress = aws.status()
            return MlServiceStatus(status="ready" if initialized else "collecting_baseline", readings_loaded=len(self.readings), latest_reading_timestamp=self.readings[-1].timestamp if self.readings else None, baseline_initialized=initialized, baseline_progress=progress, baseline_required=self.settings.baseline_size, sensor_mode=mode.value)
        base_status = self.status()
        return base_status.model_copy(update={"sensor_mode": mode.value})

    def status(self) -> MlServiceStatus:
        if self.last_error and not self.readings:
            status = "degraded"
        elif not self.baseline.initialized:
            status = "collecting_baseline"
        elif self.last_error:
            status = "degraded"
        else:
            status = "ready"
        return MlServiceStatus(status=status, readings_loaded=len(self.readings), latest_reading_timestamp=self.readings[-1].timestamp if self.readings else None, baseline_initialized=self.baseline.initialized, baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, sensor_mode=SensorMode.FULL.value)

    async def analyze(self, limit: int = 200, sensor_mode: str | None = None) -> AnalyzeResponse:
        mode = self.normalize_mode(sensor_mode)
        if not await self.refresh():
            raise RuntimeError(self.last_error or "Unable to load analysis data")
        if mode == SensorMode.AWS:
            aws = AwsAnalysisEngine(self.settings)
            aws.refresh(self.readings, self.events)
            initialized, progress = aws.status()
            return AnalyzeResponse(status="ready" if initialized else "collecting_baseline", baseline_progress=progress, baseline_required=self.settings.baseline_size, baseline_initialized=initialized, sensor_mode=mode.value, results=aws.analyze(limit))
        if not self.baseline.initialized:
            return AnalyzeResponse(status="collecting_baseline", baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, baseline_initialized=False, sensor_mode=mode.value, results=[])
        all_results = self._run_detectors()
        return AnalyzeResponse(status="ready", baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, baseline_initialized=True, sensor_mode=mode.value, results=all_results[-max(1, limit):])

    async def evaluate(self, sensor_mode: str | None = None) -> EvaluationResponse:
        mode = self.normalize_mode(sensor_mode)
        if not await self.refresh():
            raise RuntimeError(self.last_error or "Unable to load evaluation data")
        if mode == SensorMode.AWS:
            aws = AwsAnalysisEngine(self.settings)
            aws.refresh(self.readings, self.events)
            initialized, progress = aws.status()
            return EvaluationResponse(status="ready" if initialized else "insufficient_labeled_data", message=None if initialized else "At least 60 valid readings are required before AWS-mode evaluation can run.", baseline_progress=progress, baseline_required=self.settings.baseline_size, baseline_initialized=initialized, sensor_mode=mode.value, total_readings=len(self.readings), evaluated_readings=0, labeled_readings=0)
        if not self.events:
            return EvaluationResponse(status="insufficient_labeled_data", message="No simulator ground-truth events are available.", baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, baseline_initialized=self.baseline.initialized, sensor_mode=mode.value, total_readings=len(self.readings), evaluated_readings=0, labeled_readings=0)
        if not self.baseline.initialized:
            return EvaluationResponse(status="insufficient_labeled_data", message="At least 60 valid normal readings are required before evaluation can run.", baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, baseline_initialized=False, sensor_mode=mode.value, total_readings=len(self.readings), evaluated_readings=0, labeled_readings=0)
        results = self._run_detectors()
        result_by_timestamp = {result.timestamp: result for result in results}
        scored = [reading for reading in self.readings if reading.timestamp in result_by_timestamp]
        predictions = [result_by_timestamp[r.timestamp].is_anomaly for r in scored]
        truth = [reading_is_faulty(r, self.events) for r in scored]
        latencies = calculate_event_latencies(self.events, results)
        return EvaluationResponse(status="ready", baseline_progress=self.baseline.progress, baseline_required=self.baseline.required, baseline_initialized=True, sensor_mode=mode.value, total_readings=len(self.readings), evaluated_readings=len(scored), labeled_readings=len(scored), metrics=calculate_metrics(truth, predictions), event_metrics_by_fault_type=calculate_event_metrics(self.events, latencies), event_latencies=latencies)

    def _engineered_features(self) -> list[EngineeredFeatures]:
        return self.feature_engineer.transform(self.readings, [reading_is_faulty(r, self.events) for r in self.readings])

    def _baseline_features(self, _features: Sequence[EngineeredFeatures]) -> list[EngineeredFeatures]:
        baseline_features = self.feature_engineer.transform(self.baseline.readings)
        return [feature for feature in baseline_features if feature.valid_for_scoring]
