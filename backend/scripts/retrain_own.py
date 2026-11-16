"""Retrain the TF-IDF baseline on one workspace's own rated reviews (document rule: from 2000 rated reviews).
Held-out validation and test reviews (the split column) are never used for training.
Run from backend:  python -m scripts.retrain_own [--workspace 3] [--min-rated 2000]
It saves ../ml/out/tfidf_lr_ws<N>.joblib and prints how to use it. It never replaces the shared baseline by itself."""
import argparse
import asyncio
from collections import Counter
from pathlib import Path

MIN_RATED = 2000


def label3(star: float) -> str:
    s = round(star)
    return "neg" if s <= 2 else "neu" if s == 3 else "pos"


def check_ready(n_rated: int, labels: Counter, min_rated: int = MIN_RATED) -> str | None:
    """None when training can go ahead, otherwise the plain reason it cannot."""
    if n_rated < min_rated:
        return f"Only {n_rated} rated reviews are available for training; the rule needs {min_rated}. Upload {min_rated - n_rated} more."
    thin = [k for k in ("neg", "neu", "pos") if labels.get(k, 0) < 50]
    if thin:
        return "Too few reviews in class(es): " + ", ".join(thin) + " (need at least 50 each)."
    return None


def make_pipe():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, token_pattern=r"[^\s.,!?;:()\[\]\"]+"),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )


def train(texts, labels):
    """Fits on 90%, reports on the other 10%, then refits on everything. Returns (pipeline, macro_f1, accuracy)."""
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split
    xa, xb, ya, yb = train_test_split(texts, labels, test_size=0.1, random_state=7, stratify=labels)
    check = make_pipe().fit(xa, ya)
    pred = check.predict(xb)
    return make_pipe().fit(texts, labels), f1_score(yb, pred, average="macro"), accuracy_score(yb, pred)


async def load(ws: int | None):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(
            "SELECT text_clean, rating_norm FROM review WHERE workspace_id = :ws AND spam_score <= :spam "
            "AND rating_norm IS NOT NULL AND split IS NULL AND length(text_clean) > 0"), {"ws": ws, "spam": T.SPAM_MAX})).all()
    return ws, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--min-rated", type=int, default=MIN_RATED)
    a = ap.parse_args()
    ws, rows = asyncio.run(load(a.workspace))
    texts = [t for t, _ in rows]
    labels = [label3(float(r)) for _, r in rows]
    why = check_ready(len(rows), Counter(labels), a.min_rated)
    if why:
        print(why)
        return 1
    import joblib
    pipe, f1, acc = train(texts, labels)
    print(f"Workspace {ws}: trained on {len(rows)} rated reviews. Check on 10%: macro F1 {f1:.3f}, accuracy {acc:.3f}")
    print("(a sanity check on star-derived labels, not a reported score: your gold labels decide that)")
    from app.core.config import settings
    out = Path(settings.tfidf_path).with_name(f"tfidf_lr_ws{ws}.joblib")
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out)
    print("saved", out)
    print("To use it, set TFIDF_PATH to that file in backend/.env, restart the API and worker, then run the held-out evaluation again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
