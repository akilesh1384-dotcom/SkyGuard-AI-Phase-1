"""Layer 1 detectors and explicit placeholders for later ML layers."""

from __future__ import annotations

import math
from collections.abc import Sequence

from sklearn.ensemble import IsolationForest

from .models import AnomalyResult, DetectorResult, EngineeredFeatures

EPSILON = 1e-9


def _bounded_score(value: float) -> float:
    """Map a non-negative deviation to [0, 1] without calling it a probability."""

    return max(0.0, min(1.0, 1.0 - math.exp(-abs(value) / 3.0)))


class FeatureEngineer:
    """Create causal features using only the previous 20 readings."""

    def __init__(self, window: int = 20):
        if window < 2:
            raise ValueError("Feature window must be at least 2")
        self.window = window

    def transform(
        self,
        readings: Sequence,
        fault_flags: Sequence[bool] | None = None,
    ) -> list[EngineeredFeatures]:
        if fault_flags is None:
            fault_flags = [False] * len(readings)
        if len(fault_flags) != len(readings):
            raise ValueError("fault_flags must match the readings length")

        ordered = sorted(readings, key=lambda reading: reading.timestamp)
        if len(ordered) != len(readings):
            raise ValueError("FeatureEngineer requires one fault flag per reading")

        features: list[EngineeredFeatures] = []
        for index, reading in enumerate(ordered):
            history_start = max(0, index - self.window)
            history = ordered[history_start:index]
            history_flags = fault_flags[history_start : index + 1]
            history_size = len(history)
            previous = ordered[index - 1] if index > 0 else None
            valid_for_scoring = history_size >= self.window and previous is not None

            deltas = (
                (
                    reading.temperature - previous.temperature,
                    reading.humidity - previous.humidity,
                    reading.pressure - previous.pressure,
                )
                if previous is not None
                else (None, None, None)
            )

            if not valid_for_scoring:
                features.append(
                    EngineeredFeatures(
                        timestamp=reading.timestamp,
                        temperature=reading.temperature,
                        humidity=reading.humidity,
                        pressure=reading.pressure,
                        temperature_delta=deltas[0],
                        humidity_delta=deltas[1],
                        pressure_delta=deltas[2],
                        temperature_rolling_mean=None,
                        temperature_rolling_std=None,
                        humidity_rolling_mean=None,
                        humidity_rolling_std=None,
                        pressure_rolling_mean=None,
                        pressure_rolling_std=None,
                        temperature_normalized_deviation=None,
                        humidity_normalized_deviation=None,
                        pressure_normalized_deviation=None,
                        temperature_humidity_relationship=None,
                        temperature_pressure_relationship=None,
                        humidity_pressure_relationship=None,
                        history_size=history_size,
                        history_contains_fault=any(history_flags),
                        valid_for_scoring=False,
                    )
                )
                continue

            values = (
                [item.temperature for item in history],
                [item.humidity for item in history],
                [item.pressure for item in history],
            )
            means = tuple(sum(series) / len(series) for series in values)
            standard_deviations = tuple(
                math.sqrt(
                    sum((value - mean) ** 2 for value in series) / len(series)
                )
                for series, mean in zip(values, means)
            )
            medians = tuple(self._median(series) for series in values)
            scales = tuple(
                max(
                    1.4826
                    * self._median([abs(value - median) for value in series]),
                    standard_deviation,
                    EPSILON,
                )
                for series, median, standard_deviation in zip(
                    values, medians, standard_deviations
                )
            )
            normalized = tuple(
                (value - median) / scale
                for value, median, scale in zip(
                    (reading.temperature, reading.humidity, reading.pressure),
                    medians,
                    scales,
                )
            )

            features.append(
                EngineeredFeatures(
                    timestamp=reading.timestamp,
                    temperature=reading.temperature,
                    humidity=reading.humidity,
                    pressure=reading.pressure,
                    temperature_delta=deltas[0],
                    humidity_delta=deltas[1],
                    pressure_delta=deltas[2],
                    temperature_rolling_mean=means[0],
                    temperature_rolling_std=standard_deviations[0],
                    humidity_rolling_mean=means[1],
                    humidity_rolling_std=standard_deviations[1],
                    pressure_rolling_mean=means[2],
                    pressure_rolling_std=standard_deviations[2],
                    temperature_normalized_deviation=normalized[0],
                    humidity_normalized_deviation=normalized[1],
                    pressure_normalized_deviation=normalized[2],
                    temperature_humidity_relationship=normalized[0] - normalized[1],
                    temperature_pressure_relationship=normalized[0] - normalized[2],
                    humidity_pressure_relationship=normalized[1] - normalized[2],
                    history_size=history_size,
                    history_contains_fault=any(history_flags),
                    valid_for_scoring=True,
                    robust_medians=medians,
                    robust_scales=scales,
                )
            )

        return features

    @staticmethod
    def _median(values: Sequence[float]) -> float:
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2


