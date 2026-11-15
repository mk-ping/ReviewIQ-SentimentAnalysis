"""issue flags

Revision ID: b7e41c9a3d58
Revises: 9d3f5b7a1c20

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b7e41c9a3d58'
down_revision: Union[str, Sequence[str], None] = '9d3f5b7a1c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE issue ADD COLUMN few_sentences boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE issue_review ADD COLUMN is_rare boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE issue_review DROP COLUMN is_rare")
    op.execute("ALTER TABLE issue DROP COLUMN few_sentences")
