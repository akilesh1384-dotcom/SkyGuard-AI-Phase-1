from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.covariance import LedoitWolf

from .models import DetectorResult, EngineeredFeatures


class CalibratedMultivariateDetector:
    """Detect unusual joint sensor behavior using an empirical baseline percentile.

    The detector keeps the existing Ledoit-Wolf Mahalanobis distance, but maps
    each distance to its empirical percentile among the known-normal baseline.
    This avoids dividing by the baseline 99th-percentile distance, which can
    saturate normal post-baseline readings at a score of 1.0 when the baseline
    is small or slightly shifted.
    """

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self.mean_: np.ndarray | None = None
        self.cov_inv_: np.ndarray | None = None
        self.baseline_distances_: np.ndarray | None = None
        self._fitted = False

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

        covariance_model = LedoitWolf().fit(matrix)
        self.mean_ = covariance_model.location_.astype(float)
        self.cov_inv_ = np.linalg.pinv(covariance_model.covariance_)

        self.baseline_distances_ = np.sort(
            np.asarray(
                [self._distance(row) for row in matrix],
                dtype=float,
            )
        )
        self._fitted = True

    def detect(
        self,
        features: Sequence[EngineeredFeatures],
    ) -> list[DetectorResult]:
        if not self._fitted:
            raise RuntimeError("Multivariate detector has not been fitted.")
        if self.baseline_distances_ is None:
            raise RuntimeError("Multivariate baseline is not initialized.")

        results: list[DetectorResult] = []
        baseline_count = len(self.baseline_distances_)

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
            rank = int(np.searchsorted(self.baseline_distances_, distance, side="right"))

            # Empirical percentile of the observed distance among known-normal
            # baseline distances. Keep the score strictly below 1 for the most
            # normal baseline point and at 1 only for distances beyond the full
            # baseline range.
            score = float(rank / baseline_count)
            score = float(np.clip(score, 0.0, 1.0))

            results.append(
                DetectorResult(
                    timestamp=feature.timestamp,
                    score=score,
                    is_anomaly=score >= self.threshold,
                    reasons=(
                        ("multivariate_inconsistency",)
                        if score >= self.threshold
                        else ()
                    ),
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
