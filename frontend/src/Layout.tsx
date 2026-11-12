import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, TrueRating } from "./api";
import { useFilters } from "./store";

const PAGES = [
  { to: "/", label: "Home", ready: true },
  { to: "/rating-vs-text", label: "Rating vs Text", ready: true },
  { to: "/problems", label: "Problems and Priorities", ready: true },
  { to: "/aspects", label: "Aspects", ready: true },
  { to: "/trends", label: "Trends and Alerts", ready: true },
  { to: "/explorer", label: "Review Explorer", ready: true },
  { to: "/upload", label: "Upload and Data", ready: true },
];

function FilterBar() {
  const f = useFilters();
  const products = useQuery({ queryKey: ["true-rating"], queryFn: () => api<{ products: TrueRating[] }>("/true-rating") });
  const input = "rounded-md border border-slate-300 bg-white px-2 py-1 text-sm";
  return (
    <div className="flex flex-wrap items-center gap-3 border-b bg-white px-6 py-3 text-sm">
      <label className="flex items-center gap-2">Product
        <select className={input} value={f.product} onChange={(e) => f.set({ product: e.target.value })}>
          <option value="">All products</option>
          {(products.data?.products ?? []).map((p) => <option key={p.product} value={p.product}>{p.product}</option>)}
        </select>
      </label>
      <label className="flex items-center gap-2">From
        <input type="date" className={input} value={f.dateFrom} onChange={(e) => f.set({ dateFrom: e.target.value })} />
      </label>
      <label className="flex items-center gap-2">To
        <input type="date" className={input} value={f.dateTo} onChange={(e) => f.set({ dateTo: e.target.value })} />
      </label>
      <button className="rounded-md border px-2 py-1 text-slate-600 hover:bg-slate-100" onClick={f.reset}>Clear</button>
    </div>
  );
}

export default function Layout() {
  return (
    <div className="flex min-h-screen">
      <nav className="w-56 shrink-0 border-r bg-white p-4">
        <div className="mb-4 text-lg font-bold text-indigo-600">ReviewIQ</div>
        <ul className="space-y-1 text-sm">
          {PAGES.map((p) => (
            <li key={p.to}>
              {p.ready ? (
                <NavLink to={p.to} end className={({ isActive }) =>
                  "block rounded-md px-3 py-2 " + (isActive ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-700 hover:bg-slate-100")}>
                  {p.label}
                </NavLink>
              ) : (
                <span className="block cursor-not-allowed rounded-md px-3 py-2 text-slate-400" title="Coming in a later step">{p.label}</span>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 flex-1">
        <FilterBar />
        <Outlet />
      </div>
    </div>
  );
}
