from ftfy import fix_text

TOTAL_WORDS = {"total", "grand total", "sum", "average", "avg", "count", "subtotal"}


def _filled(row: list[str]) -> int:
    return sum(1 for c in row if c.strip())


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", "").strip())
        return True
    except ValueError:
        return False


def find_header_row(rows: list[list[str]], scan: int = 15) -> int:
    best_i, best_score = 0, -1.0
    width = max((_filled(r) for r in rows[:scan]), default=0)
    for i, row in enumerate(rows[:scan]):
        cells = [c.strip() for c in row if c.strip()]
        if len(cells) < 2 or len(cells) < width * 0.6:
            continue
        text_share = sum(1 for c in cells if not _is_number(c)) / len(cells)
        short_share = sum(1 for c in cells if len(c) <= 40) / len(cells)
        unique_share = len(set(cells)) / len(cells)
        score = text_share + short_share + unique_share + len(cells) / max(width, 1)
        if score > best_score + 0.05:
            best_i, best_score = i, score
    return best_i


def repair_rows(rows: list[list[str]]):
    """Returns (header, data_rows, source_row_numbers, issues)."""
    issues: list[dict] = []
    if not rows:
        return [], [], [], issues

    h = find_header_row(rows)
    if h > 0:
        issues.append({"row_no": h + 1, "field": None, "problem": f"Header found on row {h + 1}; {h} rows above it ignored", "action": "repaired", "original": None})

    width = max(len(r) for r in rows[h:])
    raw_header = [(rows[h][i] if i < len(rows[h]) else "").strip() for i in range(width)]
    header, seen = [], {}
    for i, name in enumerate(raw_header):
        name = fix_text(name) or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        header.append(name)

    data: list[list[str]] = []
    rownos: list[int] = []
    for offset, row in enumerate(rows[h + 1 :], start=h + 2):
        if not _filled(row):
            continue
        first = next((c.strip().lower() for c in row if c.strip()), "")
        if _filled(row) <= 2 and first.rstrip(":") in TOTAL_WORDS:
            issues.append({"row_no": offset, "field": None, "problem": "Total or summary row removed", "action": "quarantined", "original": " | ".join(row)[:500]})
            continue
        cells = [(row[i] if i < len(row) else "") for i in range(width)]
        if len(row) > width and any(c.strip() for c in row[width:]):
            issues.append({"row_no": offset, "field": None, "problem": "Row had more cells than the header; extra cells dropped", "action": "repaired", "original": " | ".join(row[width:])[:500]})
        fixed = []
        for c in cells:
            f = fix_text(c).strip()
            if f != c.strip():
                issues.append({"row_no": offset, "field": None, "problem": "Garbled characters repaired", "action": "repaired", "original": c[:200]})
            fixed.append(f)
        data.append(fixed)
        rownos.append(offset)
    return header, data, rownos, issues


def repair(rows: list[list[str]]):
    header, data, _, issues = repair_rows(rows)
    return header, data, issues
