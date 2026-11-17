"""Accuracy lab: which legitimate change raises macro F1 on held-out reviews?
Labels come from stars (1-2 neg, 3 neu, 4-5 pos), so stars are NOT used as a feature here.
Methods are chosen on the validation split; the test split is reported once.
Run from backend:  python -m scripts.accuracy_lab"""
import asyncio

import numpy as np
from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal, engine
from app.services import evaluation as E
from app.services import sentiment

LABELS = ("neg", "neu", "pos")
GRID = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


async def load():
    key_of = {(c["name"], c["version"]): k for k, c in sentiment.registry().items()}
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT r.review_id, r.split, r.rating_norm, m.name, m.version, p.p_neg, p.p_neu, p.p_pos
            FROM review r JOIN prediction p ON p.review_id = r.review_id JOIN model m ON m.model_id = p.model_id
            WHERE r.rating_norm IS NOT NULL AND r.split IS NOT NULL AND r.spam_score <= :sp"""), {"sp": T.SPAM_MAX})).all()
    await engine.dispose()
    by: dict = {}
    for rid, split, st, name, ver, pn, pu, pp in rows:
        k = key_of.get((name, ver))
        if k:
            by.setdefault(rid, {"split": split, "stars": st, "p": {}})["p"][k] = (pn, pu, pp)
    return by


def labels_of(p):
    return [LABELS[int(j)] for j in p.argmax(1)]


async def main():
    by = await load()
    models = sorted({k for d in by.values() for k in d["p"]})
    ids = [i for i, d in by.items() if all(m in d["p"] for m in models)]  # same reviews for every method
    print(f"models: {models}; reviews scored by all of them: {len(ids)}")
    val = [i for i in ids if by[i]["split"] == "validation"]
    test = [i for i in ids if by[i]["split"] == "test"]
    print(f"validation {len(val)}, test {len(test)}")
    if len(val) < 30 or len(test) < 30:
        print("Too few reviews for a fair comparison. Score more rated reviews first.")
        return
    P = lambda ids_, m: np.array([by[i]["p"][m] for i in ids_])
    X = lambda ids_: np.array([[x for m in models for x in by[i]["p"][m]] for i in ids_])
    y = lambda ids_: [E.stars_to_label(by[i]["stars"]) for i in ids_]
    yv, yt = y(val), y(test)

    def wavg(ids_, w):
        return sum(w[m] * P(ids_, m) for m in models) / sum(w.values())

    results = []  # (name, validation F1, test predictions)
    for m in models:
        results.append((f"{m} alone", E.macro_f1(yv, labels_of(P(val, m))), labels_of(P(test, m))))
    eq = {m: 1.0 for m in models}
    results.append(("equal-weight mean", E.macro_f1(yv, labels_of(wavg(val, eq))), labels_of(wavg(test, eq))))
    w = {m: max(E.macro_f1(yv, labels_of(P(val, m))) or 0.01, 0.01) for m in models}
    results.append(("F1-weighted ensemble (current method)", E.macro_f1(yv, labels_of(wavg(val, w))), labels_of(wavg(test, w))))

    best = max(((E.macro_f1(yv, labels_of(wavg(val, w) * np.array([a, b, 1.0]))) or 0, a, b) for a in GRID for b in GRID))
    _, a, b = best
    scale = np.array([a, b, 1.0])
    results.append((f"ensemble + class weights (neg {a}, neu {b})", best[0], labels_of(wavg(test, w) * scale)))

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    mk = lambda: LogisticRegression(max_iter=2000, class_weight="balanced")
    try:
        vf = E.macro_f1(yv, list(cross_val_predict(mk(), X(val), yv, cv=5)))
    except ValueError:
        vf = None
    clf = mk().fit(X(val), yv)
    results.append(("stacker (logistic regression on all outputs)", vf, list(clf.predict(X(test)))))

    f = lambda v: "  -  " if v is None else f"{v:.3f}"
    print(f"\n{'method':52s} {'val F1':>7s} {'test F1':>8s} {'95% range':>13s} {'test acc':>9s}")
    for name, vf, pred in results:
        ci = E.bootstrap_macro_f1(yt, pred)
        rng = f"{ci[0]:.2f}-{ci[1]:.2f}" if ci else "-"
        print(f"{name:52s} {f(vf):>7s} {f(E.macro_f1(yt, pred)):>8s} {rng:>13s} {f(E.accuracy(yt, pred)):>9s}")

    top = max(results, key=lambda r: -1 if r[1] is None else r[1])  # chosen on validation, never on test
    print(f"\nchosen on validation: {top[0]}")
    for c, d in E.per_class(yt, top[2]).items():
        print(f"  {c}: precision {f(d['precision'])} recall {f(d['recall'])} F1 {f(d['f1'])} (support {d['support']})")
    print("Report the test numbers once. If two ranges overlap, say the difference is within noise.")


asyncio.run(main())
