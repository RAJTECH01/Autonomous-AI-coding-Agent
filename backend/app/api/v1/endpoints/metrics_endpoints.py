from fastapi import APIRouter, Response, Query
from app.core.metrics import metrics_registry
from app.services.background_job_monitor import background_job_monitor

router = APIRouter(prefix="/metrics", tags=["Observability & Metrics"])


@router.get("", summary="Prometheus / JSON Metrics Endpoint")
async def get_metrics(format: str = Query(default="prometheus", description="Format: prometheus or json")):
    """
    Exposes all 12 production metrics.
    Supports standard Prometheus text exposition format (default) and JSON format.
    """
    if format.lower() == "json":
        return metrics_registry.get_dashboard_summary()
    
    prometheus_data = metrics_registry.get_prometheus_exposition()
    return Response(content=prometheus_data, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/dashboard", summary="Production Metrics Dashboard API")
async def get_dashboard_metrics():
    """
    Returns aggregated JSON telemetry dataset for production monitoring dashboards.
    Includes tasks started/completed/failed, avg execution time, avg iterations,
    tool call counts, test failures, retries, model latencies, token usage,
    estimated AI costs (USD), and sandbox failure breakdowns.
    """
    return metrics_registry.get_dashboard_summary()


@router.get("/background-jobs", summary="Background Job Monitoring Telemetry")
async def get_background_jobs_status():
    """
    Returns real-time status of all background daemon processes, agent worker jobs, and subagent state machines.
    """
    return background_job_monitor.get_job_summary()
