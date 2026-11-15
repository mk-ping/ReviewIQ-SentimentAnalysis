# Step 24: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Precision of Hidden Dissatisfaction from hand-checked reviews. Pure functions, so they test offline."""
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% interval for a share k out of n."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def summarise(rows: list[dict], flagged_pop: int | None = None, unflagged_pop: int | None = None) -> dict:
    """rows: {'flagged': bool, 'hidden': bool}. Precision = flagged reviews that really hide a complaint.
    Miss rate = unflagged reviews that really hide one. Recall is estimated only when both population sizes are known."""
    f = [r["hidden"] for r in rows if r["flagged"]]
    u = [r["hidden"] for r in rows if not r["flagged"]]
    out = {"flagged_checked": len(f), "unflagged_checked": len(u),
           "precision": sum(f) / len(f) if f else None, "precision_range": wilson(sum(f), len(f)),
           "miss_rate": sum(u) / len(u) if u else None, "miss_range": wilson(sum(u), len(u)), "recall_estimate": None}
    if f and u and flagged_pop and unflagged_pop:
        tp = out["precision"] * flagged_pop
        fn = out["miss_rate"] * unflagged_pop
        out["recall_estimate"] = tp / (tp + fn) if tp + fn else None
    return out
'@ | Set-Content -Encoding ascii backend\app\services\hidden_eval.py

@'
"""Hand-check of Hidden Dissatisfaction (document section 14: about 100 flagged and 100 unflagged reviews rated 4 or more).
  python -m scripts.hidden_check export   -> ../data/hidden_check.csv (refuses to overwrite your labels)
  python -m scripts.hidden_check score    -> precision, miss rate and an estimated recall from the filled 'hidden' column
Fill 'hidden' with 1 if the review really contains a complaint about the product, 0 if it does not."""
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import text

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.services.hidden_eval import summarise

PATH = Path("../data/hidden_check.csv")
META = Path("../data/hidden_check_meta.txt")
BASE = """FROM review r JOIN review_aspect_run u ON u.review_id = r.review_id
          WHERE r.rating_norm >= :hid AND r.spam_score <= :spam"""
NEG = """EXISTS (SELECT 1 FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg
        AND ra.confidence >= :conf AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> '')"""


async def export(n: int = 100):
    if PATH.exists():
        print(f"{PATH} already exists. Rename or delete it yourself for a fresh export."); return
    a = {"hid": T.HIDDEN_MIN_STARS, "spam": T.SPAM_MAX, "neg": T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF, "n": n}
    async with SessionLocal() as s:
        f_pop = await s.scalar(text(f"SELECT count(*) {BASE} AND {NEG}"), a)
        u_pop = await s.scalar(text(f"SELECT count(*) {BASE} AND NOT {NEG}"), a)
        flagged = (await s.execute(text(f"""
            SELECT r.review_id, r.rating_norm, r.text_clean,
                   (SELECT ra.evidence_span FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg
                      AND ra.confidence >= :conf ORDER BY ra.sentiment LIMIT 1)
            {BASE} AND {NEG} ORDER BY md5(r.review_id::text) LIMIT :n"""), a)).all()
        unflagged = (await s.execute(text(f"""
            SELECT r.review_id, r.rating_norm, r.text_clean, NULL {BASE} AND NOT {NEG} ORDER BY md5(r.review_id::text) LIMIT :n"""), a)).all()
    rows = [(1, *r) for r in flagged] + [(0, *r) for r in unflagged]
    # shuffle so you cannot tell which are flagged while labelling
    rows.sort(key=lambda r: hash((r[1], "hidden")) )
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["review_id", "flagged", "stars", "text", "flagged_phrase", "hidden"])
        w.writerows([[r[1], r[0], r[2], r[3], r[4] or "", ""] for r in rows])
    META.write_text(f"{f_pop} {u_pop}\n")
    print(f"wrote {len(rows)} reviews ({len(flagged)} flagged, {len(unflagged)} unflagged) to {PATH}")
    print("Judge the review text first. The 'flagged' column is there for scoring, so try not to peek.")


