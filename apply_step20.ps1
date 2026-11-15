# Step 20: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Aspect configuration (final pipeline document, section 8). Edit here, nothing else needs to change.

Seven aspects, each with 6 seed phrases that mix good and bad examples (8 to 10 are planned per business).
SBERT turns the seeds into a centroid; a sentence gets every aspect whose cosine similarity is ASPECT_SIM or more.
STEMS are the word starts used by the keyword fallback when no aspect passes the similarity test."""

CATEGORIES = ["quality", "price", "scent", "packaging", "delivery", "results", "ease of use"]

SEEDS = {
    "quality": ["great quality product", "poor quality, feels cheap", "well made and sturdy",
                "it broke after a few days", "defective item received", "excellent build and finish"],
    "price": ["very good value for money", "too expensive for what you get", "reasonably priced",
              "completely overpriced", "worth every rupee", "cheap and affordable"],
    "scent": ["lovely fragrance", "the smell is awful", "smells fresh and nice",
              "strong chemical odour", "pleasant mild scent", "the perfume lasts long"],
    "packaging": ["packed very well", "the box was damaged", "the bottle leaked in the parcel",
                  "the pump stopped working", "neat and secure packaging", "the cap was broken on arrival"],
    "delivery": ["arrived on time", "delivery was very late", "fast shipping",
                 "the courier delayed my order", "delivered earlier than expected", "the parcel never reached me"],
    "results": ["it really works, I saw results", "no visible difference after weeks", "my skin feels better after using it",
                "it did not work for me at all", "effective with noticeable results", "it made my problem worse"],
    "ease of use": ["very easy to use", "hard to apply", "simple setup and clear instructions",
                    "confusing and difficult to use", "convenient to use every day", "complicated to open"],
}

# regex word starts for the keyword fallback (a word must START with one of these)
STEMS = {
    "quality": ["quality", "defect", "faulty", "broke", "broken", "build", "durab", "sturdy", "damag", "cheap material"],
    "price": ["price", "expens", "cheap", "costly", "overpriced", "value", "worth", "afford", "mehng", "sast", "paisa", "paise"],
    "scent": ["smell", "scent", "fragran", "perfume", "odor", "odour", "khushbu", "aroma"],
    "packaging": ["packag", "packing", "packed", "box", "bottle", "pump", "leak", r"cap\b", "seal", "wrapper", "carton"],
    "delivery": ["deliver", "shipp", "courier", "arriv", "dispatch", "parcel", r"late\b", "delay"],
    "results": ["result", "work", "effect", "differen", "improv", "skin", "hair", "useless", "bekar", "faayda"],
    "ease of use": ["easy", "difficult", "hard to", "simple", "convenien", "setup", "instruction", "apply", "user friendly"],
}

# plain keyword lists kept for the older keyword helper in services/aspects.py
KEYWORDS = {c: [s.replace("\\b", "") for s in STEMS[c]] for c in CATEGORIES}
'@ | Set-Content -Encoding ascii backend\app\core\aspect_config.py

@'
"""Sentence-level aspects (final pipeline document, section 8). Pure functions first, so they test offline.

