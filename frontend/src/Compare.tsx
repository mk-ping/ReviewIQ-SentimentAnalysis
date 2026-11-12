import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, TrueRating } from "./api";
import Chart from "./Chart";

type CompAspect = { aspect: string; mentions: number; avg_sentiment: number | null; low_sample: boolean };
type CompProduct = {
  product: string; reviews: number; low_sample: boolean; avg_rating: number | null;
  spread: number | null; net_sentiment: number | null; aspects: CompAspect[];
};
type CompData = { products: CompProduct[]; not_found: string[] };

const f2 = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : x.toFixed(d));
const tone = (s: number | null | undefined) =>
  s == null ? "bg-slate-50 text-slate-400"
    : s <= -0.25 ? "bg-red-100 text-red-800"
    : s >= 0.25 ? "bg-green-100 text-green-800"
    : "bg-slate-100 text-slate-700";

export default function Compare() {
  const [sel, setSel] = useState<string[] | null>(null);
  const list = useQuery({ queryKey: ["true-rating"], queryFn: () => api<{ products: TrueRating[] }>("/true-rating") });
  const names = (list.data?.products ?? []).map((p) => p.product);
  const chosen = sel ?? names.slice(0, 2);
  const qs = chosen.map((n) => "products=" + encodeURIComponent(n)).join("&");
  const cmp = useQuery({
    queryKey: ["compare", qs],
    queryFn: () => api<CompData>("/compare?" + qs),
    enabled: chosen.length > 0,
  });

  if (list.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (list.error) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;

  const toggle = (n: string) =>
    setSel(chosen.includes(n) ? chosen.filter((x) => x !== n) : [...chosen, n].slice(-4));

  const prods = cmp.data?.products ?? [];
  const rated = prods.filter((p) => p.avg_rating != null).sort((a, b) => (b.avg_rating as number) - (a.avg_rating as number));
  const aspects = Array.from(new Set(prods.flatMap((p) => p.aspects.map((a) => a.aspect)))).sort();
  const cellOf = (p: CompProduct, a: string) => p.aspects.find((x) => x.aspect === a);

  let headline = "Pick at least two products to compare.";
  if (rated.length >= 2) {
    const top = rated[0], low = rated[rated.length - 1];
    headline = `${top.product} has the higher average rating (${f2(top.avg_rating)} against ${f2(low.avg_rating)} for ${low.product}).`;
  }
  let gapLine = "";
  let widest = 0;
  for (const a of aspects) {
    const v = prods.map((p) => cellOf(p, a)?.avg_sentiment).filter((x): x is number => x != null);
    if (v.length >= 2) {
      const d = Math.max(...v) - Math.min(...v);
      if (d > widest) { widest = d; gapLine = `Biggest difference is in ${a}: the products are ${f2(d)} sentiment points apart.`; }
    }
  }

  const option = {
    grid: { left: 45, right: 10, top: 30, bottom: 60 },
    legend: { top: 0 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: aspects, axisLabel: { interval: 0, rotate: 30 } },
    yAxis: { type: "value", min: -1, max: 1, name: "avg sentiment" },
    series: prods.map((p) => ({
      name: p.product, type: "bar",
      data: aspects.map((a) => cellOf(p, a)?.avg_sentiment ?? null),
    })),
  };

  const box = "rounded-xl bg-white p-4 shadow-sm";
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Who is better?</h1>
        <p className="text-slate-600">{headline}</p>
        {gapLine && <p className="text-slate-600">{gapLine}</p>}
      </header>

      <section className={box}>
        <h2 className="mb-2 font-semibold">Choose up to 4 products</h2>
        <div className="flex flex-wrap gap-3 text-sm">
          {names.map((n) => (
            <label key={n} className="flex items-center gap-1">
              <input type="checkbox" checked={chosen.includes(n)} onChange={() => toggle(n)} /> {n}
            </label>
          ))}
          {names.length === 0 && <span className="text-slate-400">No scored products yet.</span>}
        </div>
        <p className="mt-2 text-xs text-slate-400">Choosing a fifth product drops the oldest pick. This page ignores the global date filter.</p>
      </section>

      {cmp.isLoading && chosen.length > 0 && <div className="text-slate-500">Loading...</div>}
      {cmp.error && <div className="text-red-600">Could not load the comparison.</div>}
      {(cmp.data?.not_found ?? []).length > 0 && (
        <p className="text-sm text-amber-700">Not found: {cmp.data!.not_found.join(", ")}</p>
      )}

      {prods.length > 0 && (
        <>
          <section className={box}>
            <h2 className="mb-2 font-semibold">Side by side</h2>
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr><th></th>{prods.map((p) => <th key={p.product}>{p.product}</th>)}</tr>
              </thead>
              <tbody>
                <tr className="border-t"><td className="py-1">Reviews</td>
                  {prods.map((p) => <td key={p.product}>{p.reviews}{p.low_sample && <span className="ml-2 text-xs text-amber-600">few reviews</span>}</td>)}</tr>
                <tr className="border-t"><td className="py-1">Average rating</td>{prods.map((p) => <td key={p.product}>{f2(p.avg_rating)}</td>)}</tr>
                <tr className="border-t"><td className="py-1">Spread (std dev of stars)</td>{prods.map((p) => <td key={p.product}>{f2(p.spread)}</td>)}</tr>
                <tr className="border-t"><td className="py-1">Net sentiment</td>{prods.map((p) => <td key={p.product}>{f2(p.net_sentiment)}</td>)}</tr>
              </tbody>
            </table>
          </section>

          <section className={box}>
            <h2 className="mb-2 font-semibold">Aspect sentiment by product</h2>
            {aspects.length === 0 ? (
              <p className="text-sm text-slate-400">No aspect data yet. Run aspect extraction first.</p>
            ) : (
              <>
                <Chart option={option as never} height={320} />
                <table className="mt-3 w-full text-sm">
                  <thead className="text-left text-slate-500">
                    <tr><th>Aspect</th>{prods.map((p) => <th key={p.product}>{p.product}</th>)}</tr>
                  </thead>
                  <tbody>
                    {aspects.map((a) => (
                      <tr key={a} className="border-t">
                        <td className="py-1">{a}</td>
                        {prods.map((p) => {
                          const c = cellOf(p, a);
                          return (
                            <td key={p.product} className="p-1">
                              <span className={"inline-block rounded px-2 py-0.5 " + tone(c?.avg_sentiment)}>
                                {c ? `${f2(c.avg_sentiment)} (${c.mentions})` : "no mentions"}
                              </span>
                              {c?.low_sample && <span className="ml-1 text-xs text-amber-600">few</span>}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-xs text-slate-400">Red is clearly negative, green is clearly positive. The number in brackets is how many mentions it rests on.</p>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
