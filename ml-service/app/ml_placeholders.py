"""Explicit placeholders for the future SkyGuard ML methodology.

These classes intentionally do not perform anomaly detection or sensor-health
prediction. They return empty or clearly marked placeholder values until the
methodology is provided.
"""

from collections.abc import Sequence
from typing import Any

from .models import SensorReading


class FeatureEngineer:
    def transform(self, readings: Sequence[SensorReading]) -> list[dict[str, Any]]:
        # TODO: Add the approved feature-engineering methodology.
        return []


class StatisticalDetector:
    def detect(self, features: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        # TODO: Add the approved statistical detector.
        return []


class MlDetector:
    def detect(self, features: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        # TODO: Add the approved ML detector.
        return []


class ScoreFusion:
    def fuse(
        self,
        statistical_scores: Sequence[dict[str, Any]],
        ml_scores: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # TODO: Add the approved score-fusion methodology.
        return []


class FaultClassifier:
    def classify(self, fused_scores: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        # TODO: Add the approved fault-classification methodology.
        return []


class SensorHealth:
    def estimate(self, readings: Sequence[SensorReading]) -> dict[str, Any]:
        # TODO: Add the approved sensor-health methodology.
        return {"status": "not_implemented"}