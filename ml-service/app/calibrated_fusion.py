from __future__ import annotations

from collections.abc import Sequence

from .models import AnomalyResult, DiagnosticResult, DetectorResult


class CalibratedScoreFusion:
    """Fuse contextual and multivariate signals without letting one dominate.

    Sequence-specific diagnostic faults (for example MISSING_DATA and
    FROZEN_SENSOR) can trigger directly. Statistical, Isolation Forest, and
    multivariate signals are combined instead of taking the maximum, which
    reduces false positives from a single over-sensitive detector.
    """

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
        diagnostic_map = {result.timestamp: result for result in (diagnostic_scores or ())}
        multivariate_map = {result.timestamp: result for result in (multivariate_scores or ())}

        timestamps = sorted(
            set(statistical_map)
            | set(ml_map)
            | set(diagnostic_map)
            | set(multivariate_map)
        )

        results: list[AnomalyResult] = []

        for timestamp in timestamps:
            statistical = statistical_map.get(timestamp, DetectorResult(timestamp, 0.0, False, ()))
            ml = ml_map.get(timestamp, DetectorResult(timestamp, 0.0, False, ()))
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

            combined_context = 0.5 * context_score + 0.5 * multivariate.score
            final_score = max(diagnostic.diagnostic_score, combined_context)
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

            fault_type = diagnostic.fault_type
            affected_variable = diagnostic.affected_variable

            if fault_type is None and multivariate.is_anomaly and is_anomaly:
                fault_type = "MULTIVARIATE_INCONSISTENCY"
                affected_variable = "temperature,humidity,pressure"

            if fault_type is None:
                fault_type = "UNCLASSIFIED_ANOMALY" if is_anomaly else "NORMAL"

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
                    reasons=list(reasons),
                    shap_base_value=ml.shap_base_value,
                    shap_contributions=list(ml.shap_contributions),
                )
            )

        return results
