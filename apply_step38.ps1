# Step 38: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Mixed-genre stacker: learns from reviews, tweets, movie sentences and finance headlines together, with text clues
(length, hashtags, social flag) so each model can be trusted differently per kind of text. Pure functions, no downloads.
Used by scripts/train_mixed.py. The result is applied only when it beats today's weighted average and does not hurt reviews."""
from datetime import datetime, timezone

from app.services import metrics as M
from app.services import stacker as S
from app.services.ablation import paired_bootstrap_diff

REVIEW_SOURCE = "reviews"
MAX_REVIEW_DROP = 0.01   # the new stacker may not lose more than this macro F1 on star-derived reviews


def label_of(p) -> str:
    return M.LABELS[max(range(3), key=lambda c: p[c])]


def per_source(gold, pred, sources) -> dict:
    out = {}
    for s in sorted(set(sources)):
        idx = [i for i, x in enumerate(sources) if x == s]
        g, p = [gold[i] for i in idx], [pred[i] for i in idx]
        out[s] = {"n": len(idx), "accuracy": M.f_acc(g, p), "macro_f1": M.f_macro(g, p)}
    return out


def _oof(members, probs, texts, gold, meta, cfg, seed):
    X = [S.features(members, {k: probs[k][i] for k in members}, texts[i], meta) for i in range(len(gold))]
    return X, S.cv_labels(X, gold, members, 5, seed, *cfg)


def fit_mixed(members: list[str], probs: dict, texts: list[str], gold: list[str], sources: list[str], weights: dict) -> dict:
    """probs[member] = list of (p_neg, p_neu, p_pos) per row. Returns the stacker (with the evidence) plus per-source tables."""
    n = len(gold)
    if n < 60 or len(set(gold)) < 3:
        return {"model": None, "applied": False, "reason": "needs 60+ rows with all three classes"}
    base = [label_of(S.weighted_average(members, {k: probs[k][i] for k in members}, weights)) for i in range(n)]
    # choose settings on one set of folds, judge on different folds
    best = max(S.GRID, key=lambda cfg: M.f_macro(gold, _oof(members, probs, texts, gold, True, cfg, 7)[1]))
    X, oof = _oof(members, probs, texts, gold, True, best, 11)
    _, oof_plain = _oof(members, probs, texts, gold, False, best, 11)
    d = paired_bootstrap_diff(dict(enumerate(gold)), dict(enumerate(oof)), dict(enumerate(base)))
    ps_base, ps_new, ps_plain = per_source(gold, base, sources), per_source(gold, oof, sources), per_source(gold, oof_plain, sources)
    table = {s: {"weighted_average": ps_base[s], "stacker": ps_new[s], "stacker_without_text_clues": ps_plain[s]} for s in ps_base}
    rv = ps_new.get(REVIEW_SOURCE), ps_base.get(REVIEW_SOURCE)
    hurts_reviews = bool(rv[0] and rv[1] and rv[0]["macro_f1"] < rv[1]["macro_f1"] - MAX_REVIEW_DROP)
    ok_gain = bool(d) and n >= S.MIN_ROWS and d["lo"] > 0 and d["diff"] >= S.MIN_GAIN
    applied = ok_gain and not hurts_reviews
    reason = ("beats the weighted average across genres without hurting reviews" if applied else
              "it lowers macro F1 on reviews, so it is not used" if ok_gain and hurts_reviews else
              f"only {n} rows (need {S.MIN_ROWS})" if n < S.MIN_ROWS else
              f"no clear gain ({d['diff']:+.3f}, interval {d['lo']:+.3f} to {d['hi']:+.3f})" if d else "could not compare")
    model = S.fit(X, gold, members, *best, meta=True)
    model.update({"applied": applied, "reason": reason, "n_val": n, "cv_macro_f1_stacker": d["f1_a"] if d else None,
                  "cv_macro_f1_weighted_average": d["f1_b"] if d else None, "cv_diff": d["diff"] if d else None,
                  "cv_interval": [d["lo"], d["hi"]] if d else None, "sources": sorted(set(sources)), "trained_on": "mixed genres",
                  "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"model": model, "applied": applied, "reason": reason, "per_source": table, "overall": {
        "weighted_average": M.report(gold, base), "stacker": M.report(gold, oof), "paired": d}}


