from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Issue(Base):
    __tablename__ = "issue"
    __table_args__ = (Index("ix_issue_workspace", "workspace_id"),)

    issue_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    aspect_id: Mapped[int] = mapped_column(ForeignKey("aspect.aspect_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list] = mapped_column(JSONB)
    n_reviews: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IssueReview(Base):
    __tablename__ = "issue_review"
    __table_args__ = (Index("ix_issue_review_review", "review_id"),)

    issue_id: Mapped[int] = mapped_column(ForeignKey("issue.issue_id", ondelete="CASCADE"), primary_key=True)
    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True)
    evidence_span: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float] = mapped_column(Float)


class IssuePriority(Base):
    __tablename__ = "issue_priority"

    issue_id: Mapped[int] = mapped_column(ForeignKey("issue.issue_id", ondelete="CASCADE"), primary_key=True)
    frequency: Mapped[float] = mapped_column(Float)
    severity: Mapped[float] = mapped_column(Float)
    growth: Mapped[float] = mapped_column(Float)
    rating_gain: Mapped[float] = mapped_column(Float)
    hidden_share: Mapped[float | None] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
