from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db.base import Base

EMBED_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


class Vector(UserDefinedType):
    """pgvector column type. Reads and writes go through SQL text with CAST(... AS vector),
    so no extra Python package is needed."""
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dim})"


class ReviewEmbedding(Base):
    __tablename__ = "review_embedding"
    __table_args__ = (
        Index(
            "ix_review_embedding_hnsw", "embedding", postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(120))
    embedding = mapped_column(Vector(EMBED_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Filled by database triggers (see the vector_and_audit migration), never by application code."""
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity", "entity_id"), Index("ix_audit_log_at", "at"))

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_user.user_id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(10))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    detail = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
