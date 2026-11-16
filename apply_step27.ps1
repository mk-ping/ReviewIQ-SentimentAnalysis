# Step 27: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _f, _ws
from app.core import thresholds as T
from app.db.session import get_session

router = APIRouter(tags=["quality"])


@router.get("/data-quality")
async def data_quality(session: AsyncSession = Depends(get_session)):
    """What came in, what was repaired or rejected, and how clean the stored reviews are."""
    ws = await _ws(session)
    a = {"ws": ws, "spam": T.SPAM_MAX}
    up = (await session.execute(text("""
        SELECT count(*), coalesce(sum(rows_total), 0), coalesce(sum(rows_ok), 0), coalesce(sum(rows_repaired), 0),
               coalesce(sum(rows_rejected), 0) FROM upload_batch WHERE workspace_id = :ws"""), a)).one()
    rv = (await session.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE spam_score > :spam), coalesce(sum(dup_count - 1), 0),
               count(*) FILTER (WHERE rating_norm IS NULL), count(*) FILTER (WHERE review_date IS NULL),
               count(s.review_id), count(*) FILTER (WHERE r.language IS NULL)
        FROM review r LEFT JOIN review_score s ON s.review_id = r.review_id WHERE r.workspace_id = :ws"""), a)).one()
    langs = (await session.execute(text("""
        SELECT coalesce(language, 'unknown'), count(*) FROM review WHERE workspace_id = :ws GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""), a)).all()
    n_files, total, ok, repaired, rejected = up
    n, spam, dups, no_rating, no_date, scored, no_lang = rv
    pct = lambda x: _f(100 * x / n, 1) if n else None  # noqa: E731
    return {
        "files": n_files, "rows_in_files": int(total), "accepted": int(ok), "repaired": int(repaired), "rejected": int(rejected),
        "reconciles": int(ok) + int(repaired) + int(rejected) == int(total),
        "reviews": n, "spam": spam, "spam_pct": pct(spam), "duplicates_removed": int(dups),
        "missing_rating": no_rating, "missing_rating_pct": pct(no_rating), "missing_date": no_date, "missing_date_pct": pct(no_date),
        "scored": scored, "scored_pct": pct(scored), "language_unknown": no_lang,
        "languages": [{"language": l, "reviews": c} for l, c in langs],
        "note": "Accepted + repaired + rejected should equal the rows in the files: nothing is dropped without a record.",
    }


@router.get("/review-flags")
async def review_flags(session: AsyncSession = Depends(get_session)):
    """Patterns that can mean fake or pushed reviews: bursts, repeated text, one author, and rating outliers."""
    ws = await _ws(session)
    a = {"ws": ws, "z": T.SPIKE_Z, "minc": T.SPIKE_MIN_COUNT}
    ex = session.execute
    bursts = (await ex(text("""
        WITH d AS (
          SELECT review_date AS day, CASE WHEN rating_norm >= 4.5 THEN 'five_star' ELSE 'one_star' END AS kind, count(*) AS c
          FROM review WHERE workspace_id = :ws AND review_date IS NOT NULL AND (rating_norm >= 4.5 OR rating_norm <= 1.5)
          GROUP BY 1, 2),
        st AS (SELECT kind, avg(c) AS m, coalesce(nullif(stddev_pop(c), 0), 1) AS sd, count(*) AS days FROM d GROUP BY kind)
        SELECT d.day, d.kind, d.c, st.m, st.sd FROM d JOIN st USING (kind)
        WHERE st.days >= 5 AND d.c >= :minc AND d.c > st.m + :z * st.sd ORDER BY (d.c - st.m) / st.sd DESC LIMIT 10"""), a)).all()
    same_text = (await ex(text("""
        SELECT left(text_clean, 140), count(*), count(DISTINCT product_id), count(DISTINCT review_date)
        FROM review WHERE workspace_id = :ws AND length(text_clean) >= 15
        GROUP BY text_clean HAVING count(*) > 1 ORDER BY count(*) DESC LIMIT 10"""), a)).all()
    authors = (await ex(text("""
        SELECT left(extra ->> 'author', 40), count(*), count(DISTINCT product_id), avg(rating_norm),
               count(*) FILTER (WHERE rating_norm >= 4.5)
        FROM review WHERE workspace_id = :ws AND coalesce(extra ->> 'author', '') <> ''
        GROUP BY extra ->> 'author' HAVING count(*) >= 3 ORDER BY count(*) DESC LIMIT 10"""), a)).all()
    has_author = await session.scalar(text(
        "SELECT count(*) FROM review WHERE workspace_id = :ws AND coalesce(extra ->> 'author', '') <> ''"), a)
    outliers = (await ex(text("""
        WITH m AS (SELECT product_id, avg(rating_norm) AS mean, count(rating_norm) AS n FROM review
                   WHERE workspace_id = :ws GROUP BY product_id)
        SELECT r.review_id, p.name, r.rating_norm, m.mean, left(r.text_clean, 200)
        FROM review r JOIN m ON m.product_id = r.product_id JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND m.n >= 10 AND r.rating_norm IS NOT NULL AND abs(r.rating_norm - m.mean) >= 3
        ORDER BY abs(r.rating_norm - m.mean) DESC LIMIT 10"""), a)).all()
    return {
        "bursts": [{"day": str(d), "kind": k, "reviews": c, "usual": _f(m, 1)} for d, k, c, m, sd in bursts],
        "same_text": [{"text": t, "reviews": c, "products": p, "days": dd} for t, c, p, dd in same_text],
        "authors": [{"author": au, "reviews": c, "products": p, "avg_rating": _f(r), "five_star": f} for au, c, p, r, f in authors],
        "author_column_found": (has_author or 0) > 0,
        "outliers": [{"review_id": i, "product": pn, "stars": _f(r, 1), "product_average": _f(mean), "text": tx} for i, pn, r, mean, tx in outliers],
        "note": "Flags are leads to check, not proof. A burst is a day with far more 5 star or 1 star reviews than usual.",
    }