Steps: pysbd splits a review into sentences (fragments under 2 words are dropped); SBERT similarity to each aspect
centroid tags a sentence with every aspect at or above ASPECT_SIM; if none passes, a keyword check on word starts
decides; otherwise the sentence is 'general'. Sentence sentiment comes from the model chosen by route group."""
import re

from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES, SEEDS, STEMS

GENERAL = "general"
_STEM_RX = {a: re.compile(r"\b(?:" + "|".join(STEMS[a]) + ")", re.I) for a in CATEGORIES}
_FALLBACK_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|\s*[;|]\s*")
_seg = None


def split_sentences(text: str) -> list[str]:
    """pysbd when installed, a simple punctuation splitter otherwise. Fragments under 2 words are dropped."""
    global _seg
    parts = None
    try:
        if _seg is None:
            import pysbd
            _seg = pysbd.Segmenter(language="en", clean=False)
        parts = _seg.segment(text)
    except Exception:
        parts = None
    if parts is None:
        parts = _FALLBACK_SPLIT.split(text or "")
    out = []
    for p in parts:
        p = " ".join(p.split())
        if len(p.split()) >= 2:
            out.append(p)
    return out


def keyword_hits(sentence: str) -> list[str]:
    return [a for a in CATEGORIES if _STEM_RX[a].search(sentence)]


def term_of(sentence: str, aspect: str) -> str:
    m = _STEM_RX[aspect].search(sentence)
    if not m:
        return aspect
    word = re.match(r"\w+", sentence[m.start():])
    return (word.group(0) if word else aspect).lower()[:100]


def tag(sims: dict[str, float], sentence: str) -> list[tuple[str, str, float]]:
    """Returns [(aspect, method, sim)]. method is 'sbert', 'keyword' or 'general'."""
    hits = [(a, "sbert", s) for a, s in sims.items() if s >= T.ASPECT_SIM]
    if hits:
        return sorted(hits, key=lambda h: -h[2])
    kw = keyword_hits(sentence)
    if kw:
        return [(a, "keyword", float(sims.get(a, 0.0))) for a in kw]
    return [(GENERAL, GENERAL, float(max(sims.values())) if sims else 0.0)]


def centroids(embed_fn) -> dict:
    """Average of each aspect's seed vectors, scaled to length 1. embed_fn(list[str]) -> (n, dim) unit vectors."""
    import numpy as np
    out = {}
    for a in CATEGORIES:
        v = np.asarray(embed_fn(SEEDS[a]), dtype=float).mean(axis=0)
        out[a] = v / (np.linalg.norm(v) or 1.0)
    return out


def similarities(vectors, cents: dict) -> list[dict[str, float]]:
    """Cosine similarity of each (unit length) sentence vector to each centroid."""
    import numpy as np
    m = np.asarray(vectors, dtype=float)
    return [{a: float(m[i] @ c) for a, c in cents.items()} for i in range(len(m))]


def sentiment_model_for(language: str | None) -> str:
    """RoBERTa for English, Twitter XLM-RoBERTa for every other route group."""
    from app.services.routing import group_of
    return "roberta" if group_of(language) == "english" else "xlmr"


def coverage(n_tagged: int, n_total: int) -> float | None:
    """Share of sentences that received an aspect. This is coverage, not accuracy."""
    return None if n_total == 0 else n_tagged / n_total


def review_rows(review_id: int, sentences: list[dict], aspect_ids: dict[str, int]) -> list[dict]:
    """Review-level view derived from the sentence rows (one row per tagged sentence), so Hidden Dissatisfaction,
    the issues and the aspect pages keep reading review_aspect. Confidence is the sentiment model's confidence."""
    rows = []
    for s in sentences:
        if s["aspect"] == GENERAL or s["sent_score"] is None:
            continue
        rows.append({"review_id": review_id, "aspect_id": aspect_ids[s["aspect"]], "term": term_of(s["sentence"], s["aspect"]),
                     "evidence_span": s["sentence"], "sentiment": round(s["sent_score"], 3),
                     "confidence": round(s["conf"], 3), "method": s["method"]})
    return rows
'@ | Set-Content -Encoding ascii backend\app\services\sentence_aspects.py

@'
"""aspects stage: sentence-level aspects. Replaces the review-level LLM stage; the LLM no longer tags anything."""
import asyncio

from sqlalchemy import delete, func, select, text as sql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.models import Review, ReviewAspect, ReviewAspectRun, UploadBatch
from app.services import embeddings, sentence_aspects as SA, sentiment
from app.services.queue import set_progress
from app.worker.handlers import CHUNK, _aspect_ids

_cents: dict = {}


def _cents_for(model: str) -> dict:
    if model not in _cents:
        _cents[model] = SA.centroids(lambda t: embeddings.embed(t, model))
    return _cents[model]


