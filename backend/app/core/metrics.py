import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Standard LLM Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "claude-3-5-sonnet-20241022": {"prompt_per_m": 3.00, "completion_per_m": 15.00},
    "claude-3-haiku": {"prompt_per_m": 0.25, "completion_per_m": 1.25},
    "gpt-4o": {"prompt_per_m": 2.50, "completion_per_m": 10.00},
    "gpt-4o-mini": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "default": {"prompt_per_m": 2.00, "completion_per_m": 10.00},
}


class MetricsRegistry:
    """
    Production Metrics Engine tracking real-time telemetry, model costs,
    task execution averages, tool distribution, and sandbox failures.
    Thread-safe and Prometheus / JSON dashboard compatible.
    """

    def __init__(self):
        # RLock, not Lock: get_dashboard_summary() holds the lock and then reads
        # the average_* / total_* properties, which acquire it again. With a
        # plain Lock that is a self-deadlock that hangs the calling thread (and
        # therefore /api/v1/metrics) forever.
        self._lock = threading.RLock()

        # Task Metrics
        self.tasks_started: int = 0
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.execution_durations: List[float] = []
        self.task_iterations: List[int] = []

        # Tool Call Metrics
        self.tool_calls: Dict[str, Dict[str, int]] = {}
        self.test_failures: int = 0
        self.retry_count: int = 0

        # Model Telemetry
        self.model_latencies: Dict[str, List[float]] = {}
        self.prompt_tokens_total: int = 0
        self.completion_tokens_total: int = 0
        self.total_tokens: int = 0
        self.estimated_ai_cost_usd: float = 0.0

        # System & Sandbox Telemetry
        self.sandbox_failures: Dict[str, int] = {}
        self.start_time: datetime = datetime.now(timezone.utc)

    def record_task_started(self) -> None:
        with self._lock:
            self.tasks_started += 1

    def record_task_completed(self, duration_seconds: float, iterations: int) -> None:
        with self._lock:
            self.tasks_completed += 1
            self.execution_durations.append(duration_seconds)
            self.task_iterations.append(iterations)

    def record_task_failed(self, duration_seconds: float, iterations: int) -> None:
        with self._lock:
            self.tasks_failed += 1
            self.execution_durations.append(duration_seconds)
            self.task_iterations.append(iterations)

    def record_tool_call(self, tool_name: str, success: bool, duration_ms: float = 0) -> None:
        with self._lock:
            if tool_name not in self.tool_calls:
                self.tool_calls[tool_name] = {"total": 0, "success": 0, "failed": 0}
            self.tool_calls[tool_name]["total"] += 1
            if success:
                self.tool_calls[tool_name]["success"] += 1
            else:
                self.tool_calls[tool_name]["failed"] += 1

    def record_test_failure(self) -> None:
        with self._lock:
            self.test_failures += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retry_count += 1

    def record_model_call(
        self,
        provider: str,
        model_name: str,
        latency_seconds: float,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        key = f"{provider}:{model_name}"
        with self._lock:
            if key not in self.model_latencies:
                self.model_latencies[key] = []
            self.model_latencies[key].append(latency_seconds)

            self.prompt_tokens_total += prompt_tokens
            self.completion_tokens_total += completion_tokens
            self.total_tokens += (prompt_tokens + completion_tokens)

            # Estimate USD Cost
            pricing = MODEL_PRICING.get(model_name, MODEL_PRICING.get(provider, MODEL_PRICING["default"]))
            cost = (
                (prompt_tokens / 1_000_000) * pricing["prompt_per_m"] +
                (completion_tokens / 1_000_000) * pricing["completion_per_m"]
            )
            self.estimated_ai_cost_usd += cost
            return cost

    def record_sandbox_failure(self, reason: str = "container_error") -> None:
        with self._lock:
            self.sandbox_failures[reason] = self.sandbox_failures.get(reason, 0) + 1

    @property
    def average_execution_time(self) -> float:
        with self._lock:
            if not self.execution_durations:
                return 0.0
            return round(sum(self.execution_durations) / len(self.execution_durations), 2)

    @property
    def average_iterations(self) -> float:
        with self._lock:
            if not self.task_iterations:
                return 0.0
            return round(sum(self.task_iterations) / len(self.task_iterations), 2)

    @property
    def total_tool_calls_count(self) -> int:
        with self._lock:
            return sum(t["total"] for t in self.tool_calls.values())

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Returns JSON production dashboard dataset aggregating all observability metrics."""
        with self._lock:
            avg_exec = self.average_execution_time
            avg_iter = self.average_iterations

            # Average model latencies per model
            avg_model_latencies = {}
            for key, lats in self.model_latencies.items():
                avg_model_latencies[key] = round(sum(lats) / len(lats), 3) if lats else 0.0

            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            return {
                "system_uptime_seconds": round(uptime_seconds, 1),
                "tasks": {
                    "started": self.tasks_started,
                    "completed": self.tasks_completed,
                    "failed": self.tasks_failed,
                    "average_execution_time_seconds": avg_exec,
                    "average_iterations": avg_iter,
                },
                "tools": {
                    "total_calls": self.total_tool_calls_count,
                    "breakdown": self.tool_calls,
                    "test_failures": self.test_failures,
                    "retry_count": self.retry_count,
                },
                "ai_telemetry": {
                    "prompt_tokens": self.prompt_tokens_total,
                    "completion_tokens": self.completion_tokens_total,
                    "total_tokens": self.total_tokens,
                    "estimated_cost_usd": round(self.estimated_ai_cost_usd, 6),
                    "model_latencies_seconds": avg_model_latencies,
                },
                "infrastructure": {
                    "sandbox_failures": self.sandbox_failures,
                    "total_sandbox_failures": sum(self.sandbox_failures.values()),
                }
            }

    def get_prometheus_exposition(self) -> str:
        """Returns standard Prometheus text exposition format string."""
        summary = self.get_dashboard_summary()
        lines = [
            "# HELP tasks_started_total Total number of tasks started",
            "# TYPE tasks_started_total counter",
            f"tasks_started_total {summary['tasks']['started']}",
            "# HELP tasks_completed_total Total number of tasks completed",
            "# TYPE tasks_completed_total counter",
            f"tasks_completed_total {summary['tasks']['completed']}",
            "# HELP tasks_failed_total Total number of tasks failed",
            "# TYPE tasks_failed_total counter",
            f"tasks_failed_total {summary['tasks']['failed']}",
            "# HELP task_execution_duration_seconds_avg Average task execution time",
            "# TYPE task_execution_duration_seconds_avg gauge",
            f"task_execution_duration_seconds_avg {summary['tasks']['average_execution_time_seconds']}",
            "# HELP task_iterations_avg Average iterations per task",
            "# TYPE task_iterations_avg gauge",
            f"task_iterations_avg {summary['tasks']['average_iterations']}",
            "# HELP tool_calls_total Total tool calls made",
            "# TYPE tool_calls_total counter",
            f"tool_calls_total {summary['tools']['total_calls']}",
            "# HELP test_failures_total Total test suite failures",
            "# TYPE test_failures_total counter",
            f"test_failures_total {summary['tools']['test_failures']}",
            "# HELP retry_count_total Total retry operations executed",
            "# TYPE retry_count_total counter",
            f"retry_count_total {summary['tools']['retry_count']}",
            "# HELP ai_tokens_total Total LLM tokens used",
            "# TYPE ai_tokens_total counter",
            f"ai_tokens_total {summary['ai_telemetry']['total_tokens']}",
            "# HELP estimated_ai_cost_usd Total estimated AI cost in USD",
            "# TYPE estimated_ai_cost_usd counter",
            f"estimated_ai_cost_usd {summary['ai_telemetry']['estimated_cost_usd']}",
            "# HELP sandbox_failures_total Total sandbox container failures",
            "# TYPE sandbox_failures_total counter",
            f"sandbox_failures_total {summary['infrastructure']['total_sandbox_failures']}",
        ]
        return "\n".join(lines) + "\n"


# Global Metrics Registry Singleton Instance
metrics_registry = MetricsRegistry()
