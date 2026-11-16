"""app_user password and name

Revision ID: d4a96f2b7e31
Revises: 6d01c14bbe0c

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4a96f2b7e31'
down_revision: Union[str, Sequence[str], None] = '6d01c14bbe0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("app_user", sa.Column("full_name", sa.String(200), nullable=True))
    # emails are stored lower-case, so one address cannot sign up twice with different capitals
    op.execute("UPDATE app_user SET email = lower(email)")


def downgrade() -> None:
    op.drop_column("app_user", "full_name")
    op.drop_column("app_user", "password_hash")
