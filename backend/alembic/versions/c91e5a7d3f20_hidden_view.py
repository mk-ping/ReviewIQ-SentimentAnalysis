"""hidden dissatisfaction view

Revision ID: c91e5a7d3f20
Revises: 422d96601711

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c91e5a7d3f20'
down_revision: Union[str, Sequence[str], None] = '422d96601711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cutoffs mirror app/core/thresholds.py: SPAM_MAX 0.6, NEG_MENTION -0.25,
    # ASPECT_MIN_CONF 0.6, HIDDEN_MIN_STARS 4. If they change, add a new migration.
    op.execute("""
        CREATE MATERIALIZED VIEW mv_hidden_dissatisfaction AS
        SELECT r.workspace_id, r.product_id, ra.aspect_id,
               count(*) AS negative_n,
               count(*) FILTER (WHERE r.rating_norm >= 4) AS hidden_n,
               (count(*) FILTER (WHERE r.rating_norm >= 4))::float / count(*) AS blind_spot_share
        FROM review_aspect ra
        JOIN review r ON r.review_id = ra.review_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.spam_score <= 0.6
          AND r.rating_norm IS NOT NULL
          AND ra.sentiment <= -0.25
          AND ra.confidence >= 0.6
          AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> ''
          AND NOT (
                coalesce(s.mismatch_type, '') = 'overrated'
                AND NOT EXISTS (SELECT 1 FROM review_aspect p WHERE p.review_id = r.review_id AND p.sentiment >= -0.25)
              )
        GROUP BY r.workspace_id, r.product_id, ra.aspect_id
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_hidden ON mv_hidden_dissatisfaction (workspace_id, product_id, aspect_id)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_hidden_dissatisfaction")
