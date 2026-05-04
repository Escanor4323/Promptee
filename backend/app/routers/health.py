"""Health check endpoint."""

import logging

from fastapi import APIRouter, HTTPException

from app.db.sqlite import get_database_status, verify_tables_exist

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Returns database status, connectivity, and table verification.
    Raises 503 if database is not healthy.
    """
    try:
        # Verify all required tables exist
        await verify_tables_exist()

        # Get database status
        db_status = await get_database_status()

        return {
            "status": "healthy",
            "database": {
                "connected": True,
                "tables_verified": True,
                "table_count": db_status["table_count"],
                "db_path": db_status["db_path"],
                "db_size_bytes": db_status["db_size"],
            },
        }
    except RuntimeError as e:
        logger.error("Health check failed - database issue: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Database unhealthy: {str(e)}",
        ) from e
    except Exception as e:
        logger.error("Health check failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Health check failed",
        ) from e