def md_table(res: dict) -> list[str]:
    L = ["| Source | Rows | Weighted avg acc | Stacker acc | Weighted avg F1 | Stacker F1 | Stacker without text clues F1 |", "|---|---|---|---|---|---|---|"]
    for s, t in res["per_source"].items():
        a, b, c = t["weighted_average"], t["stacker"], t["stacker_without_text_clues"]
        L.append(f"| {s} | {a['n']} | {a['accuracy']:.3f} | {b['accuracy']:.3f} | {a['macro_f1']:.3f} | {b['macro_f1']:.3f} | {c['macro_f1']:.3f} |")
    return L
'@ | Set-Content -Encoding ascii backend\app\services\mixed.py

@'
"""CPU-only accuracy boost for other genres. Uses the TRAIN splits of public, human-labelled sentiment sets (tweets, movie
sentences, finance headlines, restaurant and product reviews), which are separate from the TEST splits that benchmark_labeled.py scores.
  1. retrains the TF-IDF model on part A of those rows plus your review data (kept only if reviews do not get worse)
  2. scores part B (rows the TF-IDF never saw) and your validation reviews with every available model
  3. trains one stacker that also reads text clues (short, hashtags, ...), judged by cross-validation per genre
Nothing is applied unless it passes its gate. Scores are cached in ml/out/mixed_cache.json, so a re-run is fast.
Run from backend:  python -m scripts.train_mixed --per-set 1400        (about 15 to 40 minutes on a laptop CPU, first run)"""
import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

from app.core.config import settings
from app.services import benchmark as B
from app.services import metrics as M
from app.services import mixed as X
from app.services import sentiment
from app.services.routing import MEMBERS
from scripts.eval_heldout import OUT, label_of, predict, read

SOURCES = ["tweet_eval", "tweet_sentiment", "sst5", "sst2", "yelp_polarity", "amazon_polarity", "financial_news"]
CACHE = OUT / "mixed_cache.json"
DOCS = Path("../docs")


def load_train(spec, cap):
    """Streams the train split, so a 3-million-row set is never downloaded whole."""
    from datasets import load_dataset
    key, hub, cfg, _split, kind, _lang, _note = spec
    ds = load_dataset(hub, cfg, split="train", streaming=True) if cfg else load_dataset(hub, split="train", streaming=True)
    ds = ds.shuffle(seed=7, buffer_size=10000)
    cols = list(ds.features) if getattr(ds, "features", None) else None
    names = None
    rows, seen = [], 0
    for ex in ds:
        if cols is None:
            cols = list(ex)
        tcol, lcol = B.pick_columns(cols)
        if tcol is None or lcol is None:
            raise ValueError(f"columns {cols} not recognised")
        if names is None:
            names = getattr(ds.features.get(lcol), "names", None) if getattr(ds, "features", None) else None
            names = names or []
        seen += 1
        text = str(ex[tcol] or "").strip()
        if key == "amazon_polarity":
            text = (str(ex.get("title") or "") + ". " + str(ex.get("content") or "")).strip()
        lab = B.polarity(ex[lcol], names or None, kind, key)
        if lab and 3 <= len(text) <= 1500:
            rows.append((text, lab))
        if len(rows) >= cap * 2 or seen > cap * 40:
            break
    return B.stratified(rows, cap)


def tfid(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


def cached_probs(key, rows, cache):
    c = cache.setdefault(key, {})
    todo = [(i, r) for i, r in enumerate(rows) if tfid(r["text"]) not in c]
    if todo:
        print(f"    scoring {len(todo)} rows with {key} ...")
        for (i, r), p in zip(todo, predict(key, [r for _, r in todo])):
            c[tfid(r["text"])] = [float(x) for x in p[:3]]
    return [tuple(c[tfid(r["text"])]) for r in rows]


def make_pipe():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=60000, sublinear_tf=True,
                                         token_pattern=r"[^\s.,!?;:()\[\]\"]+"), LogisticRegression(max_iter=1500, class_weight="balanced"))


