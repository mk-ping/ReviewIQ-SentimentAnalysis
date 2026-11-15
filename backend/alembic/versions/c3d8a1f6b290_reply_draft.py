
"""reply_draft: saved reply text and status per review

Revision ID: c3d8a1f6b290
Revises: b7e41c9a3d58
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d8a1f6b290"
down_revision: Union[str, Sequence[str], None] = "b7e41c9a3d58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE reply_draft (
            review_id bigint PRIMARY KEY REFERENCES review (review_id) ON DELETE CASCADE,
            body text NOT NULL,
            status varchar(10) NOT NULL DEFAULT 'draft',
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_reply_draft_status CHECK (status IN ('draft','sent','skipped'))
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reply_draft")
