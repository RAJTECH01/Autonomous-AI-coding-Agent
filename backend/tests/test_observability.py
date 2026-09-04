import pytest
from app.core.logging import (
    set_correlation_id,
    set_request_id,
    set_run_id,
    set_tool_call_id,
    get_correlation_id,
    get_request_id,
    get_run_id,
    get_tool_call_id,
    redact_sensitive_data,
)
from app.core.metrics import MetricsRegistry
from app.services.background_job_monitor import BackgroundJobMonitor


def test_sensitive_data_redaction():
    payload = {
        "user": "alice",
        "password": "SecretPassword123!",
        "access_token": "bearer-xyz-secret-token",
        "api_key": "sk-1234567890",
        "nested": {
            "secret_key": "top-secret-val",
            "normal_field": "visible",
        }
    }
    redacted = redact_sensitive_data(None, None, payload)
    
    assert redacted["user"] == "alice"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["secret_key"] == "[REDACTED]"
    assert redacted["nested"]["normal_field"] == "visible"


def test_tracing_context_propagation():
    set_correlation_id("corr-123")
    set_request_id("req-456")
    set_run_id("run-789")
    set_tool_call_id("tool-012")

    assert get_correlation_id() == "corr-123"
    assert get_request_id() == "req-456"
    assert get_run_id() == "run-789"
    assert get_tool_call_id() == "tool-012"


def test_metrics_registry_tracking():
    metrics = MetricsRegistry()

    # Record tasks
    metrics.record_task_started()
    metrics.record_task_started()
    metrics.record_task_completed(duration_seconds=10.0, iterations=3)
    metrics.record_task_failed(duration_seconds=20.0, iterations=5)

    assert metrics.tasks_started == 2
    assert metrics.tasks_completed == 1
    assert metrics.tasks_failed == 1
    assert metrics.average_execution_time == 15.0  # (10 + 20) / 2
    assert metrics.average_iterations == 4.0      # (3 + 5) / 2

    # Record tool calls
    metrics.record_tool_call("read_file", success=True)
    metrics.record_tool_call("run_tests", success=False)
    metrics.record_test_failure()
    metrics.record_retry()

    assert metrics.total_tool_calls_count == 2
    assert metrics.test_failures == 1
    assert metrics.retry_count == 1

    # Record model call & tokens
    cost = metrics.record_model_call(
        provider="anthropic",
        model_name="claude-3-5-sonnet-20241022",
        latency_seconds=2.5,
        prompt_tokens=100_000,      # 100k * $3/1M = $0.30
        completion_tokens=20_000,   # 20k * $15/1M = $0.30
    )
    assert round(cost, 2) == 0.60
    assert metrics.total_tokens == 120_000

    # Record sandbox failure
    metrics.record_sandbox_failure("container_error")
    assert metrics.sandbox_failures["container_error"] == 1

    # Check dashboard summary
    summary = metrics.get_dashboard_summary()
    assert summary["tasks"]["started"] == 2
    assert summary["ai_telemetry"]["total_tokens"] == 120_000
    assert summary["infrastructure"]["total_sandbox_failures"] == 1

    # Check Prometheus format
    prom = metrics.get_prometheus_exposition()
    assert "tasks_started_total 2" in prom
    assert "estimated_ai_cost_usd" in prom


def test_background_job_monitor():
    monitor = BackgroundJobMonitor()
    job = monitor.register_job("job-1", "Vite Dev Server", command="npm run dev")
    assert job.status == "running"

    monitor.update_job_progress("job-1", "Vite v5.4.21 ready")
    active = monitor.get_active_jobs()
    assert len(active) == 1
    assert active[0].last_log_snippet == "Vite v5.4.21 ready"

    monitor.complete_job("job-1", exit_code=0, last_log_snippet="Process exited cleanly")
    summary = monitor.get_job_summary()
    assert summary["completed"] == 1
