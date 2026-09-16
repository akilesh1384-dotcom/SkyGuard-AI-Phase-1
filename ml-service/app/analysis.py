from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from .baseline import Baseline, BaselineManager
from .config import Settings
from .data_client import SkyGuardDataClient, reading_is_faulty
from .ml_placeholders import (
    FeatureEngineer,
    MlDetector,
    ScoreFusion,
    StatisticalDetector,
    SensorDiagnosticDetector,
)
from .calibrated_multivariate import CalibratedMultivariateDetector
from .alert_state import AlertStateManager
from .models import (
    AnalyzeResponse,
    AnomalyResult,
    DiagnosticResult,
    EngineeredFeatures,
    EventDetectionMetrics,
    EventLatency,
    EvaluationMetrics,
    EvaluationResponse,
    GroundTruthEvent,
    MlServiceStatus,
    SensorReading,
)

logger = logging.getLogger(__name__)


def calculate_metrics(
    truth: Sequence[bool],
    predictions: Sequence[bool],
) -> EvaluationMetrics:
    if len(truth) != len(predictions):
        raise ValueError("Truth and prediction sequences must have the same length")

    true_positives = sum(actual and predicted for actual, predicted in zip(truth, predictions))
    false_positives = sum(not actual and predicted for actual, predicted in zip(truth, predictions))
    true_negatives = sum(not actual and not predicted for actual, predicted in zip(truth, predictions))
    false_negatives = sum(actual and not predicted for actual, predicted in zip(truth, predictions))

    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = true_positives / precision_denominator if precision_denominator else None
    recall = true_positives / recall_denominator if recall_denominator else None
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )

    return EvaluationMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
    )


def calculate_event_latencies(
    events: Sequence[GroundTruthEvent],
    results: Sequence[AnomalyResult],
) -> list[EventLatency]:
    """Measure first detection and first post-event normal return per event.

    MISSING_DATA has no sensor rows during the outage by design, so its first
    detection is evaluated at the first reading after the gap.
    """
    ordered_results = sorted(results, key=lambda result: result.timestamp)
    latencies: list[EventLatency] = []
    for event in sorted(events, key=lambda item: item.start_timestamp):
        if event.fault_type == "MISSING_DATA":
            first_after_gap = next(
                (
                    result
                    for result in ordered_results
                    if result.timestamp >= (
                        event.end_timestamp if event.end_timestamp is not None else event.start_timestamp
                    )
                    and result.is_anomaly
                    and (
                        result.fault_type == "MISSING_DATA"
                        or "missing_data" in result.reasons
                    )
                ),
                None,
            )
            first_normal_after_event = None
            if event.end_timestamp is not None:
                first_normal_after_event = next(
                    (
                        result
                        for result in ordered_results
                        if result.timestamp > event.end_timestamp and not result.is_anomaly
                    ),
                    None,
                )
        else:
            in_event = [
                result
                for result in ordered_results
                if result.timestamp >= event.start_timestamp
                and (event.end_timestamp is None or result.timestamp <= event.end_timestamp)
            ]
            first_after_gap = next((result for result in in_event if result.is_anomaly), None)
            first_normal_after_event = None
            if event.end_timestamp is not None:
                first_normal_after_event = next(
                    (
                        result
                        for result in ordered_results
                        if result.timestamp > event.end_timestamp and not result.is_anomaly
                    ),
                    None,
                )

        detection_latency = (
            (first_after_gap.timestamp - event.start_timestamp).total_seconds()
            if first_after_gap else None
        )
        recovery_latency = (
            (first_normal_after_event.timestamp - event.end_timestamp).total_seconds()
            if first_normal_after_event and event.end_timestamp else None
        )
        latencies.append(
            EventLatency(
                fault_type=event.fault_type,
                affected_variable=event.affected_variable,
                start_timestamp=event.start_timestamp,
                end_timestamp=event.end_timestamp,
                detection_latency_seconds=detection_latency,
                recovery_latency_seconds=recovery_latency,
            )
        )
    return latencies


