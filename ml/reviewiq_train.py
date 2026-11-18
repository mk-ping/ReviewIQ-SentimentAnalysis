"""ReviewIQ public-source data build for the TF-IDF baseline (fine-tuning and zero-shot commands retired, final pipeline document section 15).

Run from the ml folder (needs: pip install datasets scikit-learn):
    python reviewiq_train.py build
Everything is written under ./data. The TF-IDF baseline is then trained by backend/scripts/train_tfidf.py.

Label scheme: each row has star (0-4 = 1-5 stars, or -1) and pol (0-2 = negative, neutral, positive, or -1).
Training label = star when known, otherwise 5 + pol."""
import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

DATA, OUT = Path("data"), Path("out")
SEED = 7
AMAZON_URL = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/review_categories/{}.jsonl"
AMAZON_TRAIN = ["All_Beauty", "Health_and_Personal_Care", "Appliances", "Software", "Handmade_Products",
                "Electronics", "Home_and_Kitchen", "Grocery_and_Gourmet_Food"]
AMAZON_UNSEEN = ["Tools_and_Home_Improvement", "Clothing_Shoes_and_Jewelry"]  # never trained on
TWEET_LANGS = {"english": "en", "hindi": "hi", "spanish": "es", "french": "fr", "german": "de", "portuguese": "pt"}


# ---------------------------------------------------------------- helpers
def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def keep(t: str) -> bool:
    return 8 <= len(t) <= 3000


def lang_of(t: str, default: str) -> str:
    return "hi" if re.search("[\u0900-\u097F]", t) else default


def row(text, star=-1, pol=-1, src="", group="", lang="en"):
    return {"text": text, "star": star, "pol": pol, "src": src,
            "group": group or hashlib.md5(text.encode()).hexdigest(), "lang": lang_of(text, lang)}


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    return [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]


def collapse_idx(s: int) -> int:
    return 0 if s <= 1 else (1 if s == 2 else 2)


def softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def to3(p5):
    return np.stack([p5[:, :2].sum(1), p5[:, 2], p5[:, 3:].sum(1)], axis=1)


def label_of(r) -> int:
    return r["star"] if r["star"] >= 0 else 5 + r["pol"]


# ---------------------------------------------------------------- loaders
def load_yelp(quota):
    from datasets import load_dataset
    ds = load_dataset("Yelp/yelp_review_full", split="train")
    by = defaultdict(list)
    for i, l in enumerate(ds["label"]):
        by[l].append(i)
    rng, out = random.Random(SEED), []
    for l in range(5):
        sub = ds.select(rng.sample(by[l], min(quota * 2, len(by[l]))))
        got = 0
        for ex in sub:
            t = norm(ex["text"].replace("\\n", " "))
            if keep(t):
                out.append(row(t, star=l, src="yelp", lang="en"))
                got += 1
                if got >= quota:
                    break
    return out