class StatisticalDetector:
    """Score robust deviation and sudden variability on a normalized [0, 1] scale."""

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def detect(self, features: Sequence[EngineeredFeatures]) -> list[DetectorResult]:
        results: list[DetectorResult] = []
        for feature in features:
            if not feature.valid_for_scoring or feature.robust_medians is None:
                continue

            raw_values = (
                feature.temperature,
                feature.humidity,
                feature.pressure,
            )
            deltas = (
                feature.temperature_delta,
                feature.humidity_delta,
                feature.pressure_delta,
            )
            rolling_standard_deviations = (
                feature.temperature_rolling_std,
                feature.humidity_rolling_std,
                feature.pressure_rolling_std,
            )
            labels = ("temperature", "humidity", "pressure")

            scores: list[float] = []
            reasons: list[str] = []
            for label, value, delta, median, scale, rolling_std in zip(
                labels,
                raw_values,
                deltas,
                feature.robust_medians,
                feature.robust_scales or (EPSILON, EPSILON, EPSILON),
                rolling_standard_deviations,
            ):
                deviation_score = _bounded_score((value - median) / scale)
                variability_score = (
                    _bounded_score(delta / max(rolling_std or 0.0, EPSILON))
                    if delta is not None
                    else 0.0
                )
                component_score = max(deviation_score, variability_score)
                scores.append(component_score)
                if deviation_score >= self.threshold:
                    reasons.append(f"{label}_deviation")
                if variability_score >= self.threshold:
                    reasons.append(f"{label}_variability")

            relationship_scores = [
                _bounded_score(value)
                for value in (
                    feature.temperature_humidity_relationship or 0.0,
                    feature.temperature_pressure_relationship or 0.0,
                    feature.humidity_pressure_relationship or 0.0,
                )
            ]
            relationship_score = max(relationship_scores)
            if relationship_score >= self.threshold:
                reasons.append("multivariate_relationship")

            score = max(*scores, relationship_score)
            results.append(
                DetectorResult(
                    timestamp=feature.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=tuple(dict.fromkeys(reasons)),
                )
            )
        return results


class MlDetector:
    """Isolation Forest detector with baseline-relative score normalization."""

    def __init__(
        self,
        threshold: float = 0.75,
        n_estimators: int = 100,
        random_state: int = 42,
        contamination: str = "auto",
    ):
        self.threshold = threshold
        self.model = IsolationForest(
            n_estimators=n_estimators,
            random_state=random_state,
            contamination=contamination,
        )
        self._decision_min: float | None = None
        self._decision_max: float | None = None

    def fit(self, baseline_features: Sequence[EngineeredFeatures]) -> None:
        usable = [
            feature for feature in baseline_features if feature.valid_for_scoring
        ]
        if len(usable) < 2:
            raise ValueError("Isolation Forest requires at least two baseline rows")

        matrix = [feature.vector() for feature in usable]
        self.model.fit(matrix)
        decisions = self.model.decision_function(matrix)
        decision_min = float(min(decisions))
        decision_max = float(max(decisions))
        if math.isclose(decision_min, decision_max):
            decision_min -= 0.5
            decision_max += 0.5
        self._decision_min = decision_min
        self._decision_max = decision_max

    def detect(self, features: Sequence[EngineeredFeatures]) -> list[DetectorResult]:
        if self._decision_min is None or self._decision_max is None:
            raise RuntimeError("MlDetector must be fitted before detection")

        usable = [feature for feature in features if feature.valid_for_scoring]
        if not usable:
            return []
        decisions = self.model.decision_function([feature.vector() for feature in usable])
        scale = self._decision_max - self._decision_min
        results: list[DetectorResult] = []
        for feature, decision in zip(usable, decisions):
            # Isolation Forest decision_function is higher for normal rows.
            # This line reverses it and scales against the fitted baseline range.
            score = max(
                0.0,
                min(1.0, (self._decision_max - float(decision)) / scale),
            )
            results.append(
                DetectorResult(
                    timestamp=feature.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=("isolation_forest",) if score >= self.threshold else (),
                )
            )
        return results


class ScoreFusion:
    """Fuse already normalized detector scores using prototype weights."""

    def __init__(
        self,
        statistical_weight: float = 0.45,
        ml_weight: float = 0.55,
        threshold: float = 0.75,
    ):
        if not math.isclose(statistical_weight + ml_weight, 1.0):
            raise ValueError("Score-fusion weights must sum to 1")
        self.statistical_weight = statistical_weight
        self.ml_weight = ml_weight
        self.threshold = threshold

    def fuse(
        self,
        statistical_scores: Sequence[DetectorResult],
        ml_scores: Sequence[DetectorResult],
    ) -> list[AnomalyResult]:
        statistical_by_timestamp = {
            result.timestamp: result for result in statistical_scores
        }
        ml_by_timestamp = {result.timestamp: result for result in ml_scores}
        results: list[AnomalyResult] = []
        for timestamp in sorted(
            statistical_by_timestamp.keys() & ml_by_timestamp.keys()
        ):
            statistical = statistical_by_timestamp[timestamp]
            ml = ml_by_timestamp[timestamp]
            final_score = (
                self.statistical_weight * statistical.score
                + self.ml_weight * ml.score
            )
            results.append(
                AnomalyResult(
                    timestamp=timestamp,
                    statistical_score=statistical.score,
                    ml_score=ml.score,
                    final_score=final_score,
                    is_anomaly=final_score >= self.threshold,
                    reasons=list(
                        dict.fromkeys((*statistical.reasons, *ml.reasons))
                    ),
                )
            )
        return results


class FaultClassifier:
    def classify(self, fused_scores: Sequence[AnomalyResult]) -> list[dict]:
        # TODO: Add fault-type classification after Layer 1 validation.
        return []


class SensorHealth:
    def estimate(self, readings: Sequence) -> dict:
        # TODO: Add sensor-health methodology in a later layer.
        return {"status": "not_implemented"}