def calculate_event_metrics(
    events: Sequence[GroundTruthEvent],
    latencies: Sequence[EventLatency],
) -> dict[str, EventDetectionMetrics]:
    """Summarize detection at the event level, separate from row metrics."""
    latency_by_key = {
        (item.fault_type, item.start_timestamp): item for item in latencies
    }
    output: dict[str, EventDetectionMetrics] = {}
    fault_types = sorted({event.fault_type for event in events})
    for fault_type in fault_types:
        fault_events = [event for event in events if event.fault_type == fault_type]
        fault_latencies = [latency_by_key[(event.fault_type, event.start_timestamp)] for event in fault_events]
        detected = [item for item in fault_latencies if item.detection_latency_seconds is not None]
        recovered = [item for item in fault_latencies if item.recovery_latency_seconds is not None]
        total = len(fault_events)
        detected_count = len(detected)
        output[fault_type] = EventDetectionMetrics(
            total_events=total,
            detected_events=detected_count,
            missed_events=total - detected_count,
            detection_rate=(detected_count / total if total else None),
            mean_detection_latency_seconds=(
                sum(item.detection_latency_seconds for item in detected) / detected_count
                if detected_count else None
            ),
            mean_recovery_latency_seconds=(
                sum(item.recovery_latency_seconds for item in recovered) / len(recovered)
                if recovered else None
            ),
        )
    return output


