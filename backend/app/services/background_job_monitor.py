import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class BackgroundJobStatus(BaseModel):
    job_id: str
    name: str
    job_type: str = "daemon_process"  # daemon_process, agent_run, background_worker
    status: str = "running"  # running, completed, failed, terminated
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    command: str = ""
    exit_code: Optional[int] = None
    last_log_snippet: str = ""


class BackgroundJobMonitor:
    """
    Background Job Monitoring Service tracking long-running background tasks,
    daemon processes, and worker pipelines in real time.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, BackgroundJobStatus] = {}

    def register_job(self, job_id: str, name: str, job_type: str = "daemon_process", command: str = "") -> BackgroundJobStatus:
        with self._lock:
            status = BackgroundJobStatus(
                job_id=job_id,
                name=name,
                job_type=job_type,
                status="running",
                command=command,
                start_time=datetime.now(timezone.utc),
            )
            self._jobs[job_id] = status
            return status

    def update_job_progress(self, job_id: str, last_log_snippet: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.last_log_snippet = last_log_snippet[:400]
                job.duration_seconds = round((datetime.now(timezone.utc) - job.start_time).total_seconds(), 1)

    def complete_job(self, job_id: str, exit_code: int = 0, last_log_snippet: str = "") -> None:
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job.status = "completed" if exit_code == 0 else "failed"
                job.exit_code = exit_code
                job.end_time = datetime.now(timezone.utc)
                job.duration_seconds = round((job.end_time - job.start_time).total_seconds(), 1)
                if last_log_snippet:
                    job.last_log_snippet = last_log_snippet[:400]

    def get_active_jobs(self) -> List[BackgroundJobStatus]:
        with self._lock:
            now = datetime.now(timezone.utc)
            active = []
            for j in self._jobs.values():
                if j.status == "running":
                    j.duration_seconds = round((now - j.start_time).total_seconds(), 1)
                active.append(j)
            return active

    def get_job_summary(self) -> Dict[str, Any]:
        jobs = self.get_active_jobs()
        running_count = sum(1 for j in jobs if j.status == "running")
        completed_count = sum(1 for j in jobs if j.status == "completed")
        failed_count = sum(1 for j in jobs if j.status == "failed")
        return {
            "total_jobs_tracked": len(jobs),
            "running": running_count,
            "completed": completed_count,
            "failed": failed_count,
            "jobs": [j.model_dump() for j in jobs],
        }


# Global Singleton BackgroundJobMonitor Instance
background_job_monitor = BackgroundJobMonitor()
