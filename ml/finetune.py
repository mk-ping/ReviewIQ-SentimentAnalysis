"""Fine-tunes a 3-class sentiment model (negative, neutral, positive) on the data built by reviewiq_train.py build.
It starts from a multilingual sentiment model, so it learns your genres and the neutral class without starting from zero.
Never touches the test sets: train.jsonl trains, val.jsonl only picks the best epoch.

Needs a GPU in practice (Google Colab free T4 is enough, about 40 to 60 minutes for 40000 reviews and 2 epochs):
    pip install torch transformers
    python finetune.py --max-train 40000 --epochs 2
Then put  FT_MODEL=../ml/out/reviewiq-ft  in backend/.env  (or the Hub id if you upload it) and re-run scoring."""
import argparse
import json
import random
import shutil
import time
from pathlib import Path

DATA, OUT = Path("data"), Path("out")
LABELS = ("negative", "neutral", "positive")


def label3(r: dict) -> int:
    """0 negative, 1 neutral, 2 positive. Stars 1-2 negative, 3 neutral, 4-5 positive; polarity rows keep their label."""
    if r["star"] >= 0:
        return 0 if r["star"] <= 1 else 1 if r["star"] == 2 else 2
    return r["pol"]


def read(name: str) -> list[dict]:
    p = DATA / name
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def pick(rows: list[dict], cap: int, seed: int = 7) -> list[dict]:
    """Up to cap rows, shuffled. Keeps every neutral row first, because neutral is the rare class that hurts macro F1 most."""
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    neutral = [r for r in rows if label3(r) == 1]
    rest = [r for r in rows if label3(r) != 1]
    n_neu = min(len(neutral), cap // 3)
    keep = neutral[:n_neu] + rest[: cap - n_neu]
    rng.shuffle(keep)
    return keep


def class_weights(labels: list[int]) -> list[float]:
    """Inverse square-root frequency, scaled so the average weight is 1. Softer than full balancing, which over-predicts neutral."""
    n = [max(1, labels.count(c)) for c in range(3)]
    w = [(sum(n) / (3 * x)) ** 0.5 for x in n]
    m = sum(w) / 3
    return [x / m for x in w]


def macro_f1(gold: list[int], pred: list[int]) -> float:
    f = []
    for c in range(3):
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        if tp + fn:
            f.append(2 * tp / (2 * tp + fp + fn))
    return sum(f) / len(f) if f else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="cardiffnlp/twitter-xlm-roberta-base-sentiment", help="start model; any 3-class sentiment model or a plain xlm-roberta-base")
    ap.add_argument("--max-train", type=int, default=40000)
    ap.add_argument("--max-val", type=int, default=6000)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=128)
    a = ap.parse_args()

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    train, val = pick(read("train.jsonl"), a.max_train), pick(read("val.jsonl"), a.max_val)
    if not train or not val:
        print("No data in ml/data. Run: python reviewiq_train.py build")
        return
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cpu":
        print("WARNING: no GPU found. This will take many hours. Use Google Colab (free T4) instead.")
    print(f"train {len(train)}, val {len(val)}, device {dev}")
    tok = AutoTokenizer.from_pretrained(a.base)
    id2 = {i: n for i, n in enumerate(LABELS)}
    model = AutoModelForSequenceClassification.from_pretrained(
        a.base, num_labels=3, id2label=id2, label2id={n: i for i, n in id2.items()}, ignore_mismatched_sizes=True).to(dev)
    ytr = [label3(r) for r in train]
    w = torch.tensor(class_weights(ytr), dtype=torch.float, device=dev)
    print("class weights (neg, neu, pos):", [round(float(x), 2) for x in w])
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = a.epochs * ((len(train) + a.batch - 1) // a.batch)
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
    amp = dev == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)

    def encode(rows):
        return tok([r["text"] for r in rows], truncation=True, max_length=a.max_len, padding=True, return_tensors="pt").to(dev)

    def evaluate():
        model.eval()
        pred, gold = [], []
        order = sorted(range(len(val)), key=lambda i: len(val[i]["text"]))      # similar lengths together: faster
        with torch.no_grad():
            for i in range(0, len(order), a.batch * 2):
                rows = [val[j] for j in order[i:i + a.batch * 2]]
                with torch.autocast(dev, enabled=amp):
                    logits = model(**encode(rows)).logits
                pred += logits.argmax(-1).cpu().tolist()
                gold += [label3(r) for r in rows]
        model.train()
        return macro_f1(gold, pred), sum(g == p for g, p in zip(gold, pred)) / len(gold)

    best, final = -1.0, OUT / "reviewiq-ft"
    OUT.mkdir(exist_ok=True)
    model.train()
    t0 = time.time()
    for ep in range(a.epochs):
        random.Random(100 + ep).shuffle(train)
        for i in range(0, len(train), a.batch):
            rows = train[i:i + a.batch]
            y = torch.tensor([label3(r) for r in rows], device=dev)
            with torch.autocast(dev, enabled=amp):
                logits = model(**encode(rows)).logits
            loss = torch.nn.functional.cross_entropy(logits.float(), y, weight=w)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            if (i // a.batch) % 100 == 0:
                print(f"epoch {ep + 1} step {i // a.batch}/{len(train) // a.batch} loss {loss.item():.3f} ({(time.time() - t0) / 60:.1f} min)")
        f1, acc = evaluate()
        print(f"== epoch {ep + 1}: validation macro F1 {f1:.3f}, accuracy {acc:.3f}")
        if f1 > best:
            best = f1
            model.save_pretrained(final)
            tok.save_pretrained(final)
            print("   saved (best so far)")
    shutil.make_archive(str(OUT / "reviewiq-ft"), "zip", final)
    print(f"\nDone. Best validation macro F1 {best:.3f}. Model: {final}  (zip: {OUT / 'reviewiq-ft.zip'})")
    print("Next: set FT_MODEL=../ml/out/reviewiq-ft in backend/.env, then run backend scripts eval_heldout and train_stacker.")


if __name__ == "__main__":
    main()