def _analyse(part: list[tuple]) -> list[dict]:
    """part = [(review_id, text, language)]. Returns sentence dicts with aspect, method, sim, sent_score, conf."""
    items = []
    for rid, text, lang in part:
        for idx, s in enumerate(SA.split_sentences(text or "")):
            items.append({"review_id": rid, "idx": idx, "sentence": s, "lang": lang,
                          "english": SA.sentiment_model_for(lang) == "roberta"})
    out = []
    for english in (True, False):
        grp = [i for i in items if i["english"] == english]
        if not grp:
            continue
        model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
        vecs = embeddings.embed([i["sentence"] for i in grp], model)
        sims = SA.similarities(vecs, _cents_for(model))
        tagged = []
        for i, sm in zip(grp, sims):
            for aspect, method, sim in SA.tag(sm, i["sentence"]):
                tagged.append({**i, "aspect": aspect, "method": method, "sim": sim, "sent_score": None, "conf": 0.0})
        need = [t for t in tagged if t["aspect"] != SA.GENERAL]
        if need:
            probs = sentiment.predict([t["sentence"] for t in need], model="roberta" if english else "xlmr")
            for t, (n, u, p, _e) in zip(need, probs):
                t["sent_score"], t["conf"] = p - n, max(n, u, p)
        out.extend(tagged)
    return out


