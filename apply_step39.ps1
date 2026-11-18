# Step 39: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Detects Hindi sentiment data whose negative and positive labels are swapped, by counting obvious cue words.
In correctly labelled data, words like 'bekar' or 'kharab' show up in the negative rows more than in the positive rows, and the reverse for 'accha'.
Pure standard library; the same file lives in ml/polarity_fix.py so the data build can use it."""
POS = ["\u0905\u091a\u094d\u091b\u093e", "\u0905\u091a\u094d\u091b\u0940", "\u0905\u091a\u094d\u091b\u0947", "\u092c\u0922\u093c\u093f\u092f\u093e", "\u092c\u0947\u0939\u0924\u0930\u0940\u0928",
       "\u0936\u093e\u0928\u0926\u093e\u0930", "\u092a\u0938\u0902\u0926", "\u0909\u0924\u094d\u0924\u092e", "\u0932\u093e\u091c\u0935\u093e\u092c", "\u092e\u0938\u094d\u0924",
       "\u0916\u0941\u0936", "\u0927\u0928\u094d\u092f\u0935\u093e\u0926", "\u0938\u0941\u0902\u0926\u0930",
       "great", "good", "love", "best", "awesome", "nice", "excellent", "badhiya", "zabardast", "accha", "achha", "mast ", "shandar"]
NEG = ["\u092c\u0947\u0915\u093e\u0930", "\u0916\u0930\u093e\u092c", "\u092c\u0941\u0930\u093e", "\u092c\u0941\u0930\u0940", "\u0918\u091f\u093f\u092f\u093e", "\u0927\u094b\u0916\u093e",
       "\u0928\u093f\u0930\u093e\u0936", "\u0915\u091a\u0930\u093e", "\u092c\u0915\u0935\u093e\u0938", "\u0928\u092b\u0930\u0924", "\u0935\u0947\u0938\u094d\u091f",
       "worst", "bad", "waste", "terrible", "horrible", "bekar", "ghatiya", "kharab", "bakwas", "hate"]
MIN_PER_CLASS = 30
MARGIN = 0.03


def _has(t: str, words: list[str]) -> bool:
    t = t.lower()
    return any(w in t for w in words)


def orientation(rows: list[tuple[str, int]]) -> dict:
    """rows: (text, label) with label 0 = negative, 2 = positive (neutral ignored).
    verdict: 'ok', 'inverted' or 'unclear' (too few rows or no clear difference)."""
    pos = [t for t, y in rows if y == 2]
    neg = [t for t, y in rows if y == 0]
    if len(pos) < MIN_PER_CLASS or len(neg) < MIN_PER_CLASS:
        return {"verdict": "unclear", "score": None, "n_pos": len(pos), "n_neg": len(neg)}
    rate = lambda ts, ws: sum(_has(t, ws) for t in ts) / len(ts)   # noqa: E731
    score = (rate(pos, POS) - rate(neg, POS)) + (rate(neg, NEG) - rate(pos, NEG))
    return {"verdict": "ok" if score > MARGIN else "inverted" if score < -MARGIN else "unclear", "score": round(score, 4),
            "pos_cue_in_pos": rate(pos, POS), "pos_cue_in_neg": rate(neg, POS), "neg_cue_in_neg": rate(neg, NEG), "neg_cue_in_pos": rate(pos, NEG),
            "n_pos": len(pos), "n_neg": len(neg)}


def swap(label: int) -> int:
    return {0: 2, 2: 0}.get(label, label)
'@ | Set-Content -Encoding ascii backend\app\services\polarity_check.py

@'
"""Detects Hindi sentiment data whose negative and positive labels are swapped, by counting obvious cue words.
In correctly labelled data, words like 'bekar' or 'kharab' show up in the negative rows more than in the positive rows, and the reverse for 'accha'.
Pure standard library; the same file lives in ml/polarity_fix.py so the data build can use it."""
POS = ["\u0905\u091a\u094d\u091b\u093e", "\u0905\u091a\u094d\u091b\u0940", "\u0905\u091a\u094d\u091b\u0947", "\u092c\u0922\u093c\u093f\u092f\u093e", "\u092c\u0947\u0939\u0924\u0930\u0940\u0928",
       "\u0936\u093e\u0928\u0926\u093e\u0930", "\u092a\u0938\u0902\u0926", "\u0909\u0924\u094d\u0924\u092e", "\u0932\u093e\u091c\u0935\u093e\u092c", "\u092e\u0938\u094d\u0924",
       "\u0916\u0941\u0936", "\u0927\u0928\u094d\u092f\u0935\u093e\u0926", "\u0938\u0941\u0902\u0926\u0930",
       "great", "good", "love", "best", "awesome", "nice", "excellent", "badhiya", "zabardast", "accha", "achha", "mast ", "shandar"]
NEG = ["\u092c\u0947\u0915\u093e\u0930", "\u0916\u0930\u093e\u092c", "\u092c\u0941\u0930\u093e", "\u092c\u0941\u0930\u0940", "\u0918\u091f\u093f\u092f\u093e", "\u0927\u094b\u0916\u093e",
       "\u0928\u093f\u0930\u093e\u0936", "\u0915\u091a\u0930\u093e", "\u092c\u0915\u0935\u093e\u0938", "\u0928\u092b\u0930\u0924", "\u0935\u0947\u0938\u094d\u091f",
       "worst", "bad", "waste", "terrible", "horrible", "bekar", "ghatiya", "kharab", "bakwas", "hate"]
MIN_PER_CLASS = 30
MARGIN = 0.03


def _has(t: str, words: list[str]) -> bool:
    t = t.lower()
    return any(w in t for w in words)


def orientation(rows: list[tuple[str, int]]) -> dict:
    """rows: (text, label) with label 0 = negative, 2 = positive (neutral ignored).
    verdict: 'ok', 'inverted' or 'unclear' (too few rows or no clear difference)."""
    pos = [t for t, y in rows if y == 2]
    neg = [t for t, y in rows if y == 0]
    if len(pos) < MIN_PER_CLASS or len(neg) < MIN_PER_CLASS:
        return {"verdict": "unclear", "score": None, "n_pos": len(pos), "n_neg": len(neg)}
    rate = lambda ts, ws: sum(_has(t, ws) for t in ts) / len(ts)   # noqa: E731
    score = (rate(pos, POS) - rate(neg, POS)) + (rate(neg, NEG) - rate(pos, NEG))
    return {"verdict": "ok" if score > MARGIN else "inverted" if score < -MARGIN else "unclear", "score": round(score, 4),
            "pos_cue_in_pos": rate(pos, POS), "pos_cue_in_neg": rate(neg, POS), "neg_cue_in_neg": rate(neg, NEG), "neg_cue_in_pos": rate(pos, NEG),
            "n_pos": len(pos), "n_neg": len(neg)}


def swap(label: int) -> int:
    return {0: 2, 2: 0}.get(label, label)
'@ | Set-Content -Encoding ascii ml\polarity_fix.py

@'
"""Checks whether the Hindi polarity data has negative and positive swapped, and can repair the data files in place.
Reads ../ml/data/*.jsonl, groups the polarity rows by source, and compares cue words per label. Run from backend:
  python -m scripts.check_hindi_labels            (report only)
  python -m scripts.check_hindi_labels --fix      (swap negative and positive in every source judged inverted; keeps .bak copies)
After a fix, retrain: python -m scripts.train_tfidf   and   python -m scripts.train_stacker   (and train_mixed if you use it)."""
import argparse
import json
import shutil
from pathlib import Path

from app.services import polarity_check as P

DATA = Path("../ml/data")
FILES = ["train.jsonl", "val.jsonl", "test_seen.jsonl", "test_unseen.jsonl"]


def read(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args()
    data = {f: read(DATA / f) for f in FILES}
    if not any(data.values()):
        print("No files in ml/data. Build them first: cd ..\\ml ; python reviewiq_train.py build")
        return
    by_src: dict = {}
    for rows in data.values():
        for r in rows:
            if r.get("star", -1) < 0 and r.get("pol", -1) >= 0 and r.get("lang") == "hi":
                by_src.setdefault(r.get("src", "?"), []).append((r["text"], r["pol"]))
    if not by_src:
        print("No Hindi polarity rows found.")
        return
    inverted = []
    for src, rows in by_src.items():
        o = P.orientation(rows)
        print(f"{src}: {len(rows)} rows -> {o['verdict'].upper()}", "" if o["score"] is None else
              f"(score {o['score']:+.3f}; positive cues in positive rows {o['pos_cue_in_pos']:.2f} vs negative rows {o['pos_cue_in_neg']:.2f}; "
              f"negative cues in negative rows {o['neg_cue_in_neg']:.2f} vs positive rows {o['neg_cue_in_pos']:.2f})")
        for lab, name in ((0, "negative"), (2, "positive")):
            for t, _ in [x for x in rows if x[1] == lab][:3]:
                print(f"    labelled {name}: {t[:90]}")
        if o["verdict"] == "inverted":
            inverted.append(src)
    if not inverted:
        print("\nNo source looks inverted by this check. If you still see swapped labels, send me three example rows.")
        return
    print("\nInverted:", inverted)
    if not a.fix:
        print("Run again with --fix to swap negative and positive in those sources.")
        return
    for f, rows in data.items():
        n = 0
        for r in rows:
            if r.get("src") in inverted and r.get("star", -1) < 0 and r.get("pol", -1) in (0, 2):
                r["pol"] = P.swap(r["pol"])
                n += 1
        if n:
            shutil.copy2(DATA / f, (DATA / f).with_suffix(".jsonl.bak"))
            (DATA / f).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            print(f"  {f}: swapped {n} labels (backup kept)")
    print("Now retrain: python -m scripts.train_tfidf  then  python -m scripts.train_stacker")


if __name__ == "__main__":
    main()
'@ | Set-Content -Encoding ascii backend\scripts\check_hindi_labels.py

@'
"""Offline check of the label-orientation detector on synthetic Hindi and Hinglish rows."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import polarity_check as P

rng = random.Random(4)
POSL = ["\u092f\u0939 \u092c\u0939\u0941\u0924 \u0905\u091a\u094d\u091b\u093e \u0939\u0948", "\u092c\u0922\u093c\u093f\u092f\u093e \u092a\u094d\u0930\u094b\u0921\u0915\u094d\u091f", "bahut accha laga", "great phone love it", "\u092e\u0941\u091d\u0947 \u092f\u0939 \u092a\u0938\u0902\u0926 \u0906\u092f\u093e", "ok ok sab theek"]
NEGL = ["\u092f\u0939 \u092c\u0947\u0915\u093e\u0930 \u0939\u0948", "\u092c\u0939\u0941\u0924 \u0916\u0930\u093e\u092c \u0938\u0930\u094d\u0935\u093f\u0938", "ekdum bekar", "worst waste of money", "\u0918\u091f\u093f\u092f\u093e \u0915\u094d\u0935\u093e\u0932\u093f\u091f\u0940", "kuch nahi mila"]
good = [(rng.choice(POSL), 2) for _ in range(100)] + [(rng.choice(NEGL), 0) for _ in range(100)] + [("theek hai", 1)] * 20
flip = [(t, P.swap(y)) for t, y in good]
assert P.orientation(good)["verdict"] == "ok"
assert P.orientation(flip)["verdict"] == "inverted"
assert P.orientation(good[:10])["verdict"] == "unclear"
assert P.orientation([("same text", 2)] * 50 + [("same text", 0)] * 50)["verdict"] == "unclear"
assert P.swap(0) == 2 and P.swap(2) == 0 and P.swap(1) == 1
print("polarity checks ok")
'@ | Set-Content -Encoding ascii backend\tests\check_polarity.py

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


# Gold Labels stays out of the menu (the page and its code remain for testing, but nothing on the site links to it)
lay = pathlib.Path("frontend/src/Layout.tsx")
if lay.exists():
    lines = lay.read_text(encoding="utf-8").split("\n")
    out = [l for l in lines if 'to: "/label"' not in l]
    if len(out) != len(lines):
        lay.write_text("\n".join(out), encoding="utf-8")

# 3. Hindi labels: the data build now checks the direction and corrects a swap
edit("ml/reviewiq_train.py", [
    ("    out = []\n    for p in range(3):\n        random.Random(SEED).shuffle(by[p])\n",
     "    from polarity_fix import orientation, swap\n    flat = [r for p in range(3) for r in by[p]]\n    o = orientation([(r[\"text\"], r[\"pol\"]) for r in flat])\n"
     "    print(f\"  hindi-sentiments label direction check: {o['verdict']} (score {o['score']})\")\n"
     "    if o[\"verdict\"] == \"inverted\":\n        print(\"  negative and positive were swapped in this dataset; corrected.\")\n"
     "        by = defaultdict(list)\n        for r in flat:\n            r[\"pol\"] = swap(r[\"pol\"])\n            by[r[\"pol\"]].append(r)\n"
     "    out = []\n    for p in range(3):\n        random.Random(SEED).shuffle(by[p])\n"),
    ("        random.Random(SEED).shuffle(rows)\n        out += rows[:per_lang]\n",
     "        if lang == \"hi\":\n            from polarity_fix import orientation, swap\n            o = orientation([(r[\"text\"], r[\"pol\"]) for r in rows])\n"
     "            print(f\"  tweets/hindi label direction check: {o['verdict']}\")\n"
     "            if o[\"verdict\"] == \"inverted\":\n                for r in rows:\n                    r[\"pol\"] = swap(r[\"pol\"])\n"
     "        random.Random(SEED).shuffle(rows)\n        out += rows[:per_lang]\n"),
], "polarity_fix")
edit("backend/scripts/benchmark_labeled.py", [(
    "    return B.stratified(rows, cap)\n",
    "    if lang == \"hi\":\n        from app.services import polarity_check as P\n        o = P.orientation([(t, {\"neg\": 0, \"pos\": 2}[y]) for t, y in rows if y in (\"neg\", \"pos\")])\n"
    "        print(f\"  label direction check: {o['verdict']}\")\n        if o[\"verdict\"] == \"inverted\":\n"
    "            rows = [(t, {\"neg\": \"pos\", \"pos\": \"neg\"}.get(y, y)) for t, y in rows]\n            print(\"  negative and positive were swapped in this dataset; corrected.\")\n"
    "    return B.stratified(rows, cap)\n")], "label direction check")
print("Step 39 patches applied.")
'@ | Set-Content -Encoding ascii patch_step39.py
python patch_step39.py
Remove-Item patch_step39.py

Write-Host 'Step 39 files written.'
