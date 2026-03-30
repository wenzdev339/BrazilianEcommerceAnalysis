from fastapi import APIRouter
from pydantic import BaseModel

from api.database import check_db_connection

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="API liveness check")
async def health_check():
    """Returns 200 if the API and database are reachable."""
    db_ok = await check_db_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="connected" if db_ok else "unreachable",
        version="1.0.0",
    )