async def handle_aspects(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        ws = await s.scalar(select(UploadBatch.workspace_id).where(UploadBatch.batch_id == batch_id))
        ids = await _aspect_ids(s, ws)
        pending = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean, r.language FROM review r
            LEFT JOIN sentence_aspect_run u ON u.review_id = r.review_id
            WHERE r.batch_id = :b AND u.review_id IS NULL ORDER BY r.review_id"""), {"b": batch_id})).all()
    total = len(pending)
    for i in range(0, total, CHUNK):
        part = pending[i : i + CHUNK]
        rows = await asyncio.to_thread(_analyse, [tuple(p) for p in part])
        by: dict[int, list[dict]] = {}
        for r in rows:
            by.setdefault(r["review_id"], []).append(r)
        rids = [p[0] for p in part]
        async with SessionLocal() as s:
            await s.execute(delete(ReviewAspect).where(ReviewAspect.review_id.in_(rids)))
            await s.execute(sql("DELETE FROM sentence_aspect WHERE review_id = ANY(CAST(:ids AS bigint[]))"), {"ids": rids})
            sent_rows = [{"review_id": r["review_id"], "sent_idx": r["idx"], "sentence": r["sentence"], "aspect": r["aspect"],
                          "method": r["method"], "sim": r["sim"], "sent_score": r["sent_score"]} for r in rows]
            if sent_rows:
                await s.execute(sql("""INSERT INTO sentence_aspect (review_id, sent_idx, sentence, aspect, method, sim, sent_score)
                    VALUES (:review_id, :sent_idx, :sentence, :aspect, :method, :sim, :sent_score)"""), sent_rows)
            derived = [d for rid in rids for d in SA.review_rows(rid, by.get(rid, []), ids)]
            if derived:
                await s.execute(pg_insert(ReviewAspect), derived)
            for rid in rids:
                n = len(by.get(rid, []))
                await s.execute(sql("""INSERT INTO sentence_aspect_run (review_id, n_sentences) VALUES (:r, :n)
                    ON CONFLICT (review_id) DO UPDATE SET n_sentences = :n, processed_at = now()"""), {"r": rid, "n": n})
                await s.execute(pg_insert(ReviewAspectRun).values(review_id=rid, method="sbert", n_found=sum(1 for d in derived if d["review_id"] == rid))
                                .on_conflict_do_update(index_elements=["review_id"], set_={"method": "sbert"}))
            await s.commit()
            await set_progress(s, job_id, int(100 * min(i + CHUNK, total) / total))
    async with SessionLocal() as s:
        n_all, n_tag = (await s.execute(sql("""SELECT count(*), count(*) FILTER (WHERE aspect <> 'general') FROM sentence_aspect sa
            JOIN review r ON r.review_id = sa.review_id WHERE r.batch_id = :b"""), {"b": batch_id})).one()
    print(f"[aspects] sentences tagged: {n_tag} of {n_all} ({SA.coverage(n_tag, n_all)})")
'@ | Set-Content -Encoding ascii backend\app\worker\aspects_sbert.py

@'
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
'@ | Set-Content -Encoding ascii backend\alembic\versions\9d3f5b7a1c20_sentence_aspect.py

@'
"""Offline checks for sentence-level aspects (no models, no database). Run: python -m tests.check_sentence_aspects"""
from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES, SEEDS, STEMS
from app.services import sentence_aspects as SA

assert len(CATEGORIES) == 7 and set(SEEDS) == set(CATEGORIES) == set(STEMS)
assert all(len(v) == 6 for v in SEEDS.values())

# splitting drops fragments under 2 words and keeps 'very nice'
s = SA.split_sentences("Great scent. Ok. The pump broke after a week! very nice")
assert "Great scent." in s and "The pump broke after a week!" in s and "very nice" in s and "Ok." not in s, s

# threshold is inclusive at 0.35; a sentence can get several aspects
sims = {a: 0.1 for a in CATEGORIES}
sims["scent"], sims["packaging"] = 0.35, 0.5
got = SA.tag(sims, "the smell is nice but the box was crushed")
assert [g[0] for g in got] == ["packaging", "scent"] and all(g[1] == "sbert" for g in got), got

# keyword fallback when nothing passes, on word starts
low = {a: 0.05 for a in CATEGORIES}
assert SA.tag(low, "Delivery was slow") == [("delivery", "keyword", 0.05)]
assert SA.tag(low, "A latest model")[0][0] == "general"          # 'late' must not match 'latest'
assert SA.tag(low, "I bought it last week")[0][0] == "general"

# term
assert SA.term_of("The pump broke", "packaging") == "pump"
assert SA.term_of("Nothing here", "price") == "price"

# review-level rows are derived from sentence rows; general and unscored sentences are skipped
ids = {a: i for i, a in enumerate(CATEGORIES, 1)}
sent = [
    {"sentence": "The pump broke", "aspect": "packaging", "method": "sbert", "sent_score": -0.8, "conf": 0.9},
    {"sentence": "I bought it", "aspect": "general", "method": "general", "sent_score": None, "conf": 0.0},
]
rows = SA.review_rows(7, sent, ids)
assert len(rows) == 1 and rows[0]["aspect_id"] == ids["packaging"] and rows[0]["sentiment"] == -0.8 and rows[0]["method"] == "sbert"

# coverage and centroid/similarity maths with a fake embedder
assert SA.coverage(0, 0) is None and abs(SA.coverage(1484, 2678) - 0.554) < 0.001
import numpy as np
fake = lambda texts: np.tile(np.array([1.0, 0.0]), (len(texts), 1))
c = SA.centroids(fake)
assert abs(np.linalg.norm(c["price"]) - 1) < 1e-9
assert abs(SA.similarities([[1.0, 0.0]], c)[0]["price"] - 1) < 1e-9

assert SA.sentiment_model_for("en") == "roberta" and SA.sentiment_model_for("hi") == "xlmr" and SA.sentiment_model_for(None) == "xlmr"
assert T.ASPECT_SIM == 0.35
print("sentence aspect checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_sentence_aspects.py

@'
"""Hand-check of aspect tags (document section 14: about 100 sentences).
  python -m scripts.sentence_check export   -> ../data/sentence_check.csv (refuses to overwrite your labels)
  python -m scripts.sentence_check score    -> precision per aspect from the filled 'correct' column (1 yes, 0 no)"""
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal

PATH = Path("../data/sentence_check.csv")


async def export(n: int = 100):
    if PATH.exists():
        print(f"{PATH} already exists. Rename or delete it yourself for a fresh export."); return
    async with SessionLocal() as s:
        rows = (await s.execute(text("""SELECT sent_id, aspect, method, round(sim::numeric,3), sentence FROM sentence_aspect
            WHERE aspect <> 'general' ORDER BY md5(sent_id::text) LIMIT :n"""), {"n": n})).all()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sent_id", "aspect", "method", "sim", "sentence", "correct"])
        w.writerows([list(r) + [""] for r in rows])
    print(f"wrote {len(rows)} sentences to {PATH}. Fill the 'correct' column with 1 or 0, then run: score")


def score():
    by: dict[str, list[int]] = {}
    for r in csv.DictReader(PATH.open(encoding="utf-8")):
        if r["correct"].strip() in ("0", "1"):
            by.setdefault(r["aspect"], []).append(int(r["correct"]))
    allv = [v for vs in by.values() for v in vs]
    if not allv:
        print("No labelled rows yet."); return
    for a, vs in sorted(by.items()):
        print(f"{a:12s} n={len(vs):3d} precision={sum(vs)/len(vs):.2f}")
    print(f"overall      n={len(allv):3d} precision={sum(allv)/len(allv):.2f}  (tags checked by hand, not recall)")


if __name__ == "__main__":
    asyncio.run(export()) if sys.argv[1:] == ["export"] else score()
'@ | Set-Content -Encoding ascii backend\scripts\sentence_check.py

@'
"""Step 20 patcher (sentence-level aspects). Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s); assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2); print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

