"""How many pages is WRITEUP.md, actually?

Word counts are a proxy and the brief asks for pages, so render the markdown
at ordinary document settings (A4, 11pt, 2cm margins) and count. Not a
publishing pipeline -- just enough markdown to lay the document out honestly.

    python3 dev/page_count.py [WRITEUP.md]
"""
import io
import re
import sys
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, \
    TableStyle
from reportlab.lib import colors

src = io.open(sys.argv[1] if len(sys.argv) > 1 else "WRITEUP.md",
              encoding="utf-8").read()

body = ParagraphStyle("b", fontName="Helvetica", fontSize=11, leading=14.5,
                      spaceAfter=7)
h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=14, leading=18,
                    spaceBefore=12, spaceAfter=6)
h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=16,
                    spaceBefore=10, spaceAfter=5)
cell = ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=12)


def inline(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    t = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", t)
    return t


flow, para, tbl = [], [], []


def flush_para():
    if para:
        flow.append(Paragraph(inline(" ".join(para)), body))
        para.clear()


def flush_tbl():
    if not tbl:
        return
    rows = [[Paragraph(inline(c.strip()), cell) for c in r.strip("|").split("|")]
            for r in tbl if not re.match(r"^\s*\|[\s|:-]+\|\s*$", r)]
    if rows:
        t = Table(rows, hAlign="LEFT")
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        flow.append(t)
        flow.append(Spacer(1, 7))
    tbl.clear()


for line in src.splitlines():
    if line.startswith("|"):
        flush_para()
        tbl.append(line)
        continue
    flush_tbl()
    if not line.strip():
        flush_para()
    elif line.startswith("## "):
        flush_para()
        flow.append(Paragraph(inline(line[3:]), h1))
    elif line.startswith("# "):
        flush_para()
        flow.append(Paragraph(inline(line[2:]), h1))
    elif re.match(r"^\d+\. |^- ", line):
        flush_para()
        flow.append(Paragraph(inline(re.sub(r"^(\d+\.|-)\s*", "", line)),
                              ParagraphStyle("li", parent=body, leftIndent=12),
                              bulletText="•"))
    else:
        para.append(line.strip())
flush_para()
flush_tbl()

out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=20 * mm,
                        rightMargin=20 * mm, topMargin=20 * mm,
                        bottomMargin=20 * mm)
doc.build(flow)

import fitz                                                      # noqa: E402
n = fitz.open(out).page_count
print(f"words: {len(src.split())}")
print(f"rendered pages at A4 / 11pt / 2cm margins: {n}")
print(f"pdf: {out}")
