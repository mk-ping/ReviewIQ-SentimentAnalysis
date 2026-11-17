"""Validates our aspect sentiment against an independent aspect-based sentiment (ABSA) model.
For a sample of tagged English sentences, the ABSA model reads (sentence, aspect) and gives its own
negative / neutral / positive. We report how often it agrees with our score, Cohen's kappa, and a confusion matrix.
Model: yangheng/deberta-v3-base-absa-v1.1 (downloaded once from Hugging Face, about 700 MB, runs on CPU).
Run from backend after sentence aspects exist:  python -m scripts.absa_validate [--workspace 3] [--per-aspect 60]
Writes ../ml/out/absa_ws<N>.json (shown on the Model Checks page) and ../docs/absa_validation.md. Exit code 2 = optional piece missing."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.services.extras import ABSA_MODEL, absa_label, agreement, band

SQL = """
SELECT sent_id, aspect, sentence, sent_score FROM (
  SELECT sa.sent_id, sa.aspect, sa.sentence, sa.sent_score,
         row_number() OVER (PARTITION BY sa.aspect ORDER BY md5(sa.sent_id::text)) AS rn
  FROM sentence_aspect sa JOIN review r ON r.review_id = sa.review_id
  WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND sa.aspect <> 'general' AND sa.sent_score IS NOT NULL
    AND (r.language = 'en' OR r.language IS NULL)) x
WHERE rn <= :per ORDER BY aspect, rn"""


async def load(ws, per):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(SQL), {"ws": ws, "spam": T.SPAM_MAX, "per": per})).all()
    return ws, rows


def run_model(pairs, batch=16):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(ABSA_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(ABSA_MODEL).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(pairs), batch):
            chunk = pairs[i:i + batch]
            enc = tok([s[:400] for s, _ in chunk], [a for _, a in chunk], padding=True, truncation=True, max_length=128, return_tensors="pt")
            out += [absa_label(model.config.id2label[int(k)]) for k in model(**enc).logits.argmax(-1)]
            print(f"  {min(i + batch, len(pairs))}/{len(pairs)}", end="\r")
    print()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--per-aspect", type=int, default=60)
    a = ap.parse_args()
    try:
        import torch, transformers  # noqa: F401
    except ImportError:
        print("torch and transformers are needed (they are in requirements.txt). Run: pip install -r requirements.txt")
        return 2
    ws, rows = asyncio.run(load(a.workspace, a.per_aspect))
    if len(rows) < 30:
        print(f"Only {len(rows)} tagged English sentences. Run the aspects analysis on an upload first (Upload page, Run full analysis).")
        return 1
    print(f"Workspace {ws}: checking {len(rows)} sentences with {ABSA_MODEL} ...")
    theirs = run_model([(r.sentence, r.aspect) for r in rows])
    triples = [(r.aspect, band(float(r.sent_score)), t) for r, t in zip(rows, theirs)]
    res = agreement(triples)
    miss = [{"aspect": r.aspect, "sentence": r.sentence[:240], "ours": o, "absa": t}
            for r, (_, o, t) in zip(rows, triples) if t and o != t][:12]
    doc = {"model": ABSA_MODEL, "workspace": ws, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res, "disagreements": miss}
    from app.core.config import settings
    out = Path(settings.tfidf_path).parent / f"absa_ws{ws}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    md = [f"# ABSA validation of aspect sentiment", "", f"Model: `{ABSA_MODEL}`. Sentences checked: {res['n']}.", "",
          f"- Agreement with our scores: **{res['agree_rate']:.1%}**", f"- Cohen's kappa: **{res['kappa']}** (1 = perfect, 0 = chance)", "",
          "| Aspect | Sentences | Agreement |", "| --- | --- | --- |"]
    md += [f"| {d['aspect']} | {d['n']} | {d['agree_rate']:.1%} |" for d in res["by_aspect"]]
    md += ["", "Rows are our label, columns are the ABSA model's label.", "", "| ours \\ ABSA | neg | neu | pos |", "| --- | --- | --- | --- |"]
    md += [f"| {o} | {c['neg']} | {c['neu']} | {c['pos']} |" for o, c in res["confusion"].items()]
    Path("../docs").mkdir(exist_ok=True)
    Path("../docs/absa_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Agreement {res['agree_rate']:.1%}, kappa {res['kappa']}. Saved {out} and ../docs/absa_validation.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
