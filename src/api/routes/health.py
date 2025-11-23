"""
Health check endpoint.
"""
from fastapi import APIRouter, status
from datetime import datetime
import logging

from src.api.schemas import HealthResponse
from src.api.utils import run_in_executor
from src.models.database import get_db_cursor
from src.config import REDIS_URL
import redis

logger = logging.getLogger(__name__)

router = APIRouter()

# Reusable Redis connection pool for health checks
_redis_pool = None


def _get_redis_pool():
    """Get or create Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(REDIS_URL, max_connections=5)
    return _redis_pool


def _check_database() -> str:
    """Synchronous database health check."""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return "unhealthy"


def _check_redis() -> str:
    """Synchronous Redis health check using connection pool."""
    try:
        pool = _get_redis_pool()
        r = redis.Redis(connection_pool=pool)
        r.ping()
        return "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return "unhealthy"


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
    # Run blocking checks in thread pool executor
    db_status, redis_status = await run_in_executor(
        lambda: (_check_database(), _check_redis())
    )

    # Overall status
    overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        database=db_status,
        redis=redis_status,
    )
