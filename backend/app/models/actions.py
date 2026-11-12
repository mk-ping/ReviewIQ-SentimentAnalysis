from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Action(Base):
    __tablename__ = "action"
    __table_args__ = (
        CheckConstraint("status IN ('todo','in_progress','done','dropped')", name="status_valid"),
        Index("ix_action_workspace", "workspace_id"),
    )

    action_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    aspect_id: Mapped[int] = mapped_column(ForeignKey("aspect.aspect_id", ondelete="CASCADE"))
    issue_name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list] = mapped_column(JSONB)
    suggested_action: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(100))
    effort: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), server_default="todo")
    done_at: Mapped[date | None] = mapped_column(Date)
    impact_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
