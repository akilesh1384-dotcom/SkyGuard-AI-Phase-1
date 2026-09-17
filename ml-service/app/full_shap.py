from __future__ import annotations

from collections.abc import Callable

import numpy as np
import shap
from sklearn.ensemble import IsolationForest

from .models import AnomalyResult


def attach_full_shap(engine) -> None:
    """Attach SHAP explanations to FULL-mode Isolation Forest results.

    The existing FULL detector remains responsible for anomaly scoring. This
    wrapper fits the same Isolation Forest configuration on the same clean
    baseline feature vectors and adds TreeSHAP explanations to its results.
    """
    original: Callable[[], list[AnomalyResult]] = engine._run_detectors

    def run_with_shap() -> list[AnomalyResult]:
        results = original()
        if not results:
            return results

        try:
            features = engine._engineered_features()
            baseline_features = engine._baseline_features(features)
            if len(baseline_features) < 20:
                return results

            matrix = np.asarray(
                [feature.vector() for feature in baseline_features],
                dtype=float,
            )
            model = IsolationForest(
                n_estimators=100,
                random_state=42,
                contamination="auto",
            )
            model.fit(matrix)

            explainer = shap.TreeExplainer(model)
            expected = np.asarray(explainer.expected_value).reshape(-1)
            base_value = float(expected[0]) if expected.size else None
            feature_names = tuple(baseline_features[0].feature_names)
            feature_by_timestamp = {
                feature.timestamp: feature
                for feature in features
                if feature.valid_for_scoring
            }

            explained: list[AnomalyResult] = []
            for result in results:
                feature = feature_by_timestamp.get(result.timestamp)
                if feature is None:
                    explained.append(result)
                    continue

                row = np.asarray([feature.vector()], dtype=float)
                values = np.asarray(explainer.shap_values(row))
                if values.ndim == 3:
                    values = values[0]
                if values.ndim == 2:
                    values = values[0]
                values = values.reshape(-1)

                contributions = []
                for index, shap_value in enumerate(values[:len(feature_names)]):
                    numeric = float(shap_value)
                    contributions.append(
                        {
                            "feature": feature_names[index],
                            "value": float(row[0, index]),
                            "shap_value": numeric,
                            "direction": "increases_anomaly" if numeric < 0 else "decreases_anomaly",
                        }
                    )
                contributions.sort(key=lambda item: abs(item["shap_value"]), reverse=True)

                explained.append(
                    result.model_copy(
                        update={
                            "shap_base_value": base_value,
                            "shap_contributions": contributions,
                        }
                    )
                )

            return explained
        except Exception:
            # SHAP is explanatory metadata; never let an explanation failure
            # interrupt the actual anomaly detector.
            return results

    engine._run_detectors = run_with_shap
