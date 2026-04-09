from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_POSTGRES_URL = (
    "postgresql+psycopg://app_user:app_password@postgres:5432/oracle_migration_app"
)
DEFAULT_SQLITE_URL = "sqlite+pysqlite:///./oracle_migration_app.db"
DEFAULT_REDIS_BROKER_URL = "redis://redis:6379/0"
DEFAULT_REDIS_RESULT_BACKEND = "redis://redis:6379/1"
DEFAULT_ORACLE_CALL_TIMEOUT_MS = 15000
DEFAULT_ORACLE_CLIENT_LIB_DIR = "/opt/oracle-tools"
DEFAULT_DATAPUMP_CALL_TIMEOUT_SECONDS = 43200
DEFAULT_DATAPUMP_EXECUTION_BACKEND = "auto"
DEFAULT_APP_NAME = "oracle-migration-app"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_APP_ENV = "development"


def _get_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _default_database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if configured_url:
        return configured_url

    if os.getenv("APP_ENV", "").lower() == "development":
        return DEFAULT_POSTGRES_URL

    return DEFAULT_SQLITE_URL


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", DEFAULT_APP_NAME)
    app_version: str = os.getenv("APP_VERSION", DEFAULT_APP_VERSION)
    app_env: str = os.getenv("APP_ENV", DEFAULT_APP_ENV)
    database_url: str = _default_database_url()
    redis_broker_url: str = os.getenv("REDIS_BROKER_URL", DEFAULT_REDIS_BROKER_URL)
    redis_result_backend: str = os.getenv(
        "REDIS_RESULT_BACKEND",
        DEFAULT_REDIS_RESULT_BACKEND,
    )
    task_always_eager: bool = _get_bool("TASK_ALWAYS_EAGER", False)
    oracle_call_timeout_ms: int = int(
        os.getenv("ORACLE_CALL_TIMEOUT_MS", str(DEFAULT_ORACLE_CALL_TIMEOUT_MS))
    )
    oracle_client_lib_dir: str = os.getenv(
        "ORACLE_CLIENT_LIB_DIR",
        DEFAULT_ORACLE_CLIENT_LIB_DIR,
    )
    datapump_enabled: bool = _get_bool("DATAPUMP_ENABLED", False)
    datapump_execution_backend: str = os.getenv(
        "DATAPUMP_EXECUTION_BACKEND",
        DEFAULT_DATAPUMP_EXECUTION_BACKEND,
    ).strip().lower()
    datapump_expdp_path: str = os.getenv("DATAPUMP_EXPDP_PATH", "expdp")
    datapump_impdp_path: str = os.getenv("DATAPUMP_IMPDP_PATH", "impdp")
    datapump_work_dir: str = os.getenv("DATAPUMP_WORK_DIR", "/tmp/oracle-migration/datapump")
    datapump_call_timeout_seconds: int = int(
        os.getenv(
            "DATAPUMP_CALL_TIMEOUT_SECONDS",
            str(DEFAULT_DATAPUMP_CALL_TIMEOUT_SECONDS),
        )
    )
    otel_enabled: bool = _get_bool("OTEL_ENABLED", True)
    otel_exporter: str = os.getenv("OTEL_EXPORTER", "console").strip().lower()
    otel_service_namespace: str = os.getenv(
        "OTEL_SERVICE_NAMESPACE",
        "oracle-migration",
    )
    otel_environment: str = os.getenv("OTEL_ENVIRONMENT", os.getenv("APP_ENV", DEFAULT_APP_ENV))
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    frontend_public_api_base_url: str = os.getenv("FRONTEND_PUBLIC_API_BASE_URL", "/api/v1")


settings = Settings()
