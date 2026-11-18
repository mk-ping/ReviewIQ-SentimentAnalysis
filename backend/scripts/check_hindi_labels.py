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
