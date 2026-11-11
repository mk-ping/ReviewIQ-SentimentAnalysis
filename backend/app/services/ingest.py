from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IngestIssue, Product, RawReviewStaging, Review, UploadBatch
from app.services.cleaning import clean_text, content_hash, norm_for_hash, spam_score
from app.services.detection import ROLES
from app.services.language import detect_language
from app.services.parsing import (
    detect_scale, infer_dayfirst, normalize_rating, parse_date_cell, parse_rating_cell,
)
from app.services.structure import repair_rows

JSON_LINE_PROBLEM = "Line is not valid JSON"


class IngestError(Exception):
    pass


def _issue(row_no, field, problem, action, original):
    return {"row_no": row_no, "field": field, "problem": problem, "action": action,
            "original": (str(original)[:500] if original else None)}


async def run_ingest(session: AsyncSession, batch: UploadBatch, mapping: dict[str, str]) -> dict:
    raw = [
        r["cells"]
        for r in (
            await session.execute(
                select(RawReviewStaging.raw)
                .where(RawReviewStaging.batch_id == batch.batch_id)
                .order_by(RawReviewStaging.row_no)
            )
        ).scalars().all()
    ]
    header, data, rownos, issues = repair_rows(raw)
    if not header or not data:
        raise IngestError("The file has a header but no data rows.")

    idx: dict[str, int] = {}
    used: dict[str, str] = {}
    for role, col in mapping.items():
        if role not in ROLES:
            raise IngestError(f"Unknown role: {role}")
        if col not in header:
            raise IngestError(f"Column '{col}' (role {role}) is not in the file. Columns: {header}")
        if col in used:
            raise IngestError(f"Column '{col}' cannot be both {used[col]} and {role}.")
        used[col] = role
        idx[role] = header.index(col)
    if "text" not in idx:
        raise IngestError("A review text column is required.")

    def cell(row: list[str], role: str) -> str:
        return row[idx[role]] if role in idx else ""

    removed_total = sum(1 for i in issues if i["problem"] == "Total or summary row removed")
    json_lines = await session.scalar(
        select(func.count()).select_from(IngestIssue).where(
            IngestIssue.batch_id == batch.batch_id, IngestIssue.problem == JSON_LINE_PROBLEM
        )
    ) or 0

    col_scale = col_lo = None
    if "rating" in idx:
        parsed_all = [parse_rating_cell(cell(r, "rating")) for r in data]
        col_scale, col_lo = detect_scale([p[0] for p in parsed_all if p and p[1] is None])

    dayfirst, ambiguous = True, False
    if "date" in idx:
        dayfirst, ambiguous = infer_dayfirst([cell(r, "date") for r in data])
        if ambiguous:
            issues.append(_issue(None, "date", "Dates are ambiguous (every day and month is 12 or less); assumed DD/MM/YYYY", "repaired", None))

    stem = Path(batch.file_name or "upload").stem
    seen: dict[str, dict] = {}
    kept: list[dict] = []

    for r, rn in zip(data, rownos):
        body = cell(r, "text").strip()
        title = cell(r, "title").strip()
        if title and body and title.lower() not in body.lower():
            joiner = " " if title[-1] in ".!?" else ". "
            text_in = f"{title}{joiner}{body}"
        else:
            text_in = body or title
        text = clean_text(text_in)
        if len(text) < 2:
            issues.append(_issue(rn, "text", "Empty review text", "quarantined", cell(r, "text")))
            continue

        rating_raw = cell(r, "rating").strip()
        rating_norm = None
        if rating_raw:
            parsed = parse_rating_cell(rating_raw)
            rating_norm = normalize_rating(parsed, col_scale, col_lo) if parsed else None
            if rating_norm is None:
                issues.append(_issue(rn, "rating", "Rating could not be read or is out of range; review kept without a rating", "repaired", rating_raw))

        date_raw = cell(r, "date").strip()
        rdate = None
        if date_raw:
            rdate = parse_date_cell(date_raw, dayfirst)
            if rdate is None:
                issues.append(_issue(rn, "date", "Date could not be read or is out of range; review kept without a date", "repaired", date_raw))

        product = (cell(r, "product").strip() or ("Unknown product" if "product" in idx else stem))[:300]

        h = content_hash(product, text, rdate.isoformat() if rdate else "", rating_raw)
        if h in seen:
            seen[h]["dup_count"] += 1
            issues.append(_issue(rn, "text", "Duplicate review in this file (same text, product, date and rating)", "quarantined", text[:300]))
            continue

        extra: dict = {}
        for role in ("author", "id"):
            v = cell(r, role).strip()
            if v:
                extra["external_id" if role == "id" else role] = v
        hv = cell(r, "helpful").strip()
        if hv:
            try:
                extra["helpful"] = int(float(hv.replace(",", "")))
            except ValueError:
                extra["helpful"] = hv
        if title:
            extra["title"] = title
        lang, script = detect_language(text)
        extra["script"] = script
        other = {name: r[i] for i, name in enumerate(header) if name not in used and r[i].strip()}
        if other:
            extra["other"] = other

        entry = {
            "row_no": rn, "product": product, "text_clean": text,
            "rating_raw": rating_raw or None, "rating_norm": rating_norm, "review_date": rdate,
            "source": (batch.file_name or "")[:100], "content_hash": h,
            "spam_score": spam_score(text_in, text), "dup_count": 1, "extra": extra, "language": lang,
        }
        seen[h] = entry
        kept.append(entry)

    freq = Counter(norm_for_hash(e["text_clean"]) for e in kept)
    for e in kept:
        if freq[norm_for_hash(e["text_clean"])] >= 3:
            e["spam_score"] = round(min(1.0, e["spam_score"] + 0.3), 2)

    ws = batch.workspace_id
    hashes = [e["content_hash"] for e in kept]
    existing: set[str] = set()
    for i in range(0, len(hashes), 5000):
        res = await session.execute(
            select(Review.content_hash).where(Review.workspace_id == ws, Review.content_hash.in_(hashes[i : i + 5000]))
        )
        existing.update(res.scalars().all())

    new: list[dict] = []
    for e in kept:
        if e["content_hash"] in existing:
            issues.append(_issue(e["row_no"], "text", "Already in this workspace from an earlier upload", "quarantined", e["text_clean"][:300]))
        else:
            new.append(e)

    if new:
        names = sorted({e["product"] for e in new})
        await session.execute(
            pg_insert(Product)
            .values([{"workspace_id": ws, "name": n} for n in names])
            .on_conflict_do_nothing(index_elements=["workspace_id", "name"])
        )
        pid = {
            n: i
            for n, i in (
                await session.execute(select(Product.name, Product.product_id).where(Product.workspace_id == ws, Product.name.in_(names)))
            ).all()
        }
        payload = [
            {"workspace_id": ws, "product_id": pid[e["product"]], "batch_id": batch.batch_id,
             "text_clean": e["text_clean"], "rating_raw": e["rating_raw"], "rating_norm": e["rating_norm"],
             "review_date": e["review_date"], "source": e["source"], "language": e["language"], "content_hash": e["content_hash"],
             "spam_score": e["spam_score"], "dup_count": e["dup_count"], "extra": e["extra"]}
            for e in new
        ]
        for i in range(0, len(payload), 2000):
            await session.execute(
                pg_insert(Review).on_conflict_do_nothing(index_elements=["workspace_id", "content_hash"]),
                payload[i : i + 2000],
            )

    await session.execute(
        delete(IngestIssue).where(IngestIssue.batch_id == batch.batch_id, IngestIssue.problem != JSON_LINE_PROBLEM)
    )
    if issues:
        rows = [
            {"batch_id": batch.batch_id, "row_no": i["row_no"], "field": i["field"], "problem": i["problem"][:300],
             "action": i["action"], "original_value": i["original"]}
            for i in issues
        ]
        for i in range(0, len(rows), 2000):
            await session.execute(insert(IngestIssue), rows[i : i + 2000])

    rowset = set(rownos)
    quarantined = {i["row_no"] for i in issues if i["action"] == "quarantined" and i["row_no"] in rowset}
    repaired = {i["row_no"] for i in issues if i["action"] == "repaired" and i["row_no"] in rowset} - quarantined
    rows_rejected = len(quarantined) + removed_total + json_lines
    rows_repaired = len(repaired)
    rows_ok = len(data) - len(quarantined) - len(repaired)

    batch.rows_total = len(data) + removed_total + json_lines
    batch.rows_ok = rows_ok
    batch.rows_repaired = rows_repaired
    batch.rows_rejected = rows_rejected
    batch.status = "done"

    return {"header": header, "inserted": len(new)}
