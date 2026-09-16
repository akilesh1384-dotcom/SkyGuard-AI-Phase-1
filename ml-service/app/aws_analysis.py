from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.ensemble import IsolationForest

from .alert_state import AlertStateManager
from .models import AnomalyResult, DiagnosticResult, DetectorResult, GroundTruthEvent, SensorReading


class AwsAnalysisEngine:
    """Two-variable analysis path for the physical AWS prototype.

    Uses only temperature and relative humidity. Pressure-dependent and
    multivariate pressure features are deliberately disabled; unavailable
    pressure is never imputed or fabricated.
    """

    def __init__(self, settings):
        self.settings = settings
        self.readings: list[SensorReading] = []
        self.events: list[GroundTruthEvent] = []
        self.baseline: list[SensorReading] = []

    def refresh(self, readings: Sequence[SensorReading], events: Sequence[GroundTruthEvent]) -> None:
        self.readings = sorted(readings, key=lambda item: item.timestamp)
        self.events = sorted(events, key=lambda item: item.start_timestamp)
        self.baseline = [r for r in self.readings if not self._in_event(r)][: self.settings.baseline_size]

    def status(self) -> tuple[bool, int]:
        return len(self.baseline) >= self.settings.baseline_size, min(len(self.baseline), self.settings.baseline_size)

    def analyze(self, limit: int) -> list[AnomalyResult]:
        initialized, _ = self.status()
        if not initialized:
            return []
        results = self._run()
        return results[-max(1, limit):]

    def _run(self) -> list[AnomalyResult]:
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

        output: list[AnomalyResult] = []
        diagnostics: list[DiagnosticResult] = []
        statistical: list[DetectorResult] = []
        ml_results: list[DetectorResult] = []

        for i, reading in enumerate(self.readings):
            history = self.readings[max(0, i - window):i]
            if len(history) < window:
                continue
            temps = np.asarray([r.temperature for r in history], dtype=float)
            hums = np.asarray([r.humidity for r in history], dtype=float)
            temp_scale = max(1.4826 * float(np.median(np.abs(temps - np.median(temps)))), 1e-6)
            hum_scale = max(1.4826 * float(np.median(np.abs(hums - np.median(hums)))), 1e-6)
            tdev = abs((reading.temperature - float(np.median(temps))) / temp_scale)
            hdev = abs((reading.humidity - float(np.median(hums))) / hum_scale)
            deviation = min(max(tdev, hdev) / 6.0, 1.0)
            prev = self.readings[i - 1]
            tchange = abs(reading.temperature - prev.temperature) / max(3 * float(np.std(temps, ddof=1)), 1e-6)
            hchange = abs(reading.humidity - prev.humidity) / max(3 * float(np.std(hums, ddof=1)), 1e-6)
            stat_score = float(np.clip(0.75 * deviation + 0.25 * min(max(tchange, hchange), 1.0), 0, 1))

            decision = float(model.decision_function(np.asarray([[reading.temperature, reading.humidity]], dtype=float))[0])
            ml_score = float(np.clip((dmax - decision) / (dmax - dmin), 0, 1))

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
            ))

        return AlertStateManager(clear_after_normals=3).apply(output)

    def _in_event(self, reading: SensorReading) -> bool:
        return any(
            reading.timestamp >= event.start_timestamp
            and (event.end_timestamp is None or reading.timestamp <= event.end_timestamp)
            for event in self.events
        )