def tfidf_labels(pipe, texts):
    return list(pipe.predict(texts))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-set", type=int, default=1400, help="rows per dataset; half trains the TF-IDF, half trains the stacker")
    ap.add_argument("--review-cap", type=int, default=1400, help="validation reviews added to the stacker data")
    ap.add_argument("--skip-tfidf", action="store_true", help="do not retrain the TF-IDF")
    ap.add_argument("--only", default="", help="comma list of dataset keys")
    a = ap.parse_args()
    wanted = {x.strip() for x in a.only.split(",") if x.strip()}
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)

    pool = {}
    for spec in B.DATASETS:
        if spec[0] not in SOURCES or (wanted and spec[0] not in wanted):
            continue
        print(f"loading train split of {spec[0]} ...")
        try:
            got = load_train(spec, a.per_set)
            if len(got) < 40:
                print(f"  skipped: only {len(got)} usable rows (labels or columns not recognised)")
                continue
            pool[spec[0]] = got
        except Exception as e:
            print(f"  skipped: {type(e).__name__}: {str(e)[:120]}")
    if not pool:
        print("No dataset could be loaded. Check the internet connection and that 'datasets' is installed (pip install datasets).")
        return
    part_a, part_b = [], []
    for src, rows in pool.items():
        rows = list(rows)
        rng.shuffle(rows)
        h = len(rows) // 2
        part_a += [(t, y) for t, y in rows[:h]]
        part_b += [(src, t, y) for t, y in rows[h:]]
        print(f"  {src}: {len(rows)} rows, {len(rows[:h])} for TF-IDF, {len(rows) - h} for the stacker")

    # validation reviews (stars turned into labels) are the 'reviews' source
    val_all = [r for r in read("val.jsonl") if (r.get("lang") or "en") == "en"]
    rng.shuffle(val_all)
    val_rows = val_all[: a.review_cap]
    train_json = [r for r in read("train.jsonl") if (r.get("lang") or "en") == "en"]
    if not val_rows:
        print("Note: no ml/data/val.jsonl (run 'python reviewiq_train.py build' in ml). The stacker will have no review guard.")

    # 1. TF-IDF on more genres, gated
    if not a.skip_tfidf and sentiment.available("tfidf"):
        import joblib
        old = joblib.load(settings.tfidf_path)
        rev = [(r["text"], label_of(r)) for r in rng.sample(train_json, min(len(train_json), 8000))] if train_json else []
        data = part_a + rev
        print(f"\nretraining TF-IDF on {len(data)} rows ({len(part_a)} from other genres, {len(rev)} reviews)")
        new = make_pipe().fit([t for t, _ in data], [y for _, y in data])
        rep = {}
        for name, pipe in (("current", old), ("retrained", new)):
            row = {}
            for src in pool:
                g = [y for s, t, y in part_b if s == src]
                if not g:
                    continue
                row[src] = M.f_macro(g, tfidf_labels(pipe, [t for s, t, y in part_b if s == src]))
            if val_rows:
                row["reviews"] = M.f_macro([label_of(r) for r in val_rows], tfidf_labels(pipe, [r["text"] for r in val_rows]))
            rep[name] = row
        for src in rep["current"]:
            print(f"    {src:>16}: macro F1 {rep['current'][src]:.3f} -> {rep['retrained'][src]:.3f}")
        genres = [s for s in rep["current"] if s != "reviews"] or ["reviews"]
        gain = sum(rep["retrained"][s] - rep["current"][s] for s in genres) / len(genres)
        drop = rep["current"].get("reviews", 0) - rep["retrained"].get("reviews", 0)
        if gain > 0.01 and drop <= 0.02:
            p = Path(settings.tfidf_path)
            shutil.copy2(p, p.with_suffix(".bak"))
            joblib.dump(new, p)
            sentiment._cache.pop("tfidf", None)
            print(f"  TF-IDF replaced (average gain {gain:+.3f} on other genres, reviews change {-drop:+.3f}). Old file kept as {p.with_suffix('.bak').name}.")
        else:
            print(f"  TF-IDF kept as it was (gain {gain:+.3f}, reviews change {-drop:+.3f}).")
        (OUT / "tfidf_retrain.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")

    # 2. score the stacker rows
    members = [k for k in MEMBERS["english"] if sentiment.available(k)]
    if len(members) < 2:
        print(f"Need at least two English models, have {members}.")
        return
    rows = [{"text": t} for _, t, _ in part_b] + [{"text": r["text"]} for r in val_rows]
    gold = [y for _, _, y in part_b] + [label_of(r) for r in val_rows]
    src = [s for s, _, _ in part_b] + [X.REVIEW_SOURCE] * len(val_rows)
    texts = [r["text"] for r in rows]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    print(f"\nscoring {len(rows)} rows with {members}")
    probs = {}
    for k in members:
        if k == "tfidf":
            cache.pop("tfidf", None)          # the TF-IDF may have just changed, so never reuse its cached scores
        probs[k] = cached_probs(k, rows, cache)
    CACHE.write_text(json.dumps(cache), encoding="utf-8")

    # weights = each model's macro F1 on the review rows, the same recipe the pipeline uses
    ridx = [i for i, s in enumerate(src) if s == X.REVIEW_SOURCE] or list(range(len(rows)))
    weights = {k: M.f_macro([gold[i] for i in ridx], [X.label_of(probs[k][i]) for i in ridx]) or 1e-3 for k in members}
    print("weights:", {k: round(v, 3) for k, v in weights.items()})

    # 3. the stacker
    res = X.fit_mixed(members, probs, texts, gold, src, weights)
    print(f"\nStacker applied: {res['applied']} ({res['reason']})")
    if res.get("model") is None:
        return
    for line in X.md_table(res):
        print(line)
    sp = OUT / "stacker_english.json"
    if sp.exists():
        shutil.copy2(sp, sp.with_suffix(".bak"))
    sp.write_text(json.dumps(res["model"], indent=2), encoding="utf-8")
    (OUT / "mixed_results.json").write_text(json.dumps({"weights": weights, **{k: res[k] for k in ("applied", "reason", "per_source", "overall")}}, indent=2, default=str), encoding="utf-8")
    DOCS.mkdir(exist_ok=True)
    o = res["overall"]
    md = ["# Mixed-genre training results (cross-validated, rows the models never trained on)", "",
          f"Result: **{'applied' if res['applied'] else 'not applied'}** - {res['reason']}.", "",
          f"Overall macro F1: weighted average {o['weighted_average']['macro_f1']:.3f}, stacker {o['stacker']['macro_f1']:.3f}. "
          f"Accuracy {o['weighted_average']['accuracy']:.3f} to {o['stacker']['accuracy']:.3f}.", ""] + X.md_table(res)
    (DOCS / "mixed_training.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\nwrote", DOCS / "mixed_training.md")
    print("Next: python -m scripts.benchmark_labeled --cap 500   (the TEST splits, to see the real before and after)")


