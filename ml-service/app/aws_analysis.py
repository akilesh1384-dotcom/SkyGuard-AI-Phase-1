from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import shap
from sklearn.ensemble import IsolationForest

from .alert_state import AlertStateManager
from .models import AnomalyResult, GroundTruthEvent, SensorReading, ShapContribution


class AwsAnalysisEngine:
    """Two-variable analysis path for the physical AWS prototype.

    Uses only temperature and relative humidity. Pressure-dependent and
    multivariate pressure features are deliberately disabled; unavailable
    pressure is never imputed or fabricated.

    The baseline is fitted from the first required known-normal readings.
    Live analysis only scans a recent window so historical data does not have
    to be reprocessed on every dashboard refresh.
    """

    FEATURE_NAMES = ("temperature", "humidity")

    def __init__(self, settings):
        self.settings = settings
        self.readings: list[SensorReading] = []
        self.events: list[GroundTruthEvent] = []
        self.baseline: list[SensorReading] = []

    def refresh(self, readings: Sequence[SensorReading], events: Sequence[GroundTruthEvent]) -> None:
        self.readings = sorted(readings, key=lambda item: item.timestamp)
        self.events = sorted(events, key=lambda item: item.start_timestamp)
        baseline: list[SensorReading] = []
        for reading in self.readings:
            if not self._in_event(reading):
                baseline.append(reading)
                if len(baseline) >= self.settings.baseline_size:
                    break
        self.baseline = baseline

    def status(self) -> tuple[bool, int]:
        return len(self.baseline) >= self.settings.baseline_size, min(len(self.baseline), self.settings.baseline_size)

    def analyze(self, limit: int) -> list[AnomalyResult]:
        initialized, _ = self.status()
        if not initialized:
            return []
        results = self._run(limit)
        return results[-max(1, limit):]

    def _run(self, limit: int) -> list[AnomalyResult]:
        window = self.settings.rolling_window
        baseline = self.baseline
        if len(baseline) < self.settings.baseline_size:
            return []

        matrix = np.asarray([[r.temperature, r.humidity] for r in baseline], dtype=float)
        model = IsolationForest(n_estimators=100, random_state=42, contamination="auto")
        model.fit(matrix)
        decisions = model.decision_function(matrix)
        dmin, dmax = float(np.min(decisions)), float(np.max(decisions))
        if abs(dmax - dmin) < 1e-9:
            dmax = dmin + 1.0

        explainer = None
        shap_base_value = None
        try:
            explainer = shap.TreeExplainer(model)
            expected = np.asarray(explainer.expected_value).reshape(-1)
            if expected.size:
                shap_base_value = float(expected[0])
        except Exception:
            explainer = None

        recent_count = max(window + 3, window + limit + 3, 80)
        analysis_readings = self.readings[-recent_count:]
        start_offset = len(self.readings) - len(analysis_readings)

        output: list[AnomalyResult] = []

        for local_index, reading in enumerate(analysis_readings):
            global_index = start_offset + local_index
            if global_index <= 0:
                continue
            history = self.readings[max(0, global_index - window):global_index]
            if len(history) < window:
                continue
            temps = np.asarray([r.temperature for r in history], dtype=float)
            hums = np.asarray([r.humidity for r in history], dtype=float)
            temp_scale = max(1.4826 * float(np.median(np.abs(temps - np.median(temps)))), 1e-6)
            hum_scale = max(1.4826 * float(np.median(np.abs(hums - np.median(hums)))), 1e-6)
            tdev = abs((reading.temperature - float(np.median(temps))) / temp_scale)
            hdev = abs((reading.humidity - float(np.median(hums))) / hum_scale)
            deviation = min(max(tdev, hdev) / 6.0, 1.0)
            prev = self.readings[global_index - 1]
            tchange = abs(reading.temperature - prev.temperature) / max(3 * float(np.std(temps, ddof=1)), 1e-6)
            hchange = abs(reading.humidity - prev.humidity) / max(3 * float(np.std(hums, ddof=1)), 1e-6)
            stat_score = float(np.clip(0.75 * deviation + 0.25 * min(max(tchange, hchange), 1.0), 0, 1))

            row = np.asarray([[reading.temperature, reading.humidity]], dtype=float)
            decision = float(model.decision_function(row)[0])
            ml_score = float(np.clip((dmax - decision) / (dmax - dmin), 0, 1))
            shap_contributions = self._shap_contributions(explainer, row)

            diagnostic_score = 0.0
            fault_type = None
            affected = None
            reasons: list[str] = []
            gap = (reading.timestamp - prev.timestamp).total_seconds()
            if gap > self.settings.diagnostic_expected_interval_seconds * 1.5:
                diagnostic_score = 1.0
                fault_type, affected = "MISSING_DATA", "all"
                reasons.append("timestamp_gap")
            if tchange >= self.settings.anomaly_threshold:
                diagnostic_score = max(diagnostic_score, min(tchange, 1.0))
                fault_type, affected = fault_type or "ABRUPT_CHANGE", affected or "temperature"
                reasons.append("temperature_abrupt_change")
            if hchange >= self.settings.anomaly_threshold:
                diagnostic_score = max(diagnostic_score, min(hchange, 1.0))
                fault_type, affected = fault_type or "ABRUPT_CHANGE", affected or "humidity"
                reasons.append("humidity_abrupt_change")

            context = self.settings.statistical_weight * stat_score + self.settings.ml_weight * ml_score
            final = max(diagnostic_score, context)
            anomaly = final >= self.settings.anomaly_threshold
            if anomaly and fault_type is None:
                fault_type, affected = "UNCLASSIFIED_ANOMALY", None
            if not anomaly and fault_type is None:
                fault_type = "NORMAL"
            output.append(AnomalyResult(
                timestamp=reading.timestamp,
                statistical_score=stat_score,
                ml_score=ml_score,
                diagnostic_score=diagnostic_score,
                multivariate_score=0.0,
                final_score=final,
                is_anomaly=anomaly,
                diagnostic_anomaly=diagnostic_score >= self.settings.anomaly_threshold,
                fault_type=fault_type,
                affected_variable=affected,
                reasons=list(dict.fromkeys(reasons + (["isolation_forest"] if ml_score >= self.settings.anomaly_threshold else []))),
                shap_base_value=shap_base_value,
                shap_contributions=shap_contributions,
            ))

        return AlertStateManager(clear_after_normals=3).apply(output)

    def _shap_contributions(self, explainer, row: np.ndarray) -> list[ShapContribution]:
        if explainer is None:
            return []
        try:
            values = np.asarray(explainer.shap_values(row))
            if values.ndim == 3:
                values = values[0]
            if values.ndim == 2:
                values = values[0]
            values = values.reshape(-1)
            contributions = [
                ShapContribution(
                    feature=name,
                    value=float(row[0, index]),
                    shap_value=float(value),
                    direction="increases_anomaly" if float(value) < 0 else "decreases_anomaly",
                )
                for index, (name, value) in enumerate(zip(self.FEATURE_NAMES, values))
            ]
            contributions.sort(key=lambda item: abs(item.shap_value), reverse=True)
            return contributions
        except Exception:
            return []

    def _in_event(self, reading: SensorReading) -> bool:
        return any(
            reading.timestamp >= event.start_timestamp
            and (event.end_timestamp is None or reading.timestamp <= event.end_timestamp)
            for event in self.events
        )
