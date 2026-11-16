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
