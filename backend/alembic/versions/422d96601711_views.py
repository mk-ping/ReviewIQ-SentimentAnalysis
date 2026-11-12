"""views

Revision ID: 422d96601711
Revises: bea24e4f3e79

"""
from typing import Sequence, Union

from alembic import op

revision: str = '422d96601711'
down_revision: Union[str, Sequence[str], None] = 'bea24e4f3e79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # spam cutoff 0.6 matches app/core/thresholds.py SPAM_MAX
    op.execute("""
        CREATE MATERIALIZED VIEW mv_product_daily AS
        SELECT r.workspace_id, r.product_id, r.review_date AS day,
               count(*) AS n,
               count(r.rating_norm) AS n_rated,
               coalesce(sum(r.rating_norm), 0) AS sum_rating,
               count(s.review_id) AS n_scored,
               count(s.fused_stars) AS n_fused,
               coalesce(sum(s.fused_stars), 0) AS sum_fused,
               count(*) FILTER (WHERE s.text_label = 'pos') AS n_pos,
               count(*) FILTER (WHERE s.text_label = 'neg') AS n_neg,
               count(*) FILTER (WHERE s.mismatch_type IS NOT NULL) AS n_mismatch
        FROM review r
        LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.spam_score <= 0.6 AND r.review_date IS NOT NULL
        GROUP BY r.workspace_id, r.product_id, r.review_date
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_product_daily ON mv_product_daily (workspace_id, product_id, day)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_product_daily")
