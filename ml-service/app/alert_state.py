from collections.abc import Sequence

from .models import AnomalyResult


class AlertStateManager:
    """
    Convert noisy point-level anomaly decisions into an operational alert.

    An alert activates immediately when a raw anomaly is detected.

    Once active, the alert requires a configurable number of consecutive
    normal readings before returning to NORMAL.
    """

    def __init__(self, clear_after_normals: int = 3):
        if clear_after_normals < 1:
            raise ValueError("clear_after_normals must be >= 1")

        self.clear_after_normals = clear_after_normals

    def apply(
        self,
        results: Sequence[AnomalyResult],
    ) -> list[AnomalyResult]:
        ordered = sorted(results, key=lambda result: result.timestamp)

        output: list[AnomalyResult] = []

        alert_active = False
        consecutive_normals = 0

        for result in ordered:
            updated = result.model_copy()

            if result.is_anomaly:
                alert_active = True
                consecutive_normals = 0

                updated.alert_active = True
                updated.alert_state = "ACTIVE"

            elif alert_active:
                consecutive_normals += 1

                if consecutive_normals >= self.clear_after_normals:
                    alert_active = False
                    consecutive_normals = 0

                    updated.alert_active = False
                    updated.alert_state = "NORMAL"
                else:
                    updated.alert_active = True
                    updated.alert_state = "RECOVERING"

            else:
                updated.alert_active = False
                updated.alert_state = "NORMAL"

            output.append(updated)

        return output