"""
Health check endpoint.
"""
from fastapi import APIRouter, status
from datetime import datetime
import logging

from src.api.schemas import HealthResponse
from src.models.database import get_db_cursor
from src.config import REDIS_URL
import redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check the health status of the API and its dependencies",
)
async def health_check():
    """
    Health check endpoint.

    Returns the status of:
    - API service
    - Database connection
    - Redis connection

    Returns:
        HealthResponse: Health status information
    """
    # Check database
    db_status = "healthy"
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Redis
    redis_status = "healthy"
    try:
        r = redis.from_url(REDIS_URL)
        r.ping()
        r.close()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

    # Overall status
    overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        database=db_status,
        redis=redis_status,
    )
