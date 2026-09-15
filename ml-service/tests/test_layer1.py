from datetime import datetime, timedelta, timezone

import pytest

from app.baseline import BaselineManager
from app.data_client import reading_is_faulty
from app.ml_placeholders import (
    FeatureEngineer,
    MlDetector,
    ScoreFusion,
    StatisticalDetector,
)
from app.models import DetectorResult, GroundTruthEvent, SensorReading
from app.analysis import calculate_metrics


BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_readings(count: int, temperature_offset: float = 0.0) -> list[SensorReading]:
    return [
        SensorReading(
            timestamp=BASE_TIME + timedelta(minutes=index),
            temperature=24 + temperature_offset + index * 0.01,
            humidity=58 - index * 0.01,
            pressure=1013 + index * 0.01,
        )
        for index in range(count)
    ]


def test_feature_calculation_uses_a_causal_20_reading_window() -> None:
    readings = make_readings(25)
    features = FeatureEngineer(window=20).transform(readings)

    assert features[19].valid_for_scoring is False
    assert features[20].valid_for_scoring is True
    assert features[20].history_size == 20
    assert features[20].temperature_rolling_mean == pytest.approx(
        sum(reading.temperature for reading in readings[:20]) / 20
    )
    assert features[20].temperature_delta == pytest.approx(
        readings[20].temperature - readings[19].temperature
    )


def test_feature_calculation_does_not_use_future_readings() -> None:
    readings = make_readings(25)
    original = FeatureEngineer(window=20).transform(readings)

    future_reading = SensorReading(
        timestamp=BASE_TIME + timedelta(minutes=25),
        temperature=200,
        humidity=-100,
        pressure=500,
    )
    with_future = FeatureEngineer(window=20).transform(
        [*readings, future_reading]
    )

    assert original[24] == with_future[24]


def test_baseline_uses_only_known_normal_readings() -> None:
    readings = make_readings(65)
    event = GroundTruthEvent(
        fault_type="TEMPERATURE_SPIKE",
        affected_variable="temperature",
        start_timestamp=readings[10].timestamp,
        end_timestamp=readings[14].timestamp,
    )

    baseline = BaselineManager(required=60).build(readings, [event])

    assert baseline.initialized is True
    assert baseline.progress == 60
    assert all(
        not reading_is_faulty(reading, [event])
        for reading in baseline.readings
    )
    assert readings[10].timestamp not in {
        reading.timestamp for reading in baseline.readings
    }


def test_statistical_detector_scores_a_spike() -> None:
    readings = make_readings(21)
    readings[-1] = readings[-1].model_copy(update={"temperature": 40.0})
    features = FeatureEngineer(window=20).transform(readings)

    results = StatisticalDetector(threshold=0.75).detect(features)
    result = next(item for item in results if item.timestamp == readings[-1].timestamp)

    assert 0 <= result.score <= 1
    assert result.is_anomaly is True
    assert "temperature_deviation" in result.reasons


def test_isolation_forest_scores_are_normalized() -> None:
    readings = make_readings(65)
    features = FeatureEngineer(window=20).transform(readings)
    detector = MlDetector()
    detector.fit(features[20:60])

    results = detector.detect(features[20:])

    assert results
    assert all(0 <= result.score <= 1 for result in results)


def test_score_fusion_uses_the_documented_weights() -> None:
    timestamp = BASE_TIME
    results = ScoreFusion().fuse(
        [
            DetectorResult(
                timestamp=timestamp,
                score=0.8,
                is_anomaly=True,
                reasons=("statistical",),
            )
        ],
        [
            DetectorResult(
                timestamp=timestamp,
                score=0.6,
                is_anomaly=False,
                reasons=(),
            )
        ],
    )

    assert results[0].final_score == pytest.approx(0.45 * 0.8 + 0.55 * 0.6)
    assert results[0].is_anomaly is False


def test_ground_truth_interval_excludes_fault_readings() -> None:
    readings = make_readings(5)
    event = GroundTruthEvent(
        fault_type="PRESSURE_ANOMALY",
        affected_variable="pressure",
        start_timestamp=readings[2].timestamp,
        end_timestamp=None,
    )

    assert reading_is_faulty(readings[1], [event]) is False
    assert reading_is_faulty(readings[2], [event]) is True
    assert reading_is_faulty(readings[4], [event]) is True


def test_evaluation_metrics_are_measured_from_predictions() -> None:
    metrics = calculate_metrics(
        [True, False, True, False],
        [True, True, False, False],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.false_negatives == 1
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.f1_score == pytest.approx(0.5)