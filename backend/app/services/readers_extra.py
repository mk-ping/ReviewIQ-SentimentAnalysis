import io
import re
from collections import Counter
from pathlib import Path

from app.core.config import settings
from app.services.file_detect import Detected
from app.services.readers import ReadResult, UnsupportedFormat, _cell, _records_to_table

MAX_OCR_PAGES = 50


def _split_text(text: str) -> list[str]:
    blocks = [re.sub(r"\s*\n\s*", " ", b).strip() for b in re.split(r"\n\s*\n", text)]
    blocks = [b for b in blocks if b]
    if len(blocks) >= 3:
        return blocks
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _ocr_text(pdf) -> str:
    try:
        import pytesseract
    except ImportError:
        raise UnsupportedFormat("This PDF has no text layer (it is scanned). Install OCR support with: pip install pytesseract")
    default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    cmd = settings.tesseract_cmd or (default if Path(default).exists() else "")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        raise UnsupportedFormat(
            "This PDF is scanned (no text layer) and Tesseract OCR is not installed. "
            "Install it with: winget install -e --id UB-Mannheim.TesseractOCR, then restart the API."
        )
    pages = []
    for page in pdf.pages[:MAX_OCR_PAGES]:
        img = page.to_image(resolution=200).original
        pages.append(pytesseract.image_to_string(img))
    return "\n\n".join(pages)


def read_pdf(data: bytes) -> ReadResult:
    import pdfplumber

    notes: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) == 0:
            raise UnsupportedFormat("The PDF has no pages.")
        table: list[list[str]] = []
        for page in pdf.pages:
            for tbl in page.extract_tables():
                for r in tbl:
                    cells = [_cell(c).replace("\n", " ").strip() for c in r]
                    if any(cells):
                        table.append(cells)
        if len(table) >= 2 and max(len(r) for r in table) >= 2:
            head = table[0]
            rows = [head] + [r for r in table[1:] if r != head]
            res = ReadResult(rows)
            res.notes = [f"Read a table from the PDF: {len(rows) - 1} data rows. Check the preview before confirming."]
            return res

        text = "\n\n".join((p.extract_text() or "") for p in pdf.pages)
        method = "text"
        if len(text.strip()) < 20:
            text = _ocr_text(pdf)
            method = "ocr"

    parts = _split_text(text)
    if not parts:
        raise UnsupportedFormat("No text could be read from this PDF.")
    if method == "ocr":
        notes.append("Scanned PDF read with OCR. Accuracy depends on scan quality, so check the preview.")
    notes.append(f"Free text PDF split into {len(parts)} reviews (at blank lines, or line by line). Check the preview before confirming.")
    res = ReadResult([["text"]] + [[p] for p in parts])
    res.notes = notes
    return res


def _tag(t: str) -> str:
    return re.sub(r"^\{[^}]*\}", "", t)


def _xml_flat(el, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in el.attrib.items():
        out[f"{prefix}{_tag(k)}"] = v
    kids = list(el)
    if not kids:
        t = (el.text or "").strip()
        if t:
            out[prefix.rstrip(".") or "value"] = t
        return out
    for ch in kids:
        out.update(_xml_flat(ch, f"{prefix}{_tag(ch.tag)}."))
    return out


def read_xml(data: bytes, det: Detected) -> ReadResult:
    from defusedxml import ElementTree as ET

    try:
        root = ET.fromstring(data)
    except Exception as e:
        raise UnsupportedFormat(f"This XML file could not be parsed: {e}")
    best, best_n = None, 1
    for el in root.iter():
        for tag, n in Counter(c.tag for c in el).items():
            if n > best_n:
                best, best_n = (el, tag), n
    records = [c for c in best[0] if c.tag == best[1]] if best else [root]
    flat = [_xml_flat(r) for r in records]
    flat = [f for f in flat if f]
    if not flat:
        raise UnsupportedFormat("No review records were found in this XML file.")
    res = ReadResult(_records_to_table(flat))
    res.notes = [f"Read {len(flat)} XML records ({_tag(records[0].tag)} elements). Check the preview."]
    return res
