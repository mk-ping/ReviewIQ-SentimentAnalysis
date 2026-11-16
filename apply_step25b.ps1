# Step 25b: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""The workspace of the logged-in user for the request being served.
require_user sets it; every query that used to pick the first workspace reads it instead."""
from contextvars import ContextVar

_current: ContextVar[int | None] = ContextVar("reviewiq_workspace", default=None)


def set_workspace(ws: int | None) -> None:
    _current.set(ws)


def current_workspace() -> int | None:
    return _current.get()


async def workspace_id(session) -> int:
    """The logged-in user's workspace. With the login wall off there is no user, so the first workspace is used."""
    ws = _current.get()
    if ws:
        return ws
    from sqlalchemy import func, select

    from app.models import Workspace
    return await session.scalar(select(func.min(Workspace.workspace_id))) or 1
'@ | Set-Content -Encoding ascii backend\app\core\tenant.py

@'
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import set_workspace
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
    set_workspace(user.workspace_id if user else None)   # every query below sees only this user's reviews
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
    if await session.scalar(select(AppUser.user_id).where(AppUser.email == email)):
        raise HTTPException(409, "That email already has an account. Log in instead.")
    # every account gets its own workspace, so a new account starts with an empty dashboard
    w = Workspace(name=((body.name or "").strip() or email.split("@")[0])[:150] + "'s workspace")
    session.add(w)
    await session.flush()
    u = AppUser(workspace_id=w.workspace_id, email=email, full_name=(body.name or "").strip()[:200] or None,
                password_hash=hash_password(body.password), role="manager")
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
"""Offline check for the per-request workspace holder. Run: python -m tests.check_tenant"""
import asyncio

from app.core.tenant import current_workspace, set_workspace


async def request(ws):
    set_workspace(ws)
    await asyncio.sleep(0)
    return current_workspace()


async def main():
    a, b = await asyncio.gather(asyncio.create_task(request(5)), asyncio.create_task(request(9)))
    assert (a, b) == (5, 9)                 # two requests at once never see each other's workspace
    assert current_workspace() is None      # and the caller's own context is untouched

asyncio.run(main())
print("tenant checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_tenant.py

@'
"""Step 25b patcher. Safe to run twice."""
import io

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

OLD = "    return await session.scalar(select(func.min(Workspace.workspace_id))) or 1\n"
for f in ("actions", "dashboard", "issues"):
    def fn(s, f=f):
        s = once(s, OLD, "    return await workspace_id(session)\n")
        return once(s, "from app.db.session import get_session\n", "from app.core.tenant import workspace_id\nfrom app.db.session import get_session\n") if "from app.db.session import get_session\n" in s else s
    edit(f"backend/app/api/{f}.py", "app.core.tenant", fn)

def insights(s):
    s = once(s, "    ws = await session.scalar(select(func.min(Workspace.workspace_id)))\n    return ws or 1\n", "    return await workspace_id(session)\n")
    return once(s, "from app.db.session import get_session\n", "from app.core.tenant import workspace_id\nfrom app.db.session import get_session\n")
edit("backend/app/api/insights.py", "app.core.tenant", insights)

def uploads(s):
    s = once(s, "async def default_workspace_id(session: AsyncSession) -> int:\n",
             "async def default_workspace_id(session: AsyncSession) -> int:\n    mine = current_workspace()\n    if mine:\n        return mine\n")
    return once(s, "from app.db.session import get_session\n", "from app.core.tenant import current_workspace\nfrom app.db.session import get_session\n")
edit("backend/app/api/uploads.py", "current_workspace", uploads)

def home(s):
    return once(s, "  const sum = s.data, dist = d.data;\n",
'''  const sum = s.data, dist = d.data;
  if (sum.reviews === 0) {
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <h1 className="text-2xl font-bold">Nothing here yet</h1>
        <p className="mt-2 text-slate-500">Upload a file of reviews and run the analysis. Your dashboards fill up as soon as it finishes.</p>
        <Link to="/upload" className="mt-6 inline-block rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50 hover:opacity-90">Upload reviews</Link>
      </div>
    );
  }
''')
edit("frontend/src/Home.tsx", "Nothing here yet", home)
'@ | Set-Content -Encoding ascii patch_step25b.py
python patch_step25b.py
Remove-Item patch_step25b.py

Write-Host 'Step 25b files written.'
