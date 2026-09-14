from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SensorReading(BaseModel):
    """The exact four-field reading contract returned by SkyGuard."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class MlServiceStatus(BaseModel):
    status: str
    readings_loaded: int = Field(ge=0)
    latest_reading_timestamp: datetime | None
    baseline_initialized: bool