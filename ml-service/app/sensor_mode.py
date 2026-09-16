from enum import StrEnum


class SensorMode(StrEnum):
    """Available telemetry profiles for the ML pipeline."""

    FULL = "FULL"
    AWS = "AWS"


def is_valid_sensor_mode(value: str) -> bool:
    return value.upper() in {mode.value for mode in SensorMode}
