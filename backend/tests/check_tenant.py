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
