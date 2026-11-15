"""Held-out evaluation table (final pipeline document, sections 4, 5 and 14).
Weights = macro F1 on val.jsonl; the table is scored on the test sets only.
Run from backend:  python -m scripts.eval_heldout --cap 300      (build the data first: ml/reviewiq_train.py build)"""
import argparse
import json
import random
from pathlib import Path

from app.core import thresholds as T
from app.services import ablation as A
from app.services import evaluation as E
from app.services import sentiment
from app.services.fusion import ensemble
from app.services.routing import MEMBERS, group_of

DATA = Path("../ml/data")
OUT = Path("../ml/out")


def read(name):
    p = DATA / name
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def label_of(r):
    if r["star"] >= 0:
        return E.stars_to_label(r["star"] + 1)
    return ("neg", "neu", "pos")[r["pol"]]


def predict(key, rows):
    texts = [r["text"] for r in rows]
    if not texts:
        return []
    if key == "tfidf":
        return sentiment.get_scorer("tfidf").predict(texts)
    return sentiment.predict(texts, 32, key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=300, help="max rows per test set and route group")
    a = ap.parse_args()
    rng = random.Random(7)

    def take(rows):
        rows = list(rows)
        rng.shuffle(rows)
        return rows[: a.cap]

    seen, unseen, val_all = read("test_seen.jsonl"), read("test_unseen.jsonl"), read("val.jsonl")
    if not seen:
        print("No held-out data in ml/data. Run: cd ..\\ml ; python reviewiq_train.py build")
        return
    sets = {
        "seen categories (stars)": [r for r in seen if r["star"] >= 0],
        "unseen categories (stars)": [r for r in unseen if r["star"] >= 0],
        "polarity (tweets, Hindi)": [r for r in seen if r["star"] < 0],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    for g in MEMBERS:
        members = [k for k in MEMBERS[g] if sentiment.available(k)]
        if not members:
            continue
        vrows = take([r for r in val_all if group_of(r["lang"]) == g])
        weights = {k: 1.0 for k in members}
        vprobs = {}
        for k in list(members):
            try:
                vprobs[k] = predict(k, vrows)
            except Exception as e:
                print(f"[{g}] skipping {k}: {type(e).__name__}: {str(e)[:120]}")
                members.remove(k)
        if len(vrows) >= T.MIN_VAL_PER_GROUP and members:
            gold = [label_of(r) for r in vrows]
            f1s = {k: E.macro_f1(gold, [E.argmax_label(*p[:3]) for p in vprobs[k]]) for k in members}
            if all(v for v in f1s.values()):
                weights = f1s
        else:
            print(f"[{g}] {len(vrows)} validation rows (< {T.MIN_VAL_PER_GROUP}): equal weights")
        print(f"\n=== route group {g}: models {members}, weights { {k: round(v, 3) for k, v in weights.items()} }")

        for sname, rows in sets.items():
            rows_g = take([r for r in rows if group_of(r["lang"]) == g])
            if len(rows_g) < 10 or not members:
                continue
            gold = [label_of(r) for r in rows_g]
            probs = {k: predict(k, rows_g) for k in members}

            def ens(subset):
                return [E.argmax_label(*ensemble([probs[k][i][:3] for k in subset], [weights[k] for k in subset]))
                        for i in range(len(rows_g))]

            systems = {k: [E.argmax_label(*p[:3]) for p in probs[k]] for k in members}
            if len(members) > 1:
                systems["ensemble (all)"] = ens(members)
                for k in members:
                    rest = [m for m in members if m != k]
                    if len(rest) > 1:
                        systems[f"ensemble without {k}"] = ens(rest)
            print(f"\n{sname}, n={len(rows_g)}")
            table = []
            for name, pred in systems.items():
                f1, acc, ci = E.macro_f1(gold, pred), E.accuracy(gold, pred), E.bootstrap_macro_f1(gold, pred)
                rng_txt = f"{ci[0]:.2f}-{ci[1]:.2f}" if ci else "-"
                print(f"  {name:28s} macro F1 {f1:.3f} ({rng_txt})  accuracy {acc:.3f}")
                table.append({"system": name, "macro_f1": f1, "accuracy": acc, "ci": ci})
            if "ensemble (all)" in systems:
                best = max(members, key=lambda k: E.macro_f1(gold, systems[k]) or 0)
                d = A.paired_bootstrap_diff(dict(enumerate(gold)), dict(enumerate(systems["ensemble (all)"])),
                                            dict(enumerate(systems[best])))
                if d:
                    print(f"  ensemble minus best single ({best}): {d['diff']:+.3f} -> {d['verdict']}")
                    table.append({"ensemble_vs_best_single": best, **{k: d[k] for k in ("diff", "lo", "hi", "verdict")}})
            results.setdefault(g, {})[sname] = table
    (OUT / "heldout_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\nsaved", OUT / "heldout_results.json")
    print("Say it honestly: if the ensemble does not clearly beat the best single model, the gain is within noise.")


if __name__ == "__main__":
    main()
