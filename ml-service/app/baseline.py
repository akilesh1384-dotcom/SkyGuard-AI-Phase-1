from dataclasses import dataclass
from collections.abc import Sequence

from .data_client import reading_is_faulty
from .models import GroundTruthEvent, SensorReading


@dataclass(frozen=True)
class Baseline:
    """The first known-normal readings used for model fitting."""

    readings: tuple[SensorReading, ...]
    required: int

    @property
    def progress(self) -> int:
        return min(len(self.readings), self.required)

    @property
    def initialized(self) -> bool:
        return len(self.readings) >= self.required


class BaselineManager:
    def __init__(self, required: int = 60):
        self.required = required

    def build(
        self,
        readings: Sequence[SensorReading],
        events: Sequence[GroundTruthEvent],
    ) -> Baseline:
        chronological = sorted(readings, key=lambda reading: reading.timestamp)
        normal_readings = [
            reading
            for reading in chronological
            if not reading_is_faulty(reading, events)
        ]
        return Baseline(
            readings=tuple(normal_readings[: self.required]),
            required=self.required,
        )