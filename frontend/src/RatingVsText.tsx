import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, RatingVsTextData, MismatchList, HiddenData } from "./api";
import { filterQs, useFilters } from "./store";
import Chart from "./Chart";

const pct = (x: number | null | undefined) => (x == null ? "n/a" : (x * 100).toFixed(0) + "%");
const num = (x: number | null | undefined, d = 1) => (x == null ? "n/a" : x.toFixed(d));

/** Wrap the first case-insensitive occurrence of each phrase in <mark>. */
function Highlighted({ text, phrases }: { text: string; phrases: string[] }) {
  const lower = text.toLowerCase();
  const spans: [number, number][] = [];
  for (const ph of phrases) {
    const i = ph ? lower.indexOf(ph.toLowerCase()) : -1;
    if (i >= 0) spans.push([i, i + ph.length]);
  }
  spans.sort((a, b) => a[0] - b[0]);
  const out: ReactNode[] = [];
  let at = 0;
  spans.forEach(([s, e], k) => {
    if (s < at) return;
    out.push(text.slice(at, s));
    out.push(<mark key={k} className="rounded bg-red-100 px-0.5 text-red-800">{text.slice(s, e)}</mark>);
    at = e;
  });
  out.push(text.slice(at));
  return <>{out}</>;
}

const KIND: Record<string, string> = {
  underrated: "Under-rated: the text is happier than the stars",
  overrated: "Over-rated: the text is unhappier than the stars",
  sarcasm: "Possible sarcasm",
};

export default function RatingVsText() {
  const f = useFilters();
  const [tab, setTab] = useState<"mismatch" | "hidden">("mismatch");
  const rvt = useQuery({ queryKey: ["rvt", f.product, f.dateFrom, f.dateTo], queryFn: () => api<RatingVsTextData>("/rating-vs-text" + filterQs(f)) });
  const mm = useQuery({ queryKey: ["mismatches"], queryFn: () => api<MismatchList>("/mismatches?limit=200") });
  const hd = useQuery({ queryKey: ["hidden"], queryFn: () => api<HiddenData>("/hidden-dissatisfaction?limit=100") });

  if (rvt.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (rvt.error || !rvt.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const d = rvt.data;

  const chart = {
    grid: { left: 45, right: 10, top: 30, bottom: 30 },
    legend: { top: 0 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: d.by_star.map((b) => b.stars + " star") },
    yAxis: { type: "value", min: 1, max: 5, name: "stars" },
    series: [
      { name: "Customer stars", type: "line", data: d.by_star.map((b) => b.stars), lineStyle: { type: "dashed" }, itemStyle: { color: "#94a3b8" } },
      { name: "What the text says", type: "bar", data: d.by_star.map((b) => b.avg_text_stars), itemStyle: { color: "#4f46e5" } },
    ],
  };

  const product = f.product;
  const mismatches = (mm.data?.items ?? []).filter((m) => !product || m.product === product);
  const hidden = (hd.data?.items ?? []).filter((m) => !product || m.product === product);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Can I trust the stars?</h1>
        <p className="text-slate-600">
          Stars and text agree on {pct(d.agreement_rate)} of {d.n} reviews.
          {d.mismatches > 0 && ` ${d.underrated} look under-rated and ${d.overrated} look over-rated.`}
        </p>
        {d.low_sample && <p className="mt-1 text-sm text-amber-600">Warning: fewer than 30 reviews, so treat these numbers as a first look.</p>}
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Agreement", pct(d.agreement_rate), `${d.n} scored reviews`],
          ["Mismatches", String(d.mismatches), "stars and text disagree"],
          ["Average star gap", num(d.mean_abs_star_gap), "stars between text and rating"],
          ["Big gaps", pct(d.big_gap_share), "gap of 1.5 stars or more"],
        ].map(([t, v, n]) => (
          <div key={t} className="rounded-xl bg-white p-4 shadow-sm">
            <div className="text-sm text-slate-500">{t}</div>
            <div className="mt-1 text-3xl font-semibold">{v}</div>
            <div className="mt-1 text-xs text-slate-400">{n}</div>
          </div>
        ))}
      </div>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">What the text says at each star level</h2>
        <Chart option={chart as never} />
        <p className="text-xs text-slate-400">{d.note}</p>
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <div className="mb-3 flex gap-2 text-sm">
          {([["mismatch", `Mismatches (${mismatches.length})`], ["hidden", `Hidden Dissatisfaction (${hd.data?.hidden_reviews ?? 0})`]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={"rounded-md px-3 py-1 " + (tab === k ? "bg-indigo-600 text-white" : "border text-slate-600 hover:bg-slate-100")}>{label}</button>
          ))}
        </div>

        {tab === "mismatch" && (
          <ul className="space-y-3 text-sm">
            {mismatches.map((m) => (
              <li key={m.review_id} className="border-t pt-3">
                <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-500">
                  <span>{m.product} | customer gave {num(m.stars, 0)} stars | text suggests {num(m.fused_stars)} | gap {num(m.star_gap)}</span>
                  <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-700">{KIND[m.type] ?? m.type}</span>
                </div>
                <p className="mt-1">{m.text}</p>
              </li>
            ))}
            {mismatches.length === 0 && <li className="text-slate-400">No mismatches for this selection.</li>}
          </ul>
        )}

        {tab === "hidden" && hd.data && (
          <div>
            <p className="mb-3 text-sm text-slate-600">
              {hd.data.hidden_reviews} of {hd.data.rated_4plus_analysed} reviews rated 4 or 5 stars still contain a clear complaint
              {hd.data.hidden_rate != null && ` (${pct(hd.data.hidden_rate)})`}.
              {hd.data.low_sample && " Few reviews analysed so far, so this is a first look."}
            </p>
            {hd.data.blind_spots.length > 0 && (
              <table className="mb-4 w-full text-sm">
                <thead className="text-left text-slate-500"><tr><th>Aspect</th><th>Complaints</th><th>In 4-5 star reviews</th><th>Share</th></tr></thead>
                <tbody>
                  {hd.data.blind_spots.map((b) => (
                    <tr key={b.aspect} className="border-t">
                      <td className="py-1">{b.aspect}{b.low_sample && <span className="ml-2 text-xs text-amber-600">few reviews</span>}</td>
                      <td>{b.negative_mentions}</td><td>{b.in_4_5_star}</td><td>{pct(b.blind_spot_share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="space-y-3 text-sm">
              {hidden.map((h) => (
                <li key={h.review_id} className="border-t pt-3">
                  <div className="text-xs text-slate-500">{h.product} | {num(h.stars, 0)} stars</div>
                  <p className="mt-1"><Highlighted text={h.text} phrases={h.negative_mentions.map((n) => n.phrase)} /></p>
                </li>
              ))}
              {hidden.length === 0 && <li className="text-slate-400">No hidden complaints for this selection.</li>}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
