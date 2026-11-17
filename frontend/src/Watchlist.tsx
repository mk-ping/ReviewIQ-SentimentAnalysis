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
        {p.low_sample && <span className="text-xs text-amber-500">Early read ({p.n} reviews)</span>}
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
