from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


APP_JSON = JSON().with_variant(JSONB, "postgresql")


class AppUserModel(Base):
    __tablename__ = "app_users"

    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class MigrationRequestModel(Base):
    __tablename__ = "migration_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)
    source_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    target_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    scope_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    business_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    connectivity_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    features_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    metadata_collection_payload: Mapped[dict] = mapped_column(
        APP_JSON,
        nullable=False,
        default=dict,
    )
    source_metadata_payload: Mapped[dict] = mapped_column(
        APP_JSON,
        nullable=False,
        default=dict,
    )
    target_metadata_payload: Mapped[dict] = mapped_column(
        APP_JSON,
        nullable=False,
        default=dict,
    )
    migration_validation_payload: Mapped[dict] = mapped_column(
        APP_JSON,
        nullable=False,
        default=dict,
    )

    recommendations: Mapped[list["RecommendationResultModel"]] = relationship(
        back_populates="migration_request",
        cascade="all, delete-orphan",
    )


class RecommendationResultModel(Base):
    __tablename__ = "recommendation_results"

    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    request_id: Mapped[str] = mapped_column(
        ForeignKey("migration_requests.request_id"),
        nullable=False,
        index=True,
    )
    recommended_approach: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    response_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    migration_request: Mapped[MigrationRequestModel] = relationship(
        back_populates="recommendations",
    )
    audits: Mapped[list["RecommendationAuditModel"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )


class RecommendationAuditModel(Base):
    __tablename__ = "recommendation_rule_audit"

    audit_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_results.recommendation_id"),
        nullable=False,
        index=True,
    )
    recommended_approach: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    evaluation_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation: Mapped[RecommendationResultModel] = relationship(
        back_populates="audits",
    )


class DataPumpJobModel(Base):
    __tablename__ = "datapump_jobs"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    job_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_connection_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    target_connection_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False, default=dict)
    options_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False)
    result_payload: Mapped[dict] = mapped_column(APP_JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