class AnalysisEngine:
    """Own the Layer 1 cache, baseline, detectors, and evaluation flow."""

    def __init__(self, client: SkyGuardDataClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.baseline_manager = BaselineManager(settings.baseline_size)
        self.feature_engineer = FeatureEngineer(settings.rolling_window)
        self.readings: list[SensorReading] = []
        self.events: list[GroundTruthEvent] = []
        self.baseline = Baseline((), settings.baseline_size)
        self.last_error: str | None = None

    async def refresh(self, limit: int | None = None) -> bool:
        try:
            readings, events = await asyncio.gather(
                self.client.fetch_readings(limit),
                self.client.fetch_ground_truth(),
            )
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

        diagnostic_results = SensorDiagnosticDetector(
            frozen_consecutive=self.settings.diagnostic_frozen_consecutive,
            frozen_tolerance=self.settings.diagnostic_frozen_tolerance,
            expected_interval_seconds=self.settings.diagnostic_expected_interval_seconds,
            threshold=self.settings.anomaly_threshold,
        ).detect(features)

        multivariate_detector = CalibratedMultivariateDetector(
            threshold=self.settings.multivariate_threshold,
        )
        multivariate_detector.fit(baseline_features)
        multivariate_results = multivariate_detector.detect(features)

        fused_results = ScoreFusion(
            statistical_weight=self.settings.statistical_weight,
            ml_weight=self.settings.ml_weight,
            threshold=self.settings.anomaly_threshold,
        ).fuse(
            statistical_results,
            ml_results,
            diagnostic_results,
            multivariate_results,
        )

        return AlertStateManager(clear_after_normals=3).apply(fused_results)

    def status(self) -> MlServiceStatus:
        if self.last_error and not self.readings:
            status = "degraded"
        elif not self.baseline.initialized:
            status = "collecting_baseline"
        elif self.last_error:
            status = "degraded"
        else:
            status = "ready"
        latest = self.readings[-1].timestamp if self.readings else None
        return MlServiceStatus(
            status=status,
            readings_loaded=len(self.readings),
            latest_reading_timestamp=latest,
            baseline_initialized=self.baseline.initialized,
            baseline_progress=self.baseline.progress,
            baseline_required=self.baseline.required,
        )

    async def get_status(self) -> MlServiceStatus:
        await self.refresh()
        return self.status()

    async def analyze(self, limit: int = 200) -> AnalyzeResponse:
        if not await self.refresh():
            raise RuntimeError(self.last_error or "Unable to load analysis data")
        if not self.baseline.initialized:
            return self._cold_start_response()
        all_results = self._run_detectors()
        results = all_results[-max(1, limit):]
        return AnalyzeResponse(
            status="ready",
            baseline_progress=self.baseline.progress,
            baseline_required=self.baseline.required,
            baseline_initialized=True,
            results=results,
        )

    async def evaluate(self) -> EvaluationResponse:
        if not await self.refresh():
            raise RuntimeError(self.last_error or "Unable to load evaluation data")
        if not self.events:
            return EvaluationResponse(
                status="insufficient_labeled_data",
                message="No simulator ground-truth events are available.",
                baseline_progress=self.baseline.progress,
                baseline_required=self.baseline.required,
                baseline_initialized=self.baseline.initialized,
                total_readings=len(self.readings),
                evaluated_readings=0,
                labeled_readings=0,
            )
        if not self.baseline.initialized:
            return EvaluationResponse(
                status="insufficient_labeled_data",
                message="At least 60 valid normal readings are required before evaluation can run.",
                baseline_progress=self.baseline.progress,
                baseline_required=self.baseline.required,
                baseline_initialized=False,
                total_readings=len(self.readings),
                evaluated_readings=0,
                labeled_readings=0,
            )

        results = self._run_detectors()
        result_by_timestamp = {result.timestamp: result for result in results}
        scored_readings = [reading for reading in self.readings if reading.timestamp in result_by_timestamp]
        if not scored_readings:
            return EvaluationResponse(
                status="insufficient_labeled_data",
                message="No readings have enough causal history to evaluate.",
                baseline_progress=self.baseline.progress,
                baseline_required=self.baseline.required,
                baseline_initialized=True,
                total_readings=len(self.readings),
                evaluated_readings=0,
                labeled_readings=0,
            )

        predictions = [result_by_timestamp[reading.timestamp].is_anomaly for reading in scored_readings]
        truth = [reading_is_faulty(reading, self.events) for reading in scored_readings]
        metrics = calculate_metrics(truth, predictions)
        event_latencies = calculate_event_latencies(self.events, results)
        event_metrics_by_fault_type = calculate_event_metrics(self.events, event_latencies)

        by_fault_type = {}
        for fault_type in sorted({event.fault_type for event in self.events}):
            type_truth = [reading_is_faulty(reading, self.events, fault_type) for reading in scored_readings]
            if sum(type_truth) > 0 and len(type_truth) >= 2:
                by_fault_type[fault_type] = calculate_metrics(type_truth, predictions)

        return EvaluationResponse(
            status="ready",
            baseline_progress=self.baseline.progress,
            baseline_required=self.baseline.required,
            baseline_initialized=True,
            total_readings=len(self.readings),
            evaluated_readings=len(scored_readings),
            labeled_readings=len(scored_readings),
            metrics=metrics,
            by_fault_type=by_fault_type,
            event_metrics_by_fault_type=event_metrics_by_fault_type,
            event_latencies=event_latencies,
        )

    def _cold_start_response(self) -> AnalyzeResponse:
        return AnalyzeResponse(
            status="collecting_baseline",
            baseline_progress=self.baseline.progress,
            baseline_required=self.baseline.required,
            baseline_initialized=False,
            results=[],
        )

    def _engineered_features(self) -> list[EngineeredFeatures]:
        fault_flags = [reading_is_faulty(reading, self.events) for reading in self.readings]
        return self.feature_engineer.transform(self.readings, fault_flags)

    def _baseline_features(self, _features: Sequence[EngineeredFeatures]) -> list[EngineeredFeatures]:
        """Build model-training features from the known-normal baseline itself."""
        baseline_features = self.feature_engineer.transform(self.baseline.readings)
        return [feature for feature in baseline_features if feature.valid_for_scoring]
