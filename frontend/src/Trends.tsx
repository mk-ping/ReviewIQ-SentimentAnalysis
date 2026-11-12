import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { filterQs, useFilters } from "./store";
import Chart from "./Chart";

type Point = { period: string; reviews: number; low_sample: boolean; avg_rating: number | null; avg_fused_rating: number | null; net_sentiment: number | null };
type TrendData = { grain: string; points: Point[]; note: string };
type AlertData = {
  alerts: { aspect: string; week: string; count: number; usual: number; z: number }[];
  weeks: number; enough_history?: boolean; note: string;
};

const d1 = (x: number | null | undefined) => (x == null ? "n/a" : x.toFixed(2));

export default function Trends() {
  const f = useFilters();
  const [grain, setGrain] = useState<"week" | "month">("week");
  const qs = filterQs(f);
  const join = qs ? qs + "&" : "?";
  const t = useQuery({ queryKey: ["trends", grain, qs], queryFn: () => api<TrendData>("/trends" + join + "grain=" + grain) });
  const a = useQuery({ queryKey: ["alerts"], queryFn: () => api<AlertData>("/alerts") });

  if (t.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (t.error || !t.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const pts = t.data.points;
  const labels = pts.map((p) => p.period);

  const first = pts.find((p) => p.avg_rating != null), last = [...pts].reverse().find((p) => p.avg_rating != null);
  let headline = "Not enough dated reviews to draw a trend yet.";
  if (first && last && first !== last) {
    const diff = (last.avg_rating as number) - (first.avg_rating as number);
    const word = Math.abs(diff) < 0.1 ? "stayed about the same" : diff > 0 ? "went up" : "went down";
    headline = `The average rating ${word}: ${d1(first.avg_rating)} in ${first.period}, ${d1(last.avg_rating)} in ${last.period}.`;
  }

  const ratingOpt = {
    grid: { left: 45, right: 10, top: 30, bottom: 30 }, legend: { top: 0 }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: labels }, yAxis: { type: "value", min: 1, max: 5 },
    series: [
      { name: "Customer stars", type: "line", data: pts.map((p) => p.avg_rating), itemStyle: { color: "#94a3b8" } },
      { name: "What the text supports", type: "line", data: pts.map((p) => p.avg_fused_rating), itemStyle: { color: "#4f46e5" } },
    ],
  };
  const sentOpt = {
    grid: { left: 45, right: 10, top: 20, bottom: 30 }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: labels }, yAxis: { type: "value", min: -1, max: 1 },
    series: [{ name: "Net sentiment", type: "bar", data: pts.map((p) => p.net_sentiment), itemStyle: { color: "#0f766e" } }],
  };
  const volOpt = {
    grid: { left: 45, right: 10, top: 20, bottom: 30 }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: labels }, yAxis: { type: "value" },
    series: [{ name: "Reviews", type: "bar", data: pts.map((p) => p.reviews), itemStyle: { color: "#64748b" } }],
  };
  const thin = pts.filter((p) => p.low_sample).length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Is it getting worse?</h1>
        <p className="text-slate-600">{headline}</p>
        {thin > 0 && <p className="mt-1 text-sm text-amber-600">Warning: {thin} of {pts.length} periods have fewer than 30 reviews, so small swings may be noise.</p>}
      </header>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">Alerts</h2>
        {(a.data?.alerts ?? []).length > 0 ? (
          <ul className="space-y-2 text-sm">
            {a.data!.alerts.map((x) => (
              <li key={x.aspect} className="rounded-md bg-red-50 p-2 text-red-800">
                Complaints about <b>{x.aspect}</b> jumped to {x.count} in the week of {x.week}, against a usual {x.usual} (z = {x.z}).
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No spikes. {a.data?.note}</p>
        )}
      </section>

      <div className="flex gap-2 text-sm">
        {(["week", "month"] as const).map((g) => (
          <button key={g} onClick={() => setGrain(g)}
            className={"rounded-md px-3 py-1 " + (grain === g ? "bg-indigo-600 text-white" : "border text-slate-600 hover:bg-slate-100")}>
            By {g}
          </button>
        ))}
      </div>

      {pts.length === 0 ? (
        <p className="text-slate-400">No dated reviews for this selection.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-xl bg-white p-4 shadow-sm md:col-span-2">
            <h2 className="mb-2 font-semibold">Rating over time: stars versus what the text supports</h2>
            <Chart option={ratingOpt as never} />
          </section>
          <section className="rounded-xl bg-white p-4 shadow-sm">
            <h2 className="mb-2 font-semibold">Net sentiment (positive minus negative)</h2>
            <Chart option={sentOpt as never} />
          </section>
          <section className="rounded-xl bg-white p-4 shadow-sm">
            <h2 className="mb-2 font-semibold">Review volume</h2>
            <Chart option={volOpt as never} />
          </section>
        </div>
      )}
      <p className="text-xs text-slate-400">{t.data.note}</p>
    </div>
  );
}