if __name__ == "__main__":
    main()
'@ | Set-Content -Encoding ascii backend\scripts\train_mixed.py

@'
"""Offline check: with two models that are each good on a different kind of text, the text-aware stacker beats the weighted average."""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import mixed as X
from app.services import stacker as S

rng = random.Random(3)
texts, gold, src = [], [], []
probs = {"a": [], "b": []}


def noisy(label, acc):
    c = ("neg", "neu", "pos").index(label)
    if rng.random() > acc:
        c = rng.choice([i for i in range(3) if i != c])
    z = [rng.gauss(0, 0.6) for _ in range(3)]
    z[c] += 2.0
    e = [math.exp(v) for v in z]
    return tuple(v / sum(e) for v in e)


for i in range(1600):
    social = i % 2 == 0
    lab = rng.choice(["neg", "neu", "pos"])
    texts.append("so good #love @you" if social else "The battery lasts the whole day and the screen is sharp and bright, the speakers are clear and loud, delivery was fast, setup took five minutes, and support answered quickly, so I would buy again for sure.")
    gold.append(lab)
    src.append("tweets" if social else X.REVIEW_SOURCE)
    probs["a"].append(noisy(lab, 0.85 if social else 0.45))   # a: good on tweets
    probs["b"].append(noisy(lab, 0.45 if social else 0.85))   # b: good on reviews
res = X.fit_mixed(["a", "b"], probs, texts, gold, src, {"a": 0.6, "b": 0.6})
t = res["per_source"]
assert res["model"] and res["model"]["meta"] is True
assert res["applied"], res["reason"]
for s in ("tweets", X.REVIEW_SOURCE):
    assert t[s]["stacker"]["macro_f1"] > t[s]["weighted_average"]["macro_f1"] + 0.03, (s, t[s])
