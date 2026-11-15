"""model_weight

Revision ID: 878ede29e931
Revises: 4c4a92a7546a

"""
from typing import Sequence, Union

from alembic import op

revision: str = '878ede29e931'
down_revision: Union[str, Sequence[str], None] = '4c4a92a7546a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE model_weight (
            route_group varchar(20) NOT NULL,
            model_id integer NOT NULL REFERENCES model (model_id) ON DELETE CASCADE,
            weight double precision NOT NULL,
            n_val integer NOT NULL DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (route_group, model_id),
            CONSTRAINT ck_model_weight_positive CHECK (weight > 0),
            CONSTRAINT ck_model_weight_group CHECK (route_group IN ('english','european','multi'))
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_weight")
