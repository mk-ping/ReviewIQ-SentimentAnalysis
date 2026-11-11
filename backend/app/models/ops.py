from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScoringJob(Base):
    __tablename__ = "scoring_job"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status_valid"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        Index("ix_scoring_job_queue", "job_id", postgresql_where=text("status = 'queued'")),
        Index(
            "uq_scoring_job_active", "batch_id", "stage", unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )

    job_id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), server_default="queued")
    progress: Mapped[int] = mapped_column(Integer, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
