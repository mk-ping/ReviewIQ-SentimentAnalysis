# Step 25: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Password hashing and signed session tokens. Standard library only."""
import base64
import hashlib
import hmac
import secrets
import time

ITERATIONS = 200_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2$%d$%s$%s" % (iterations, salt.hex(), dk.hex())


def verify_password(password: str, stored: str | None) -> bool:
    try:
        kind, it, salt, want = (stored or "").split("$")
        if kind != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), want)
    except (ValueError, TypeError):
        return False


def _sig(secret: str, body: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def make_token(user_id: int, secret: str, ttl_seconds: int, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + ttl_seconds)
    body = "%d.%d" % (user_id, exp)
    return body + "." + _sig(secret, body)


def read_token(token: str | None, secret: str, now: float | None = None) -> int | None:
    """Returns the user id, or None when the token is missing, altered or expired."""
    try:
        uid, exp, sig = (token or "").split(".")
        if not hmac.compare_digest(sig, _sig(secret, uid + "." + exp)):
            return None
        if int(exp) < (time.time() if now is None else now):
            return None
        return int(uid)
    except (ValueError, TypeError):
        return None
'@ | Set-Content -Encoding ascii backend\app\core\security.py

@'
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, make_token, read_token, verify_password
from app.db.session import get_session
from app.models.tenancy import AppUser, Workspace

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "reviewiq_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_fails: dict[str, list[float]] = {}   # email -> times of recent failed logins (one process only)


class Credentials(BaseModel):
    email: str
    password: str
    name: str | None = None


def _public(u: AppUser) -> dict:
    return {"user_id": u.user_id, "email": u.email, "name": u.full_name or u.email.split("@")[0], "role": u.role}


def _set_cookie(resp: Response, user_id: int) -> None:
    ttl = settings.session_hours * 3600
    resp.set_cookie(COOKIE, make_token(user_id, settings.secret_key, ttl), max_age=ttl, httponly=True,
                    samesite="lax", secure=settings.cookie_secure, path="/")


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> AppUser | None:
    uid = read_token(request.cookies.get(COOKIE), settings.secret_key)
    return await session.get(AppUser, uid) if uid else None


async def require_user(user: AppUser | None = Depends(current_user)) -> AppUser | None:
    if settings.auth_required and user is None:
        raise HTTPException(401, "Please log in.")
    return user


@router.get("/me")
async def me(user: AppUser | None = Depends(current_user)):
    return {"auth_required": settings.auth_required, "user": _public(user) if user else None}


@router.post("/signup")
async def signup(body: Credentials, resp: Response, session: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 320:
        raise HTTPException(422, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(422, "Use a password of at least 8 characters.")
    ws = await session.scalar(select(func.min(Workspace.workspace_id)))
    if ws is None:
        w = Workspace(name=settings.default_workspace_name)
        session.add(w)
        await session.flush()
        ws = w.workspace_id
    if await session.scalar(select(AppUser.user_id).where(AppUser.workspace_id == ws, AppUser.email == email)):
        raise HTTPException(409, "That email already has an account. Log in instead.")
    first = (await session.scalar(select(func.count()).select_from(AppUser).where(AppUser.password_hash.is_not(None)))) == 0
    u = AppUser(workspace_id=ws, email=email, full_name=(body.name or "").strip()[:200] or None,
                password_hash=hash_password(body.password), role="manager" if first else "analyst")
    session.add(u)
    await session.commit()
    _set_cookie(resp, u.user_id)
    return {"user": _public(u)}


@router.post("/login")
async def login(body: Credentials, resp: Response, session: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    now = time.time()
    recent = [t for t in _fails.get(email, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many wrong attempts. Wait a few minutes and try again.")
    u = await session.scalar(select(AppUser).where(AppUser.email == email).order_by(AppUser.user_id).limit(1))
    if u is None or not verify_password(body.password, u.password_hash):
        _fails[email] = recent + [now]
        raise HTTPException(401, "Email or password is not right.")
    _fails.pop(email, None)
    _set_cookie(resp, u.user_id)
    return {"user": _public(u)}


@router.post("/logout")
async def logout(resp: Response):
    resp.delete_cookie(COOKIE, path="/")
    return {"ok": True}
'@ | Set-Content -Encoding ascii backend\app\api\auth.py

@'
"""app_user password and name

Revision ID: d4a96f2b7e31
Revises: 6d01c14bbe0c

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4a96f2b7e31'
down_revision: Union[str, Sequence[str], None] = '6d01c14bbe0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("app_user", sa.Column("full_name", sa.String(200), nullable=True))
    # emails are stored lower-case, so one address cannot sign up twice with different capitals
    op.execute("UPDATE app_user SET email = lower(email)")


def downgrade() -> None:
    op.drop_column("app_user", "full_name")
    op.drop_column("app_user", "password_hash")
'@ | Set-Content -Encoding ascii backend\alembic\versions\d4a96f2b7e31_user_password.py

@'
"""Offline checks for passwords and session tokens. Run: python -m tests.check_auth"""
from app.core.security import hash_password, make_token, read_token, verify_password

h = hash_password("correct horse", iterations=1000)
assert verify_password("correct horse", h)
assert not verify_password("wrong", h)
assert not verify_password("x", None) and not verify_password("x", "garbage")
assert hash_password("same", 1000) != hash_password("same", 1000)      # fresh salt every time

t = make_token(7, "secret-a", 3600, now=1000)
assert read_token(t, "secret-a", now=2000) == 7
assert read_token(t, "secret-b", now=2000) is None                      # wrong key
assert read_token(t, "secret-a", now=1000 + 3601) is None               # expired
uid, exp, sig = t.split(".")
assert read_token("8." + exp + "." + sig, "secret-a", now=2000) is None  # user id swapped
assert read_token(None, "secret-a") is None and read_token("a.b", "secret-a") is None
print("auth checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_auth.py

@'
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { send } from "./api";

export type User = { user_id: number; email: string; name: string; role: string };
type Me = { auth_required: boolean; user: User | null };
type Ctx = {
  loading: boolean; user: User | null; authRequired: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function useAuth(): Ctx {
  const c = useContext(AuthCtx);
  if (!c) throw new Error("useAuth must be used inside AuthProvider");
  return c;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [authRequired, setAuthRequired] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? (r.json() as Promise<Me>) : Promise.reject(new Error(String(r.status)))))
      .then((m) => { setUser(m.user); setAuthRequired(m.auth_required); })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onExpired = () => { setUser(null); qc.clear(); };
    window.addEventListener("reviewiq:401", onExpired);
    return () => window.removeEventListener("reviewiq:401", onExpired);
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await send<{ user: User }>("POST", "/auth/login", { email, password });
    qc.clear(); setUser(r.user);
  }, [qc]);
  const signup = useCallback(async (name: string, email: string, password: string) => {
    const r = await send<{ user: User }>("POST", "/auth/signup", { name, email, password });
    qc.clear(); setUser(r.user);
  }, [qc]);
  const logout = useCallback(async () => {
    try { await send("POST", "/auth/logout"); } finally { setUser(null); qc.clear(); }
  }, [qc]);

  return <AuthCtx.Provider value={{ loading, user, authRequired, login, signup, logout }}>{children}</AuthCtx.Provider>;
}

export function Splash() {
  return (
    <div className="grid min-h-screen place-items-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-accent" />
    </div>
  );
}

/** Wraps every dashboard page. Logged-out visitors are sent to the landing page or the login page. */
export function Protected() {
  const { loading, user, authRequired } = useAuth();
  const loc = useLocation();
  if (loading) return <Splash />;
  if (authRequired && !user) {
    return <Navigate to={loc.pathname === "/" ? "/welcome" : "/login"} replace state={{ from: loc.pathname }} />;
  }
  return <Outlet />;
}
'@ | Set-Content -Encoding ascii frontend\src\auth.tsx

@'
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="grid place-items-center rounded-lg bg-gradient-to-br from-accent to-accent2" style={{ width: size, height: size }}>
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="#07080b" strokeWidth="3" strokeLinecap="round">
        <path d="M5 19V11M12 19V5M19 19v-5" />
      </svg>
    </span>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2 text-base font-semibold tracking-tight text-slate-900">
      <Logo /> ReviewIQ
    </span>
  );
}

const ICONS: Record<string, string> = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  smile: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8 14s1.5 2 4 2 4-2 4-2 M9 9.5h.01 M15 9.5h.01",
  gap: "M7 4v16 M17 4v16 M3 8l4-4 4 4 M13 16l4 4 4-4",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  alert: "M12 3l10 18H2z M12 10v5 M12 18h.01",
  compare: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
  trend: "M3 17l6-6 4 4 8-8 M15 7h6v6",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M21 21l-4.3-4.3",
  upload: "M12 16V4 M7 9l5-5 5 5 M4 20h16",
  tag: "M20 12l-8 8-9-9V3h8z M7.5 7.5h.01",
  file: "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z M14 3v5h5 M9 13h6 M9 17h6",
  logout: "M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4 M16 17l5-5-5-5 M21 12H9",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  check: "M5 12l5 5 9-10",
};

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d={ICONS[name] ?? ICONS.star} />
    </svg>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Brand.tsx

@'
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
    { to: "/rating-vs-text", label: "Rating vs Text", icon: "gap" },
    { to: "/aspects", label: "Aspects", icon: "layers" },
  ] },
  { title: "Insights", pages: [
    { to: "/problems", label: "Problems and Priorities", icon: "alert" },
    { to: "/compare", label: "Products and Competitors", icon: "compare" },
    { to: "/trends", label: "Trends and Alerts", icon: "trend" },
    { to: "/listing", label: "Listing vs Reality", icon: "star" },
  ] },
  { title: "Workspace", pages: [
    { to: "/explorer", label: "Review Explorer", icon: "search" },
    { to: "/upload", label: "Upload and Data", icon: "upload" },
    { to: "/label", label: "Gold Labels and Evaluation", icon: "tag" },
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
'@ | Set-Content -Encoding ascii frontend\src\Layout.tsx

@'
import { Link } from "react-router-dom";
import { useAuth } from "./auth";
import { Icon, Wordmark } from "./Brand";

const FEATURES = [
  { icon: "smile", title: "Three models, one answer", body: "Each review is read by three sentiment models chosen for its language, then combined with weights earned on validation data." },
  { icon: "gap", title: "Stars versus words", body: "Fused stars show where the text disagrees with the rating, and which reviews are under-rated or over-rated." },
  { icon: "layers", title: "Aspect sentiment", body: "Every sentence is tagged with the aspects it talks about, so you see what people love and hate, not only how many." },
  { icon: "alert", title: "Problems, ranked", body: "Complaints are clustered into issues and ranked by how often they appear, how severe they are and whether they are growing." },
  { icon: "star", title: "Listing versus reality", body: "Compare the rating shown on the listing with the rating the text supports, and find unhappy customers hiding in 4 and 5 star reviews." },
  { icon: "globe", title: "Many languages", body: "English, Spanish, French, German, Italian, Dutch, Hindi and Hinglish are routed to models that handle them." },
];
const STEPS = [
  { n: "1", title: "Upload", body: "Drop in a CSV or Excel export of reviews. Columns are mapped for you and bad rows are set aside." },
  { n: "2", title: "Analyse", body: "Sentiment, aspects and issues are computed in the background with live progress." },
  { n: "3", title: "Act", body: "Read the dashboards, assign actions, draft replies and export an Excel or PDF report." },
];

function Preview() {
  const bars = [["Positive", "w-4/5", "bg-emerald-600"], ["Neutral", "w-2/5", "bg-slate-400"], ["Negative", "w-3/5", "bg-red-600"]];
  return (
    <div className="relative mx-auto mt-14 max-w-3xl">
      <div className="absolute -inset-6 rounded-3xl bg-gradient-to-r from-accent/20 to-accent2/20 blur-3xl" />
      <div className="relative rounded-2xl border border-slate-300 bg-white p-5 shadow-2xl shadow-black/60">
        <div className="mb-4 flex items-center justify-between text-xs text-slate-500">
          <span className="flex gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-red-600" /><i className="h-2.5 w-2.5 rounded-full bg-amber-600" /><i className="h-2.5 w-2.5 rounded-full bg-emerald-600" /></span>
          <span>Sample layout, not real data</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4">
            <div className="mb-3 text-sm font-medium text-slate-800">Who feels what</div>
            {bars.map(([label, w, color]) => (
              <div key={label} className="mb-2.5">
                <div className="mb-1 text-xs text-slate-500">{label}</div>
                <div className="h-2 rounded-full bg-slate-200"><div className={`h-2 rounded-full ${w} ${color}`} /></div>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4">
            <div className="mb-3 text-sm font-medium text-slate-800">Rating versus text</div>
            <div className="flex h-24 items-end gap-2">
              {[30, 45, 35, 60, 85].map((h, i) => (
                <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-accent/40 to-accent" style={{ height: h + "%" }} />
              ))}
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-500"><span>1 star</span><span>5 stars</span></div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-100 p-4 sm:col-span-2">
            <div className="mb-3 text-sm font-medium text-slate-800">Aspect heatmap</div>
            <div className="grid grid-cols-7 gap-1.5">
              {Array.from({ length: 14 }).map((_, i) => (
                <div key={i} className="h-6 rounded" style={{ background: ["#34d399", "#22d3ee", "#8b7bff", "#fb7185"][(i * 3 + (i % 4)) % 4], opacity: 0.35 + ((i * 37) % 60) / 100 }} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { user, authRequired } = useAuth();
  const inside = !!user || !authRequired;
  const primary = "rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50 hover:opacity-90";
  const ghost = "rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-100";
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Wordmark />
        <nav className="flex items-center gap-2">
          <a href="#features" className="hidden px-3 py-2 text-sm text-slate-600 hover:text-slate-900 sm:block">Features</a>
          <a href="#how" className="hidden px-3 py-2 text-sm text-slate-600 hover:text-slate-900 sm:block">How it works</a>
          {inside ? (
            <Link to="/" className={primary}>Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="px-3 py-2 text-sm text-slate-800 hover:text-slate-900">Log in</Link>
              <Link to="/signup" className={primary}>Sign up</Link>
            </>
          )}
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-5 pb-10 pt-16 text-center">
        <span className="rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs text-slate-600">Sentiment analysis for customer reviews</span>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-tight tracking-tight text-slate-900 sm:text-6xl">
          Know what your customers <span className="text-gradient">really</span> mean
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-500">
          ReviewIQ reads every review, finds the gap between the stars and the words, and tells you which problems to fix first.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {inside ? <Link to="/" className={primary}>Open dashboard</Link> : <Link to="/signup" className={primary}>Get started free</Link>}
          {!inside && <Link to="/login" className={ghost}>Log in</Link>}
        </div>
        <Preview />
      </section>

      <section id="features" className="mx-auto max-w-6xl px-5 py-20">
        <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">Everything the reviews are trying to tell you</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-slate-200 bg-white p-5 transition-colors hover:border-accent/60">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-50 text-accent"><Icon name={f.icon} size={20} /></span>
              <h3 className="mt-4 font-semibold text-slate-900">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="how" className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="text-center text-3xl font-bold tracking-tight text-slate-900">From file to action in three steps</h2>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-2xl border border-slate-200 bg-white p-6">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-accent to-accent2 font-bold text-slate-50">{s.n}</span>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-5 py-20">
        <div className="rounded-3xl border border-slate-300 bg-gradient-to-br from-indigo-100 to-white p-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">Ready to read between the stars?</h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-500">Create an account, upload a file of reviews and have your first dashboards in minutes.</p>
          <div className="mt-6">
            {inside ? <Link to="/" className={primary}>Open dashboard</Link> : <Link to="/signup" className={primary}>Create your account</Link>}
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-8 text-center text-sm text-slate-400">ReviewIQ &middot; built for an Advanced Database Management Systems project</footer>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Landing.tsx

@'
import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth, Splash } from "./auth";
import { Icon, Wordmark } from "./Brand";

const POINTS = [
  "Fused stars that show under-rated and over-rated reviews",
  "Aspect sentiment for every sentence, in many languages",
  "A ranked list of problems to fix first",
];

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { loading, user, login, signup } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from || "/";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isLogin = mode === "login";

  if (loading) return <Splash />;
  if (user) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!isLogin && password.length < 8) { setError("Use a password of at least 8 characters."); return; }
    setBusy(true);
    try {
      if (isLogin) await login(email, password); else await signup(name, email, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1.5 w-full rounded-lg border border-slate-300 bg-slate-100 px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-accent focus:ring-2 focus:ring-accent/30";
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-slate-200 bg-white p-12 lg:flex">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-accent/20 blur-3xl" />
        <div className="absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-accent2/15 blur-3xl" />
        <Link to="/welcome" className="relative"><Wordmark /></Link>
        <div className="relative">
          <h2 className="max-w-md text-4xl font-bold leading-tight tracking-tight text-slate-900">
            Read between the <span className="text-gradient">stars</span>
          </h2>
          <ul className="mt-8 space-y-4">
            {POINTS.map((p) => (
              <li key={p} className="flex items-start gap-3 text-slate-600">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-indigo-50 text-accent"><Icon name="check" size={14} /></span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative text-sm text-slate-400">ReviewIQ &middot; ADBMS project</div>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <Link to="/welcome" className="mb-8 block lg:hidden"><Wordmark /></Link>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{isLogin ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1.5 text-sm text-slate-500">{isLogin ? "Log in to see your dashboards." : "It takes a few seconds. The first account becomes the manager."}</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {!isLogin && (
              <label className="block text-sm text-slate-600">Name
                <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
              </label>
            )}
            <label className="block text-sm text-slate-600">Email
              <input className={field} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            </label>
            <label className="block text-sm text-slate-600">Password
              <div className="relative">
                <input className={field + " pr-16"} type={show ? "text" : "password"} required value={password}
                       onChange={(e) => setPassword(e.target.value)} placeholder={isLogin ? "Your password" : "At least 8 characters"}
                       autoComplete={isLogin ? "current-password" : "new-password"} />
                <button type="button" onClick={() => setShow(!show)} className="absolute right-3 top-1/2 mt-0.5 -translate-y-1/2 text-xs text-slate-500 hover:text-slate-800">
                  {show ? "Hide" : "Show"}
                </button>
              </div>
            </label>
            {error && <div role="alert" className="rounded-lg border border-red-700/40 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
            <button disabled={busy} className="w-full rounded-lg bg-gradient-to-r from-accent to-accent2 py-2.5 text-sm font-semibold text-slate-50 hover:opacity-90 disabled:opacity-60">
              {busy ? "Please wait..." : isLogin ? "Log in" : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            {isLogin ? "New here? " : "Already have an account? "}
            <Link to={isLogin ? "/signup" : "/login"} state={loc.state} className="font-medium text-accent hover:underline">{isLogin ? "Create an account" : "Log in"}</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\AuthPage.tsx

@'
@import "tailwindcss";

/* Dark theme: the slate scale is inverted so every existing page re-skins without edits.
   Two accents: violet and cyan. Green and red stay only for good and bad sentiment. */
@theme {
  --color-accent: #8b7bff;
  --color-accent2: #22d3ee;

  --color-slate-50: #07080b;
  --color-slate-100: #171a22;
  --color-slate-200: #232733;
  --color-slate-300: #303545;
  --color-slate-400: #6b7389;
  --color-slate-500: #8a92a6;
  --color-slate-600: #a7aebf;
  --color-slate-700: #c3c9d6;
  --color-slate-800: #dde1ea;
  --color-slate-900: #f2f4f8;

  --color-indigo-50: #1b1640;
  --color-indigo-100: #261f58;
  --color-indigo-500: #8b7bff;
  --color-indigo-600: #7566fa;
  --color-indigo-700: #b3a8ff;

  --color-red-50: #2a1118;
  --color-red-100: #3a1620;
  --color-red-600: #fb7185;
  --color-red-700: #fb8a9a;
  --color-red-800: #fda4af;
  --color-amber-50: #2a2010;
  --color-amber-100: #3a2c12;
  --color-amber-600: #f5b83d;
  --color-amber-700: #f8c860;
  --color-amber-800: #fbd988;
  --color-emerald-100: #0e2b22;
  --color-emerald-600: #0f9f6e;
  --color-emerald-700: #4ade9d;
  --color-emerald-800: #86efc0;
  --color-green-100: #0e2b22;
  --color-green-800: #86efc0;
  --color-purple-100: #261b46;
  --color-purple-800: #d2c2ff;
  --color-orange-100: #33200f;
  --color-orange-800: #fdba74;
}

:root { color-scheme: dark; }

/* Tailwind v4 draws borders in currentColor unless told otherwise */
@layer base {
  *, ::after, ::before { border-color: var(--color-slate-200); }
}

/* white cannot be remapped in the theme (text-white needs it), so cards get the surface colour here */
.bg-white { background-color: #0f1117; }

body {
  @apply text-slate-900;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  background:
    radial-gradient(900px 500px at 85% -10%, rgba(139, 123, 255, 0.10), transparent 60%),
    radial-gradient(700px 400px at -5% 0%, rgba(34, 211, 238, 0.06), transparent 60%),
    var(--color-slate-50);
  background-attachment: fixed;
  -webkit-font-smoothing: antialiased;
}

.text-gradient {
  background: linear-gradient(90deg, var(--color-accent), var(--color-accent2));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

html { scroll-behavior: smooth; }
option { background: #0f1117; color: #f2f4f8; }
::selection { background: rgba(139, 123, 255, 0.4); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--color-slate-300); border-radius: 8px; }
::-webkit-scrollbar-track { background: transparent; }
'@ | Set-Content -Encoding ascii frontend\src\index.css

@'
import { useEffect, useRef } from "react";
import * as echarts from "echarts";

const axis = {
  axisLine: { lineStyle: { color: "#303545" } },
  axisTick: { lineStyle: { color: "#303545" } },
  axisLabel: { color: "#8a92a6" },
  splitLine: { lineStyle: { color: "#232733" } },
  nameTextStyle: { color: "#8a92a6" },
};
echarts.registerTheme("reviewiq", {
  color: ["#8b7bff", "#22d3ee", "#34d399", "#f5b83d", "#fb7185", "#60a5fa"],
  backgroundColor: "transparent",
  textStyle: { color: "#a7aebf" },
  title: { textStyle: { color: "#f2f4f8" } },
  legend: { textStyle: { color: "#a7aebf" } },
  tooltip: { backgroundColor: "#171a22", borderColor: "#303545", textStyle: { color: "#f2f4f8" } },
  categoryAxis: axis,
  valueAxis: axis,
  timeAxis: axis,
});

export default function Chart({ option, height = 260 }: { option: echarts.EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, "reviewiq");
    c.setOption(option);
    const onResize = () => c.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); c.dispose(); };
  }, [option]);
  return <div ref={ref} style={{ height, width: "100%" }} />;
}
'@ | Set-Content -Encoding ascii frontend\src\Chart.tsx

@'
"""Step 25 patcher. Safe to run twice."""
import glob
import io
import re

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s)
    assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2)
    print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

def config_py(s):
    return once(s, '    tesseract_cmd: str = ""\n',
        '    tesseract_cmd: str = ""\n'
        '    # login: set SECRET_KEY in .env to a long random string; AUTH_REQUIRED=false turns the login wall off\n'
        '    secret_key: str = "dev-only-change-me"\n'
        '    auth_required: bool = True\n'
        '    session_hours: int = 168\n'
        '    cookie_secure: bool = False\n')
edit("backend/app/core/config.py", "secret_key", config_py)

def model_py(s):
    s = once(s, "from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func",
                "from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func")
    return once(s, '    email: Mapped[str] = mapped_column(String(320))\n',
        '    email: Mapped[str] = mapped_column(String(320))\n'
        '    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)\n'
        '    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)\n')
edit("backend/app/models/tenancy.py", "password_hash", model_py)

def main_py(s):
    s = once(s, "from app.api.actions import router as actions_router\n",
        "from app.api.actions import router as actions_router\nfrom app.api.auth import require_user, router as auth_router\n")
    s = once(s, '    allow_origins=["http://localhost:5173"],\n',
        '    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],\n    allow_credentials=True,\n')
    s = once(s, "app.include_router(uploads_router)\n",
        "protected = [Depends(require_user)]   # every data route needs a logged-in user (settings.auth_required)\n"
        "app.include_router(auth_router)\napp.include_router(uploads_router)\n")
    s, n = re.subn(r"app\.include_router\((?!auth_router)(\w+_router)\)", r"app.include_router(\1, dependencies=protected)", s)
    assert n >= 15, n
    return s
edit("backend/app/main.py", "protected = ", main_py)

def api_ts(s):
    s = once(s, "  if (!r.ok) throw new Error(`${r.status} ${path}`);\n",
        "  if (r.status === 401) window.dispatchEvent(new Event(\"reviewiq:401\"));\n  if (!r.ok) throw new Error(`${r.status} ${path}`);\n")
    return once(s, "  if (!r.ok) {\n    let msg = `${r.status} ${path}`;\n",
        "  if (r.status === 401 && !path.startsWith(\"/auth/\")) window.dispatchEvent(new Event(\"reviewiq:401\"));\n  if (!r.ok) {\n    let msg = `${r.status} ${path}`;\n")
edit("frontend/src/api.ts", "reviewiq:401", api_ts)

def main_tsx(s):
    s = once(s, 'import Layout from "./Layout";\n',
        'import Layout from "./Layout";\nimport Landing from "./Landing";\nimport AuthPage from "./AuthPage";\nimport { AuthProvider, Protected } from "./auth";\n')
    s = once(s, "      <BrowserRouter>\n        <Routes>\n          <Route element={<Layout />}>\n",
        '      <BrowserRouter>\n        <AuthProvider>\n        <Routes>\n'
        '          <Route path="welcome" element={<Landing />} />\n'
        '          <Route path="login" element={<AuthPage mode="login" />} />\n'
        '          <Route path="signup" element={<AuthPage mode="signup" />} />\n'
        '          <Route element={<Protected />}>\n          <Route element={<Layout />}>\n')
    return once(s, "          </Route>\n        </Routes>\n      </BrowserRouter>\n",
        "          </Route>\n          </Route>\n        </Routes>\n        </AuthProvider>\n      </BrowserRouter>\n")
edit("frontend/src/main.tsx", "<Protected", main_tsx)

# chart colours that were picked for a white page
SWAP = {"#4f46e5": "#8b7bff", "#0f766e": "#22d3ee", "#16a34a": "#34d399", "#dc2626": "#fb7185"}
for f in glob.glob("frontend/src/*.tsx"):
    s = io.open(f, encoding="utf-8").read(); s2 = s
    for a, b in SWAP.items():
        s2 = s2.replace(a, b)
    if s2 != s:
        io.open(f, "w", encoding="utf-8", newline="\n").write(s2); print("recoloured:", f)

def fuzz(s):
    return once(s, "    with httpx.Client(base_url=BASE, timeout=300) as c:\n",
        "    with httpx.Client(base_url=BASE, timeout=300) as c:\n"
        "        cred = {\"email\": \"fuzz@reviewiq.local\", \"password\": \"fuzz-password-1\", \"name\": \"Fuzz\"}\n"
        "        if c.post(\"/auth/signup\", json=cred).status_code == 409:\n"
        "            c.post(\"/auth/login\", json=cred)\n")
edit("backend/scripts/fuzz_ingest.py", "fuzz@reviewiq.local", fuzz)

def envex(s):
    return s.rstrip("\n") + "\n# login: use a long random string in real use; AUTH_REQUIRED=false turns the login wall off\nSECRET_KEY=change-me-to-a-long-random-string\nAUTH_REQUIRED=true\n"
edit("backend/.env.example", "SECRET_KEY", envex)

def compose(s):
    return once(s, "    TFIDF_PATH: /ml/out/tfidf_lr.joblib\n",
        "    TFIDF_PATH: /ml/out/tfidf_lr.joblib\n    SECRET_KEY: ${SECRET_KEY:-change-me-in-a-real-deployment}\n")
edit("docker-compose.full.yml", "SECRET_KEY", compose)
'@ | Set-Content -Encoding ascii patch_step25.py
python patch_step25.py
Remove-Item patch_step25.py

Write-Host 'Step 25 files written.'
