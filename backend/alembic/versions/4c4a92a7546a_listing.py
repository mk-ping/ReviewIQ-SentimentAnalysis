"""listing vs reality

Revision ID: 4c4a92a7546a
Revises: f5b2d8e41a7c

"""
from typing import Sequence, Union

from alembic import op

revision: str = '4c4a92a7546a'
down_revision: Union[str, Sequence[str], None] = 'f5b2d8e41a7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE listing (
            listing_id serial PRIMARY KEY,
            workspace_id integer NOT NULL REFERENCES workspace (workspace_id) ON DELETE CASCADE,
            product_id integer NOT NULL REFERENCES product (product_id) ON DELETE CASCADE,
            source_text text NOT NULL,
            uploaded_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX ix_listing_product ON listing (product_id, uploaded_at)")
    op.execute("""
        CREATE TABLE claim (
            claim_id serial PRIMARY KEY,
            listing_id integer NOT NULL REFERENCES listing (listing_id) ON DELETE CASCADE,
            text text NOT NULL,
            quote text NOT NULL,
            aspect_id integer REFERENCES aspect (aspect_id) ON DELETE SET NULL
        )""")
    op.execute("CREATE INDEX ix_claim_listing ON claim (listing_id)")
    op.execute("""
        CREATE TABLE claim_evidence (
            claim_id integer NOT NULL REFERENCES claim (claim_id) ON DELETE CASCADE,
            review_id bigint NOT NULL REFERENCES review (review_id) ON DELETE CASCADE,
            sentence text NOT NULL,
            stance varchar(12) NOT NULL,
            score double precision NOT NULL,
            PRIMARY KEY (claim_id, review_id),
            CONSTRAINT ck_claim_evidence_stance_valid CHECK (stance IN ('supports','contradicts','unrelated'))
        )""")
    op.execute("""
        CREATE TABLE claim_verdict (
            claim_id integer PRIMARY KEY REFERENCES claim (claim_id) ON DELETE CASCADE,
            supports integer NOT NULL,
            contradicts integer NOT NULL,
            verdict varchar(24) NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_claim_verdict_valid CHECK (verdict IN ('confirmed','contradicted','mixed','not_enough_evidence'))
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_verdict")
    op.execute("DROP TABLE IF EXISTS claim_evidence")
    op.execute("DROP TABLE IF EXISTS claim")
    op.execute("DROP TABLE IF EXISTS listing")