def load_amazon(cat, quota, scan, src_prefix="amazon"):
    """Reads the jsonl straight from the Hub (the dataset script no longer loads) and stops once every star has its quota."""
    got, out, scanned = Counter(), [], 0
    req = urllib.request.Request(AMAZON_URL.format(cat), headers={"User-Agent": "reviewiq-train"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            for line in r:
                scanned += 1
                if scanned > scan or all(got[c] >= quota for c in range(5)):
                    break
                try:
                    d = json.loads(line)
                    star = int(round(float(d.get("rating")))) - 1
                except (ValueError, TypeError):
                    continue
                if not 0 <= star <= 4 or got[star] >= quota:
                    continue
                t = norm(f"{d.get('title') or ''}. {d.get('text') or ''}".strip(" ."))
                if keep(t):
                    out.append(row(t, star=star, src=f"{src_prefix}:{cat}", group=str(d.get("parent_asin") or t[:40]), lang="en"))
                    got[star] += 1
    except Exception as e:
        print(f"  skip {cat}: {type(e).__name__}: {str(e)[:100]}")
    print(f"  {cat}: {len(out)} rows, per star {[got[c] for c in range(5)]}, scanned {min(scanned, scan)}")
    return out


def load_tweets(per_lang):
    from datasets import load_dataset
    out = []
    for name, lang in TWEET_LANGS.items():
        try:
            ds = load_dataset("cardiffnlp/tweet_sentiment_multilingual", name)
        except Exception as e:
            print(f"  skip tweets/{name}: {type(e).__name__}: {str(e)[:100]}")
            continue
        rows = [row(norm(ex["text"]), pol=int(ex["label"]), src=f"tweets:{name}", lang=lang)
                for sp in ds for ex in ds[sp] if keep(norm(ex["text"]))]
        if lang == "hi":
            from polarity_fix import orientation, swap
            o = orientation([(r["text"], r["pol"]) for r in rows])
            print(f"  tweets/hindi label direction check: {o['verdict']}")
            if o["verdict"] == "inverted":
                for r in rows:
                    r["pol"] = swap(r["pol"])
        random.Random(SEED).shuffle(rows)
        out += rows[:per_lang]
        print(f"  tweets/{name}: {len(rows[:per_lang])} rows")
    return out


def load_hindi(n):
    from datasets import load_dataset
    try:
        ds = load_dataset("iam-tsr/hindi-sentiments")
    except Exception as e:
        print(f"  skip hindi-sentiments: {type(e).__name__}: {str(e)[:100]}")
        return []
    d = ds["train"] if "train" in ds else ds[list(ds)[0]]
    cols = d.column_names
    first = d[0]
    print("  hindi-sentiments columns:", cols, "first row:", {k: str(v)[:50] for k, v in first.items()})
    strs = [c for c in cols if isinstance(first[c], str)]
    if not strs:
        print("  skip hindi-sentiments: no text column found")
        return []
    tcol = max(strs, key=lambda c: sum(len(str(d[i][c])) for i in range(min(50, len(d)))))
    lcol = next((c for c in cols if c != tcol and c.lower() in ("label", "labels", "sentiment", "target")), None)
    if not lcol:
        print("  skip hindi-sentiments: no label column found")
        return []
    names = {"negative": 0, "neutral": 1, "positive": 2, "neg": 0, "neu": 1, "pos": 2, "0": 0, "1": 1, "2": 2}
    by = defaultdict(list)
    for ex in d:
        p = names.get(str(ex[lcol]).strip().lower())
        t = norm(str(ex[tcol]))
        if p is not None and keep(t):
            by[p].append(row(t, pol=p, src="hindi-sentiments", lang="hi"))
    from polarity_fix import orientation, swap
    flat = [r for p in range(3) for r in by[p]]
    o = orientation([(r["text"], r["pol"]) for r in flat])
    print(f"  hindi-sentiments label direction check: {o['verdict']} (score {o['score']})")
    if o["verdict"] == "inverted":
        print("  negative and positive were swapped in this dataset; corrected.")
        by = defaultdict(list)
        for r in flat:
            r["pol"] = swap(r["pol"])
            by[r["pol"]].append(r)
    out = []
    for p in range(3):
        random.Random(SEED).shuffle(by[p])
        out += by[p][: n // 3]
    print(f"  hindi-sentiments: {len(out)} rows. Integer labels are read as 0=negative 1=neutral 2=positive: check against the first row above.")
    return out


def load_local(cap):
    """Your own CSVs in data/external (for example a Flipkart export from Kaggle). Needs a text column and a 1-5 rating column."""
    out = []
    for p in sorted(Path("data/external").glob("*.csv")):
        try:
            rows = list(csv.DictReader(open(p, encoding="utf-8-sig", errors="replace", newline="")))
            cols = list(rows[0].keys())
            sample = rows[:200]
            tcol = max(cols, key=lambda c: sum(len(r.get(c) or "") for r in sample))

            def is_star(c):
                vals = [(r.get(c) or "").strip() for r in sample if (r.get(c) or "").strip()]
                ok = [v for v in vals if re.fullmatch(r"[1-5](\.0)?", v)]
                return len(vals) >= 20 and len(ok) / len(vals) > 0.95

            rcol = next((c for c in cols if c != tcol and is_star(c)), None)
            if not rcol:
                print(f"  skip {p.name}: no 1-5 rating column found")
                continue
            got = 0
            random.Random(SEED).shuffle(rows)
            for r in rows:
                t = norm(r.get(tcol) or "")
                v = (r.get(rcol) or "").strip()
                if keep(t) and re.fullmatch(r"[1-5](\.0)?", v):
                    out.append(row(t, star=int(float(v)) - 1, src=f"local:{p.stem}", lang="en"))
                    got += 1
                    if got >= cap:
                        break
            print(f"  {p.name}: {got} rows (text={tcol}, rating={rcol})")
        except Exception as e:
            print(f"  skip {p.name}: {type(e).__name__}: {str(e)[:100]}")
    return out


# ---------------------------------------------------------------- build
def bucket(group: str) -> int:
    return int(hashlib.md5(group.encode()).hexdigest()[:8], 16) % 100


def drop_noise(train, threshold=0.85):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    star = [r for r in train if r["star"] >= 0]
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=200000, sublinear_tf=True),
                         LogisticRegression(max_iter=300, C=2.0))
    proba = cross_val_predict(pipe, [r["text"] for r in star], [r["star"] for r in star],
                              cv=StratifiedKFold(3, shuffle=True, random_state=SEED), method="predict_proba")
    bad = {id(r) for r, p in zip(star, proba) if p.max() >= threshold and abs(int(p.argmax()) - r["star"]) >= 2}
    print(f"  label-noise filter removed {len(bad)} of {len(star)} star rows")
    return [r for r in train if id(r) not in bad]


def cmd_build(a):
    DATA.mkdir(exist_ok=True)
    Path("data/external").mkdir(parents=True, exist_ok=True)
    pool = []
    print("Yelp"); pool += load_yelp(a.yelp_per_star)
    print("Amazon (training categories)")
    for c in AMAZON_TRAIN:
        pool += load_amazon(c, a.amazon_per_star, a.scan)
    print("Amazon (held-out categories, never trained on)")
    unseen = []
    for c in AMAZON_UNSEEN:
        unseen += load_amazon(c, a.unseen_per_star, a.scan, src_prefix="unseen")
    print("Polarity data")
    pool += load_tweets(a.tweets_per_lang)
    pool += load_hindi(a.hindi_total)
    print("Extra datasets")
    from extra_sources import load_extra
    pool += load_extra(a.extra_per_source, row, norm, keep)
    print("Extra genres (hotels, app reviews)")
    from extra_genres import load_genres
    pool += load_genres(a.genre_per_star, row, norm, keep)
    print("Local CSVs (data/external)")
    pool += load_local(a.local_cap)

    seen_text, dedup = set(), []
    for r in unseen + pool:  # unseen first, so held-out texts never leak into training
        k = norm(r["text"]).lower()
        if k not in seen_text:
            seen_text.add(k)
            dedup.append(r)
    unseen = [r for r in dedup if r["src"].startswith("unseen:")]
    pool = [r for r in dedup if not r["src"].startswith("unseen:")]
    train = [r for r in pool if bucket(r["group"]) < 80]
    val = [r for r in pool if 80 <= bucket(r["group"]) < 90]
    test = [r for r in pool if bucket(r["group"]) >= 90]
    print("Removing noisy training labels")
    train = drop_noise(train)
    for name, rows in [("train", train), ("val", val), ("test_seen", test), ("test_unseen", unseen)]:
        write_jsonl(DATA / f"{name}.jsonl", rows)
        print(f"{name}: {len(rows)} rows | star {dict(sorted(Counter(r['star'] + 1 for r in rows if r['star'] >= 0).items()))} "
              f"| polarity {sum(1 for r in rows if r['star'] < 0)} | languages {dict(Counter(r['lang'] for r in rows))}")
    print("sources in train:", dict(Counter(r["src"].split(":")[0] for r in train)))
    print("done. Training set size:", len(train))


# ---------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build"])
    p.add_argument("--yelp-per-star", type=int, default=1500)
    p.add_argument("--amazon-per-star", type=int, default=350)
    p.add_argument("--unseen-per-star", type=int, default=300)
    p.add_argument("--scan", type=int, default=80000, help="max jsonl lines to read per Amazon category")
    p.add_argument("--tweets-per-lang", type=int, default=1200)
    p.add_argument("--hindi-total", type=int, default=6000)
    p.add_argument("--extra-per-source", type=int, default=3000)
    p.add_argument("--local-cap", type=int, default=4000)
    p.add_argument("--genre-per-star", type=int, default=800, help="hotel and app reviews per star")
    cmd_build(p.parse_args())


if __name__ == "__main__":
    main()
