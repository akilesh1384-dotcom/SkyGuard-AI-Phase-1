import logging
from collections.abc import Sequence

import httpx
from pydantic import TypeAdapter, ValidationError

from .config import Settings
from .models import SensorReading

logger = logging.getLogger(__name__)
READINGS_ADAPTER = TypeAdapter(list[SensorReading])


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


def readings_are_chronological(readings: Sequence[SensorReading]) -> bool:
    """Small internal invariant helper for future pipeline implementations."""

    return all(
        left.timestamp <= right.timestamp
        for left, right in zip(readings, readings[1:])
    )