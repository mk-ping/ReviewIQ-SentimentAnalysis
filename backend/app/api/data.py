from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import workspace_id
from app.db.session import get_session

router = APIRouter(prefix="/data", tags=["data"])


async def _cleanup(session: AsyncSession, ws: int) -> None:
    """After deleting reviews: drop issues and products that no longer have any, then refresh the summary views."""
    await session.execute(text("""
        DELETE FROM issue WHERE workspace_id = :ws
          AND NOT EXISTS (SELECT 1 FROM issue_review ir WHERE ir.issue_id = issue.issue_id)"""), {"ws": ws})
    await session.execute(text("""
        DELETE FROM product p WHERE p.workspace_id = :ws
          AND NOT EXISTS (SELECT 1 FROM review r WHERE r.product_id = p.product_id)"""), {"ws": ws})
    await session.commit()
    try:
        from app.services.views import refresh_views
        await refresh_views()
    except Exception as e:   # the views refresh again on the next analysis, so this is not fatal
        print(f"[data] view refresh skipped: {type(e).__name__}: {str(e)[:100]}")


@router.get("/sources")
async def sources(session: AsyncSession = Depends(get_session)):
    """What this account has loaded: every upload and every product with its review count."""
    ws = await workspace_id(session)
    ups = (await session.execute(text("""
        SELECT b.batch_id, b.file_name, b.status, b.rows_total, b.created_at, count(r.review_id)
        FROM upload_batch b LEFT JOIN review r ON r.batch_id = b.batch_id
        WHERE b.workspace_id = :ws GROUP BY b.batch_id ORDER BY b.batch_id DESC"""), {"ws": ws})).all()
    prods = (await session.execute(text("""
        SELECT p.product_id, p.name, count(r.review_id) FROM product p LEFT JOIN review r ON r.product_id = p.product_id
        WHERE p.workspace_id = :ws GROUP BY p.product_id ORDER BY p.name"""), {"ws": ws})).all()
    return {"uploads": [{"batch_id": i, "file_name": n, "status": s, "rows": t, "uploaded_at": str(c)[:16], "reviews": k} for i, n, s, t, c, k in ups],
            "products": [{"product_id": i, "name": n, "reviews": k} for i, n, k in prods]}


@router.delete("/uploads/{batch_id}")
async def delete_upload(batch_id: int, session: AsyncSession = Depends(get_session)):
    ws = await workspace_id(session)
    row = (await session.execute(text("SELECT status FROM upload_batch WHERE batch_id = :b AND workspace_id = :ws"), {"b": batch_id, "ws": ws})).first()
    if row is None:
        raise HTTPException(404, "Upload not found.")
    if row[0] in ("ingesting", "scoring"):
        raise HTTPException(409, "This upload is still being analysed. Wait for it to finish, then delete it.")
    n = await session.scalar(text("SELECT count(*) FROM review WHERE batch_id = :b"), {"b": batch_id}) or 0
    await session.execute(text("DELETE FROM upload_batch WHERE batch_id = :b AND workspace_id = :ws"), {"b": batch_id, "ws": ws})
    await _cleanup(session, ws)
    return {"deleted_upload": batch_id, "reviews_removed": n}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, session: AsyncSession = Depends(get_session)):
    ws = await workspace_id(session)
    row = (await session.execute(text("SELECT name FROM product WHERE product_id = :p AND workspace_id = :ws"), {"p": product_id, "ws": ws})).first()
    if row is None:
        raise HTTPException(404, "Product not found.")
    busy = await session.scalar(text("""SELECT count(*) FROM review r JOIN upload_batch b ON b.batch_id = r.batch_id
                                        WHERE r.product_id = :p AND b.status IN ('ingesting', 'scoring')"""), {"p": product_id})
    if busy:
        raise HTTPException(409, "This product has reviews that are still being analysed. Try again in a moment.")
    n = await session.scalar(text("SELECT count(*) FROM review WHERE product_id = :p"), {"p": product_id}) or 0
    await session.execute(text("DELETE FROM product WHERE product_id = :p AND workspace_id = :ws"), {"p": product_id, "ws": ws})
    await _cleanup(session, ws)
    return {"deleted_product": row[0], "reviews_removed": n}


@router.delete("/all")
async def delete_all(session: AsyncSession = Depends(get_session)):
    """Starts the account again from empty: every upload, review, issue and tracked action."""
    ws = await workspace_id(session)
    busy = await session.scalar(text("SELECT count(*) FROM upload_batch WHERE workspace_id = :ws AND status IN ('ingesting', 'scoring')"), {"ws": ws})
    if busy:
        raise HTTPException(409, "An upload is still being analysed. Wait for it to finish first.")
    n = await session.scalar(text("SELECT count(*) FROM review WHERE workspace_id = :ws"), {"ws": ws}) or 0
    await session.execute(text("DELETE FROM upload_batch WHERE workspace_id = :ws"), {"ws": ws})
    await session.execute(text("DELETE FROM action WHERE workspace_id = :ws"), {"ws": ws})
    await _cleanup(session, ws)
    return {"deleted_all": True, "reviews_removed": n}
