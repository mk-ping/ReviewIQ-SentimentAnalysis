# Step 37: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Benchmark on public datasets whose sentiment labels were given by people (not derived from star ratings).
Pure helpers: label mapping, group choice, scoring and the markdown table. The script scripts/benchmark_labeled.py does the downloading."""
from app.services import metrics as M

# (key, hub id, config, split, label kind, language, note). kind: 3 = neg/neu/pos, 5 = five levels, 2 = binary.
DATASETS = [
    ("tweet_eval", "cardiffnlp/tweet_eval", "sentiment", "test", "3", "en", "Tweets, 3 classes, people-labelled (SemEval)"),
    ("tweet_sentiment", "mteb/tweet_sentiment_extraction", None, "test", "3", "en", "Tweets, 3 classes, people-labelled"),
    ("sst5", "SetFit/sst5", None, "test", "5", "en", "Movie sentences, 5 levels collapsed to 3"),
    ("sst2", "stanfordnlp/sst2", None, "validation", "2", "en", "Movie sentences, positive or negative"),
    ("yelp_polarity", "fancyzhx/yelp_polarity", None, "test", "2", "en", "Restaurant reviews, positive or negative"),
    ("amazon_polarity", "fancyzhx/amazon_polarity", None, "test", "2", "en", "Product reviews, positive or negative"),
    ("financial_news", "zeroshot/twitter-financial-news-sentiment", None, "validation", "3", "en", "Finance tweets, 3 classes"),
    ("multilingual_hi", "tyqiangz/multilingual-sentiment-datasets", "hindi", "test", "3", "hi", "Hindi, 3 classes"),
    ("multilingual_es", "tyqiangz/multilingual-sentiment-datasets", "spanish", "test", "3", "es", "Spanish, 3 classes"),
    ("multilingual_de", "tyqiangz/multilingual-sentiment-datasets", "german", "test", "3", "de", "German, 3 classes"),
]
TEXT_COLS = ("text", "sentence", "content", "review", "tweet", "headline")
LABEL_COLS = ("label", "label_text", "sentiment", "labels")
FALLBACK = {"3": ("neg", "neu", "pos"), "5": ("neg", "neg", "neu", "pos", "pos"), "2": ("neg", "pos")}


def polarity(value, names, kind: str) -> str | None:
    """neg, neu or pos for one raw label. names: the dataset's own label names when it has them."""
    if isinstance(value, str) and not value.isdigit():
        s = value.lower()
    elif names is not None and 0 <= int(value) < len(names):
        s = str(names[int(value)]).lower()
    else:
        seq = FALLBACK.get(kind)
        try:
            return seq[int(value)] if seq else None
        except (ValueError, IndexError):
            return None
    if "neg" in s or "bear" in s:
        return "neg"
    if "pos" in s or "bull" in s:
        return "pos"
    if "neu" in s:
        return "neu"
    return None


def pick_columns(columns: list[str]) -> tuple[str | None, str | None]:
    low = {c.lower(): c for c in columns}
    return next((low[c] for c in TEXT_COLS if c in low), None), next((low[c] for c in LABEL_COLS if c in low), None)


def stratified(rows: list[tuple], cap: int, seed: int = 7) -> list[tuple]:
    """Up to cap rows with the label mix kept. Rows are (text, label)."""
    import random
    rng = random.Random(seed)
    by: dict = {}
    for r in rows:
        by.setdefault(r[1], []).append(r)
    total = len(rows)
    out = []
    for lab, rs in by.items():
        rng.shuffle(rs)
        out += rs[: max(1, round(cap * len(rs) / total))] if total > cap else rs
    rng.shuffle(out)
    return out[:cap]


def decide(probs: tuple, binary: bool) -> str:
    """The label from (p_neg, p_neu, p_pos). Binary datasets have no neutral, so only negative and positive compete."""
    if binary:
        return "neg" if probs[0] >= probs[2] else "pos"
    return M.LABELS[max(range(3), key=lambda c: probs[c])]


def score_system(gold: list[str], probs: list[tuple], binary: bool) -> dict:
    pred = [decide(p, binary) for p in probs]
    if binary:
        probs = [(p[0], 0.0, p[2]) if (p[0] + p[2]) > 0 else (0.5, 0.0, 0.5) for p in probs]
        probs = [(a / (a + c), 0.0, c / (a + c)) for a, _, c in probs]
    r = M.report(gold, pred, probs)
    r["macro_f1_ci"] = M.bootstrap_ci(M.f_macro, gold, pred)
    r["accuracy_ci"] = M.bootstrap_ci(M.f_acc, gold, pred)
    return r


def f(x, k=3):
    return "-" if x is None else f"{x:.{k}f}"


