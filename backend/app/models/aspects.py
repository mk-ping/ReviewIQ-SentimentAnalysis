from sqlalchemy import (
    BigInteger, CheckConstraint, Float, ForeignKey, Index, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Aspect(Base):
    __tablename__ = "aspect"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    aspect_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("aspect.aspect_id", ondelete="SET NULL"))


class ReviewAspect(Base):
    __tablename__ = "review_aspect"
    __table_args__ = (
        CheckConstraint("sentiment >= -1 AND sentiment <= 1", name="sentiment_range"),
        CheckConstraint("method IN ('llm','sbert','keyword')", name="method_valid"),
        Index("ix_review_aspect_aspect_review", "aspect_id", "review_id"),
        Index("ix_review_aspect_review", "review_id"),
    )

    review_aspect_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"))
    aspect_id: Mapped[int] = mapped_column(ForeignKey("aspect.aspect_id", ondelete="CASCADE"))
    term: Mapped[str | None] = mapped_column(String(200))
    evidence_span: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(10))
