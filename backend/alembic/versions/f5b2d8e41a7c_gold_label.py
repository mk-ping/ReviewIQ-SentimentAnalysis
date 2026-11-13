"""gold_label

Revision ID: f5b2d8e41a7c
Revises: e3a7c10d5b42

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f5b2d8e41a7c'
down_revision: Union[str, Sequence[str], None] = 'e3a7c10d5b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gold_label (
            review_id bigint PRIMARY KEY REFERENCES review (review_id) ON DELETE CASCADE,
            label varchar(3) NOT NULL,
            mismatch_label boolean,
            source varchar(10) NOT NULL DEFAULT 'gold',
            labelled_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_gold_label_label_valid CHECK (label IN ('neg','neu','pos')),
            CONSTRAINT ck_gold_label_source_valid CHECK (source IN ('gold','manager'))
        )
    """)
    # label changes are recorded by the audit trigger function created in the previous migration
    op.execute("""
        CREATE TRIGGER trg_audit_gold_label AFTER INSERT OR UPDATE OR DELETE ON gold_label
        FOR EACH ROW EXECUTE FUNCTION audit_row('review_id')
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_gold_label ON gold_label")
    op.execute("DROP TABLE IF EXISTS gold_label")
