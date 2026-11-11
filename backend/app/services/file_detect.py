import csv
import io
import json
import zipfile
from collections import Counter
from dataclasses import dataclass

import chardet

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass
class Detected:
    format: str = "unknown"
    encoding: str | None = None
    delimiter: str | None = None
    error: str | None = None


def decode_text(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    guess = chardet.detect(data[:200_000]).get("encoding") or "cp1252"
    try:
        return data.decode(guess), guess
    except (UnicodeDecodeError, LookupError):
        return data.decode("cp1252", errors="replace"), "cp1252"


def sniff_delimiter(lines: list[str]) -> str | None:
    best, best_key = None, (0.0, 0)
    for d in (",", "\t", ";", "|"):
        lens = [len(r) for r in csv.reader(lines, delimiter=d) if r]
        if not lens:
            continue
        mode, n_mode = Counter(lens).most_common(1)[0]
        if mode < 2:
            continue
        frac = n_mode / len(lens)
        if frac >= 0.6 and (frac, mode) > best_key:
            best, best_key = d, (frac, mode)
    return best


def detect(data: bytes) -> Detected:
    if not data.strip():
        return Detected("empty", error="The file is empty.")

    if data.startswith(OLE_MAGIC):
        return Detected(
            "ole",
            error="This looks like an encrypted Office file or an old .xls. "
            "Remove the password or save it as .xlsx or .csv, then upload again.",
        )

    if data.startswith(b"%PDF"):
        if b"/Encrypt" in data:
            return Detected("pdf", error="This PDF is encrypted. Remove the password and upload again.")
        return Detected("pdf")

    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return Detected("zip", error="The file is a damaged ZIP archive.")
        if "xl/workbook.xml" in names:
            return Detected("xlsx")
        return Detected("zip", error="This is a ZIP or Office file that is not an Excel workbook.")

    is_utf16 = data.startswith((b"\xff\xfe", b"\xfe\xff"))
    if b"\x00" in data[:4096] and not is_utf16:
        return Detected("binary", error="This looks like a binary file, not a text or Excel file.")

    text, enc = decode_text(data)
    stripped = text.lstrip()

    if stripped.startswith(("{", "[")):
        try:
            json.loads(text)
            return Detected("json", encoding=enc)
        except ValueError:
            pass

    lines = [ln for ln in text.splitlines() if ln.strip()]

    if lines and all(ln.lstrip().startswith("{") for ln in lines[:20]):
        try:
            for ln in lines[:20]:
                json.loads(ln)
            return Detected("jsonl", encoding=enc)
        except ValueError:
            pass

    if stripped.startswith("<"):
        return Detected("xml", encoding=enc)

    if len(lines) >= 2:
        delim = sniff_delimiter(lines[:50])
        if delim:
            return Detected("tsv" if delim == "\t" else "csv", encoding=enc, delimiter=delim)

    return Detected("txt", encoding=enc)