assert t["tweets"]["stacker"]["macro_f1"] > t["tweets"]["stacker_without_text_clues"]["macro_f1"]
# the saved model works through the production hook, and falls back when the text is missing
m = res["model"]
p = S.predict(m, {"a": probs["a"][0], "b": probs["b"][0]}, texts[0])
assert p and abs(sum(p) - 1) < 1e-9
assert S.predict(m, {"a": probs["a"][0], "b": probs["b"][0]}) is None
# old review-only stackers still load without text
old = S.fit([S.features(["a", "b"], {"a": probs["a"][i], "b": probs["b"][i]}) for i in range(300)], gold[:300], ["a", "b"])
assert S.predict(old, {"a": probs["a"][0], "b": probs["b"][0]}) is not None
assert len(S.meta_features("Great #phone!")) == 9
print("\n".join(X.md_table(res)))
print("mixed checks ok")
'@ | Set-Content -Encoding ascii backend\tests\check_mixed.py

@'
# Step 38: one command for the whole CPU accuracy boost, then the before/after benchmark.
# Usage (from the repo root):  .\tools\boost_accuracy.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
& .\.venv\Scripts\Activate.ps1
pip install datasets scikit-learn | Out-Null
Copy-Item ..\docs\benchmark_results.md ..\docs\benchmark_before.md -ErrorAction SilentlyContinue
python -m scripts.train_mixed --per-set 1400
python -m scripts.benchmark_labeled --cap 500
Write-Host ""
Write-Host "Done. Compare docs\benchmark_before.md with docs\benchmark_results.md, and read docs\mixed_training.md."
'@ | Set-Content -Encoding ascii tools\boost_accuracy.ps1

@'
import pathlib


def edit(rel, pairs, marker):
    p = pathlib.Path(rel)
    if not p.exists():
        print("skipped (not found):", rel)
        return
    t = p.read_text(encoding="utf-8")
    if marker in t:
        return
    for a, b in pairs:
        assert a in t, f"{rel}: text not found: {a[:70]!r}"
        t = t.replace(a, b, 1)
    p.write_text(t, encoding="utf-8")


