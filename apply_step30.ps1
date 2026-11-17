# Step 30: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Product watchlist: one explainable 0-100 risk score per product, so a manager sees which product needs attention first.
Six signals, each scaled 0 to 1 and multiplied by its weight (the weights add to 100). Pure functions, so they test offline."""

WEIGHTS = {"negative": 30, "trend": 20, "rating_drop": 10, "severe": 15, "hidden": 10, "concentration": 15}
LABELS = {
    "negative": "Share of negative reviews",
    "trend": "Complaints rising recently",
    "rating_drop": "Average rating falling",
    "severe": "Safety, allergy, fraud or legal mentions",
    "hidden": "Unhappy customers inside 4 and 5 star reviews",
    "concentration": "One aspect drawing most complaints",
}
FULL_AT = {"negative": 0.40, "trend": 0.20, "rating_drop": 1.0, "severe": 3, "hidden": 0.20, "concentration": 0.25}
MIN_WINDOW = 10      # reviews needed in both the recent and the earlier window before a trend is judged
HIGH, WATCH = 60, 35
LOW_SAMPLE = 30


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def risk(m: dict) -> dict:
    """m: n, neg_share, recent_n, earlier_n, recent_neg, earlier_neg, recent_avg, earlier_avg, severe_n, hidden_share,
    top_aspect, top_aspect_share. Missing or None signals score 0 and are named in 'not_judged'."""
    n = m.get("n") or 0
    have_trend = (m.get("recent_n") or 0) >= MIN_WINDOW and (m.get("earlier_n") or 0) >= MIN_WINDOW
    raw: dict[str, float | None] = {
        "negative": _clip((m.get("neg_share") or 0) / FULL_AT["negative"]) if n else 0.0,
        "trend": _clip(((m.get("recent_neg") or 0) - (m.get("earlier_neg") or 0)) / FULL_AT["trend"]) if have_trend else None,
        "rating_drop": _clip(((m.get("earlier_avg") or 0) - (m.get("recent_avg") or 0)) / FULL_AT["rating_drop"])
        if have_trend and m.get("earlier_avg") is not None and m.get("recent_avg") is not None else None,
        "severe": _clip((m.get("severe_n") or 0) / FULL_AT["severe"]),
        "hidden": _clip(m["hidden_share"] / FULL_AT["hidden"]) if m.get("hidden_share") is not None else None,
        "concentration": _clip((m.get("top_aspect_share") or 0) / FULL_AT["concentration"]) if m.get("top_aspect") else 0.0,
    }
    parts = {k: round(WEIGHTS[k] * (v or 0.0), 1) for k, v in raw.items()}
    score = round(sum(parts.values()))
    level = "high" if score >= HIGH else "watch" if score >= WATCH else "ok"
    reasons = []
    for k in sorted(parts, key=lambda k: -parts[k]):
        if raw[k] is None or raw[k] < 0.5:
            continue
        if k == "negative":
            reasons.append(f"{round(100 * (m.get('neg_share') or 0))}% of reviews are negative.")
        elif k == "trend":
            reasons.append(f"Negative reviews rose from {round(100 * (m.get('earlier_neg') or 0))}% to {round(100 * (m.get('recent_neg') or 0))}% in the last 30 days.")
        elif k == "rating_drop":
            reasons.append(f"Average rating fell from {m['earlier_avg']:.1f} to {m['recent_avg']:.1f} stars recently.")
        elif k == "severe":
            reasons.append(f"{m.get('severe_n')} review(s) mention safety, allergy, fraud or legal terms.")
        elif k == "hidden":
            reasons.append(f"{round(100 * m['hidden_share'])}% of 4 and 5 star reviews still contain a complaint.")
        elif k == "concentration":
            reasons.append(f"{m['top_aspect']} draws complaints in {round(100 * (m.get('top_aspect_share') or 0))}% of reviews.")
    not_judged = [LABELS[k] for k, v in raw.items() if v is None]
    if n == 0:
        action = "No scored reviews yet."
    elif level == "ok":
        action = "No action needed now. Keep monitoring."
    elif m.get("top_aspect"):
        action = f"Start with {m['top_aspect']}: read its recent complaints and assign an owner."
    else:
        action = "Read the most recent negative reviews and assign an owner."
    return {"score": score, "level": level, "parts": parts, "reasons": reasons, "not_judged": not_judged,
            "low_sample": n < LOW_SAMPLE, "action": action}


def trend_word(m: dict) -> str:
    if (m.get("recent_n") or 0) < MIN_WINDOW or (m.get("earlier_n") or 0) < MIN_WINDOW:
        return "not enough recent reviews"
    d = (m.get("recent_neg") or 0) - (m.get("earlier_neg") or 0)
    return "rising" if d >= 0.05 else "falling" if d <= -0.05 else "steady"
'@ | Set-Content -Encoding ascii backend\app\services\watchlist.py

@'
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import thresholds as T
from app.core.severe_terms import PREFILTER, severe_hits
from app.db.session import get_session
from app.services.watchlist import risk, trend_word

router = APIRouter(tags=["watchlist"])

RECENT_DAYS, EARLIER_DAYS = 30, 60
BASE = "FROM review r JOIN product p ON p.product_id = r.product_id WHERE r.workspace_id = :ws AND r.spam_score <= :spam"


@router.get("/watchlist")
async def watchlist(session: AsyncSession = Depends(get_session)):
    """Every product ranked by a 0-100 risk score, with the reasons, its worst aspect and its top issue."""
    ws = await _ws(session)
    ex = session.execute
    a = {"ws": ws, "spam": T.SPAM_MAX}
    last = (await ex(text(f"SELECT max(r.review_date) {BASE}"), a)).scalar()
    if last is None:
        return {"products": [], "n_products": 0, "as_of": None, "note": "No reviews yet."}
    last = last if isinstance(last, date) else date.fromisoformat(str(last))
    recent_from, earlier_from = last - timedelta(days=RECENT_DAYS), last - timedelta(days=RECENT_DAYS + EARLIER_DAYS)
    w = dict(a, rf=recent_from, ef=earlier_from)

    base = (await ex(text(f"""
        SELECT p.product_id, p.name, count(*),
          count(*) FILTER (WHERE s.text_label = 'neg'),
          count(*) FILTER (WHERE r.review_date > :rf), count(*) FILTER (WHERE r.review_date > :rf AND s.text_label = 'neg'),
          avg(r.rating_norm) FILTER (WHERE r.review_date > :rf),
          count(*) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf),
          count(*) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf AND s.text_label = 'neg'),
          avg(r.rating_norm) FILTER (WHERE r.review_date > :ef AND r.review_date <= :rf)
        {BASE.replace('WHERE', 'JOIN review_score s ON s.review_id = r.review_id WHERE')} AND s.text_label IS NOT NULL
        GROUP BY 1, 2"""), w)).all()

    hid = {pid: (n, k) for pid, n, k in (await ex(text(f"""
        SELECT r.product_id, count(*), count(*) FILTER (WHERE EXISTS (
          SELECT 1 FROM review_aspect ra WHERE ra.review_id = r.review_id AND ra.sentiment <= :neg AND ra.confidence >= :conf))
        {BASE} AND r.rating_norm >= :stars GROUP BY 1"""), dict(a, neg=T.NEG_MENTION, conf=T.ASPECT_MIN_CONF, stars=T.HIDDEN_MIN_STARS))).all()}

    asp: dict[int, tuple[str, int]] = {}
    for pid, name, k in (await ex(text(f"""
        SELECT r.product_id, x.name, count(DISTINCT r.review_id)
        FROM review r JOIN review_aspect ra ON ra.review_id = r.review_id JOIN aspect x ON x.aspect_id = ra.aspect_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.sentiment <= :neg AND ra.confidence >= :conf
        GROUP BY 1, 2 ORDER BY 3 DESC"""), dict(a, neg=T.NEG_MENTION, conf=T.ASPECT_MIN_CONF))).all():
        asp.setdefault(pid, (name, k))

    severe: dict[int, list] = {}
    for pid, rid, txt in (await ex(text(f"""
        SELECT r.product_id, r.review_id, r.text_clean {BASE} AND r.text_clean ~* :rx ORDER BY r.review_date DESC LIMIT 3000"""),
            dict(a, rx=PREFILTER))).all():
        cats = severe_hits(txt)
        if cats:
            severe.setdefault(pid, []).append({"review_id": rid, "categories": cats, "text": (txt or "")[:200]})

    top_issue = {}
    for pid, name, asp_name, score, k in (await ex(text("""
        SELECT r.product_id, i.name, x.name, coalesce(ip.priority_score, 0), count(*)
        FROM issue_review ir JOIN issue i ON i.issue_id = ir.issue_id JOIN aspect x ON x.aspect_id = i.aspect_id
        JOIN review r ON r.review_id = ir.review_id LEFT JOIN issue_priority ip ON ip.issue_id = i.issue_id
        WHERE r.workspace_id = :ws GROUP BY 1, 2, 3, 4 ORDER BY 4 DESC, 5 DESC"""), {"ws": ws})).all():
        top_issue.setdefault(pid, {"issue": name, "aspect": asp_name, "reviews": k})

    out = []
    for pid, name, n, neg, rn, rneg, ravg, en, eneg, eavg in base:
        hn, hk = hid.get(pid, (0, 0))
        asp_name, asp_k = asp.get(pid, (None, 0))
        m = {"n": n, "neg_share": neg / n if n else 0,
             "recent_n": rn, "recent_neg": rneg / rn if rn else None, "recent_avg": float(ravg) if ravg is not None else None,
             "earlier_n": en, "earlier_neg": eneg / en if en else None, "earlier_avg": float(eavg) if eavg is not None else None,
             "severe_n": len(severe.get(pid, [])), "hidden_share": hk / hn if hn >= 5 else None,
             "top_aspect": asp_name, "top_aspect_share": asp_k / n if n else 0}
        r = risk(m)
        out.append({"product_id": pid, "product": name, "n": n, "neg_share": round(m["neg_share"], 3),
                    "avg_rating_recent": round(m["recent_avg"], 2) if m["recent_avg"] is not None else None,
                    "trend": trend_word(m), "top_aspect": asp_name, "top_issue": top_issue.get(pid),
                    "severe": severe.get(pid, [])[:3], **r})
    out.sort(key=lambda d: (-d["score"], -d["n"]))
    return {"products": out, "n_products": len(out), "as_of": str(last),
            "windows": {"recent_days": RECENT_DAYS, "earlier_days": EARLIER_DAYS},
            "note": "Risk score runs 0 to 100. 60 or more is High, 35 to 59 is Watch. Each score lists the reasons behind it."}
'@ | Set-Content -Encoding ascii backend\app\api\watchlist.py

@'
"""Offline checks for the product risk score. Run: python -m tests.check_watchlist"""
from app.services.watchlist import HIGH, WATCH, WEIGHTS, risk, trend_word

assert sum(WEIGHTS.values()) == 100

calm = {"n": 200, "neg_share": 0.05, "recent_n": 40, "earlier_n": 80, "recent_neg": 0.05, "earlier_neg": 0.05,
        "recent_avg": 4.6, "earlier_avg": 4.6, "severe_n": 0, "hidden_share": 0.02, "top_aspect": "price", "top_aspect_share": 0.03}
r = risk(calm)
assert r["level"] == "ok" and r["score"] < WATCH and r["reasons"] == [] and not r["low_sample"]

bad = {"n": 300, "neg_share": 0.45, "recent_n": 50, "earlier_n": 90, "recent_neg": 0.60, "earlier_neg": 0.30,
       "recent_avg": 2.4, "earlier_avg": 3.8, "severe_n": 4, "hidden_share": 0.3, "top_aspect": "packaging", "top_aspect_share": 0.3}
b = risk(bad)
assert b["score"] == 100 and b["level"] == "high" and b["score"] >= HIGH
assert b["parts"]["negative"] == 30 and b["parts"]["severe"] == 15
assert len(b["reasons"]) == 6 and "packaging" in b["action"]

mid = dict(bad, recent_n=3)                       # too few recent reviews: the trend and the rating drop are not judged
m = risk(mid)
assert m["parts"]["trend"] == 0 and m["parts"]["rating_drop"] == 0 and len(m["not_judged"]) == 2
assert 0 < m["score"] < b["score"]
assert trend_word(mid) == "not enough recent reviews" and trend_word(bad) == "rising" and trend_word(calm) == "steady"

tiny = risk({"n": 5, "neg_share": 0.6})
assert tiny["low_sample"] and tiny["parts"]["trend"] == 0 and tiny["score"] == 30
empty = risk({"n": 0})
assert empty["score"] == 0 and empty["action"] == "No scored reviews yet."
assert risk({"n": 100, "neg_share": 0.2})["score"] == 15
print("watchlist checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_watchlist.py

@'
export default function LoadError({ what = "this page", compact = false }: { what?: string; compact?: boolean }) {
  return (
    <div className={compact ? "py-2" : "mx-auto max-w-md p-10 text-center"}>
      <p className="font-medium text-slate-800">We could not load {what}.</p>
      <p className="mt-1 text-sm text-slate-500">Check your connection and try again. If it keeps happening, sign out and back in.</p>
      <button onClick={() => window.location.reload()} className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">Try again</button>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\LoadError.tsx

@'
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "./api";
import LoadError from "./LoadError";

export type WatchItem = {
  product_id: number; product: string; n: number; neg_share: number; avg_rating_recent: number | null; trend: string;
  top_aspect: string | null; top_issue: { issue: string; aspect: string; reviews: number } | null;
  severe: { review_id: number; categories: string[]; text: string }[];
  score: number; level: "high" | "watch" | "ok"; parts: Record<string, number>; reasons: string[]; not_judged: string[];
  low_sample: boolean; action: string;
};
type Watch = { products: WatchItem[]; n_products: number; as_of: string | null; note: string };

const LABELS: Record<string, string> = {
  negative: "Negative reviews", trend: "Rising complaints", rating_drop: "Rating drop",
  severe: "Safety or legal terms", hidden: "Hidden complaints", concentration: "Worst aspect",
};
const WEIGHTS: Record<string, number> = { negative: 30, trend: 20, rating_drop: 10, severe: 15, hidden: 10, concentration: 15 };
const TONE = { high: "#f87171", watch: "#f5b83d", ok: "#34d399" } as const;
const WORD = { high: "High risk", watch: "Watch", ok: "On track" } as const;

export const useWatchlist = () => useQuery({ queryKey: ["watchlist"], queryFn: () => api<Watch>("/watchlist") });

function Badge({ level }: { level: WatchItem["level"] }) {
  return <span className="rounded-full px-2.5 py-0.5 text-xs font-semibold" style={{ color: TONE[level], border: `1px solid ${TONE[level]}` }}>{WORD[level]}</span>;
}

function Card({ p, open }: { p: WatchItem; open?: boolean }) {
  return (
    <details open={open} className="rounded-xl border border-slate-200 bg-white p-4">
      <summary className="flex cursor-pointer flex-wrap items-center gap-3">
        <span className="w-10 text-2xl font-semibold tabular-nums" style={{ color: TONE[p.level] }}>{p.score}</span>
        <span className="flex-1 font-semibold">{p.product}</span>
        <Badge level={p.level} />
        {p.low_sample && <span className="text-xs text-amber-500">Few reviews ({p.n})</span>}
      </summary>
      <p className="mt-3 text-sm text-slate-300">{p.action}</p>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Why it is flagged</div>
          {p.reasons.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{p.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            : <p className="text-sm text-slate-400">No warning signs.</p>}
          {p.not_judged.length > 0 && <p className="mt-2 text-xs text-slate-500">Not enough data to judge: {p.not_judged.join(", ").toLowerCase()}.</p>}
          {p.top_issue && <p className="mt-2 text-sm">Biggest problem: <b>{p.top_issue.issue}</b> <span className="text-slate-500">({p.top_issue.aspect}, {p.top_issue.reviews} reviews)</span></p>}
        </div>
        <div>
          <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Score breakdown</div>
          {Object.keys(WEIGHTS).map((k) => (
            <div key={k} className="mb-1 flex items-center gap-2 text-xs">
              <span className="w-36 text-slate-400">{LABELS[k]}</span>
              <span className="h-1.5 flex-1 rounded bg-slate-200"><span className="block h-1.5 rounded" style={{ width: `${(100 * (p.parts[k] ?? 0)) / WEIGHTS[k]}%`, background: "#8b7bff" }} /></span>
              <span className="w-10 text-right tabular-nums text-slate-400">{p.parts[k]}/{WEIGHTS[k]}</span>
            </div>
          ))}
        </div>
      </div>
      {p.severe.length > 0 && (
        <div className="mt-3 rounded-lg border border-red-400/40 p-3">
          <div className="mb-1 text-xs font-semibold text-red-400">Reviews to read first</div>
          {p.severe.map((s) => <p key={s.review_id} className="text-sm text-slate-300">"{s.text}" <span className="text-xs text-slate-500">({s.categories.join(", ")})</span></p>)}
        </div>
      )}
    </details>
  );
}

export function NeedsAttention() {
  const w = useWatchlist();
  if (!w.data || w.data.products.length === 0) return null;
  const top = w.data.products.filter((p) => p.level !== "ok").slice(0, 3);
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Needs attention</h2>
        <Link to="/watchlist" className="text-sm text-accent hover:underline">Open watchlist</Link>
      </div>
      {top.length === 0 ? <p className="mt-2 text-sm text-slate-400">No product is flagged right now.</p> : (
        <ul className="mt-2 space-y-2 text-sm">
          {top.map((p) => (
            <li key={p.product_id} className="flex items-start gap-3">
              <span className="w-8 font-semibold tabular-nums" style={{ color: TONE[p.level] }}>{p.score}</span>
              <span><b>{p.product}</b> <span className="text-slate-500">{p.reasons[0] ?? p.action}</span></span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Watchlist() {
  const w = useWatchlist();
  if (w.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (w.error || !w.data) return <LoadError what="the watchlist" />;
  const d = w.data;
  if (d.products.length === 0) {
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <h1 className="text-2xl font-bold">Nothing to watch yet</h1>
        <p className="mt-2 text-slate-500">Upload reviews and run the analysis to see which products need attention first.</p>
        <Link to="/upload" className="mt-6 inline-block rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50">Upload reviews</Link>
      </div>
    );
  }
  const count = (l: string) => d.products.filter((p) => p.level === l).length;
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Product Watchlist</h1>
        <p className="text-slate-500">Products ranked by risk, highest first. Based on reviews up to {d.as_of}. {count("high")} high risk, {count("watch")} to watch, {count("ok")} on track.</p>
      </header>
      {d.products.map((p, i) => <Card key={p.product_id} p={p} open={i === 0 && p.level !== "ok"} />)}
      <p className="text-xs text-slate-500">{d.note} The score combines negative share (30), rising complaints (20), rating drop (10), safety or legal terms (15), hidden complaints in 4 and 5 star reviews (10) and how concentrated complaints are on one aspect (15). Compares the last 30 days with the 60 before.</p>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Watchlist.tsx

@'
import re, pathlib
S = pathlib.Path("frontend/src")

def rd(n): return (S / n).read_text(encoding="utf-8")
def wr(n, t): (S / n).write_text(t, encoding="utf-8")

# 1. friendly load errors on every page
rx = re.compile(r'<(div|p) className="([^"]*)text-red-600">Could not reach the API\. Is uvicorn running on port 8010\?</\1>')
for f in S.glob("*.tsx"):
    t = f.read_text(encoding="utf-8")
    if "uvicorn" not in t: continue
    t2 = rx.sub(lambda m: "<LoadError compact />" if m.group(1) == "p" or "p-8" not in m.group(2) else "<LoadError />", t)
    if t2 != t:
        if 'from "./LoadError"' not in t2:
            lines = t2.split("\n"); i = max(j for j, l in enumerate(lines) if l.startswith("import "))
            lines.insert(i + 1, 'import LoadError from "./LoadError";'); t2 = "\n".join(lines)
        f.write_text(t2, encoding="utf-8")

# 2. professional wording
def sub(n, a, b):
    t = rd(n)
    if a in t: wr(n, t.replace(a, b))
sub("AuthPage.tsx", "ReviewIQ &middot; ADBMS project", "ReviewIQ &middot; Customer review intelligence")
sub("Landing.tsx", "ReviewIQ &middot; built for an Advanced Database Management Systems project", "ReviewIQ &middot; Customer review intelligence")
sub("AuthPage.tsx", "It takes a few seconds. The first account becomes the manager.", "It takes a few seconds. Your workspace is private to you.")
sub("Label.tsx", " A model stays only if it beats stars alone and the TF-IDF baseline (python -m scripts.baseline_tfidf).", " A model is kept only if it beats stars alone and the simple word-count baseline.")
sub("Sentiment.tsx", "No progress for 20 seconds. Is the worker running? Start it with: python -m app.worker.main", "Analysis is taking longer than usual. It keeps running in the background, so you can leave this page and come back.")
sub("Upload.tsx", "No progress for 20 seconds. Is the worker running? Start it with: python -m app.worker.main (it keeps the job, so nothing is lost).", "Analysis is taking longer than usual. It keeps running in the background, so nothing is lost.")
sub("Upload.tsx", "Lost the progress stream. Is the worker running?", "Lost the live progress feed. Refresh the page to see the latest status.")
sub("Upload.tsx", "Needs the worker running. Aspect finding is the slow step if a local LLM is used.", "This can take a few minutes for large files.")
sub("Layout.tsx", 'label: "Upload and Data"', 'label: "Data Sources"')
sub("Layout.tsx", 'label: "Gold Labels and Evaluation"', 'label: "Model Evaluation"')

# 3. watchlist route, nav entry, home card
t = rd("main.tsx")
if "./Watchlist" not in t:
    t = t.replace('import Quality from "./Quality";', 'import Quality from "./Quality";\nimport Watchlist from "./Watchlist";')
    t = t.replace('<Route path="quality" element={<Quality />} />', '<Route path="quality" element={<Quality />} />\n            <Route path="watchlist" element={<Watchlist />} />')
    wr("main.tsx", t)
t = rd("Layout.tsx")
if "/watchlist" not in t:
    t = t.replace('    { to: "/problems",', '    { to: "/watchlist", label: "Product Watchlist", icon: "alert" },\n    { to: "/problems",', 1)
    wr("Layout.tsx", t)
t = rd("Home.tsx")
if "NeedsAttention" not in t:
    t = t.replace('import Chart from "./Chart";', 'import Chart from "./Chart";\nimport { NeedsAttention } from "./Watchlist";', 1)
    t = t.replace('      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">', '      <NeedsAttention />\n\n      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">', 1)
    wr("Home.tsx", t)

# 4. register the API router
m = pathlib.Path("backend/app/main.py"); t = m.read_text(encoding="utf-8")
if "watchlist_router" not in t:
    t = t.replace("from app.api.distribution import router as distribution_router", "from app.api.distribution import router as distribution_router\nfrom app.api.watchlist import router as watchlist_router", 1)
    t = t.replace("app.include_router(distribution_router, dependencies=protected)", "app.include_router(distribution_router, dependencies=protected)\napp.include_router(watchlist_router, dependencies=protected)", 1)
    m.write_text(t, encoding="utf-8")
print("step 30 patched")
'@ | Set-Content -Encoding ascii patch_step30.py
python patch_step30.py
Remove-Item patch_step30.py

Write-Host 'Step 30 files written.'
