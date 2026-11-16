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