# stacker: optional text features so one model can behave differently on tweets, headlines and reviews
edit("backend/app/services/stacker.py", [
    ('def features(members: list[str], probs: dict) -> list[float] | None:\n    row: list[float] = []\n    for k in members:\n        if k not in probs:\n            return None\n        row += [math.log(max(float(x), 1e-6)) for x in probs[k][:3]]',
     'def meta_features(text: str) -> list[float]:\n'
     '    """Eight cheap clues about the kind of text: length, hashtags or mentions, links, exclamations, questions, capitals, numbers, and a social flag."""\n'
     '    t = text or ""\n    n = len(t.split())\n    letters = [c for c in t if c.isalpha()]\n'
     '    caps = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0\n'
     '    social = 1.0 if ("#" in t or "@" in t or n <= 20) else 0.0\n'
     '    return [math.log1p(n) / 4, 1.0 if n <= 15 else 0.0, 1.0 if ("#" in t or "@" in t) else 0.0, 1.0 if "http" in t else 0.0,\n'
     '            min(t.count("!"), 3) / 3, 1.0 if "?" in t else 0.0, caps, 1.0 if any(c.isdigit() or c in "$%" for c in t) else 0.0, social]\n\n\n'
     'def features(members: list[str], probs: dict, text: str | None = None, meta: bool = False) -> list[float] | None:\n    row: list[float] = []\n    for k in members:\n        if k not in probs:\n            return None\n        row += [math.log(max(float(x), 1e-6)) for x in probs[k][:3]]\n'
     '    if meta:\n        if text is None:\n            return None\n        m = meta_features(text)\n        row += m[:-1] + [m[-1] * v for v in row[:]]   # social text gets its own weight on every model'),
    ('def predict(model: dict, probs: dict) -> tuple[float, float, float] | None:\n    x = features(model["members"], probs)',
     'def predict(model: dict, probs: dict, text: str | None = None) -> tuple[float, float, float] | None:\n    x = features(model["members"], probs, text, bool(model.get("meta")))'),
    ('def refine(group: str, probs: dict, fallback: tuple, folder: Path | None = None) -> tuple:',
     'def refine(group: str, probs: dict, fallback: tuple, folder: Path | None = None, text: str | None = None) -> tuple:'),
    ('    out = predict(m, probs)\n    return out if out else fallback', '    out = predict(m, probs, text)\n    return out if out else fallback'),
    ('def fit(X: list[list[float]], y: list[str], members: list[str], C: float = 1.0, class_weight=None) -> dict | None:',
     'def fit(X: list[list[float]], y: list[str], members: list[str], C: float = 1.0, class_weight=None, meta: bool = False) -> dict | None:'),
    ('"b": [float(clf.intercept_[i]) for i in order], "C": C, "class_weight": class_weight}',
     '"b": [float(clf.intercept_[i]) for i in order], "C": C, "class_weight": class_weight, "meta": meta}'),
], "def meta_features")
# the scorer hands the review text to the stacker
edit("backend/app/services/fusion.py", [
    ('select(Review.review_id, Review.rating_norm, Review.language, Prediction.model_id,', 'select(Review.review_id, Review.rating_norm, Review.language, Review.text_clean, Prediction.model_id,'),
    ('    for rid, st, lang, mid, n, u, p, e in rows:', '    for rid, st, lang, txt, mid, n, u, p, e in rows:'),
    ('d = by.setdefault(rid, {"stars": st, "group": group_of(lang), "preds": {}})', 'd = by.setdefault(rid, {"stars": st, "group": group_of(lang), "text": txt, "preds": {}})'),
    ('{k: d["preds"][k][:3] for k in keys}, (n, u, p))', '{k: d["preds"][k][:3] for k in keys}, (n, u, p), text=d["text"])'),
], 'text=d["text"]')
# benchmark: financial label order, multilingual source, text to stacker
edit("backend/app/services/benchmark.py", [
    ('def polarity(value, names, kind: str) -> str | None:\n    """neg, neu or pos for one raw label. names: the dataset\'s own label names when it has them."""\n',
     'OVERRIDE = {"financial_news": {0: "neg", 1: "pos", 2: "neu"}}   # that dataset codes 0 bearish, 1 bullish, 2 neutral\n\n\n'
     'def polarity(value, names, kind: str, key: str | None = None) -> str | None:\n    """neg, neu or pos for one raw label. names: the dataset\'s own label names when it has them."""\n'
     '    if key in OVERRIDE and str(value).isdigit():\n        return OVERRIDE[key].get(int(value))\n'),
    ('    ("multilingual_hi", "tyqiangz/multilingual-sentiment-datasets", "hindi", "test", "3", "hi", "Hindi, 3 classes"),\n'
     '    ("multilingual_es", "tyqiangz/multilingual-sentiment-datasets", "spanish", "test", "3", "es", "Spanish, 3 classes"),\n'
     '    ("multilingual_de", "tyqiangz/multilingual-sentiment-datasets", "german", "test", "3", "de", "German, 3 classes"),\n',
     '    ("multilingual_hi", "cardiffnlp/tweet_sentiment_multilingual", "hindi", "test", "3", "hi", "Hindi tweets, 3 classes"),\n'
     '    ("multilingual_es", "cardiffnlp/tweet_sentiment_multilingual", "spanish", "test", "3", "es", "Spanish tweets, 3 classes"),\n'
     '    ("multilingual_de", "cardiffnlp/tweet_sentiment_multilingual", "german", "test", "3", "de", "German tweets, 3 classes"),\n'
     '    ("multilingual_fr", "cardiffnlp/tweet_sentiment_multilingual", "french", "test", "3", "fr", "French tweets, 3 classes"),\n'),
], "OVERRIDE")
edit("backend/scripts/benchmark_labeled.py", [
    ('B.polarity(ex[lcol], names, kind)', 'B.polarity(ex[lcol], names, kind, key)'),
    ('sp = [S.predict(st, {k: probs[k][i] for k in members}) for i in range(len(gold))]', 'sp = [S.predict(st, {k: probs[k][i] for k in members}, texts[i]["text"]) for i in range(len(gold))]'),
], "B.polarity(ex[lcol], names, kind, key)")
print("Step 38 patches applied.")
'@ | Set-Content -Encoding ascii patch_step38.py
python patch_step38.py
Remove-Item patch_step38.py

Write-Host 'Step 38 files written.'
