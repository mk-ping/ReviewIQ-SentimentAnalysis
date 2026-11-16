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
