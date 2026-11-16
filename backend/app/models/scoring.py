from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MLModel(Base):
    __tablename__ = "model"
    __table_args__ = (UniqueConstraint("name", "version"),)

    model_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(30))


class ModelWeight(Base):
    """Ensemble weight of one model inside one route group: its macro F1 on the validation reviews."""
    __tablename__ = "model_weight"
    __table_args__ = (
        CheckConstraint("weight > 0", name="positive"),
        CheckConstraint("route_group IN ('english','european','multi')", name="group_valid"),
    )

    route_group: Mapped[str] = mapped_column(String(20), primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model.model_id", ondelete="CASCADE"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)
    n_val: Mapped[int] = mapped_column(Integer, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    __tablename__ = "prediction"
    __table_args__ = (
        CheckConstraint("p_neg >= 0 AND p_neu >= 0 AND p_pos >= 0", name="prob_nonneg"),
    )

    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[int] = mapped_column(ForeignKey("model.model_id"), primary_key=True)
    p_neg: Mapped[float] = mapped_column(Float)
    p_neu: Mapped[float] = mapped_column(Float)
    p_pos: Mapped[float] = mapped_column(Float)
    expected_stars: Mapped[float | None] = mapped_column(Float)


class ReviewScore(Base):
    __tablename__ = "review_score"
    __table_args__ = (
        CheckConstraint(
            "mismatch_type IS NULL OR mismatch_type IN ('underrated','overrated','sarcasm')",
            name="mismatch_valid",
        ),
        Index(
            "ix_review_score_mismatch",
            "review_id",
            postgresql_where=text("mismatch_type IS NOT NULL"),
        ),
    )

    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True
    )
    text_label: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float | None] = mapped_column(Float)
    fused_stars: Mapped[float | None] = mapped_column(Float)
    pred_stars: Mapped[float | None] = mapped_column(Float)
    star_gap: Mapped[float | None] = mapped_column(Float)
    mismatch_type: Mapped[str | None] = mapped_column(String(20))
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
