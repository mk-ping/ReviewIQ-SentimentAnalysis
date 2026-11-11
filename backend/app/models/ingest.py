from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UploadBatch(Base):
    __tablename__ = "upload_batch"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','mapping_needed','ingesting','scoring','done','failed')",
            name="status_valid",
        ),
        Index("ix_upload_batch_workspace_hash", "workspace_id", "file_hash"),
    )

    batch_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    file_name: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    format: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default="uploaded")
    rows_total: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_ok: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_repaired: Mapped[int] = mapped_column(Integer, server_default="0")
    rows_rejected: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ColumnMapping(Base):
    __tablename__ = "column_mapping"
    __table_args__ = (
        UniqueConstraint("batch_id", "role"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    mapping_id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(30))
    column_name: Mapped[str] = mapped_column(String(500))
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    confirmed: Mapped[bool] = mapped_column(Boolean, server_default="false")


class ColumnProfile(Base):
    __tablename__ = "column_profile"
    __table_args__ = (UniqueConstraint("batch_id", "column_name"),)

    profile_id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    column_name: Mapped[str] = mapped_column(String(500))
    dtype: Mapped[str | None] = mapped_column(String(30))
    null_rate: Mapped[float | None] = mapped_column(Float)
    unique_ratio: Mapped[float | None] = mapped_column(Float)
    avg_len: Mapped[float | None] = mapped_column(Float)


class SourceTemplate(Base):
    __tablename__ = "source_template"
    __table_args__ = (UniqueConstraint("workspace_id", "fingerprint"),)

    template_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawReviewStaging(Base):
    __tablename__ = "raw_review_staging"
    __table_args__ = (UniqueConstraint("batch_id", "row_no"),)

    staging_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    row_no: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSONB)


class IngestIssue(Base):
    __tablename__ = "ingest_issue"
    __table_args__ = (
        CheckConstraint("action IN ('repaired','quarantined')", name="action_valid"),
        Index("ix_ingest_issue_batch", "batch_id"),
    )

    issue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    row_no: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str | None] = mapped_column(String(100))
    problem: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(String(20))
    original_value: Mapped[str | None] = mapped_column(Text)
