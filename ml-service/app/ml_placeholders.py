from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest

from .models import (
    AnomalyResult,
    DiagnosticResult,
    DetectorResult,
    EngineeredFeatures,
    GroundTruthEvent,
    SensorReading,
)


class FeatureEngineer:
    """Build causal features using only the current and previous readings."""

    def __init__(self, window: int = 20):
        self.window = window

    def transform(
        self,
        readings: Sequence[SensorReading],
        ground_truth_events: Sequence[GroundTruthEvent] | None = None,
    ) -> list[EngineeredFeatures]:
        events = tuple(ground_truth_events or ())
        output: list[EngineeredFeatures] = []

        for index, reading in enumerate(readings):
            history = readings[max(0, index - self.window):index]
            history_size = len(history)

            if history_size < self.window:
                output.append(
                    EngineeredFeatures(
                        timestamp=reading.timestamp,
                        temperature=reading.temperature,
                        humidity=reading.humidity,
                        pressure=reading.pressure,
                        temperature_delta=None,
                        humidity_delta=None,
                        pressure_delta=None,
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
                        history_contains_fault=self._history_contains_fault(
                            history, events
                        ),
                        valid_for_scoring=False,
                    )
                )
                continue

            temperatures = np.asarray(
                [item.temperature for item in history], dtype=float
            )
            humidities = np.asarray(
                [item.humidity for item in history], dtype=float
            )
            pressures = np.asarray(
                [item.pressure for item in history], dtype=float
            )

            previous = readings[index - 1]

            temperature_median, temperature_scale = self._robust_location_scale(
                temperatures
            )
            humidity_median, humidity_scale = self._robust_location_scale(
                humidities
            )
            pressure_median, pressure_scale = self._robust_location_scale(
                pressures
            )

            temperature_dev = self._normalized_deviation(
                reading.temperature,
                temperature_median,
                temperature_scale,
            )
            humidity_dev = self._normalized_deviation(
                reading.humidity,
                humidity_median,
                humidity_scale,
            )
            pressure_dev = self._normalized_deviation(
                reading.pressure,
                pressure_median,
                pressure_scale,
            )

            output.append(
                EngineeredFeatures(
                    timestamp=reading.timestamp,
                    temperature=reading.temperature,
                    humidity=reading.humidity,
                    pressure=reading.pressure,
                    temperature_delta=(
                        reading.temperature - previous.temperature
                    ),
                    humidity_delta=reading.humidity - previous.humidity,
                    pressure_delta=reading.pressure - previous.pressure,
                    temperature_rolling_mean=float(np.mean(temperatures)),
                    temperature_rolling_std=self._safe_std(temperatures),
                    humidity_rolling_mean=float(np.mean(humidities)),
                    humidity_rolling_std=self._safe_std(humidities),
                    pressure_rolling_mean=float(np.mean(pressures)),
                    pressure_rolling_std=self._safe_std(pressures),
                    temperature_normalized_deviation=temperature_dev,
                    humidity_normalized_deviation=humidity_dev,
                    pressure_normalized_deviation=pressure_dev,
                    temperature_humidity_relationship=(
                        temperature_dev - humidity_dev
                    ),
                    temperature_pressure_relationship=(
                        temperature_dev - pressure_dev
                    ),
                    humidity_pressure_relationship=(
                        humidity_dev - pressure_dev
                    ),
                    history_size=history_size,
                    history_contains_fault=self._history_contains_fault(
                        history, events
                    ),
                    valid_for_scoring=True,
                    robust_medians=(
                        temperature_median,
                        humidity_median,
                        pressure_median,
                    ),
                    robust_scales=(
                        temperature_scale,
                        humidity_scale,
                        pressure_scale,
                    ),
                )
            )

        return output

    @staticmethod
    def _safe_std(values: np.ndarray) -> float:
        if len(values) < 2:
            return 0.0

        result = float(np.std(values, ddof=1))
        return result if np.isfinite(result) else 0.0

    @classmethod
    def _robust_location_scale(
        cls,
        values: np.ndarray,
    ) -> tuple[float, float]:
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))

        if mad > 1e-9:
            scale = 1.4826 * mad
        else:
            scale = cls._safe_std(values)

        if scale <= 1e-9:
            scale = 1e-9

        return median, scale

    @staticmethod
    def _normalized_deviation(
        value: float,
        median: float,
        scale: float,
    ) -> float:
        return float((value - median) / scale)

    @staticmethod
    def _history_contains_fault(
        history: Sequence[SensorReading],
        events: Sequence[GroundTruthEvent | bool],
    ) -> bool:
        if not history or not events:
            return False

        if all(isinstance(event, bool) for event in events):
            history_count = len(history)
            if len(events) >= history_count:
                return any(events[-history_count:])
            return any(events)

        for reading in history:
            for event in events:
                if not isinstance(event, GroundTruthEvent):
                    continue
                if reading.timestamp < event.start_timestamp:
                    continue
                if (
                    event.end_timestamp is None
                    or reading.timestamp <= event.end_timestamp
                ):
                    return True

        return False


