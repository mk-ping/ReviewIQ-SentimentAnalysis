"""Honest baseline for the report: TF-IDF + logistic regression, cross-validated on the gold labels,
compared with the sentiment model and with stars alone on the same reviews.
Run from backend:  python -m scripts.baseline_tfidf   (needs scikit-learn)"""
import asyncio
from collections import Counter

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services import evaluation as E


async def main() -> None:
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT g.review_id, g.label, r.text_clean, r.rating_norm FROM gold_label g
            JOIN review r ON r.review_id = g.review_id WHERE g.source = 'gold' ORDER BY g.review_id"""))).all()
        preds = (await s.execute(text("""
            SELECT pr.review_id, m.name, pr.p_neg, pr.p_neu, pr.p_pos FROM prediction pr
            JOIN model m ON m.model_id = pr.model_id JOIN gold_label g ON g.review_id = pr.review_id AND g.source = 'gold'"""))).all()
    counts = Counter(r[1] for r in rows)
    print(f"gold labels: {len(rows)} {dict(counts)}")
    usable = [c for c, k in counts.items() if k >= 2]
    if len(usable) < 2:
        print("Need at least two classes with two or more labels each. Label more reviews first.")
        return

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    rows = [r for r in rows if r[1] in usable]
    y = [r[1] for r in rows]
    k = max(2, min(5, min(counts[c] for c in usable)))
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
                         LogisticRegression(max_iter=1000, class_weight="balanced"))
    cv = cross_val_predict(pipe, [r[2] for r in rows], y, cv=StratifiedKFold(k, shuffle=True, random_state=7))
    print(f"\nTF-IDF + logistic regression, {k}-fold cross-validated: macro F1 {E.macro_f1(y, list(cv)):.3f}, accuracy {E.accuracy(y, list(cv)):.3f}")

    ids = {r[0]: r[1] for r in rows}
    by_model: dict[str, dict[int, str]] = {}
    for rid, name, pn, pu, pp in preds:
        if rid in ids:
            by_model.setdefault(name, {})[rid] = E.argmax_label(pn, pu, pp)
    for name, p in by_model.items():
        keys = sorted(p)
        g = [ids[i] for i in keys]
        print(f"{name}: macro F1 {E.macro_f1(g, [p[i] for i in keys]):.3f} on {len(keys)} reviews")
    st = {r[0]: E.stars_to_label(r[3]) for r in rows if r[3] is not None}
    keys = sorted(st)
    if keys:
        print(f"Stars alone: macro F1 {E.macro_f1([ids[i] for i in keys], [st[i] for i in keys]):.3f} on {len(keys)} reviews")
    print("\nA model earns its place only if it beats this baseline and stars alone on the gold set.")


asyncio.run(main())