def score():
    rows = []
    for r in csv.DictReader(PATH.open(encoding="utf-8-sig")):
        if r["hidden"].strip() in ("0", "1"):
            rows.append({"flagged": r["flagged"] == "1", "hidden": r["hidden"].strip() == "1"})
    if not rows:
        print("No labelled rows yet."); return
    pops = META.read_text().split() if META.exists() else []
    res = summarise(rows, int(pops[0]) if pops else None, int(pops[1]) if len(pops) > 1 else None)
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
    rng = lambda v: "n/a" if v is None else f"{v[0]:.2f}-{v[1]:.2f}"
    print(f"flagged reviews checked {res['flagged_checked']}: precision {fmt(res['precision'])} (95% range {rng(res['precision_range'])})")
    print(f"unflagged reviews checked {res['unflagged_checked']}: miss rate {fmt(res['miss_rate'])} (95% range {rng(res['miss_range'])})")
    print(f"estimated recall {fmt(res['recall_estimate'])}  (needs the population sizes saved at export)")
    print("Small samples give wide ranges. Quote the range, not just the point value.")


if __name__ == "__main__":
    asyncio.run(export()) if sys.argv[1:] == ["export"] else score()
'@ | Set-Content -Encoding ascii backend\scripts\hidden_check.py

@'
"""Offline checks for the hidden-dissatisfaction precision maths. Run: python -m tests.check_hidden_eval"""
from app.services.hidden_eval import summarise, wilson

lo, hi = wilson(80, 100)
assert 0.70 < lo < 0.80 < hi < 0.88, (lo, hi)
assert wilson(0, 0) is None
lo, hi = wilson(0, 10)
assert lo == 0.0 and 0.2 < hi < 0.35

rows = [{"flagged": True, "hidden": True}] * 8 + [{"flagged": True, "hidden": False}] * 2 \
     + [{"flagged": False, "hidden": True}] * 1 + [{"flagged": False, "hidden": False}] * 9
r = summarise(rows)
assert r["precision"] == 0.8 and r["miss_rate"] == 0.1 and r["recall_estimate"] is None
r = summarise(rows, flagged_pop=100, unflagged_pop=400)      # 80 true flagged; 40 missed among the unflagged
assert abs(r["recall_estimate"] - 80 / 120) < 1e-9, r
assert summarise([])["precision"] is None
print("hidden evaluation checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_hidden_eval.py

@'
-- EXPLAIN ANALYZE evidence for the queries added in Steps 20-22. Run it with tools\make_evidence.ps1.
-- On small data the planner prefers sequential scans, so each "with index" plan forces the index.

ANALYZE sentence_aspect;
ANALYZE review_embedding;

\echo ===== SIMILAR REVIEWS, same model only, WITH HNSW INDEX =====
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.review_id FROM review_embedding e
WHERE e.model = (SELECT model FROM review_embedding ORDER BY review_id LIMIT 1)
ORDER BY e.embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;
RESET enable_seqscan;

\echo ===== SIMILAR REVIEWS, same model only, WITHOUT INDEX =====
SET enable_indexscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.review_id FROM review_embedding e
WHERE e.model = (SELECT model FROM review_embedding ORDER BY review_id LIMIT 1)
ORDER BY e.embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;
RESET enable_indexscan;

\echo ===== SENTENCES FOR ONE ASPECT, WITH ix_sentence_aspect_aspect =====
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT sentence, sent_score FROM sentence_aspect WHERE aspect = 'delivery' AND sent_score <= -0.25 LIMIT 20;
RESET enable_seqscan;

\echo ===== SENTENCES FOR ONE ASPECT, WITHOUT INDEX =====
SET enable_indexscan = off; SET enable_bitmapscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT sentence, sent_score FROM sentence_aspect WHERE aspect = 'delivery' AND sent_score <= -0.25 LIMIT 20;
RESET enable_indexscan; RESET enable_bitmapscan;

\echo ===== ASPECT COVERAGE (tagged vs general sentences) =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FILTER (WHERE aspect <> 'general') AS tagged, count(*) AS total FROM sentence_aspect;
'@ | Set-Content -Encoding ascii backend\scripts\explain_evidence.sql

@'
# Writes the EXPLAIN ANALYZE evidence file (UTF-8, so it opens normally). Run from the project root.
Get-Content backend\scripts\explain_evidence.sql | docker exec -i reviewiq_db psql -U reviewiq -d reviewiq | Out-File -Encoding utf8 docs\explain_evidence.txt
Write-Host "Wrote docs\explain_evidence.txt"
'@ | Set-Content -Encoding ascii tools\make_evidence.ps1

Write-Host 'Step 24 files written.'
