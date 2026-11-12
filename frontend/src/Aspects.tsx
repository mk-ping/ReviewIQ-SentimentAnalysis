import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, AspectRow, Drivers } from "./api";
import Chart from "./Chart";

const pct = (x: number | null | undefined) => (x == null ? "n/a" : (x * 100).toFixed(0) + "%");

export default function Aspects() {
  const [range, setRange] = useState<[number, number]>([1, 2]);
  const a = useQuery({ queryKey: ["aspects"], queryFn: () => api<{ aspects: AspectRow[] }>("/aspects") });
  const d = useQuery({ queryKey: ["drivers", range], queryFn: () => api<Drivers>(`/aspects/drivers?min_stars=${range[0]}&max_stars=${range[1]}`) });

  if (a.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (a.error || !a.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const rows = [...a.data.aspects].sort((x, y) => x.avg_sentiment - y.avg_sentiment);
  const worst = rows[0], best = rows[rows.length - 1];

  const option = {
    grid: { left: 110, right: 20, top: 10, bottom: 30 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", min: -1, max: 1, name: "average sentiment" },
    yAxis: { type: "category", data: rows.map((r) => r.aspect) },
    series: [{
      type: "bar",
      data: rows.map((r) => ({ value: r.avg_sentiment, itemStyle: { color: r.avg_sentiment < -0.25 ? "#dc2626" : r.avg_sentiment > 0.25 ? "#16a34a" : "#94a3b8" } })),
    }],
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">What do customers care about?</h1>
        <p className="text-slate-600">
          {rows.length === 0 ? "No aspects yet. Run aspect extraction on a scored batch first." :
            `Customers like ${best.aspect} most and are least happy with ${worst.aspect}.`}
        </p>
      </header>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">Average sentiment by aspect</h2>
        <Chart option={option as never} height={Math.max(200, rows.length * 36 + 40)} />
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th>Aspect</th><th>Mentions</th><th>Positive</th><th>Neutral</th><th>Negative</th></tr></thead>
          <tbody>
            {[...rows].reverse().map((r) => (
              <tr key={r.aspect} className="border-t">
                <td className="py-1">{r.aspect}{r.low_sample && <span className="ml-2 text-xs text-amber-600">few mentions</span>}</td>
                <td>{r.mentions}</td><td>{r.positive}</td><td>{r.neutral}</td><td>{r.negative}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">What do unhappy customers talk about?</h2>
        <div className="mb-3 flex gap-2 text-sm">
          {([[1, 2, "1-2 stars"], [3, 3, "3 stars"], [4, 5, "4-5 stars"]] as const).map(([lo, hi, label]) => (
            <button key={label} onClick={() => setRange([lo, hi])}
              className={"rounded-md px-3 py-1 " + (range[0] === lo ? "bg-indigo-600 text-white" : "border text-slate-600 hover:bg-slate-100")}>{label}</button>
          ))}
        </div>
        {d.data && (
          <>
            {d.data.low_sample && <p className="mb-2 text-sm text-amber-600">Warning: only {d.data.reviews_in_range} reviews in this range.</p>}
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500"><tr><th>Aspect</th><th>Share of this group</th><th>Share of others</th><th>Avg sentiment</th></tr></thead>
              <tbody>
                {d.data.drivers.map((x) => (
                  <tr key={x.aspect} className="border-t">
                    <td className="py-1">{x.aspect}</td><td>{pct(x.share_in_range)}</td><td>{pct(x.share_elsewhere)}</td>
                    <td>{x.avg_sentiment_in_range == null ? "n/a" : x.avg_sentiment_in_range.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate-400">{d.data.note}</p>
          </>
        )}
      </section>
    </div>
  );
}
