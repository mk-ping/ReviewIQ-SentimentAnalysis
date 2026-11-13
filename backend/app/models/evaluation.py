from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoldLabel(Base):
    """A person's label for one review. source 'gold' feeds evaluation; 'manager' corrections feed the stacker later."""
    __tablename__ = "gold_label"
    __table_args__ = (
        CheckConstraint("label IN ('neg','neu','pos')", name="label_valid"),
        CheckConstraint("source IN ('gold','manager')", name="source_valid"),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True)
    label: Mapped[str] = mapped_column(String(3))
    mismatch_label: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(10), server_default="gold")
    labelled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