class StatisticalDetector:
    """Robust causal detector based on rolling deviation and change."""

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def detect(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> list[DetectorResult]:
        results: list[DetectorResult] = []

        for row in features:
            if not row.valid_for_scoring:
                continue

            deviations = {
                "temperature_deviation": abs(
                    row.temperature_normalized_deviation or 0.0
                ),
                "humidity_deviation": abs(
                    row.humidity_normalized_deviation or 0.0
                ),
                "pressure_deviation": abs(
                    row.pressure_normalized_deviation or 0.0
                ),
            }

            max_variable, max_deviation = max(
                deviations.items(),
                key=lambda item: item[1],
            )

            deviation_score = float(
                np.clip(max_deviation / 6.0, 0.0, 1.0)
            )

            change_scores: dict[str, float] = {}
            change_scores["temperature_change"] = self._change_score(
                row.temperature_delta,
                row.temperature_rolling_std,
            )
            change_scores["humidity_change"] = self._change_score(
                row.humidity_delta,
                row.humidity_rolling_std,
            )
            change_scores["pressure_change"] = self._change_score(
                row.pressure_delta,
                row.pressure_rolling_std,
            )

            max_change_name, max_change_score = max(
                change_scores.items(),
                key=lambda item: item[1],
            )

            score = float(
                np.clip(
                    0.75 * deviation_score + 0.25 * max_change_score,
                    0.0,
                    1.0,
                )
            )

            reasons: list[str] = []
            if deviation_score >= 0.75:
                reasons.append(max_variable)
            if max_change_score >= 0.75:
                reasons.append(max_change_name)

            results.append(
                DetectorResult(
                    timestamp=row.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=tuple(reasons),
                )
            )

        return results

    @staticmethod
    def _change_score(
        delta: float | None,
        rolling_std: float | None,
    ) -> float:
        if delta is None or rolling_std is None or rolling_std <= 1e-9:
            return 0.0

        return float(
            np.clip(abs(delta) / (3.0 * rolling_std), 0.0, 1.0)
        )


class MlDetector:
    """Isolation Forest anomaly detector."""

    def __init__(
        self,
        threshold: float = 0.75,
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        self.model = IsolationForest(
            n_estimators=n_estimators,
            random_state=random_state,
            contamination="auto",
        )
        self.threshold = threshold
        self._fitted = False
        self._baseline_min = 0.0
        self._baseline_max = 1.0

    def fit(self, features: Sequence[EngineeredFeatures]) -> None:
        usable = [
            feature
            for feature in features
            if feature.valid_for_scoring
            and not feature.history_contains_fault
        ]

        if len(usable) < 20:
            raise ValueError(
                "At least 20 clean scoreable feature rows are required."
            )

        matrix = np.asarray(
            [feature.vector() for feature in usable],
            dtype=float,
        )
        self.model.fit(matrix)
        decisions = self.model.decision_function(matrix)
        self._baseline_min = float(np.min(decisions))
        self._baseline_max = float(np.max(decisions))

        if abs(self._baseline_max - self._baseline_min) < 1e-9:
            self._baseline_max = self._baseline_min + 1.0

        self._fitted = True

    def detect(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> list[DetectorResult]:
        if not self._fitted:
            raise RuntimeError("Isolation Forest has not been fitted.")

        results: list[DetectorResult] = []
        scoreable = [feature for feature in features if feature.valid_for_scoring]
        if not scoreable:
            return results

        matrix = np.asarray(
            [feature.vector() for feature in scoreable],
            dtype=float,
        )
        decisions = self.model.decision_function(matrix)

        for feature, decision in zip(scoreable, decisions):
            score = float(
                np.clip(
                    (self._baseline_max - float(decision))
                    / (self._baseline_max - self._baseline_min),
                    0.0,
                    1.0,
                )
            )
            results.append(
                DetectorResult(
                    timestamp=feature.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=(
                        ("isolation_forest",)
                        if score >= self.threshold
                        else ()
                    ),
                )
            )

        return results


class MultivariateDetector:
    """Detect unusual joint temperature/humidity/pressure behavior."""

    FEATURE_NAMES = (
        "temperature",
        "humidity",
        "pressure",
        "temperature_delta",
        "humidity_delta",
        "pressure_delta",
    )

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self.mean_: np.ndarray | None = None
        self.cov_inv_: np.ndarray | None = None
        self.scale_: float = 1.0
        self._fitted = False

    def fit(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> None:
        usable = [
            feature
            for feature in features
            if feature.valid_for_scoring
            and not feature.history_contains_fault
        ]

        if len(usable) < 20:
            raise ValueError(
                "At least 20 clean scoreable feature rows are required."
            )

        matrix = np.asarray(
            [
                [
                    feature.temperature,
                    feature.humidity,
                    feature.pressure,
                    feature.temperature_delta,
                    feature.humidity_delta,
                    feature.pressure_delta,
                ]
                for feature in usable
            ],
            dtype=float,
        )

        # The baseline is intentionally small (60 readings), so the raw sample
        # covariance can be ill-conditioned in correlated weather features.
        # Ledoit-Wolf shrinkage provides a stable covariance inverse without
        # changing the detector's causal behavior.
        covariance_model = LedoitWolf().fit(matrix)
        self.mean_ = covariance_model.location_.astype(float)
        self.cov_inv_ = np.linalg.pinv(covariance_model.covariance_)

        distances = np.asarray(
            [self._distance(row) for row in matrix],
            dtype=float,
        )
        self.scale_ = max(float(np.percentile(distances, 99)), 1e-6)
        self._fitted = True

    def detect(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> list[DetectorResult]:
        if not self._fitted:
            raise RuntimeError("Multivariate detector has not been fitted.")

        results: list[DetectorResult] = []
        for feature in features:
            if not feature.valid_for_scoring:
                continue

            row = np.asarray(
                [
                    feature.temperature,
                    feature.humidity,
                    feature.pressure,
                    feature.temperature_delta,
                    feature.humidity_delta,
                    feature.pressure_delta,
                ],
                dtype=float,
            )
            distance = self._distance(row)
            score = float(np.clip(distance / self.scale_, 0.0, 1.0))
            reasons = (
                ("multivariate_inconsistency",)
                if score >= self.threshold
                else ()
            )
            results.append(
                DetectorResult(
                    timestamp=feature.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=reasons,
                )
            )

        return results

    def _distance(self, row: np.ndarray) -> float:
        if self.mean_ is None or self.cov_inv_ is None:
            raise RuntimeError("Multivariate detector is not fitted.")

        delta = row - self.mean_
        return float(
            np.sqrt(
                max(
                    delta @ self.cov_inv_ @ delta.T,
                    0.0,
                )
            )
        )


class SensorDiagnosticDetector:
    """Detect sequence-based sensor faults missed by pointwise ML models."""

    def __init__(
        self,
        frozen_consecutive: int = 5,
        frozen_tolerance: float = 1e-3,
        expected_interval_seconds: float = 1.0,
        threshold: float = 0.75,
        drift_window: int = 8,
    ):
        self.frozen_consecutive = max(2, frozen_consecutive)
        self.frozen_tolerance = frozen_tolerance
        self.expected_interval_seconds = expected_interval_seconds
        self.threshold = threshold
        self.drift_window = max(4, drift_window)

    def detect(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> list[DiagnosticResult]:
        results: list[DiagnosticResult] = []
        frozen_counts = {"temperature": 0, "humidity": 0, "pressure": 0}

        for index, feature in enumerate(features):
            reasons: list[str] = []
            fault_type: str | None = None
            affected_variable: str | None = None
            diagnostic_score = 0.0

            if index > 0:
                previous = features[index - 1]
                gap = (feature.timestamp - previous.timestamp).total_seconds()
                if gap > self.expected_interval_seconds * 1.5:
                    diagnostic_score = 1.0
                    fault_type = "MISSING_DATA"
                    affected_variable = "all"
                    reasons.append("timestamp_gap")

            for variable in ("temperature", "humidity", "pressure"):
                current = getattr(feature, variable)
                previous_value = (
                    getattr(features[index - 1], variable)
                    if index > 0
                    else None
                )

                if (
                    previous_value is not None
                    and abs(current - previous_value) <= self.frozen_tolerance
                ):
                    frozen_counts[variable] += 1
                else:
                    frozen_counts[variable] = 0

                if frozen_counts[variable] >= self.frozen_consecutive:
                    diagnostic_score = max(diagnostic_score, 1.0)
                    fault_type = fault_type or "FROZEN_SENSOR"
                    affected_variable = affected_variable or variable
                    reasons.append(f"{variable}_frozen")

            if feature.valid_for_scoring:
                change_candidates = {
                    "temperature": abs(feature.temperature_delta or 0.0),
                    "humidity": abs(feature.humidity_delta or 0.0),
                    "pressure": abs(feature.pressure_delta or 0.0),
                }
                max_change_variable, max_change = max(
                    change_candidates.items(),
                    key=lambda item: item[1],
                )
                max_scale = {
                    "temperature": feature.temperature_rolling_std or 0.0,
                    "humidity": feature.humidity_rolling_std or 0.0,
                    "pressure": feature.pressure_rolling_std or 0.0,
                }[max_change_variable]
                if max_scale > 1e-9:
                    change_ratio = max_change / (3.0 * max_scale)
                    if change_ratio >= self.threshold:
                        diagnostic_score = max(diagnostic_score, min(change_ratio, 1.0))
                        reasons.append(f"{max_change_variable}_abrupt_change")
                        fault_type = fault_type or "ABRUPT_CHANGE"
                        affected_variable = affected_variable or max_change_variable

                start = max(0, index - self.drift_window + 1)
                drift_window = features[start:index + 1]
                if len(drift_window) >= self.drift_window:
                    for variable in ("temperature", "humidity", "pressure"):
                        values = np.asarray(
                            [getattr(row, variable) for row in drift_window],
                            dtype=float,
                        )
                        slope = abs(float(np.polyfit(np.arange(len(values)), values, 1)[0]))
                        baseline_scale = {
                            "temperature": feature.temperature_rolling_std or 0.0,
                            "humidity": feature.humidity_rolling_std or 0.0,
                            "pressure": feature.pressure_rolling_std or 0.0,
                        }[variable]
                        if baseline_scale > 1e-9 and slope / baseline_scale >= 0.25:
                            diagnostic_score = max(
                                diagnostic_score,
                                min(slope / baseline_scale, 1.0),
                            )
                            reasons.append(f"{variable}_gradual_drift")
                            fault_type = fault_type or "GRADUAL_DRIFT"
                            affected_variable = affected_variable or variable

            diagnostic_is_anomaly = diagnostic_score >= self.threshold
            results.append(
                DiagnosticResult(
                    timestamp=feature.timestamp,
                    diagnostic_score=float(np.clip(diagnostic_score, 0.0, 1.0)),
                    diagnostic_anomaly=diagnostic_is_anomaly,
                    fault_type=fault_type,
                    affected_variable=affected_variable,
                    reasons=tuple(dict.fromkeys(reasons)),
                )
            )

        return results


class ScoreFusion:
    """Fuse statistical, ML, diagnostic, and multivariate anomaly signals."""

    def __init__(
        self,
        statistical_weight: float = 0.45,
        ml_weight: float = 0.55,
        threshold: float = 0.75,
    ):
        self.statistical_weight = statistical_weight
        self.ml_weight = ml_weight
        self.threshold = threshold

    def fuse(
        self,
        statistical_scores: Sequence[DetectorResult],
        ml_scores: Sequence[DetectorResult],
        diagnostic_scores: Sequence[DiagnosticResult] | None = None,
        multivariate_scores: Sequence[DetectorResult] | None = None,
    ) -> list[AnomalyResult]:
        statistical_map = {result.timestamp: result for result in statistical_scores}
        ml_map = {result.timestamp: result for result in ml_scores}
        diagnostic_map = {
            result.timestamp: result
            for result in (diagnostic_scores or ())
        }
        multivariate_map = {
            result.timestamp: result
            for result in (multivariate_scores or ())
        }

        timestamps = sorted(
            set(statistical_map)
            | set(ml_map)
            | set(diagnostic_map)
            | set(multivariate_map)
        )

        results: list[AnomalyResult] = []

        for timestamp in timestamps:
            statistical = statistical_map.get(
                timestamp,
                DetectorResult(timestamp, 0.0, False, ()),
            )
            ml = ml_map.get(
                timestamp,
                DetectorResult(timestamp, 0.0, False, ()),
            )
            diagnostic = diagnostic_map.get(
                timestamp,
                DiagnosticResult(timestamp, 0.0, False, None, None, ()),
            )
            multivariate = multivariate_map.get(
                timestamp,
                DetectorResult(timestamp, 0.0, False, ()),
            )

            context_score = (
                self.statistical_weight * statistical.score
                + self.ml_weight * ml.score
            )
            final_score = max(
                context_score,
                diagnostic.diagnostic_score,
                multivariate.score,
            )
            is_anomaly = final_score >= self.threshold

            reasons = list(statistical.reasons)
            for reason in ml.reasons:
                if reason not in reasons:
                    reasons.append(reason)
            for reason in diagnostic.reasons:
                if reason not in reasons:
                    reasons.append(reason)
            for reason in multivariate.reasons:
                if reason not in reasons:
                    reasons.append(reason)

            fault_type = (
                diagnostic.fault_type
                or (
                    "MULTIVARIATE_INCONSISTENCY"
                    if multivariate.is_anomaly
                    else None
                )
                or ("UNCLASSIFIED_ANOMALY" if is_anomaly else None)
                or "NORMAL"
            )
            affected_variable = diagnostic.affected_variable
            if affected_variable is None and multivariate.is_anomaly:
                affected_variable = "temperature,humidity,pressure"

            results.append(
                AnomalyResult(
                    timestamp=timestamp,
                    statistical_score=statistical.score,
                    ml_score=ml.score,
                    diagnostic_score=diagnostic.diagnostic_score,
                    multivariate_score=multivariate.score,
                    final_score=final_score,
                    is_anomaly=is_anomaly,
                    alert_active=False,
                    alert_state="NORMAL",
                    diagnostic_anomaly=(
                        diagnostic.diagnostic_anomaly
                        or multivariate.is_anomaly
                    ),
                    fault_type=fault_type,
                    affected_variable=affected_variable,
                    reasons=tuple(reasons),
                )
            )

        return results