'@ | Set-Content -Encoding ascii backend\app\api\quality.py

@'
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
'@ | Set-Content -Encoding ascii backend\scripts\download_demo.py

@'
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "./api";

type Quality = {
  files: number; rows_in_files: number; accepted: number; repaired: number; rejected: number; reconciles: boolean;
  reviews: number; spam: number; spam_pct: number | null; duplicates_removed: number;
  missing_rating: number; missing_rating_pct: number | null; missing_date: number; missing_date_pct: number | null;
  scored: number; scored_pct: number | null; language_unknown: number; languages: { language: string; reviews: number }[]; note: string;
};
type Flags = {
  bursts: { day: string; kind: string; reviews: number; usual: number | null }[];
  same_text: { text: string; reviews: number; products: number; days: number }[];
  authors: { author: string; reviews: number; products: number; avg_rating: number | null; five_star: number }[];
  author_column_found: boolean;
  outliers: { review_id: number; product: string; stars: number | null; product_average: number | null; text: string }[];
  note: string;
};

function Stat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "good" | "warn" }) {
  const color = tone === "good" ? "#34d399" : tone === "warn" ? "#f5b83d" : undefined;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold" style={{ color }}>{value}</div>
      {note && <div className="mt-1 text-xs text-slate-400">{note}</div>}
    </div>
  );
}

function Panel({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-3 text-xs text-slate-500">{sub}</p>
      {children}
    </section>
  );
}

const Empty = ({ children }: { children: ReactNode }) => <p className="text-sm text-slate-400">{children}</p>;

