from __future__ import annotations

from celery import Celery

from backend.app.core.config import settings


celery_app = Celery(
    "oracle_migration_worker",
    broker=settings.redis_broker_url,
    backend=settings.redis_result_backend,
)

celery_app.conf.update(
    task_default_queue="migration",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.task_always_eager,
    task_store_eager_result=settings.task_always_eager,
    imports=(
        "backend.app.workers.recommendation_tasks",
        "backend.app.workers.metadata_tasks",
        "backend.app.workers.transfer_tasks",
    ),
)


@celery_app.task(name="worker.ping")
def ping() -> dict[str, str]:
    return {"status": "ok", "service": "worker"}


# Import task modules after Celery app creation so task registration is eager
# for both API-side enqueueing and worker startup.
from backend.app.workers import recommendation_tasks as _recommendation_tasks  # noqa: E402,F401
from backend.app.workers import metadata_tasks as _metadata_tasks  # noqa: E402,F401
from backend.app.workers import transfer_tasks as _transfer_tasks  # noqa: E402,F401


def initialize_worker_runtime() -> None:
    from backend.app.core.telemetry import bind_celery_telemetry, setup_telemetry

    setup_telemetry(f"{settings.app_name}-worker")
    bind_celery_telemetry(celery_app)
