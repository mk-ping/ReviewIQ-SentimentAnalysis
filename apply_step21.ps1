# Step 21: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Issue clustering (final pipeline document, section 10). Pure functions, so they test offline.

Per aspect: KMeans for k from ISSUE_K_MIN to ISSUE_K_MAX, the silhouette score picks k, each cluster is named with
c-TF-IDF, and a sentence farther from its cluster centre than mean + ISSUE_RARE_STD x std is flagged as a rare complaint."""
import numpy as np

from app.core import thresholds as T


def cluster_kmeans(X):
    """Returns (labels, centers). Falls back to one cluster when no k gives two real clusters."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    X = np.asarray(X, dtype=float)
    n = len(X)
    best = None
    for k in range(T.ISSUE_K_MIN, min(T.ISSUE_K_MAX, n - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=T.KMEANS_SEED).fit(X)
        if len(set(km.labels_.tolist())) < 2:
            continue
        score = silhouette_score(X, km.labels_)
        if best is None or score > best[0]:
            best = (score, km)
    if best is None:
        return [0] * n, X.mean(axis=0, keepdims=True)
    return [int(v) for v in best[1].labels_], best[1].cluster_centers_


def rare_flags(X, labels, centers) -> list[bool]:
    """True for sentences farther from their cluster centre than mean + 2 std (clusters of 5 or more only)."""
    X = np.asarray(X, dtype=float)
    lab = np.asarray(labels)
    dist = np.linalg.norm(X - np.asarray(centers)[lab], axis=1)
    out = np.zeros(len(X), dtype=bool)
    for c in set(lab.tolist()):
        idx = np.where(lab == c)[0]
        if len(idx) >= 5:
            cut = dist[idx].mean() + T.ISSUE_RARE_STD * dist[idx].std()
            out[idx] = dist[idx] > cut
    return [bool(v) for v in out]


def c_tfidf(texts: list[str], labels, top: int = 3) -> dict[int, list[str]]:
    """Class-based TF-IDF: each cluster is one document. Returns the top words per cluster label."""
    from sklearn.feature_extraction.text import CountVectorizer

    labs = sorted(set(int(v) for v in labels))
    docs = [" ".join(t for t, l in zip(texts, labels) if int(l) == c) for c in labs]
    cv = CountVectorizer(stop_words="english", token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
    try:
        counts = cv.fit_transform(docs).toarray().astype(float)
    except ValueError:
        return {}
    words = cv.get_feature_names_out()
    tf = counts / np.clip(counts.sum(axis=1, keepdims=True), 1, None)
    avg_words = counts.sum() / len(labs)
    idf = np.log(1 + avg_words / np.clip(counts.sum(axis=0), 1, None))
    score = tf * idf
    return {c: [str(words[j]) for j in score[i].argsort()[::-1][:top] if score[i][j] > 0] for i, c in enumerate(labs)}
'@ | Set-Content -Encoding ascii backend\app\services\issue_cluster.py

@'
"""embed stage with a model per review: all-MiniLM-L6-v2 for English, the multilingual model for everything else.
The model name is stored on every vector, and search only compares vectors from the same model."""
import asyncio

from sqlalchemy import text as sql

from app.db.session import SessionLocal
from app.services.embeddings import embed, embed_model_for
from app.services.queue import set_progress
from app.worker.handlers import CHUNK


async def handle_embed(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        rows = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean, r.language, e.model FROM review r
            LEFT JOIN review_embedding e ON e.review_id = r.review_id
            WHERE r.batch_id = :b ORDER BY r.review_id"""), {"b": batch_id})).all()
    by_model: dict[str, list] = {}
    for rid, text, lang, cur in rows:
        want = embed_model_for(lang)
        if cur != want:
            by_model.setdefault(want, []).append((rid, text or ""))
    total = sum(len(v) for v in by_model.values())
    done = 0
    for model, items in by_model.items():
        for i in range(0, len(items), CHUNK):
            part = items[i : i + CHUNK]
            vectors = await asyncio.to_thread(embed, [t for _, t in part], model)
            batch = [{"rid": rid, "m": model, "v": "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"}
                     for (rid, _), vec in zip(part, vectors)]
            async with SessionLocal() as s:
                await s.execute(sql("""
                    INSERT INTO review_embedding (review_id, model, embedding) VALUES (:rid, :m, CAST(:v AS vector))
                    ON CONFLICT (review_id) DO UPDATE SET model = EXCLUDED.model, embedding = EXCLUDED.embedding, created_at = now()"""), batch)
                await s.commit()
                done += len(part)
                await set_progress(s, job_id, int(100 * done / total))
'@ | Set-Content -Encoding ascii backend\app\worker\embed_models.py

@'
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
'@ | Set-Content -Encoding ascii backend\alembic\versions\b7e41c9a3d58_issue_flags.py

@'
"""Offline checks for issue clustering and the what-if lift. Run: python -m tests.check_issues"""
import numpy as np

from app.services.issue_cluster import c_tfidf, cluster_kmeans, rare_flags
from app.services.issues import lift

rng = np.random.default_rng(0)
dirs = np.eye(8)[:3]
X = np.vstack([d + rng.normal(0, 0.05, (40, 8)) for d in dirs])
X /= np.linalg.norm(X, axis=1, keepdims=True)
labels, centers = cluster_kmeans(X)
assert len(set(labels)) == 3, set(labels)                                   # silhouette picks k = 3 from 2..4
assert len({tuple(labels[i * 40:(i + 1) * 40]) for i in range(3)}) == 3 and all(len(set(labels[i * 40:(i + 1) * 40])) == 1 for i in range(3))
print("KMeans picked k =", len(set(labels)))

# one point pushed away from its centre is flagged as rare
Y = X.copy()
Y[0] = Y[0] + np.array([0.6, 0, 0, 0, 0, 0, 0, 0.6])
flags = rare_flags(Y, labels, centers)
assert flags[0] and sum(flags) <= 6, (flags[0], sum(flags))
print("rare complaints flagged:", sum(flags))

texts = ["the pump broke", "pump stopped working", "pump leaks badly", "parcel arrived late", "delivery was delayed", "late delivery again"]
kw = c_tfidf(texts, [0, 0, 0, 1, 1, 1])
assert "pump" in kw[0] and any(w in kw[1] for w in ("late", "delivery")), kw
print("c-TF-IDF:", kw)

old, new, n = lift({1: 5.0, 2: 1.0, 3: 1.0, 4: 3.0}, {2, 3})
assert old == 2.5 and abs(new - 4.0) < 1e-9 and n == 2, (old, new, n)
old, new, n = lift({1: 5.0, 2: 5.0}, {1})
assert new == old == 5.0 and n == 0, "must never lower a rating"
print("issue checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_issues.py

@'
"""Step 21 patcher (KMeans issues, per-language embeddings). Safe to run twice. Run Step 20 first."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s); assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2); print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:80]
    return s.replace(old, new)

edit("backend/app/core/thresholds.py", "ISSUE_MIN_SENTENCES", lambda s: s.rstrip("\n") + '''

ISSUE_MIN_SENTENCES = 30  # an aspect needs this many problem sentences before KMeans runs; fewer become one 'few sentences' issue
ISSUE_K_MIN = 2           # KMeans k range, the silhouette score picks k
ISSUE_K_MAX = 4
ISSUE_RARE_STD = 2.0      # a sentence farther than mean + this many std from its cluster centre is a rare complaint
KMEANS_SEED = 42
''')

edit("backend/app/services/embeddings.py", "embed_model_for", lambda s: s.rstrip("\n") + '''


def embed_model_for(language: str | None) -> str:
    """all-MiniLM-L6-v2 for English, the multilingual model for every other language."""
    from app.services.routing import group_of

    return T.SBERT_EN_MODEL if group_of(language) == "english" else T.EMBED_MODEL
''')

def issues(s):
    s = once(s, "from app.services.embeddings import embed\n",
             "from app.services import issue_cluster as IC\nfrom app.services.embeddings import embed\nfrom app.services.sentence_aspects import sentiment_model_for\n")
    a = s.index("def cluster(texts: list[str]) -> list[int]:")
    b = s.index("def lift(")
    s = s[:a] + s[b:]
    s = once(s, "ReviewAspect.evidence_span, ReviewAspect.sentiment)", "ReviewAspect.evidence_span, ReviewAspect.sentiment, Review.language)")
    old_start = s.index("    found = []\n")
    old_end = s.index("    await session.execute(delete(Issue)")
    new = '''    found = []   # (aspect_id, mentions, keywords or None, few_sentences)
    for aid, ms_all in by_aspect.items():
        by_lang: dict[bool, list] = {True: [], False: []}
        for m in ms_all:
            by_lang[sentiment_model_for(m[5]) == "roberta"].append(m)
        for english, ms in by_lang.items():
            if not ms:
                continue
            if len(ms) >= T.ISSUE_MIN_SENTENCES:
                model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
                X = await asyncio.to_thread(embed, [m[3] for m in ms], model)
                labels, centers = await asyncio.to_thread(IC.cluster_kmeans, X)
                rare = IC.rare_flags(X, labels, centers)
                kws = IC.c_tfidf([m[3] for m in ms], labels)
                few = False
            else:  # small-data rule: one issue for the whole aspect, named by its top keywords
                labels, rare, kws, few = [0] * len(ms), [False] * len(ms), {}, True
            groups: dict[int, list] = {}
            for lab, r, m in zip(labels, rare, ms):
                groups.setdefault(lab, []).append((*m[:5], r))
            for lab, g in groups.items():
                best: dict[int, tuple] = {}
                for m in g:  # one mention per review: keep the most negative
                    if m[0] not in best or m[4] < best[m[0]][4]:
                        best[m[0]] = m
                if len(best) >= T.ISSUE_MIN_REVIEWS:
                    found.append((aid, list(best.values()), kws.get(lab) or None, few))

'''
    s = s[:old_start] + new + s[old_end:]
    s = once(s, "    for aid, ms in found:\n        ids = {m[0] for m in ms}\n        kw = [t for t, _ in Counter(m[2].lower() for m in ms if m[2]).most_common(3)]\n",
             "    for aid, ms, ckw, few in found:\n        ids = {m[0] for m in ms}\n        kw = ckw or [t for t, _ in Counter(m[2].lower() for m in ms if m[2]).most_common(3)]\n")
    s = once(s, "keywords=kw, n_reviews=len(ids))", "keywords=kw, n_reviews=len(ids), few_sentences=few)")
    return once(s, '"evidence_span": m[3], "sentiment": m[4]}', '"evidence_span": m[3], "sentiment": m[4], "is_rare": m[5]}')
edit("backend/app/services/issues.py", "IC.cluster_kmeans", issues)

def models(s):
    s = once(s, "from sqlalchemy import BigInteger, DateTime,", "from sqlalchemy import BigInteger, Boolean, DateTime,")
    s = once(s, "    n_reviews: Mapped[int] = mapped_column(Integer)\n", "    n_reviews: Mapped[int] = mapped_column(Integer)\n    few_sentences: Mapped[bool] = mapped_column(Boolean, server_default=\"false\")\n")
    return once(s, "    sentiment: Mapped[float] = mapped_column(Float)\n", "    sentiment: Mapped[float] = mapped_column(Float)\n    is_rare: Mapped[bool] = mapped_column(Boolean, server_default=\"false\")\n")
edit("backend/app/models/issues.py", "few_sentences", models)

def api_issues(s):
    s = once(s, "select(Issue.issue_id, Issue.name, Aspect.name, Issue.keywords, Issue.n_reviews,\n",
             "select(Issue.issue_id, Issue.name, Aspect.name, Issue.keywords, Issue.n_reviews, Issue.few_sentences,\n")
    s = once(s, '    return {"issues": [\n', '''    rare: dict[int, int] = {}
    if rows:
        rare = dict((await session.execute(
            select(IssueReview.issue_id, func.count()).where(IssueReview.is_rare.is_(True),
                IssueReview.issue_id.in_([r[0] for r in rows])).group_by(IssueReview.issue_id))).all())
    return {"issues": [
''')
    s = once(s, '"priority_score": ps, "evidence": ev.get(i, [])}', '"priority_score": ps, "evidence": ev.get(i, []),\n         "few_sentences": few, "rare_reviews": rare.get(i, 0)}')
    return once(s, "for i, n, a, kw, nr, f, s, g, rg, hs, ps in rows", "for i, n, a, kw, nr, few, f, s, g, rg, hs, ps in rows")
edit("backend/app/api/issues.py", "few_sentences", api_issues)

edit("frontend/src/api.ts", "few_sentences", lambda s: once(s, "export type Issue = {\n", "export type Issue = {\n  few_sentences?: boolean; rare_reviews?: number;\n"))
edit("frontend/src/Problems.tsx", "few_sentences", lambda s: once(s,
 '{i.low_sample && <span className="ml-1 text-amber-600">few reviews</span>}',
 '{i.low_sample && <span className="ml-1 text-amber-600">few reviews</span>}\n                    {i.few_sentences && <span className="ml-1 text-amber-600">few sentences</span>}\n                    {(i.rare_reviews ?? 0) > 0 && <span className="ml-1 text-slate-500">{i.rare_reviews} rare</span>}'))

edit("backend/app/worker/handlers.py", "embed_models", lambda s: once(s,
 "from app.worker.aspects_sbert import handle_aspects as handle_aspects_sentences\n",
 "from app.worker.aspects_sbert import handle_aspects as handle_aspects_sentences\nfrom app.worker.embed_models import handle_embed as handle_embed_models\n").replace('"embed": handle_embed}', '"embed": handle_embed_models}'))

def similar(s):
    s = once(s, 'SELECT e.embedding::text FROM review_embedding e JOIN review r ON r.review_id = e.review_id\n        WHERE e.review_id = :id AND r.workspace_id = :ws"""), {"id": review_id, "ws": ws})).scalar()',
             'SELECT e.embedding::text, e.model FROM review_embedding e JOIN review r ON r.review_id = e.review_id\n        WHERE e.review_id = :id AND r.workspace_id = :ws"""), {"id": review_id, "ws": ws})).first()')
    s = once(s, 'for its upload first.")\n', 'for its upload first.")\n    src, emodel = src\n')
    s = once(s, "WHERE e.review_id <> :id AND r.workspace_id = :ws\n", "WHERE e.review_id <> :id AND r.workspace_id = :ws AND e.model = :m\n")
    return once(s, '{"q": src, "id": review_id, "ws": ws, "lim": limit}', '{"q": src, "id": review_id, "ws": ws, "lim": limit, "m": emodel}')
edit("backend/app/api/explorer.py", "emodel", similar)

def listing(s):
    s = once(s, "    q = embed([claim])[0]\n", "    q = embed([claim], T.SBERT_EN_MODEL)[0]\n")
    s = once(s, "sims = embed(parts) @ q", "sims = embed(parts, T.SBERT_EN_MODEL) @ q")
    s = once(s, "(await asyncio.to_thread(embed, [claim]))[0]", "(await asyncio.to_thread(embed, [claim], T.SBERT_EN_MODEL))[0]")
    s = once(s, "AND r.spam_score <= :spam\n        ORDER BY e.embedding", "AND r.spam_score <= :spam AND e.model = :m\n        ORDER BY e.embedding")
    return once(s, '"q": vec, "k": T.LISTING_TOP_K}', '"q": vec, "k": T.LISTING_TOP_K, "m": T.SBERT_EN_MODEL}')
edit("backend/app/services/listing.py", "SBERT_EN_MODEL", listing)
'@ | Set-Content -Encoding ascii patch_step21.py
python patch_step21.py
Remove-Item patch_step21.py

Write-Host 'Step 21 files written.'
