"""Celery worker package.

`app.worker.celery_app:celery_app` is the entrypoint the worker container runs:

    celery -A app.worker.celery_app:celery_app worker
    celery -A app.worker.celery_app:celery_app beat
"""

from app.worker.celery_app import celery_app

__all__ = ["celery_app"]
