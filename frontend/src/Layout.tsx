import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, TrueRating } from "./api";
import { useFilters } from "./store";
import { useAuth } from "./auth";
import { Icon, Wordmark } from "./Brand";

const GROUPS = [
  { title: "Overview", pages: [
    { to: "/", label: "Home", icon: "home" },
    { to: "/sentiment", label: "Sentiment", icon: "smile" },
    { to: "/distribution", label: "Who Likes What", icon: "compare" },
    { to: "/rating-vs-text", label: "Rating vs Text", icon: "gap" },
    { to: "/aspects", label: "Aspects", icon: "layers" },
  ] },
  { title: "Insights", pages: [
    { to: "/watchlist", label: "Product Watchlist", icon: "alert" },
    { to: "/problems", label: "Problems and Priorities", icon: "alert" },
    { to: "/compare", label: "Products and Competitors", icon: "compare" },
    { to: "/trends", label: "Trends and Alerts", icon: "trend" },
    { to: "/listing", label: "Listing vs Reality", icon: "star" },
  ] },
  { title: "Workspace", pages: [
    { to: "/explorer", label: "Review Explorer", icon: "search" },
    { to: "/upload", label: "Data Sources", icon: "upload" },
    { to: "/quality", label: "Data Quality", icon: "check" },
    { to: "/checks", label: "Model Checks", icon: "bolt" },
    { to: "/label", label: "Model Evaluation", icon: "tag" },
    { to: "/reports", label: "Reports and Replies", icon: "file" },
  ] },
];
const ALL = GROUPS.flatMap((g) => g.pages);

function FilterBar() {
  const f = useFilters();
  const products = useQuery({ queryKey: ["true-rating"], queryFn: () => api<{ products: TrueRating[] }>("/true-rating") });
  const input = "rounded-md border border-slate-300 bg-slate-100 px-2 py-1 text-sm text-slate-800 outline-none focus:border-accent";
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-200 px-4 py-2.5 text-sm text-slate-500 sm:px-6">
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
      <button className="rounded-md border border-slate-300 px-2 py-1 text-slate-600 hover:bg-slate-100" onClick={f.reset}>Clear</button>
    </div>
  );
}

function UserMenu() {
  const { user, authRequired, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  if (!user) {
    return authRequired ? null : <span className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-500">Guest mode</span>;
  }
  const initial = (user.name || user.email).slice(0, 1).toUpperCase();
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 rounded-full border border-slate-300 py-1 pl-1 pr-3 hover:bg-slate-100">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-accent to-accent2 text-xs font-bold text-slate-50">{initial}</span>
        <span className="hidden max-w-32 truncate text-sm text-slate-800 sm:inline">{user.name}</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-40 mt-2 w-64 rounded-xl border border-slate-300 bg-white p-2 shadow-2xl shadow-black/60">
            <div className="px-3 py-2">
              <div className="truncate text-sm font-medium text-slate-900">{user.name}</div>
              <div className="truncate text-xs text-slate-500">{user.email}</div>
              <span className="mt-2 inline-block rounded-full bg-indigo-50 px-2 py-0.5 text-xs capitalize text-indigo-700">{user.role}</span>
            </div>
            <div className="my-1 border-t border-slate-200" />
            <Link to="/welcome" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-100">
              <Icon name="home" /> About ReviewIQ
            </Link>
            <button onClick={async () => { await logout(); nav("/welcome"); }}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-700 hover:bg-slate-100">
              <Icon name="logout" /> Log out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function Layout() {
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [loc.pathname]);
  const title = ALL.find((p) => p.to === loc.pathname)?.label ?? "ReviewIQ";

  return (
    <div className="flex min-h-screen">
      {open && <div className="fixed inset-0 z-30 bg-black/70 lg:hidden" onClick={() => setOpen(false)} />}
      <nav className={"fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white p-4 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 " + (open ? "translate-x-0" : "-translate-x-full")}>
        <Link to="/" className="mb-6 px-2"><Wordmark /></Link>
        {GROUPS.map((g) => (
          <div key={g.title} className="mb-5">
            <div className="mb-1 px-3 text-xs font-medium uppercase tracking-wider text-slate-400">{g.title}</div>
            <ul className="space-y-0.5 text-sm">
              {g.pages.map((p) => (
                <li key={p.to}>
                  <NavLink to={p.to} end className={({ isActive }) =>
                    "flex items-center gap-3 rounded-lg px-3 py-2 transition-colors " +
                    (isActive ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900")}>
                    <Icon name={p.icon} /> {p.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="mt-auto rounded-xl border border-slate-200 bg-slate-100 p-3 text-xs text-slate-500">
          Tip: pick a product or a date range above, and every page follows it.
        </div>
      </nav>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-slate-50/80 backdrop-blur">
          <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
            <button className="rounded-md border border-slate-300 p-1.5 text-slate-700 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
              <Icon name="menu" size={18} />
            </button>
            <h1 className="truncate text-base font-semibold text-slate-900">{title}</h1>
            <div className="ml-auto flex items-center gap-3">
              <Link to="/upload" className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent to-accent2 px-3 py-1.5 text-sm font-medium text-slate-50 hover:opacity-90">
                <Icon name="upload" /> <span className="hidden sm:inline">Upload reviews</span>
              </Link>
              <UserMenu />
            </div>
          </div>
          <FilterBar />
        </header>
        <Outlet />
      </div>
    </div>
  );
}
