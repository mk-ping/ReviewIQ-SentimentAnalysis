"""Stops one account from opening another account's records by changing the id in the address."""

OWNER_SQL = {
    "batch_id": "SELECT workspace_id FROM upload_batch WHERE batch_id = :i",
    "product_id": "SELECT workspace_id FROM product WHERE product_id = :i",
    "review_id": "SELECT workspace_id FROM review WHERE review_id = :i",
    "action_id": "SELECT workspace_id FROM action WHERE action_id = :i",
    "job_id": "SELECT b.workspace_id FROM scoring_job j JOIN upload_batch b ON b.batch_id = j.batch_id WHERE j.job_id = :i",
}


async def belongs_elsewhere(session, path_params: dict, workspace_id: int) -> bool:
    """True when an id in the path names a record that exists but belongs to a different workspace.
    A record that does not exist is left to the endpoint, which answers 404 itself."""
    from sqlalchemy import text
    for key, sql in OWNER_SQL.items():
        raw = path_params.get(key)
        if raw is None:
            continue
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        owner = await session.scalar(text(sql), {"i": i})
        if owner is not None and owner != workspace_id:
            return True
    return False
