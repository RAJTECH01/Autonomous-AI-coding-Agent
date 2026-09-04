import time
import os
import shutil
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

try:
    import psutil
except ImportError:
    psutil = None

from app.infrastructure.db.session import get_db
from app.core.config import settings
from app.core.metrics import metrics_registry
from app.services.background_job_monitor import background_job_monitor

router = APIRouter()


@router.get("/health", summary="System Liveness Check")
async def liveness_check():
    """Basic liveness probe checking if application server process is up."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/detail", summary="Detailed System Telemetry & Health")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """Comprehensive health check checking CPU, memory, database latency, disk space, and background workers."""
    db_status = "ok"
    db_latency_ms = 0.0
    
    t0 = time.time()
    try:
        await db.execute(text("SELECT 1"))
        db_latency_ms = round((time.time() - t0) * 1000, 2)
    except Exception as e:
        db_status = f"unavailable: {str(e)}"

    # System Resource Metrics with fallback
    cpu_percent = psutil.cpu_percent(interval=None) if psutil else 0.0
    memory_info = psutil.virtual_memory() if psutil else None
    disk_info = shutil.disk_usage(os.getcwd())

    bg_summary = background_job_monitor.get_job_summary()
    dashboard_metrics = metrics_registry.get_dashboard_summary()

    mem_percent = memory_info.percent if memory_info else 0.0
    is_healthy = (db_status == "ok") and (mem_percent < 95.0)

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": {
            "status": db_status,
            "latency_ms": db_latency_ms,
        },
        "resources": {
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "memory_used_mb": round(memory_info.used / (1024 * 1024), 1) if memory_info else 0.0,
            "memory_total_mb": round(memory_info.total / (1024 * 1024), 1) if memory_info else 0.0,
            "disk_free_gb": round(disk_info.free / (1024 * 1024 * 1024), 2),
            "disk_total_gb": round(disk_info.total / (1024 * 1024 * 1024), 2),
        },
        "background_jobs": {
            "running": bg_summary["running"],
            "completed": bg_summary["completed"],
            "failed": bg_summary["failed"],
        },
        "telemetry_summary": dashboard_metrics,
    }


@router.get("/readiness", summary="System Readiness Check")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe verifying database connectivity and disk capacity before receiving traffic."""
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unavailable: {str(e)}"

    disk_info = shutil.disk_usage(os.getcwd())
    disk_ok = disk_info.free > (50 * 1024 * 1024)  # At least 50MB free

    is_ready = (db_status == "ok") and disk_ok
    return {
        "status": "ready" if is_ready else "unhealthy",
        "database": db_status,
        "disk_storage": "ok" if disk_ok else "insufficient_space",
        "service": settings.PROJECT_NAME,
    }