def table_for(name: str, note: str, n: int, mix: dict, systems: dict) -> list[str]:
    """Markdown block for one dataset. systems: label -> report dict."""
    L = [f"### {name}", "", f"{note}. {n} reviews ({', '.join(f'{k} {v}' for k, v in sorted(mix.items()))}).", "",
         "| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |", "|---|---|---|---|---|---|---|---|---|"]
    for lab, r in systems.items():
        ci = r.get("accuracy_ci")
        L.append(f"| {lab} | {f(r['accuracy'])} | {'-' if not ci else f'{ci[0]:.3f} to {ci[1]:.3f}'} | {f(r['macro_f1'])} | {f(r['mcc'])} | {f(r['kappa'])} | "
                 f"{f(r.get('auc_ovr'))} | {f(r.get('calibration', {}).get('ece'), 4)} | {f(r['opposite_error_rate'])} |")
    return L + [""]
'@ | Set-Content -Encoding ascii backend\app\services\benchmark.py

@'
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
        lab = B.polarity(ex[lcol], names, kind)
        text = str(ex[tcol] or "").strip()
        if key == "amazon_polarity":
            text = (str(ex.get("title") or "") + ". " + str(ex.get("content") or "")).strip()
        if lab and 3 <= len(text) <= 1500:
            rows.append((text, lab))
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
    a = ap.parse_args()
    wanted = {x.strip() for x in a.only.split(",") if x.strip()}
    val_all = read("val.jsonl")
    out_json, md = {}, ["# Benchmark on human-labelled sentiment datasets", "",
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
            sp = [S.predict(st, {k: probs[k][i] for k in members}) for i in range(len(gold))]
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
    (DOCS / "benchmark_results.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "benchmark_results.json").write_text(json.dumps(out_json, indent=2, default=str), encoding="utf-8")
    print("\nwrote", DOCS / "benchmark_results.md")


if __name__ == "__main__":
    main()
'@ | Set-Content -Encoding ascii backend\scripts\benchmark_labeled.py

@'
"""Offline checks for the benchmark helpers (no downloads)."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import benchmark as B

assert B.polarity(0, ["negative", "neutral", "positive"], "3") == "neg"
assert B.polarity(2, ["negative", "neutral", "positive"], "3") == "pos"
assert B.polarity(1, None, "3") == "neu"
assert B.polarity(0, None, "5") == "neg" and B.polarity(3, None, "5") == "pos" and B.polarity(2, None, "5") == "neu"
assert B.polarity(1, None, "2") == "pos" and B.polarity("Bearish", None, "3") == "neg"
assert B.polarity("positive", None, "3") == "pos" and B.polarity(9, None, "3") is None
assert B.pick_columns(["idx", "Sentence", "label"]) == ("Sentence", "label")
assert B.pick_columns(["a", "b"]) == (None, None)

rng = random.Random(1)
rows = [("t%d" % i, rng.choice(["neg", "pos", "pos", "neu"])) for i in range(2000)]
s = B.stratified(rows, 400)
assert len(s) <= 400 and abs(sum(1 for r in s if r[1] == "pos") / len(s) - 0.5) < 0.06
assert len(B.stratified(rows[:50], 400)) == 50

assert B.decide((0.5, 0.4, 0.1), True) == "neg" and B.decide((0.3, 0.6, 0.1), False) == "neu"
gold = ["pos"] * 60 + ["neg"] * 40
good = [(0.1, 0.1, 0.8)] * 54 + [(0.8, 0.1, 0.1)] * 6 + [(0.8, 0.1, 0.1)] * 36 + [(0.1, 0.1, 0.8)] * 4
r = B.score_system(gold, good, True)
assert abs(r["accuracy"] - 0.9) < 1e-9 and r["accuracy_ci"][0] < 0.9 < r["accuracy_ci"][1] + 1e-9
assert r["per_class"]["neu"]["support"] == 0
# a model that predicts mostly neutral is not penalised on binary sets: only neg/pos compete
r2 = B.score_system(gold, [(0.2, 0.7, 0.1)] * 100, True)
assert r2["confusion"][1] == [0, 0, 0]
md = "\n".join(B.table_for("demo", "Demo set", 100, {"pos": 60, "neg": 40}, {"a": r, "b": r2}))
assert "| a |" in md and "| b |" in md
print("benchmark checks ok")
'@ | Set-Content -Encoding ascii backend\tests\check_benchmark.py

@'
print("Step 37: no existing files patched.")
'@ | Set-Content -Encoding ascii patch_step37.py
python patch_step37.py
Remove-Item patch_step37.py

Write-Host 'Step 37 files written.'
