from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SensorReading(BaseModel):
    """Sensor reading. Pressure is optional for the physical AWS prototype."""
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class GroundTruthEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fault_type: str
    affected_variable: str
    start_timestamp: datetime
    end_timestamp: datetime | None = None

    @field_validator("start_timestamp", "end_timestamp")
    @classmethod
    def normalize_event_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


FEATURE_NAMES = (
    "temperature", "humidity", "pressure", "temperature_delta", "humidity_delta", "pressure_delta",
    "temperature_rolling_mean", "temperature_rolling_std", "humidity_rolling_mean", "humidity_rolling_std",
    "pressure_rolling_mean", "pressure_rolling_std", "temperature_normalized_deviation", "humidity_normalized_deviation",
    "pressure_normalized_deviation", "temperature_humidity_relationship", "temperature_pressure_relationship",
    "humidity_pressure_relationship",
)


@dataclass(frozen=True)
class EngineeredFeatures:
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float | None
    temperature_delta: float | None
    humidity_delta: float | None
    pressure_delta: float | None
    temperature_rolling_mean: float | None
    temperature_rolling_std: float | None
    humidity_rolling_mean: float | None
    humidity_rolling_std: float | None
    pressure_rolling_mean: float | None
    pressure_rolling_std: float | None
    temperature_normalized_deviation: float | None
    humidity_normalized_deviation: float | None
    pressure_normalized_deviation: float | None
    temperature_humidity_relationship: float | None
    temperature_pressure_relationship: float | None
    humidity_pressure_relationship: float | None
    history_size: int
    history_contains_fault: bool
    valid_for_scoring: bool
    robust_medians: tuple[float, float, float] | None = None
    robust_scales: tuple[float, float, float] | None = None
    feature_names: ClassVar[tuple[str, ...]] = FEATURE_NAMES

    def vector(self) -> list[float]:
        if not self.valid_for_scoring:
            raise ValueError("Feature row does not have enough causal history")
        values = [getattr(self, name) for name in self.feature_names]
        if any(value is None for value in values):
            raise ValueError("Valid feature row contains an unset feature")
        return [float(value) for value in values]


@dataclass(frozen=True)
class DetectorResult:
    timestamp: datetime
    score: float
    is_anomaly: bool
    reasons: tuple[str, ...] = ()
    shap_base_value: float | None = None
    shap_contributions: tuple["ShapContribution", ...] = ()


@dataclass(frozen=True)
class DiagnosticResult:
    timestamp: datetime
    diagnostic_score: float
    diagnostic_anomaly: bool
    fault_type: str | None
    affected_variable: str | None
    reasons: tuple[str, ...] = ()


class MlServiceStatus(BaseModel):
    status: str
    readings_loaded: int = Field(ge=0)
    latest_reading_timestamp: datetime | None
    baseline_initialized: bool
    baseline_progress: int = Field(ge=0)
    baseline_required: int = Field(default=60, ge=1)
    sensor_mode: str = "FULL"


class ShapContribution(BaseModel):
    feature: str
    value: float
    shap_value: float
    direction: str


class AnomalyResult(BaseModel):
    timestamp: datetime
    statistical_score: float = Field(ge=0, le=1)
    ml_score: float = Field(ge=0, le=1)
    diagnostic_score: float = Field(ge=0, le=1)
    multivariate_score: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    is_anomaly: bool
    alert_active: bool = False
    alert_state: str = "NORMAL"
    diagnostic_anomaly: bool
    fault_type: str
    affected_variable: str | None = None
    reasons: list[str]
    shap_base_value: float | None = None
    shap_contributions: list[ShapContribution] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    status: str
    baseline_progress: int = Field(ge=0)
    baseline_required: int = Field(default=60, ge=1)
    baseline_initialized: bool
    sensor_mode: str = "FULL"
    results: list[AnomalyResult]


class EvaluationMetrics(BaseModel):
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1_score: float | None = Field(default=None, ge=0, le=1)


class EventDetectionMetrics(BaseModel):
    total_events: int = Field(ge=0)
    detected_events: int = Field(ge=0)
    missed_events: int = Field(ge=0)
    detection_rate: float | None = Field(default=None, ge=0, le=1)
    mean_detection_latency_seconds: float | None = Field(default=None, ge=0)
    mean_recovery_latency_seconds: float | None = Field(default=None, ge=0)


class EventLatency(BaseModel):
    fault_type: str
    affected_variable: str
    start_timestamp: datetime
    end_timestamp: datetime | None
    detection_latency_seconds: float | None = Field(default=None, ge=0)
    recovery_latency_seconds: float | None = Field(default=None, ge=0)


class EvaluationResponse(BaseModel):
    status: str
    message: str | None = None
    baseline_progress: int = Field(ge=0)
    baseline_required: int = Field(default=60, ge=1)
    baseline_initialized: bool
    sensor_mode: str = "FULL"
    total_readings: int = Field(ge=0)
    evaluated_readings: int = Field(ge=0)
    labeled_readings: int = Field(ge=0)
    metrics: EvaluationMetrics | None = None
    by_fault_type: dict[str, EvaluationMetrics] = Field(default_factory=dict)
    event_metrics_by_fault_type: dict[str, EventDetectionMetrics] = Field(default_factory=dict)
    event_latencies: list[EventLatency] = Field(default_factory=list)
