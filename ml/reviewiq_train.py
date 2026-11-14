"""ReviewIQ star-engine data build, baselines and fine-tuning.

Run on Google Colab (free GPU) or any machine with a GPU:
    pip install -q transformers datasets scikit-learn accelerate sentencepiece
    python reviewiq_train.py build       # download and balance the datasets
    python reviewiq_train.py baseline    # majority, TF-IDF and pretrained zero-shot baselines
    python reviewiq_train.py train       # fine-tune, calibrate, evaluate, export
    python reviewiq_train.py all
Everything is written under ./data and ./out.

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


# ---------------------------------------------------------------- metrics
def score_star(y, p5):
    from sklearn.metrics import accuracy_score, f1_score
    y, pred = np.array(y), p5.argmax(1)
    y3, pred3 = np.array([collapse_idx(s) for s in y]), to3(p5).argmax(1)
    out = {"n": int(len(y)), "macro_f1_5": f1_score(y, pred, average="macro", labels=list(range(5)), zero_division=0),
           "mae_stars": float(np.abs(pred - y).mean()),
           "macro_f1_3": f1_score(y3, pred3, average="macro", labels=[0, 1, 2], zero_division=0),
           "acc_3": accuracy_score(y3, pred3)}
    return {k: round(float(v), 4) if isinstance(v, float) else v for k, v in out.items()}


def score_pol(y3, p3):
    from sklearn.metrics import accuracy_score, f1_score
    y3, pred3 = np.array(y3), p3.argmax(1)
    return {"n": int(len(y3)), "macro_f1_3": round(float(f1_score(y3, pred3, average="macro", labels=[0, 1, 2], zero_division=0)), 4),
            "acc_3": round(float(accuracy_score(y3, pred3)), 4)}


def eval_sets(a):
    rng = random.Random(SEED)

    def cap(rows):
        rows = list(rows)
        rng.shuffle(rows)
        return rows[: a.eval_cap]
    seen, unseen = read_jsonl(DATA / "test_seen.jsonl"), read_jsonl(DATA / "test_unseen.jsonl")
    return {"seen_stars": cap(r for r in seen if r["star"] >= 0),
            "unseen_categories": cap(r for r in unseen if r["star"] >= 0),
            "polarity": cap(r for r in seen if r["star"] < 0)}


def evaluate(predict5, predict3, sets):
    """predict5(texts) -> (n,5) probabilities or None; predict3(texts) -> (n,3) probabilities."""
    res = {}
    for name, rows in sets.items():
        if not rows:
            continue
        texts = [r["text"] for r in rows]
        if name == "polarity":
            p3 = predict3(texts)
            res[name] = score_pol([r["pol"] for r in rows], p3)
        else:
            y = [r["star"] for r in rows]
            p5 = predict5(texts)
            res[name] = score_star(y, p5) if p5 is not None else score_pol([collapse_idx(s) for s in y], predict3(texts))
    return res


def show(results):
    sets = sorted({s for m in results.values() for s in m})
    print(f"{'model':38}" + "".join(f"{s:>26}" for s in sets))
    for model, per in results.items():
        cells = []
        for s in sets:
            m = per.get(s)
            cells.append(f"{'-':>26}" if not m else f"{'F1(3) ' + str(m['macro_f1_3']) + ' n=' + str(m['n']):>26}")
        print(f"{model:38}" + "".join(cells))
    print("F1(3) = macro F1 after collapsing stars to negative / neutral / positive. 5-class and MAE are in the JSON file.")


# ---------------------------------------------------------------- baselines
def label_to_star(label: str):
    low = label.lower().replace("_", " ")
    if "very" in low and "neg" in low:
        return 1
    if "very" in low and "pos" in low:
        return 5
    return 2 if "neg" in low else 3 if "neu" in low else 4 if "pos" in low else None


def label_to_pol(label: str):
    low = label.lower()
    return 0 if "neg" in low else 1 if "neu" in low else 2 if "pos" in low else None


class HF:
    """A pretrained classifier with its labels mapped to canonical order (stars 1-5, or neg/neu/pos)."""
    def __init__(self, name):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForSequenceClassification.from_pretrained(name).eval()
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.dev)
        id2 = self.model.config.id2label
        self.n = len(id2)
        fn = (lambda l: (label_to_star(l) or 0) - 1) if self.n == 5 else label_to_pol
        self.order = [fn(id2[i]) for i in range(self.n)]
        if sorted(self.order) != list(range(self.n)):
            raise RuntimeError(f"cannot map labels of {name}: {id2}")

    def probs(self, texts, bs=64):
        out = []
        for i in range(0, len(texts), bs):
            enc = self.tok(texts[i:i + bs], truncation=True, max_length=256, padding=True, return_tensors="pt").to(self.dev)
            with self.torch.no_grad():
                p = self.torch.softmax(self.model(**enc).logits, dim=-1).cpu().numpy()
            out.append(p)
        p = np.concatenate(out)
        canon = np.zeros_like(p)
        for src_i, dst_i in enumerate(self.order):
            canon[:, dst_i] = p[:, src_i]
        return canon


def cmd_baseline(a):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    OUT.mkdir(exist_ok=True)
    sets = eval_sets(a)
    train = [r for r in read_jsonl(DATA / "train.jsonl") if r["star"] >= 0]
    results = {}

    majority = Counter(r["star"] for r in train).most_common(1)[0][0]
    one_hot = lambda texts: np.tile(np.eye(5)[majority], (len(texts), 1))
    results["majority class"] = evaluate(one_hot, lambda t: to3(one_hot(t)), sets)

    print("TF-IDF + logistic regression (the plan's benchmark)")
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=300000, sublinear_tf=True),
                         LogisticRegression(max_iter=400, C=2.0, class_weight="balanced"))
    pipe.fit([r["text"] for r in train], [r["star"] for r in train])
    p5 = lambda texts: pipe.predict_proba(texts)
    results["tfidf + logistic regression"] = evaluate(p5, lambda t: to3(p5(t)), sets)

    for name in ("tabularisai/multilingual-sentiment-analysis", "cardiffnlp/twitter-xlm-roberta-base-sentiment"):
        print("zero-shot:", name)
        try:
            m = HF(name)
        except Exception as e:
            print(f"  skipped: {type(e).__name__}: {str(e)[:120]}")
            continue
        if m.n == 5:
            results[name + " (zero-shot)"] = evaluate(m.probs, lambda t, m=m: to3(m.probs(t)), sets)
        else:
            results[name + " (zero-shot)"] = evaluate(lambda t: None, m.probs, sets)
    json.dump(results, open(OUT / "baseline_results.json", "w"), indent=2)
    show(results)


# ---------------------------------------------------------------- training
def ece(conf, correct, bins=10):
    conf, correct, e = np.array(conf), np.array(correct), 0.0
    for b in range(bins):
        m = (conf >= b / bins) & (conf < (b + 1) / bins if b < bins - 1 else conf <= 1.0)
        if m.any():
            e += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return round(float(e), 4)


def fit_temperature(logits, labels):
    import torch
    lg, y = torch.tensor(logits, dtype=torch.float32), torch.tensor(labels)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.cross_entropy(lg / torch.exp(log_t), y)
        loss.backward()
        return loss
    opt.step(closure)
    return float(torch.exp(log_t))


def cmd_train(a):
    import torch
    from datasets import Dataset
    from sklearn.metrics import f1_score
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
                              EarlyStoppingCallback, Trainer, TrainingArguments)
    OUT.mkdir(exist_ok=True)
    train, val = read_jsonl(DATA / "train.jsonl"), read_jsonl(DATA / "val.jsonl")
    print(f"train {len(train)} rows, val {len(val)} rows, device {'cuda' if torch.cuda.is_available() else 'CPU (this will be very slow)'}")
    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSequenceClassification.from_pretrained(
        a.base, num_labels=5, id2label={i: f"star_{i + 1}" for i in range(5)}, label2id={f"star_{i + 1}": i for i in range(5)})

    def prep(rows):
        ds = Dataset.from_list([{"text": r["text"], "labels": label_of(r)} for r in rows])
        return ds.map(lambda b: tok(b["text"], truncation=True, max_length=a.max_len), batched=True, remove_columns=["text"])
    tr, va = prep(train), prep(val)

    class MixedTrainer(Trainer):
        """Star rows: cross-entropy. Polarity rows: negative log of the probability mass on the matching group of stars."""
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            labels = inputs["labels"]
            out = model(**{k: v for k, v in inputs.items() if k != "labels"})
            logp = torch.log_softmax(out.logits, dim=-1)
            star = labels < 5
            parts = []
            if star.any():
                parts.append(-logp[star].gather(1, labels[star].unsqueeze(1)).squeeze(1))
            if (~star).any():
                grp = torch.stack([torch.logsumexp(logp[:, :2], 1), logp[:, 2], torch.logsumexp(logp[:, 3:], 1)], dim=1)
                parts.append(-grp[~star].gather(1, (labels[~star] - 5).unsqueeze(1)).squeeze(1))
            loss = torch.cat(parts).mean()
            return (loss, out) if return_outputs else loss

    def metrics(ep):
        lg, y = np.asarray(ep.predictions), np.asarray(ep.label_ids)
        p5 = softmax(lg)
        star = y < 5
        y3 = np.array([collapse_idx(int(v)) if v < 5 else int(v) - 5 for v in y])
        out = {"f1_3class": f1_score(y3, to3(p5).argmax(1), average="macro", labels=[0, 1, 2], zero_division=0)}
        out["f1_star"] = f1_score(y[star], p5[star].argmax(1), average="macro", labels=list(range(5)), zero_division=0) if star.any() else 0.0
        return out

    kw = dict(output_dir=str(OUT / "ckpt"), learning_rate=a.lr, num_train_epochs=a.epochs, per_device_train_batch_size=a.batch,
              per_device_eval_batch_size=a.batch * 2, weight_decay=0.01, warmup_ratio=0.06, save_strategy="epoch",
              save_total_limit=1, load_best_model_at_end=True, metric_for_best_model="f1_star", greater_is_better=True,
              fp16=torch.cuda.is_available(), report_to="none", seed=SEED)
    try:
        args = TrainingArguments(eval_strategy="epoch", **kw)
    except TypeError:
        args = TrainingArguments(evaluation_strategy="epoch", **kw)
    trainer = MixedTrainer(model=model, args=args, train_dataset=tr, eval_dataset=va, data_collator=DataCollatorWithPadding(tok),
                           compute_metrics=metrics, callbacks=[EarlyStoppingCallback(early_stopping_patience=1)])
    trainer.train()

    final = OUT / "reviewiq-star"
    trainer.save_model(str(final))
    tok.save_pretrained(str(final))

    # temperature scaling on validation star rows
    pv = trainer.predict(va)
    yv = np.asarray(pv.label_ids)
    star = yv < 5
    lg_v = np.asarray(pv.predictions)[star]
    temp = fit_temperature(lg_v, yv[star])
    conf0, conf1 = softmax(lg_v).max(1), softmax(lg_v / temp).max(1)
    ok = softmax(lg_v).argmax(1) == yv[star]
    cal = {"temperature": round(temp, 4), "ece_before": ece(conf0, ok), "ece_after": ece(conf1, ok)}
    json.dump(cal, open(final / "temperature.json", "w"))
    print("calibration:", cal)

    # evaluation on the held-out sets, with and without the pretrained baselines
    def predict_logits(texts):
        enc_ds = Dataset.from_list([{"text": t, "labels": 0} for t in texts]).map(
            lambda b: tok(b["text"], truncation=True, max_length=a.max_len), batched=True, remove_columns=["text"])
        return np.asarray(trainer.predict(enc_ds).predictions)
    sets = eval_sets(a)
    p5 = lambda texts: softmax(predict_logits(texts) / temp)
    res = {"reviewiq fine-tuned (calibrated)": evaluate(p5, lambda t: to3(p5(t)), sets)}
    json.dump(res, open(OUT / "finetune_results.json", "w"), indent=2)
    base = OUT / "baseline_results.json"
    show({**(json.load(open(base)) if base.exists() else {}), **res})
    shutil.make_archive(str(OUT / "reviewiq-star"), "zip", str(final))
    print("model saved to", final, "and zipped to", OUT / "reviewiq-star.zip")
    print("Compare 'seen_stars' with 'unseen_categories' for the generalisation claim, and 'polarity' for Hindi and tweets.")


# ---------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "baseline", "train", "all"])
    p.add_argument("--yelp-per-star", type=int, default=1500)
    p.add_argument("--amazon-per-star", type=int, default=350)
    p.add_argument("--unseen-per-star", type=int, default=300)
    p.add_argument("--scan", type=int, default=80000, help="max jsonl lines to read per Amazon category")
    p.add_argument("--tweets-per-lang", type=int, default=1200)
    p.add_argument("--hindi-total", type=int, default=6000)
    p.add_argument("--local-cap", type=int, default=4000)
    p.add_argument("--eval-cap", type=int, default=2000)
    p.add_argument("--base", default="xlm-roberta-base")
    p.add_argument("--max-len", type=int, default=128)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--batch", type=int, default=32)
    a = p.parse_args()
    if a.cmd in ("build", "all"):
        cmd_build(a)
    if a.cmd in ("baseline", "all"):
        cmd_baseline(a)
    if a.cmd in ("train", "all"):
        cmd_train(a)


if __name__ == "__main__":
    main()
