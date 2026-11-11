from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, DateTime, Float,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    brand_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))


class Product(Base):
    __tablename__ = "product"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    product_id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brand.brand_id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    external_id: Mapped[str | None] = mapped_column(String(100))
    is_competitor: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Review(Base):
    __tablename__ = "review"
    __table_args__ = (
        UniqueConstraint("workspace_id", "content_hash"),
        CheckConstraint("rating_norm IS NULL OR (rating_norm >= 1 AND rating_norm <= 5)", name="rating_range"),
        CheckConstraint("spam_score >= 0 AND spam_score <= 1", name="spam_range"),
        Index("ix_review_ws_product_date", "workspace_id", "product_id", "review_date"),
        Index("ix_review_extra_gin", "extra", postgresql_using="gin"),
        Index("ix_review_tsv_gin", "tsv", postgresql_using="gin"),
        Index("ix_review_batch", "batch_id"),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.workspace_id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id", ondelete="CASCADE"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batch.batch_id", ondelete="CASCADE"))
    text_clean: Mapped[str] = mapped_column(Text)
    rating_raw: Mapped[str | None] = mapped_column(String(50))
    rating_norm: Mapped[float | None] = mapped_column(Float)
    review_date: Mapped[date | None] = mapped_column(Date)
    language: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64))
    spam_score: Mapped[float] = mapped_column(Float, server_default="0")
    dup_count: Mapped[int] = mapped_column(Integer, server_default="1")
    extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text_clean, ''))", persisted=True),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
