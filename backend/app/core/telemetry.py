from __future__ import annotations

from typing import Any
from uuid import uuid4

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun
from fastapi import Request, Response
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, use_span
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.config import settings


_TELEMETRY_INITIALIZED = False
_CELERY_SIGNALS_BOUND = False
_TASK_SPANS: dict[str, tuple[Span, Any]] = {}


def setup_telemetry(service_name: str) -> None:
    global _TELEMETRY_INITIALIZED

    if _TELEMETRY_INITIALIZED or not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": settings.otel_service_namespace,
            "service.version": settings.app_version,
            "deployment.environment": settings.otel_environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _TELEMETRY_INITIALIZED = True


def shutdown_telemetry() -> None:
    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()


def get_tracer(name: str):
    return trace.get_tracer(name)


class TelemetryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        tracer = get_tracer("backend.api")
        route_template = request.scope.get("route")
        route_path = getattr(route_template, "path", request.url.path)

        with tracer.start_as_current_span(f"{request.method} {route_path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", route_path)
            span.set_attribute("http.target", str(request.url.path))
            span.set_attribute("request.id", request_id)

            response = await call_next(request)

            span.set_attribute("http.status_code", response.status_code)
            response.headers["X-Request-ID"] = request_id
            return response


def bind_celery_telemetry(celery_app: Celery) -> None:
    global _CELERY_SIGNALS_BOUND

    if _CELERY_SIGNALS_BOUND or not settings.otel_enabled:
        return

    tracer = get_tracer("worker.celery")

    @task_prerun.connect(weak=False)
    def _task_prerun(
        task_id: str | None = None,
        task: Any | None = None,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        if task is None or task_id is None or getattr(task, "app", None) is not celery_app:
            return

        span = tracer.start_span(f"celery {task.name}")
        span.set_attribute("celery.task_name", task.name)
        span.set_attribute("celery.task_id", task_id)
        if kwargs and "payload" in kwargs and isinstance(kwargs["payload"], dict):
            request_id = kwargs["payload"].get("request_id")
            if request_id:
                span.set_attribute("request.id", str(request_id))
        span_context = use_span(span, end_on_exit=True)
        span_context.__enter__()
        _TASK_SPANS[task_id] = (span, span_context)

    @task_postrun.connect(weak=False)
    def _task_postrun(
        task_id: str | None = None,
        task: Any | None = None,
        state: str | None = None,
        **_: Any,
    ) -> None:
        if task is None or task_id is None or getattr(task, "app", None) is not celery_app:
            return

        span_state = _TASK_SPANS.pop(task_id, None)
        if span_state is None:
            return

        span, span_context = span_state
        span.set_attribute("celery.state", state or "UNKNOWN")
        span_context.__exit__(None, None, None)

    @task_failure.connect(weak=False)
    def _task_failure(
        task_id: str | None = None,
        task: Any | None = None,
        exception: BaseException | None = None,
        **_: Any,
    ) -> None:
        if task is None or task_id is None or getattr(task, "app", None) is not celery_app:
            return

        span_state = _TASK_SPANS.get(task_id)
        if span_state is None:
            return

        span, _ = span_state
        if exception is not None:
            span.record_exception(exception)
        span.set_attribute("celery.failed", True)

    _CELERY_SIGNALS_BOUND = True
