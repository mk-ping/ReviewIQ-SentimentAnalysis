"""BERTopic-style topic discovery on negative sentences: SBERT embeddings, UMAP, HDBSCAN, c-TF-IDF word lists.
It finds complaint topics the seven aspects may not cover (a topic is 'emerging' when most of its sentences were tagged 'general').
Optional: needs  pip install -r requirements-extra.txt   (bertopic, umap-learn, hdbscan).
Run from backend after sentence aspects exist:  python -m scripts.topic_discovery [--workspace 3] [--limit 20000]
Writes ../ml/out/topics_ws<N>.json (shown on the Model Checks page) and ../docs/topics_ws<N>.md. Exit code 2 = optional packages missing."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services.extras import summarise_topics

MIN_SENTENCES = 200

SQL = """
SELECT sa.sentence, sa.aspect FROM sentence_aspect sa JOIN review r ON r.review_id = sa.review_id
WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND sa.sent_score <= :neg AND (r.language = 'en' OR r.language IS NULL)
ORDER BY md5(sa.sent_id::text) LIMIT :lim"""


async def load(ws, lim):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(SQL), {"ws": ws, "spam": T.SPAM_MAX, "neg": T.NEG_MENTION, "lim": lim})).all()
    return ws, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--limit", type=int, default=20000)
    a = ap.parse_args()
    try:
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer
        from umap import UMAP
    except ImportError:
        print("Optional packages missing. Run: pip install -r requirements-extra.txt   (bertopic, umap-learn, hdbscan)")
        return 2
    ws, rows = asyncio.run(load(a.workspace, a.limit))
    docs, aspects = [r.sentence for r in rows], [r.aspect for r in rows]
    if len(docs) < MIN_SENTENCES:
        print(f"Only {len(docs)} negative English sentences; at least {MIN_SENTENCES} are needed. Analyse a bigger upload first.")
        return 1
    from app.core import thresholds as T
    from app.services.embeddings import embed
    print(f"Workspace {ws}: embedding {len(docs)} negative sentences ...")
    import numpy as np
    emb = np.vstack([embed(docs[i:i + 512], T.SBERT_EN_MODEL) for i in range(0, len(docs), 512)])
    model = BERTopic(
        embedding_model=None,
        umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42),
        hdbscan_model=HDBSCAN(min_cluster_size=max(10, len(docs) // 100), metric="euclidean", cluster_selection_method="eom"),
        vectorizer_model=CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2),
        calculate_probabilities=False, verbose=False)
    ids, _ = model.fit_transform(docs, embeddings=emb)
    words = {t: [w for w, _ in model.get_topic(t)[:8]] for t in set(ids) if t != -1}
    res = summarise_topics(docs, [int(i) for i in ids], aspects, words)
    doc = {"workspace": ws, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res}
    from app.core.config import settings
    out = Path(settings.tfidf_path).parent / f"topics_ws{ws}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    md = [f"# Complaint topics (workspace {ws})", "", f"{res['sentences']} negative sentences, {len(res['topics'])} topics, {res['outliers']} outliers.", "",
          "| Topic | Sentences | Top words | Main aspect | Emerging |", "| --- | --- | --- | --- | --- |"]
    md += [f"| {t['topic']} | {t['size']} | {', '.join(t['words'])} | {t['dominant_aspect']} | {'yes' if t['emerging'] else ''} |" for t in res["topics"]]
    Path("../docs").mkdir(exist_ok=True)
    Path(f"../docs/topics_ws{ws}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(res['topics'])} topics, {sum(t['emerging'] for t in res['topics'])} emerging. Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
