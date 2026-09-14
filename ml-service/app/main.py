import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .data_client import SkyGuardDataClient
from .models import MlServiceStatus, SensorReading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class ReadingState:
    def __init__(self, client: SkyGuardDataClient):
        self.client = client
        self.readings: list[SensorReading] = []
        self.last_error: str | None = None

    async def refresh(self) -> None:
        try:
            self.readings = await self.client.fetch_readings()
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)
            logger.warning("Keeping the last valid reading cache after fetch failure")

    def status(self) -> MlServiceStatus:
        latest = self.readings[-1].timestamp if self.readings else None
        return MlServiceStatus(
            status="degraded" if self.last_error else "ready",
            readings_loaded=len(self.readings),
            latest_reading_timestamp=latest,
            # TODO: Set true only after the approved baseline methodology runs.
            baseline_initialized=False,
        )


client = SkyGuardDataClient(settings)
reading_state = ReadingState(client)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting SkyGuard ML service")
    await reading_state.refresh()
    yield
    logger.info("Stopping SkyGuard ML service")


app = FastAPI(
    title="SkyGuard AI ML Service",
    description="Independent ML service shell; anomaly algorithms are intentionally pending.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ml/status", response_model=MlServiceStatus)
async def ml_status() -> MlServiceStatus:
    await reading_state.refresh()
    return reading_state.status()