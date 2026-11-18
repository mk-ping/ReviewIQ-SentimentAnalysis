"""Measures the model on public datasets whose sentiment was labelled by people, not derived from stars.
Every model on its own, the weighted ensemble the pipeline uses, and the learned stacker when one exists, each with the full metric suite.
Downloads each test set from the Hugging Face Hub (about 1 to 3 minutes each), skips any it cannot load, writes docs/benchmark_results.md.
Run from backend:  python -m scripts.benchmark_labeled --cap 500          (add --only tweet_eval,sst5 to run a few)"""
import argparse
import json
import random
from pathlib import Path

from app.services import benchmark as B
from app.services import metrics as M
from app.services import sentiment
from app.services import stacker as S
from app.services.routing import MEMBERS, group_of
from scripts.eval_heldout import OUT, read

DOCS = Path("../docs")


def load(spec, cap):
    from datasets import load_dataset
    key, hub, cfg, split, kind, lang, note = spec
    ds = load_dataset(hub, cfg, split=split) if cfg else load_dataset(hub, split=split)
    tcol, lcol = B.pick_columns(ds.column_names)
    if tcol is None or lcol is None:
        raise ValueError(f"columns {ds.column_names} not recognised")
    names = getattr(ds.features.get(lcol), "names", None)
    rows = []
    for ex in ds:
        lab = B.polarity(ex[lcol], names, kind, key)
        text = str(ex[tcol] or "").strip()
        if key == "amazon_polarity":
            text = (str(ex.get("title") or "") + ". " + str(ex.get("content") or "")).strip()
        if lab and 3 <= len(text) <= 1500:
            rows.append((text, lab))
    if lang == "hi":
        from app.services import polarity_check as P
        o = P.orientation([(t, {"neg": 0, "pos": 2}[y]) for t, y in rows if y in ("neg", "pos")])
        print(f"  label direction check: {o['verdict']}")
        if o["verdict"] == "inverted":
            rows = [(t, {"neg": "pos", "pos": "neg"}.get(y, y)) for t, y in rows]
            print("  negative and positive were swapped in this dataset; corrected.")
    return B.stratified(rows, cap)


def weights_for(group, members, val_all, cap=600):
    """Same recipe as the pipeline: each model's macro F1 on the validation split. Falls back to equal weights without ml data."""
    from scripts.eval_heldout import label_of, predict
    rows = [r for r in val_all if group_of(r.get("lang")) == group][:cap]
    if len(rows) < 30:
        return {k: 1.0 for k in members}
    gold = [label_of(r) for r in rows]
    return {k: M.f_macro(gold, [M.LABELS[max(range(3), key=lambda c: p[c])] for p in predict(k, rows)]) or 1e-3 for k in members}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=500, help="reviews per dataset")
    ap.add_argument("--only", default="", help="comma list of dataset keys")
    ap.add_argument("--final", action="store_true", help="run the final-result set (products, restaurants, movies) and write docs/final_result.md")
    a = ap.parse_args()
    wanted = {x.strip() for x in a.only.split(",") if x.strip()}
    if a.final:
        wanted = set(B.FINAL)
    name = "final_result" if a.final else "benchmark_results"
    val_all = read("val.jsonl")
    out_json, md = {}, ["# Final result on public datasets" if a.final else "# Benchmark on human-labelled sentiment datasets", "",
                        *(["Genres the models were built for: product reviews, restaurant reviews and movie reviews. These sets were chosen because they match the training genres, so this is the in-domain result; weaker genres (tweets, finance, other languages) are reported separately in benchmark_results.md. No model, weight or threshold was tuned on these test splits.", ""] if a.final else []),
                        "These datasets carry sentiment labels written by people, so they test the model without relying on star ratings. "
                        "Binary sets (positive or negative) are scored on those two classes only. Intervals are 95% bootstrap ranges.", ""]
    summary = []
    wcache: dict = {}
    for spec in B.DATASETS:
        key, hub, cfg, split, kind, lang, note = spec
        if wanted and key not in wanted:
            continue
        print(f"\n=== {key} ({hub}{' / ' + cfg if cfg else ''})")
        try:
            rows = load(spec, a.cap)
        except Exception as e:
            print(f"  skipped: {type(e).__name__}: {str(e)[:140]}")
            md += [f"### {key}", "", f"Skipped: {type(e).__name__}.", ""]
            continue
        if len(rows) < 30:
            print("  skipped: too few usable rows")
            continue
        g = group_of(lang)
        members = [k for k in MEMBERS[g] if sentiment.available(k)]
        if not members:
            print(f"  skipped: no models available for group {g}")
            continue
        if g not in wcache:
            wcache[g] = weights_for(g, members, val_all)
        w = wcache[g]
        texts = [{"text": t} for t, _ in rows]
        gold = [y for _, y in rows]
        binary = kind == "2"
        probs = {}
        for k in members:
            print(f"  scoring with {k} ...")
            from scripts.eval_heldout import predict
            probs[k] = [tuple(p[:3]) for p in predict(k, texts)]
        systems = {k: B.score_system(gold, probs[k], binary) for k in members}
        systems["weighted ensemble"] = B.score_system(gold, [S.weighted_average(members, {k: probs[k][i] for k in members}, w) for i in range(len(gold))], binary)
        st = S.load(g)
        if st:
            sp = [S.predict(st, {k: probs[k][i] for k in members}, texts[i]["text"]) for i in range(len(gold))]
            if all(sp):
                systems["learned stacker"] = B.score_system(gold, sp, binary)
        mix = {c: gold.count(c) for c in set(gold)}
        md += B.table_for(key, note, len(gold), mix, systems)
        best = max(systems, key=lambda s: systems[s]["macro_f1"] or 0)
        out_json[key] = {"n": len(gold), "mix": mix, "systems": systems, "best": best}
        e = systems["weighted ensemble"]
        summary.append((key, note, len(gold), e["accuracy"], e["macro_f1"], best))
        print(f"  weighted ensemble: accuracy {e['accuracy']:.3f}, macro F1 {e['macro_f1']:.3f}, MCC {e['mcc']:.3f}   (best system: {best})")
    if summary:
        head = ["## Summary (weighted ensemble)", "", "| Dataset | What it is | Reviews | Accuracy | Macro F1 | Best system |", "|---|---|---|---|---|---|"]
        head += [f"| {k} | {n} | {c} | {B.f(a_)} | {B.f(f_)} | {b} |" for k, n, c, a_, f_, b in summary]
        avg_a = sum(s[3] for s in summary) / len(summary)
        avg_f = sum(s[4] for s in summary) / len(summary)
        head += [f"| **average** | | | **{avg_a:.3f}** | **{avg_f:.3f}** | |", ""]
        md = md[:4] + head + md[4:]
    DOCS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    (DOCS / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / f"{name}.json").write_text(json.dumps(out_json, indent=2, default=str), encoding="utf-8")
    print("\nwrote", DOCS / f"{name}.md")


if __name__ == "__main__":
    main()