export default function QualityPage() {
  const q = useQuery({ queryKey: ["data-quality"], queryFn: () => api<Quality>("/data-quality") });
  const f = useQuery({ queryKey: ["review-flags"], queryFn: () => api<Flags>("/review-flags") });
  if (q.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (q.error || !q.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const d = q.data;
  if (d.reviews === 0 && d.files === 0) {
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <h2 className="text-2xl font-bold">No data yet</h2>
        <p className="mt-2 text-slate-500">Upload a file and this page shows what was accepted, repaired or rejected, and which reviews look suspicious.</p>
        <Link to="/upload" className="mt-6 inline-block rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50">Upload reviews</Link>
      </div>
    );
  }
  const fl = f.data;
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold">Data quality and review flags</h1>
        <p className="text-slate-500">What happened to every row you uploaded, and which reviews may be fake or pushed.</p>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Rows in files" value={String(d.rows_in_files)} note={`${d.files} file(s)`} />
        <Stat label="Accepted" value={String(d.accepted)} tone="good" />
        <Stat label="Repaired" value={String(d.repaired)} note="fixed and kept" />
        <Stat label="Rejected" value={String(d.rejected)} tone={d.rejected ? "warn" : undefined} note="kept aside with a reason" />
      </div>
      <p className={"text-sm " + (d.reconciles ? "text-emerald-700" : "text-amber-700")}>
        {d.reconciles ? "Every row is accounted for: accepted + repaired + rejected = rows in files." : "These counts do not add up to the rows in the files. Check the upload report."}
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Reviews stored" value={String(d.reviews)} />
        <Stat label="Spam" value={String(d.spam)} note={`${d.spam_pct ?? 0}% , left out of scores`} tone={d.spam ? "warn" : undefined} />
        <Stat label="Duplicates removed" value={String(d.duplicates_removed)} note="same text, product, date, rating" />
        <Stat label="Scored" value={(d.scored_pct ?? 0) + "%"} note={`${d.scored} reviews`} />
        <Stat label="No rating" value={String(d.missing_rating)} note={`${d.missing_rating_pct ?? 0}%`} />
        <Stat label="No date" value={String(d.missing_date)} note={`${d.missing_date_pct ?? 0}% , not in trends`} />
        <Stat label="Language unknown" value={String(d.language_unknown)} />
        <Stat label="Languages" value={String(d.languages.length)} note={d.languages.map((l) => `${l.language} ${l.reviews}`).join(", ")} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Rating bursts" sub="Days with far more 5 star or 1 star reviews than usual">
          {!fl || fl.bursts.length === 0 ? <Empty>No bursts found (needs at least 5 days of data).</Empty> : (
            <table className="w-full text-sm"><thead className="text-left text-slate-500"><tr><th>Day</th><th>Type</th><th>Reviews</th><th>Usual</th></tr></thead>
              <tbody>{fl.bursts.map((b) => <tr key={b.day + b.kind} className="border-t"><td className="py-1">{b.day}</td><td>{b.kind === "five_star" ? "5 star" : "1 star"}</td><td>{b.reviews}</td><td>{b.usual}</td></tr>)}</tbody></table>
          )}
        </Panel>
        <Panel title="Repeated text" sub="The same words posted more than once">
          {!fl || fl.same_text.length === 0 ? <Empty>No repeated text found.</Empty> : (
            <ul className="space-y-2 text-sm">{fl.same_text.map((s, i) => (
              <li key={i} className="border-t pt-2 first:border-0 first:pt-0"><span className="text-slate-800">&ldquo;{s.text}&rdquo;</span>
                <div className="text-xs text-slate-500">{s.reviews} reviews, {s.products} product(s), {s.days} day(s)</div></li>
            ))}</ul>
          )}
        </Panel>
        <Panel title="One author, many reviews" sub="Authors with 3 or more reviews">
          {fl && !fl.author_column_found ? <Empty>No author column was found in your files, so this check cannot run.</Empty>
            : !fl || fl.authors.length === 0 ? <Empty>No author has 3 or more reviews.</Empty> : (
            <table className="w-full text-sm"><thead className="text-left text-slate-500"><tr><th>Author</th><th>Reviews</th><th>Products</th><th>Avg stars</th><th>5 star</th></tr></thead>
              <tbody>{fl.authors.map((a) => <tr key={a.author} className="border-t"><td className="py-1">{a.author}</td><td>{a.reviews}</td><td>{a.products}</td><td>{a.avg_rating}</td><td>{a.five_star}</td></tr>)}</tbody></table>
          )}
        </Panel>
        <Panel title="Rating outliers" sub="Reviews 3 or more stars away from their product's average">
          {!fl || fl.outliers.length === 0 ? <Empty>No outliers found.</Empty> : (
            <ul className="space-y-2 text-sm">{fl.outliers.map((o) => (
              <li key={o.review_id} className="border-t pt-2 first:border-0 first:pt-0">
                <div className="text-xs text-slate-500">{o.product}: {o.stars} stars against an average of {o.product_average}</div>
                <div className="text-slate-800">{o.text}</div></li>
            ))}</ul>
          )}
        </Panel>
      </div>
      <p className="text-xs text-slate-400">{d.note} {fl?.note}</p>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Quality.tsx

@'
"""Step 27 patcher. Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s)
    assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2)
    print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

def main_py(s):
    s = once(s, "from app.api.replies import router as replies_router\n", "from app.api.quality import router as quality_router\nfrom app.api.replies import router as replies_router\n")
    return once(s, "app.include_router(sentiment_router, dependencies=protected)\n",
                "app.include_router(sentiment_router, dependencies=protected)\napp.include_router(quality_router, dependencies=protected)\n")
edit("backend/app/main.py", "quality_router", main_py)

edit("backend/app/api/dashboard.py", '"quarter", "year"', lambda s: once(s, 'grain: Literal["week", "month"] = "week"', 'grain: Literal["week", "month", "quarter", "year"] = "week"'))

def trends(s):
    s = once(s, 'useState<"week" | "month">("week")', 'useState<"week" | "month" | "quarter" | "year">("week")')
    return once(s, '{(["week", "month"] as const).map((g) => (', '{(["week", "month", "quarter", "year"] as const).map((g) => (')
edit("frontend/src/Trends.tsx", '"quarter", "year"', trends)

edit("frontend/src/Layout.tsx", "/quality", lambda s: once(s,
    '    { to: "/upload", label: "Upload and Data", icon: "upload" },\n',
    '    { to: "/upload", label: "Upload and Data", icon: "upload" },\n    { to: "/quality", label: "Data Quality", icon: "check" },\n'))

def main_tsx(s):
    s = once(s, 'import Upload from "./Upload";\n', 'import Upload from "./Upload";\nimport Quality from "./Quality";\n')
    return once(s, '            <Route path="upload" element={<Upload />} />\n',
                '            <Route path="upload" element={<Upload />} />\n            <Route path="quality" element={<Quality />} />\n')
edit("frontend/src/main.tsx", "<Quality", main_tsx)
'@ | Set-Content -Encoding ascii patch_step27.py
python patch_step27.py
Remove-Item patch_step27.py

Write-Host 'Step 27 files written.'
