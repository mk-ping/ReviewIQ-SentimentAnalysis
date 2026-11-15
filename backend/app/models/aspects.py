from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
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


class ReviewAspectRun(Base):
    """One row per review that has been through aspect extraction, even if nothing was found.
    This is the cache: a review with a row here is never sent to the LLM again."""
    __tablename__ = "review_aspect_run"
    __table_args__ = (CheckConstraint("method IN ('llm','keyword')", name="method_valid"),)

    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True
    )
    method: Mapped[str] = mapped_column(String(10))
    n_found: Mapped[int] = mapped_column(Integer, server_default="0")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SentenceAspect(Base):
    """One row per (sentence, aspect). Sentences with no aspect are stored as 'general' so coverage can be measured."""
    __tablename__ = "sentence_aspect"
    __table_args__ = (
        CheckConstraint("method IN ('sbert','keyword','general')", name="method_valid"),
        CheckConstraint("sent_score IS NULL OR (sent_score >= -1 AND sent_score <= 1)", name="score_range"),
        UniqueConstraint("review_id", "sent_idx", "aspect", name="uq_sentence_aspect_sentence"),
    )

    sent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"))
    sent_idx: Mapped[int] = mapped_column(Integer)
    sentence: Mapped[str] = mapped_column(Text)
    aspect: Mapped[str] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(10))
    sim: Mapped[float | None] = mapped_column(Float)
    sent_score: Mapped[float | None] = mapped_column(Float)


class SentenceAspectRun(Base):
    __tablename__ = "sentence_aspect_run"

    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True)
    n_sentences: Mapped[int] = mapped_column(Integer, server_default="0")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
