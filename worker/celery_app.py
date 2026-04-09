from backend.app.workers.celery_app import celery_app, initialize_worker_runtime, ping


initialize_worker_runtime()


__all__ = ["celery_app", "ping"]
