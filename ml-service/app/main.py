import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from .analysis import AnalysisEngine
from .config import settings
from .data_client import SkyGuardDataClient
from .models import AnalyzeResponse, EvaluationResponse, MlServiceStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


client = SkyGuardDataClient(settings)
analysis_engine = AnalysisEngine(client, settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting SkyGuard ML service")
    await analysis_engine.refresh()
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
    return await analysis_engine.get_status()


@app.get("/ml/analyze", response_model=AnalyzeResponse)
async def ml_analyze(
    limit: int = Query(default=200, ge=1, le=10000),
) -> AnalyzeResponse:
    try:
        return await analysis_engine.analyze(limit)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/ml/evaluation", response_model=EvaluationResponse)
async def ml_evaluation() -> EvaluationResponse:
    try:
        return await analysis_engine.evaluate()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error