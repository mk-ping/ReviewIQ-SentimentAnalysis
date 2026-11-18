"""Accuracy experiment (final pipeline document sections 5 and 14): does a method really raise accuracy?
Compared, all out-of-fold: the ensemble as it runs now, gold-fitted weights, gold weights plus model selection,
and mismatch thresholds tuned on gold labels.
Run from backend:  python -m scripts.accuracy_experiment                       (gold labels from the database; label 200+ first)
                   python -m scripts.accuracy_experiment --source public --cap 300   (held-out public data, star-derived labels: a smoke test)
Appends a dated section to ../docs/accuracy_results.md and writes ../ml/out/accuracy_results.json."""
import argparse
import asyncio
import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app.core import thresholds as T
from app.core.config import settings
from app.services import accuracy as AC
from app.services import evaluation as E
from app.services import tuning as U
from app.services.routing import MEMBERS, group_of

NEEDS = 30


def key_of():
    keys = {(settings.roberta_model, "pretrained"): "roberta", (settings.nlptown_model, "pretrained"): "nlptown",
            (settings.xlmr_model, "pretrained"): "xlmr", ("reviewiq-tfidf-lr", "trained"): "tfidf"}
    if settings.distil_model:
        keys[(settings.distil_model, "pretrained")] = "distil"
    return keys


async def load_gold():
    from app.db.session import SessionLocal, engine

    keys = key_of()
    async with SessionLocal() as s:
        g = (await s.execute(text("""
            SELECT g.review_id, g.label, r.language, r.rating_norm FROM gold_label g
            JOIN review r ON r.review_id = g.review_id WHERE g.source = 'gold'"""))).all()
        preds = (await s.execute(text("""
            SELECT pr.review_id, m.name, m.version, pr.p_neg, pr.p_neu, pr.p_pos FROM prediction pr
            JOIN model m ON m.model_id = pr.model_id
            JOIN gold_label g ON g.review_id = pr.review_id AND g.source = 'gold'"""))).all()
        w = (await s.execute(text("""
            SELECT w.route_group, m.name, m.version, w.weight, w.n_val FROM model_weight w
            JOIN model m ON m.model_id = w.model_id"""))).all()
        mm = (await s.execute(text("""
            SELECT g.review_id, g.mismatch_label, s.fused_stars, r.rating_norm, s.confidence FROM gold_label g
            JOIN review r ON r.review_id = g.review_id JOIN review_score s ON s.review_id = g.review_id
            WHERE g.source = 'gold' AND g.mismatch_label IS NOT NULL AND s.fused_stars IS NOT NULL
              AND r.rating_norm IS NOT NULL"""))).all()
    await engine.dispose()
    probs = {}
    for rid, name, ver, pn, pu, pp in preds:
        k = keys.get((name, ver))
        if k:
            probs.setdefault(k, {})[rid] = (pn, pu, pp)
    stored = {}
    for grp, name, ver, weight, n_val in w:
        k = keys.get((name, ver))
        if k and n_val >= T.MIN_VAL_PER_GROUP:
            stored.setdefault(grp, {})[k] = float(weight)
    return {
        "gold": {r[0]: r[1] for r in g},
        "group": {r[0]: group_of(r[2]) for r in g},
        "stars": {r[0]: E.stars_to_label(r[3]) for r in g if r[3] is not None},
        "probs": probs, "stored": stored,
        "mismatch": [(rid, bool(m), U.text_score_from_fused(f, st, c, T.FUSION_W_MIN, T.FUSION_W_MAX), (st - 3) / 2, c)
                     for rid, m, f, st, c in mm],
        "label_note": "hand labels from the Label page (source gold), never derived from stars",
    }


def load_public(cap):
    from app.services import sentiment

    data = Path("../ml/data")
    rows = []
    for name in ("val.jsonl", "test_seen.jsonl"):
        p = data / name
        if p.exists():
            rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        return None
    rng = random.Random(7)
    by = {}
    for r in rows:
        by.setdefault(group_of(r["lang"]), []).append(r)
    gold, group, items = {}, {}, []
    for g, rs in by.items():
        rng.shuffle(rs)
        for r in rs[:cap]:
            i = len(gold)
            gold[i] = E.stars_to_label(r["star"] + 1) if r["star"] >= 0 else ("neg", "neu", "pos")[r["pol"]]
            group[i] = g
            items.append((i, g, r["text"]))
    probs = {}
    for k in sorted({m for ms in MEMBERS.values() for m in ms}):
        if not sentiment.available(k):
            continue
        todo = [(i, t) for i, g, t in items if k in MEMBERS[g]]
        if not todo:
            continue
        try:
            texts = [t for _, t in todo]
            ps = sentiment.get_scorer("tfidf").predict(texts) if k == "tfidf" else sentiment.predict(texts, 32, k)
        except Exception as e:
            print(f"skipping {k}: {type(e).__name__}: {str(e)[:120]}")
            continue
        probs[k] = {i: tuple(p[:3]) for (i, _), p in zip(todo, ps)}
    return {"gold": gold, "group": group, "stars": None, "probs": probs, "stored": None, "mismatch": [],
            "label_note": "derived from stars or dataset polarity, so noisy: a smoke test of the method, not an accuracy claim"}


