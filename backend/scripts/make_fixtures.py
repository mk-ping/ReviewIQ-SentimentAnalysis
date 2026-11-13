import csv
import io
from pathlib import Path

FIX = Path(__file__).resolve().parents[2] / "data" / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)

ROWS = [
    ("Lip balm", 5, "Smooth and lasting, love it", "14/03/2026"),
    ("Lip balm", 2, "Melts in the heat and the cap is loose", "18/03/2026"),
    ("Face wash", 4, "Gentle on skin but the bottle is small", "21/03/2026"),
    ("Face wash", 1, "Delivery was late and the box was damaged", "25/03/2026"),
    ("Face wash", 5, "Crème texture is lovely, will buy again", "28/03/2026"),
    ("Lip balm", 3, "Okay for the price, nothing special", "30/03/2026"),
]


def make_csv(header, rows, delim=","):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


H = ["Product", "Rating", "Review", "Date"]
out = {}
txt = make_csv(H, ROWS)
(FIX / "enc_utf16.csv").write_text(txt, encoding="utf-16")
(FIX / "enc_cp1252_semicolon.csv").write_bytes(make_csv(H, ROWS, ";").encode("cp1252"))
(FIX / "delim_pipe.csv").write_text(make_csv(H, ROWS, "|"), encoding="utf-8")
(FIX / "delim_tab.tsv").write_text(make_csv(H, ROWS, "\t"), encoding="utf-8")
(FIX / "header_only.csv").write_text("Product,Rating,Review\n", encoding="utf-8")
(FIX / "no_text_column.csv").write_text("id,count\n1,5\n2,7\n3,9\n", encoding="utf-8")
(FIX / "no_rating.csv").write_text(make_csv(["Product", "Review", "Date"], [(p, t, d) for p, _, t, d in ROWS]), encoding="utf-8")
(FIX / "no_date.csv").write_text(make_csv(["Product", "Rating", "Review"], [(p, r, t) for p, r, t, _ in ROWS]), encoding="utf-8")
(FIX / "ambiguous_dates.csv").write_text(
    make_csv(H, [(p, r, t, f"0{i + 1}/0{i + 2}/2026") for i, (p, r, t, _) in enumerate(ROWS[:5])]), encoding="utf-8")

good = ['{"stars": %d, "body": "%s", "product": "%s"}' % (r, t, p) for p, r, t, _ in ROWS]
bad = ["this is not json", "{broken", "{'single': 'quotes'}", "also not json"]
(FIX / "half_bad.jsonl").write_text("\n".join(good[:3] + bad[:2] + good[3:] + bad[2:]) + "\n", encoding="utf-8")

xml = ['<?xml version="1.0" encoding="utf-8"?>', "<reviews>"]
for i, (p, r, t, d) in enumerate(ROWS, 1):
    xml.append(f'  <review id="{i}"><product>{p}</product><rating>{r}</rating><text>{t}</text><date>{d}</date></review>')
xml.append("</reviews>")
(FIX / "reviews.xml").write_text("\n".join(xml), encoding="utf-8")

# PDFs
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

data = [["Product", "Rating", "Review"]] + [[p, str(r), t] for p, r, t, _ in ROWS]
table = Table(data)
table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
SimpleDocTemplate(str(FIX / "reviews_table.pdf"), pagesize=A4).build([table])

c = canvas.Canvas(str(FIX / "reviews_text.pdf"), pagesize=A4)
y = 800
for _, _, t, _ in ROWS:
    c.drawString(50, y, t)
    y -= 40
c.save()

from PIL import Image, ImageDraw, ImageFont

img = Image.new("RGB", (1400, 700), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.load_default(size=36)
except TypeError:
    font = ImageFont.load_default()
y = 40
for _, _, t, _ in ROWS:
    d.text((40, y), t, fill="black", font=font)
    y += 90
img.save(FIX / "reviews_scanned.pdf", "PDF", resolution=150)

print("fixtures written to", FIX)