edit("backend/app/core/thresholds.py", "ASPECT_SIM", lambda s: s.rstrip("\n") + '\n\nASPECT_SIM = 0.35         # a sentence gets every aspect whose cosine similarity is at least this (recheck for multilingual SBERT)\nSBERT_EN_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # English sentences; others use EMBED_MODEL\n')

edit("backend/app/services/embeddings.py", "_models", lambda s: s.replace("_model = None\n", "_models: dict = {}\n").replace(
'''def embed(texts: list[str]):
    """Returns a (n, dim) array of unit-length sentence embeddings. Loads the model once per process."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(T.EMBED_MODEL)
    return _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)''',
'''def embed(texts: list[str], model: str | None = None):
    """Returns a (n, dim) array of unit-length sentence embeddings. Each model loads once per process."""
    name = model or T.EMBED_MODEL
    if name not in _models:
        from sentence_transformers import SentenceTransformer

        _models[name] = SentenceTransformer(name)
    return _models[name].encode(texts, normalize_embeddings=True, show_progress_bar=False)'''))

edit("backend/app/models/aspects.py", "class SentenceAspect", lambda s: s.rstrip("\n") + '''


class SentenceAspect(Base):
    """One row per (sentence, aspect). Sentences with no aspect are stored as 'general' so coverage can be measured."""
    __tablename__ = "sentence_aspect"
    __table_args__ = (
        CheckConstraint("method IN ('sbert','keyword','general')", name="method_valid"),
        CheckConstraint("sent_score IS NULL OR (sent_score >= -1 AND sent_score <= 1)", name="score_range"),
        UniqueConstraint("review_id", "sent_idx", "aspect", name="uq_sentence_aspect_sentence"),
    )

    sent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"))
    sent_idx: Mapped[int] = mapped_column(Integer)
    sentence: Mapped[str] = mapped_column(Text)
    aspect: Mapped[str] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(10))
    sim: Mapped[float | None] = mapped_column(Float)
    sent_score: Mapped[float | None] = mapped_column(Float)


class SentenceAspectRun(Base):
    __tablename__ = "sentence_aspect_run"

    review_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("review.review_id", ondelete="CASCADE"), primary_key=True)
    n_sentences: Mapped[int] = mapped_column(Integer, server_default="0")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
''')

def models(s):
    s = once(s, "from app.models.aspects import Aspect, ReviewAspect, ReviewAspectRun", "from app.models.aspects import Aspect, ReviewAspect, ReviewAspectRun, SentenceAspect, SentenceAspectRun")
    return once(s, '"ReviewAspectRun",', '"ReviewAspectRun", "SentenceAspect", "SentenceAspectRun",')
edit("backend/app/models/__init__.py", "SentenceAspectRun", models)

edit("backend/app/worker/handlers.py", "aspects_sbert", lambda s: once(s,
 '\n\nHANDLERS = {"score": handle_score_all, "aspects": handle_aspects,',
 '\nfrom app.worker.aspects_sbert import handle_aspects as handle_aspects_sentences\n\n\nHANDLERS = {"score": handle_score_all, "aspects": handle_aspects_sentences,'))

edit("backend/app/core/action_rules.py", '"results":', lambda s: once(s, '    "customer service":',
 '    "results": ("Compare the claimed results with customer feedback and review the formulation or the instructions", "Product and R&D"),\n    "customer service":'))

edit("backend/tests/check_actions.py", "<= set(RULES)", lambda s: once(s, "assert set(RULES) == set(CATEGORIES), set(RULES) ^ set(CATEGORIES)",
 "assert set(CATEGORIES) <= set(RULES), set(CATEGORIES) - set(RULES)   # older aspect names keep their rules"))

edit("backend/requirements.txt", "pysbd", lambda s: s.rstrip("\n") + "\npysbd\n")
'@ | Set-Content -Encoding ascii patch_step20.py
python patch_step20.py
Remove-Item patch_step20.py

Write-Host 'Step 20 files written.'