def show(rows, before):
    print(f"\n{'system':44s} {'n':>5s} {'macro F1':>9s} {'95% range':>13s} {'acc':>6s}  vs before")
    for r in rows:
        ci = f"{r['ci'][0]:.2f}-{r['ci'][1]:.2f}" if r["ci"] else "-"
        v = r["vs_before"]
        vs = "(before)" if r["system"] == before else ("-" if v is None else f"{v['diff']:+.3f} {v['verdict']}")
        f1 = "-" if r["macro_f1"] is None else f"{r['macro_f1']:.3f}"
        acc = "-" if r["accuracy"] is None else f"{r['accuracy']:.3f}"
        print(f"{r['system'][:44]:44s} {r['n']:5d} {f1:>9s} {ci:>13s} {acc:>6s}  {vs}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["gold", "public"], default="gold")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--min-fit", type=int, default=T.MIN_VAL_PER_GROUP,
                    help="labelled reviews a route group needs in the fit folds before its weights are refitted (document rule: 100)")
    ap.add_argument("--cap", type=int, default=300, help="public mode: reviews per route group")
    a = ap.parse_args()
    d = asyncio.run(load_gold()) if a.source == "gold" else load_public(a.cap)
    if d is None:
        print("No data in ml/data. Build it first: cd ..\\ml ; python reviewiq_train.py build")
        return 2
    gold = d["gold"]
    n = len(gold)
    if n < NEEDS:
        print(f"Only {n} labelled reviews; at least {NEEDS} are needed for a smoke test and 200 for a result you can quote. Label more on the Label page.")
        return 2
    if a.source == "gold" and n < 200:
        print(f"Warning: {n} gold labels (the document asks for 200 to 500). Treat this as a first look.")
    if not d["probs"]:
        print("No model predictions found for these reviews. Run the score stage on their uploads first.")
        return 2

    systems = {}
    if d["stars"]:
        systems["stars alone"] = d["stars"]
    for k, pr in sorted(d["probs"].items()):
        systems[f"{k} alone"] = {i: E.argmax_label(*p) for i, p in pr.items() if i in gold}
    systems.update(AC.cross_validate(gold, d["group"], d["probs"], MEMBERS, d["stored"], a.folds, a.min_fit))
    before = AC.STORED if AC.STORED in systems else AC.EQUAL
    rows = AC.summarise(gold, systems, before)
    show(rows, before)

    mism = AC.mismatch_cv(d["mismatch"], a.folds) if len(d["mismatch"]) >= U.MIN_LABELLED else None
    if mism:
        print("\nmismatch flags, out-of-fold:")
        for name in ("default", "tuned"):
            m = mism[name]
            p, r = m["precision"], m["recall"]
            print(f"  {name:8s} flagged {m['flagged']:3d} of {m['n']}, precision {'-' if p is None else f'{p:.2f}'}, recall {'-' if r is None else f'{r:.2f}'}")
    else:
        print(f"\nmismatch tuning skipped: needs {U.MIN_LABELLED}+ reviews with a yes/no mismatch label (have {len(d['mismatch'])}).")

    meta = {"date": date.today().isoformat(), "label_note": d["label_note"], "n": n,
            "classes": ", ".join(f"{k} {v}" for k, v in sorted(Counter(gold.values()).items())),
            "folds": a.folds, "min_fit": a.min_fit,
            "note": None if d["stored"] else "No stored weights from 100+ validation reviews, so the current pipeline uses equal weights in every group."}
    md = AC.render_markdown(meta, rows, mism, before)
    doc = Path("../docs/accuracy_results.md")
    doc.parent.mkdir(exist_ok=True)
    old = doc.read_text(encoding="utf-8") if doc.exists() else "# Accuracy results\n\nEach section is one measurement. Newest at the bottom.\n"
    doc.write_text(old.rstrip("\n") + "\n\n" + md + "\n", encoding="utf-8")
    out = Path("../ml/out")
    out.mkdir(parents=True, exist_ok=True)
    (out / "accuracy_results.json").write_text(json.dumps({"meta": meta, "rows": rows, "mismatch": mism}, indent=2, default=str), encoding="utf-8")
    print("\n" + AC.conclusion(rows, before))
    print(f"recorded in {doc} and {out / 'accuracy_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
