"""Download demo reviews: Amazon Reviews 2023, category All_Beauty (Hugging Face, no API key).

Keeps the 15 most-reviewed products, at most 3000 reviews each, and writes a CSV you can upload on the Upload page.
Run from the backend folder:  python -m scripts.download_demo
Options:  --products 15  --per-product 3000  --out ../data/demo_all_beauty.csv  --max-lines 0 (0 = whole file)
The file is a few hundred MB and is read line by line twice, so it takes a few minutes. Nothing is installed."""
import argparse
import csv
import datetime as dt
import json
import sys
import urllib.request
from collections import Counter

BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/"
REVIEWS = BASE + "review_categories/All_Beauty.jsonl"
META = BASE + "meta_categories/meta_All_Beauty.jsonl"


def lines(url: str, max_lines: int):
    req = urllib.request.Request(url, headers={"User-Agent": "reviewiq-demo/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        for i, raw in enumerate(r):
            if max_lines and i >= max_lines:
                return
            try:
                yield json.loads(raw)
            except ValueError:
                continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", type=int, default=15)
    ap.add_argument("--per-product", type=int, default=3000)
    ap.add_argument("--out", default="../data/demo_all_beauty.csv")
    ap.add_argument("--max-lines", type=int, default=0)
    a = ap.parse_args()
    try:
        print("Pass 1: counting reviews per product...")
        counts = Counter(r.get("parent_asin") for r in lines(REVIEWS, a.max_lines) if r.get("parent_asin"))
        top = [asin for asin, _ in counts.most_common(a.products)]
        print("Top products:", len(top), "with", sum(min(counts[t], a.per_product) for t in top), "reviews to keep")
        print("Reading product titles and brands...")
        meta = {}
        for m in lines(META, 0):
            if m.get("parent_asin") in top:
                meta[m["parent_asin"]] = ((m.get("title") or m["parent_asin"])[:60], m.get("store") or "")
            if len(meta) == len(top):
                break
        print("Pass 2: writing the CSV...")
        kept = Counter()
        n = 0
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["product", "brand", "rating", "date", "title", "review", "author", "helpful"])
            for r in lines(REVIEWS, a.max_lines):
                asin = r.get("parent_asin")
                if asin not in meta or kept[asin] >= a.per_product or not (r.get("text") or "").strip():
                    continue
                kept[asin] += 1
                ts = r.get("timestamp")
                day = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date().isoformat() if ts else ""
                title, brand = meta[asin]
                w.writerow([title, brand, r.get("rating"), day, r.get("title") or "", r["text"], r.get("user_id") or "", r.get("helpful_vote") or 0])
                n += 1
        print(f"Done: {n} reviews written to {a.out}. Upload it on the Upload page.")
        return 0
    except Exception as e:  # network blocked, URL moved, disk full
        print("Could not download the demo data:", e, file=sys.stderr)
        print("If the address has moved, open the dataset page McAuley-Lab/Amazon-Reviews-2023 on Hugging Face, "
              "download All_Beauty.jsonl and meta_All_Beauty.jsonl by hand and change REVIEWS and META at the top of this script.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
