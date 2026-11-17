"""Trains a stacker per route group on the validation split, gates it with cross-validation, and measures it on the
held-out test sets against the weighted average the pipeline uses today. Writes ml/out/stacker_<group>.json (used by the
pipeline only when it passed the gate) and ml/out/stack_results.json (every metric, for the final report).
Run from backend:  python -m scripts.train_stacker --val-cap 1500 --test-cap 600     (build the data first: ml/reviewiq_train.py build)"""
import argparse
import json
import random

from app.core import thresholds as T
from app.services import metrics as M
from app.services import sentiment
from app.services import stacker as S
from app.services.routing import MEMBERS, group_of
from scripts.eval_heldout import OUT, label_of, predict, read


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-cap", type=int, default=1500, help="validation reviews per route group used for training and gating")
    ap.add_argument("--test-cap", type=int, default=600, help="test reviews per set and route group")
    a = ap.parse_args()
    rng = random.Random(7)

    def take(rows, cap):
        rows = list(rows)
        rng.shuffle(rows)
        return rows[:cap]

    seen, unseen, val_all = read("test_seen.jsonl"), read("test_unseen.jsonl"), read("val.jsonl")
    if not val_all or not seen:
        print("No data in ml/data. Run: cd ..\\ml ; python reviewiq_train.py build")
        return
    sets = {"seen categories (stars)": [r for r in seen if r["star"] >= 0],
            "unseen categories (stars)": [r for r in unseen if r["star"] >= 0],
            "polarity (tweets, Hindi)": [r for r in seen if r["star"] < 0]}
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    for g, wanted in MEMBERS.items():
        members = [k for k in wanted if sentiment.available(k)]
        if members != wanted:
            print(f"[{g}] skipped: needs all of {wanted}, available {members}")
            continue
        vrows = take([r for r in val_all if group_of(r["lang"]) == g], a.val_cap)
        if len(vrows) < 30:
            print(f"[{g}] skipped: only {len(vrows)} validation rows")
            continue
        vgold = [label_of(r) for r in vrows]
        vprobs = {k: [tuple(p[:3]) for p in predict(k, vrows)] for k in members}
        weights = {k: M.f_macro(vgold, [M.LABELS[max(range(3), key=lambda c: p[c])] for p in vprobs[k]]) or 1e-3 for k in members}
        res = S.train_group(members, vprobs, vgold, weights)
        print(f"\n=== {g}: {len(vrows)} validation reviews. Stacker applied: {res['applied']} ({res['reason']})")
        if res["model"] is None:
            continue
        (OUT / f"stacker_{g}.json").write_text(json.dumps(res["model"], indent=2), encoding="utf-8")
        for sname, rows in sets.items():
            rows_g = take([r for r in rows if group_of(r["lang"]) == g], a.test_cap)
            if len(rows_g) < 30:
                continue
            gold = [label_of(r) for r in rows_g]
            probs = {k: [tuple(p[:3]) for p in predict(k, rows_g)] for k in members}
            cmp = S.compare(res["model"], members, probs, gold, weights)
            b, s = cmp["weighted_average"], cmp["stacker"]
            print(f"  {sname}, n={len(gold)}: macro F1 {b['macro_f1']:.3f} -> {s['macro_f1']:.3f}, accuracy {b['accuracy']:.3f} -> {s['accuracy']:.3f}, "
                  f"MCC {b['mcc']:.3f} -> {s['mcc']:.3f}, McNemar p={cmp['mcnemar']['p_value']:.3f}")
            results.setdefault(g, {})[sname] = {**cmp, "applied": res["applied"], "weights": weights}
        results.setdefault(g, {})["_gate"] = {k: res["model"].get(k) for k in ("applied", "reason", "n_val", "cv_macro_f1_stacker",
                                                                               "cv_macro_f1_weighted_average", "cv_diff", "cv_interval", "C", "class_weight")}
    (OUT / "stack_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\nsaved", OUT / "stack_results.json")
    print("A stacker is used by the pipeline only when it passed the gate above. The test-set numbers are the honest estimate.")
    print(f"(Validation minimum for applying a stacker: {S.MIN_ROWS} reviews per route group. Group minimum for weights: {T.MIN_VAL_PER_GROUP}.)")


if __name__ == "__main__":
    main()
