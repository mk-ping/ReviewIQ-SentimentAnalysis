"""sentence_aspect

Revision ID: 9d3f5b7a1c20
Revises: ac21c8e41654

"""
from typing import Sequence, Union

from alembic import op

revision: str = '9d3f5b7a1c20'
down_revision: Union[str, Sequence[str], None] = 'ac21c8e41654'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sentence_aspect (
            sent_id bigserial PRIMARY KEY,
            review_id bigint NOT NULL REFERENCES review (review_id) ON DELETE CASCADE,
            sent_idx integer NOT NULL,
            sentence text NOT NULL,
            aspect varchar(50) NOT NULL,
            method varchar(10) NOT NULL,
            sim real,
            sent_score real,
            CONSTRAINT ck_sentence_aspect_method_valid CHECK (method IN ('sbert','keyword','general')),
            CONSTRAINT ck_sentence_aspect_score_range CHECK (sent_score IS NULL OR (sent_score >= -1 AND sent_score <= 1)),
            CONSTRAINT uq_sentence_aspect_sentence UNIQUE (review_id, sent_idx, aspect)
        )""")
    op.execute("CREATE INDEX ix_sentence_aspect_aspect ON sentence_aspect (aspect)")
    op.execute("""
        CREATE TABLE sentence_aspect_run (
            review_id bigint PRIMARY KEY REFERENCES review (review_id) ON DELETE CASCADE,
            n_sentences integer NOT NULL DEFAULT 0,
            processed_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("ALTER TABLE review_aspect_run DROP CONSTRAINT ck_review_aspect_run_method_valid")
    op.execute("""ALTER TABLE review_aspect_run ADD CONSTRAINT ck_review_aspect_run_method_valid
                  CHECK (method IN ('llm','keyword','sbert'))""")


def downgrade() -> None:
    op.execute("ALTER TABLE review_aspect_run DROP CONSTRAINT ck_review_aspect_run_method_valid")
    op.execute("""ALTER TABLE review_aspect_run ADD CONSTRAINT ck_review_aspect_run_method_valid
                  CHECK (method IN ('llm','keyword'))""")
    op.execute("DROP TABLE sentence_aspect_run")
    op.execute("DROP TABLE sentence_aspect")
