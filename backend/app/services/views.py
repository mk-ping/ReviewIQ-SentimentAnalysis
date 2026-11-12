from sqlalchemy import text

from app.db.session import engine

VIEWS = ["mv_product_daily"]


async def refresh_views() -> None:
    """CONCURRENTLY keeps the view readable while it refreshes. It cannot run inside a transaction."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for v in VIEWS:
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {v}"))
