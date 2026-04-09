from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings
from backend.app.models.base import Base
from backend.app.models import persistence as _persistence_models  # noqa: F401


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _add_missing_json_column(table_name: str, column_name: str) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in columns:
        return

    dialect = engine.dialect.name
    if dialect == "postgresql":
        ddl = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} JSONB NOT NULL DEFAULT '{{}}'::jsonb"
        )
    else:
        ddl = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} JSON NOT NULL DEFAULT '{{}}'"
        )

    with engine.begin() as connection:
        connection.execute(text(ddl))


def _apply_runtime_schema_upgrades() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "migration_requests" in tables:
        _add_missing_json_column("migration_requests", "metadata_collection_payload")
        _add_missing_json_column("migration_requests", "source_metadata_payload")
        _add_missing_json_column("migration_requests", "target_metadata_payload")
        _add_missing_json_column("migration_requests", "migration_validation_payload")
    if "recommendation_results" in tables:
        _add_missing_json_column("recommendation_results", "request_payload")
    if "recommendation_rule_audit" in tables:
        _add_missing_json_column("recommendation_rule_audit", "request_payload")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _apply_runtime_schema_upgrades()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
