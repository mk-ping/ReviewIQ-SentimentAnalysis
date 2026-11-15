"""review split

Revision ID: ac21c8e41654
Revises: 878ede29e931

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'ac21c8e41654'
down_revision: Union[str, Sequence[str], None] = '878ede29e931'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE review ADD COLUMN split varchar(10)")
    op.execute("ALTER TABLE review ADD CONSTRAINT ck_review_split_valid CHECK (split IS NULL OR split IN ('validation','test'))")
    op.execute("""
        UPDATE review SET split = CASE WHEN ('x' || substr(content_hash, 1, 8))::bit(32)::bigint % 3 = 0
                                       THEN 'validation' ELSE 'test' END""")


def downgrade() -> None:
    op.execute("ALTER TABLE review DROP CONSTRAINT IF EXISTS ck_review_split_valid")
    op.execute("ALTER TABLE review DROP COLUMN IF EXISTS split")
