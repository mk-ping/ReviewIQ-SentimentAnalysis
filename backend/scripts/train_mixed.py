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
