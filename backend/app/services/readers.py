import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook

from app.services.file_detect import Detected

csv.field_size_limit(10_000_000)


class UnsupportedFormat(Exception):
    pass


@dataclass
class ReadResult:
    rows: list[list[str]]
    issues: list[tuple[int, str, str]] = field(default_factory=list)  # (row_no, problem, original)


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _read_delimited(data: bytes, det: Detected) -> ReadResult:
    text = data.decode(det.encoding or "utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=det.delimiter or ",")
    return ReadResult([row for row in reader])


def _read_xlsx(data: bytes) -> ReadResult:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    best: list[list[str]] = []
    best_filled = -1
    try:
        for ws in wb.worksheets:
            rows = [[_cell(c) for c in r] for r in ws.iter_rows(values_only=True)]
            filled = sum(1 for r in rows if any(r))
            if filled > best_filled:
                best, best_filled = rows, filled
    finally:
        wb.close()
    return ReadResult(best)


def _flatten(value, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.update(_flatten(v, key))
    elif isinstance(value, list):
        if all(not isinstance(i, (dict, list)) for i in value):
            out[prefix or "value"] = "; ".join(_cell(i) for i in value)
        else:
            out[prefix or "value"] = json.dumps(value, ensure_ascii=False)
    else:
        out[prefix or "value"] = _cell(value)
    return out


def _records_to_table(records: list) -> list[list[str]]:
    flat = [_flatten(r) for r in records]
    header: list[str] = []
    seen: set[str] = set()
    for f in flat:
        for k in f:
            if k not in seen:
                seen.add(k)
                header.append(k)
    return [header] + [[f.get(k, "") for k in header] for f in flat]


def _find_records(obj) -> list:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
                return v
    return [obj]


def _read_json(data: bytes, det: Detected) -> ReadResult:
    text = data.decode(det.encoding or "utf-8", errors="replace")
    return ReadResult(_records_to_table(_find_records(json.loads(text))))


def _read_jsonl(data: bytes, det: Detected) -> ReadResult:
    text = data.decode(det.encoding or "utf-8", errors="replace")
    records, issues = [], []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            issues.append((n, "Line is not valid JSON", line[:500]))
    return ReadResult(_records_to_table(records) if records else [], issues)


def _read_txt(data: bytes, det: Detected) -> ReadResult:
    text = data.decode(det.encoding or "utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return ReadResult([["text"]] + [[ln] for ln in lines] if lines else [])


def read_table(data: bytes, det: Detected) -> ReadResult:
    if det.format in ("csv", "tsv"):
        return _read_delimited(data, det)
    if det.format == "xlsx":
        return _read_xlsx(data)
    if det.format == "json":
        return _read_json(data, det)
    if det.format == "jsonl":
        return _read_jsonl(data, det)
    if det.format == "txt":
        return _read_txt(data, det)
    if det.format == "pdf":
        raise UnsupportedFormat("PDF reading (text, tables and OCR) is added in a later step.")
    if det.format == "xml":
        raise UnsupportedFormat("XML reading is added in a later step.")
    raise UnsupportedFormat(f"Unsupported file type: {det.format}")
