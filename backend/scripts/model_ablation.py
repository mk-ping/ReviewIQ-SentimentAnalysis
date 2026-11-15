
"""Which models earn their place? Compares every model, the pipeline's mean fusion, leave-one-model-out fusion,
stars alone, a TF-IDF baseline and a trained stacker, all on the hand-labelled gold set.
Run from backend:  python -m scripts.model_ablation      (needs scikit-learn; label 200+ reviews first)"""
import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services import ablation as A
from app.services import evaluation as E


def _f(x):
    return "  -  " if x is None else f"{x:.3f}"


async def main() -> None:
    async with SessionLocal() as s:
        gold_rows = (await s.execute(text("""
            SELECT g.review_id, g.label, r.text_clean, r.rating_norm FROM gold_label g
            JOIN review r ON r.review_id = g.review_id WHERE g.source = 'gold' ORDER BY g.review_id"""))).all()
        preds = (await s.execute(text("""
            SELECT pr.review_id, m.name, pr.p_neg, pr.p_neu, pr.p_pos FROM prediction pr
            JOIN model m ON m.model_id = pr.model_id JOIN gold_label g ON g.review_id = pr.review_id AND g.source = 'gold'
            ORDER BY m.name"""))).all()
    gold = {r[0]: r[1] for r in gold_rows}
    print(f"gold labels: {len(gold)}")
    if len(gold) < 30:
        print("Fewer than 30 gold labels: numbers below are only a smoke test. Label 200+ for anything you quote.")
    if len(set(gold.values())) < 2:
        print("Need at least two classes. Label more reviews first.")
        return

    names = sorted({p[1] for p in preds})
    by_model: dict[str, dict[int, tuple]] = {n: {} for n in names}
    for rid, name, pn, pu, pp in preds:
        by_model[name][rid] = (pn, pu, pp)
    stars = {r[0]: E.stars_to_label(r[3]) for r in gold_rows if r[3] is not None}

    systems: dict[str, dict[int, str]] = {"stars alone": stars}
    for n in names:
        systems[n] = {i: E.argmax_label(*p) for i, p in by_model[n].items()}
    per_review = {i: [by_model[n][i] for n in names if i in by_model[n]] for i in gold}
    per_review = {i: v for i, v in per_review.items() if v}
    systems["mean fusion (pipeline)"] = A.mean_fusion(per_review)
    if len(names) > 1:
        for k, n in enumerate(names):
            # position k in per_review only lines up when every model ran, so build this one explicitly
            rest = {i: [by_model[m][i] for m in names if m != n and i in by_model[m]] for i in gold}
            systems[f"fusion without {n.split('/')[-1]}"] = A.mean_fusion({i: v for i, v in rest.items() if v})

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    texts = {r[0]: r[2] for r in gold_rows}
    ids = sorted(gold)
    counts = {c: list(gold.values()).count(c) for c in set(gold.values())}
    k = max(2, min(5, min(counts.values())))
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True), LogisticRegression(max_iter=1000, class_weight="balanced"))
    cv = cross_val_predict(pipe, [texts[i] for i in ids], [gold[i] for i in ids], cv=StratifiedKFold(k, shuffle=True, random_state=7))
    systems["TF-IDF + LR (cross-validated)"] = dict(zip(ids, cv))

    star_val = {r[0]: r[3] for r in gold_rows}
    X = [A.stacker_features(star_val[i], [by_model[n].get(i) for n in names]) for i in ids]
    st = A.stack_cv(X, [gold[i] for i in ids])
    systems["stacker (trained, cross-validated)"] = dict(zip(ids, st))

    print(f"\n{'system':44s} {'n':>5s} {'macro F1':>9s} {'95% range':>16s} {'acc':>6s}  vs stars alone   vs TF-IDF")
    for name, sysd in systems.items():
        idl = A.common_ids(gold, sysd)
        g, p = [gold[i] for i in idl], [sysd[i] for i in idl]
        ci = E.bootstrap_macro_f1(g, p)
        rng = f"{ci[0]:.2f}-{ci[1]:.2f}" if ci else "   -"
        v1 = A.paired_bootstrap_diff(gold, sysd, stars) if name != "stars alone" and stars else None
        v2 = A.paired_bootstrap_diff(gold, sysd, systems["TF-IDF + LR (cross-validated)"]) if "TF-IDF" not in name else None
        print(f"{name[:44]:44s} {len(idl):5d} {_f(E.macro_f1(g, p)):>9s} {rng:>16s} {_f(E.accuracy(g, p)):>6s}  "
              f"{(v1 or {}).get('verdict', '-'):16s} {(v2 or {}).get('verdict', '-')}")
    print("\nKeep a model only if it beats stars alone AND the TF-IDF baseline, or if it covers languages the others cannot.")
    print("The stacker is trained on gold labels with cross-validation. Use it in the pipeline only if it beats mean fusion.")


asyncio.run(main())
