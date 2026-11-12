import { useQuery } from "@tanstack/react-query";
import { api, Distribution, Summary, TrueRating } from "./api";
import Chart from "./Chart";

const fmt = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : x.toFixed(d));

function Card({ title, value, note, warn }: { title: string; value: string; note: string; warn?: boolean }) {
  return (
    <div className="rounded-xl bg-white p-4 shadow-sm">
      <div className="text-sm text-slate-500">{title}</div>
      <div className="mt-1 text-3xl font-semibold">{value}</div>
      <div className={"mt-1 text-xs " + (warn ? "text-amber-600" : "text-slate-400")}>
        {warn ? "Warning: small sample. " : ""}{note}
      </div>
    </div>
  );
}

export default function Home() {
  const s = useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/summary") });
  const d = useQuery({ queryKey: ["distribution"], queryFn: () => api<Distribution>("/distribution") });
  const t = useQuery({ queryKey: ["true-rating"], queryFn: () => api<{ products: TrueRating[] }>("/true-rating") });

  if (s.isLoading || d.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (s.error || d.error || !s.data || !d.data)
    return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const sum = s.data, dist = d.data;

  const option = {
    grid: { left: 40, right: 10, top: 20, bottom: 30 },
    xAxis: { type: "category", data: dist.histogram.map((b) => b.stars + " star") },
    yAxis: { type: "value" },
    tooltip: { trigger: "axis" },
    series: [{ type: "bar", data: dist.histogram.map((b) => b.count), itemStyle: { color: "#4f46e5" } }],
  } as const;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">How are we doing?</h1>
        <p className="text-slate-600">
          {sum.reviews} reviews. Customers are {dist.audience ?? "not yet rated"}.
          {sum.mismatch_rate != null && ` Stars and text disagree on ${(sum.mismatch_rate * 100).toFixed(0)}% of reviews.`}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card title="Average rating" value={fmt(sum.average_rating)} note={`${sum.rated_reviews} rated reviews`} warn={sum.low_sample} />
        <Card title="Weighted rating" value={fmt(sum.weighted_rating)} note="pulled toward the overall average" warn={sum.low_sample} />
        <Card title="Net sentiment" value={fmt(sum.net_sentiment)} note={`${sum.scored_reviews} scored reviews`} warn={sum.scored_reviews < 30} />
        <Card title="Negative" value={sum.percent_negative == null ? "n/a" : sum.percent_negative + "%"} note="of scored reviews" warn={sum.scored_reviews < 30} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Rating distribution ({dist.n} reviews)</h2>
          <Chart option={option as never} />
        </section>
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Top problems</h2>
          <ul className="space-y-1 text-sm">
            {sum.top_problems.map((p) => (
              <li key={p.issue} className="flex justify-between"><span>{p.issue}</span><span className="text-slate-500">{p.reviews} reviews, priority {p.priority_score}</span></li>
            ))}
            {sum.top_problems.length === 0 && <li className="text-slate-400">No issues built yet.</li>}
          </ul>
          <h2 className="mb-2 mt-4 font-semibold">Top strengths</h2>
          <ul className="space-y-1 text-sm">
            {sum.top_strengths.map((p) => (
              <li key={p.aspect} className="flex justify-between"><span>{p.aspect}</span><span className="text-slate-500">{p.positive_mentions} positive mentions</span></li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">True Rating: shown versus what the text supports</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th>Product</th><th>Reviews</th><th>Shown</th><th>True</th><th>Verdict</th></tr></thead>
          <tbody>
            {(t.data?.products ?? []).map((p) => (
              <tr key={p.product} className="border-t">
                <td className="py-1">{p.product}</td><td>{p.n}</td><td>{fmt(p.shown_avg)}</td><td>{fmt(p.true_rating)}</td>
                <td className="text-slate-500">{p.clear_difference ? "clear difference" : p.low_sample ? "too few reviews" : "no clear difference"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-400">Both numbers are always shown. Small products are pulled toward the overall average.</p>
      </section>
    </div>
  );
}
