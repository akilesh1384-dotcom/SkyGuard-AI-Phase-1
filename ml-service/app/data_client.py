import logging
from collections.abc import Sequence

import httpx
from pydantic import TypeAdapter, ValidationError

from .config import Settings
from .models import GroundTruthEvent, SensorReading

logger = logging.getLogger(__name__)
READINGS_ADAPTER = TypeAdapter(list[SensorReading])
GROUND_TRUTH_ADAPTER = TypeAdapter(list[GroundTruthEvent])


class SkyGuardDataClient:
    """Fetch and validate readings from the existing SkyGuard API."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_readings(self, limit: int | None = None) -> list[SensorReading]:
        params = {"limit": limit} if limit is not None else None

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds
            ) as client:
                response = await client.get(self.settings.readings_url, params=params)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception(
                "SkyGuard API connection failed",
                extra={"url": self.settings.readings_url},
            )
            raise

        try:
            payload = response.json()
            readings = READINGS_ADAPTER.validate_python(payload)
        except (ValueError, ValidationError):
            logger.exception("SkyGuard API returned invalid sensor data")
            raise

        ordered = sorted(readings, key=lambda reading: reading.timestamp)
        logger.info(
            "Fetched sensor readings from SkyGuard API",
            extra={"count": len(ordered)},
        )
        return ordered

    async def fetch_ground_truth(self) -> list[GroundTruthEvent]:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds
            ) as client:
                response = await client.get(self.settings.ground_truth_url)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception(
                "SkyGuard ground-truth API connection failed",
                extra={"url": self.settings.ground_truth_url},
            )
            raise

        try:
            payload = response.json()
            events = GROUND_TRUTH_ADAPTER.validate_python(payload)
        except (ValueError, ValidationError):
            logger.exception("SkyGuard API returned invalid ground-truth data")
            raise

        ordered = sorted(events, key=lambda event: event.start_timestamp)
        logger.info(
            "Fetched simulator ground-truth events from SkyGuard API",
            extra={"count": len(ordered)},
        )
        return ordered


def readings_are_chronological(readings: Sequence[SensorReading]) -> bool:
    """Small internal invariant helper for future pipeline implementations."""

    return all(
        left.timestamp <= right.timestamp
        for left, right in zip(readings, readings[1:])
    )


def reading_is_in_event(
    reading: SensorReading,
    event: GroundTruthEvent,
) -> bool:
    if reading.timestamp < event.start_timestamp:
        return False
    if event.end_timestamp is None:
        return True
    return reading.timestamp <= event.end_timestamp


def reading_is_faulty(
    reading: SensorReading,
    events: Sequence[GroundTruthEvent],
    fault_type: str | None = None,
) -> bool:
    return any(
        (fault_type is None or event.fault_type == fault_type)
        and reading_is_in_event(reading, event)
        for event in events
    )