"""Build the command reference PDF from captured real output.

Reads runs/command_outputs.json (written by dev/capture_commands.py) and
renders each command with exactly what it printed. Nothing here invents or
edits output; the only transformation is truncating a very long listing, which
is marked where it happens.

    python3 dev/build_commands_pdf.py
"""
import io
import json
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "runs/command_outputs.json")
OUT = os.path.join(ROOT, "interview/Auric_Rota_Commands_and_Output.pdf")

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5b6472")
ACCENT = colors.HexColor("#1f5f8b")
CMD_BG = colors.HexColor("#1e2a36")
OUT_BG = colors.HexColor("#f4f6f8")
RULE = colors.HexColor("#c9d2dc")
OK = colors.HexColor("#1b7f4b")
BAD = colors.HexColor("#b3261e")

MAX_LINES = 44          # beyond this an output is middle-truncated
WRAP = 104              # characters per line before the font would overflow


def st(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.6, leading=13.6,
                textColor=INK, alignment=TA_LEFT, spaceAfter=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "title": st("title", fontName="Helvetica-Bold", fontSize=21, leading=25,
                textColor=ACCENT, spaceAfter=4),
    "sub": st("sub", fontSize=11, leading=15, textColor=MUTED, spaceAfter=10),
    "h1": st("h1", fontName="Helvetica-Bold", fontSize=13.5, leading=18,
             textColor=ACCENT, spaceBefore=15, spaceAfter=7, keepWithNext=1),
    "body": st("body", spaceAfter=7),
    "note": st("note", fontSize=8.8, leading=12.4, textColor=MUTED,
               spaceAfter=4),
    "cmd": st("cmd", fontName="Courier-Bold", fontSize=8.5, leading=11.4,
              textColor=colors.white),
    "out": st("out", fontName="Courier", fontSize=7.9, leading=10.4),
    "meta": st("meta", fontName="Helvetica", fontSize=7.8, leading=10.6,
               textColor=MUTED),
}

FLOW = []


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap(line, n=WRAP):
    if len(line) <= n:
        return [line]
    out, cur = [], line
    while len(cur) > n:
        out.append(cur[:n])
        cur = cur[n:]
    out.append(cur)
    return out


def box(text, style, bg, pad=6):
    t = Table([[Paragraph(text, S[style])]], colWidths=[172 * mm],
              hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad - 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 1),
    ]))
    return t


def render(rec):
    blk = []
    cmd = "<br/>".join(esc(l) for l in rec["command"].split("\n"))
    blk.append(box("$ " + cmd, "cmd", CMD_BG))

    status = ("exit 0" if rec["exit"] == 0 else f"exit {rec['exit']}")
    colour = OK if rec["exit"] == 0 else BAD
    meta = (f'<font color="{colour.hexval()}">{status}</font> &nbsp;·&nbsp; '
            f'{rec["seconds"]}s')
    if rec.get("note"):
        meta += " &nbsp;·&nbsp; <b>reduced run</b>"
    blk.append(Spacer(1, 2))
    blk.append(Paragraph(meta, S["meta"]))

    if rec.get("note"):
        blk.append(Spacer(1, 2))
        blk.append(Paragraph(esc(rec["note"]), S["note"]))

    lines = rec["output"].split("\n") if rec["output"].strip() else ["(no output)"]
    if len(lines) > MAX_LINES:
        head, tail = lines[:MAX_LINES - 12], lines[-10:]
        lines = head + ["", f"... {len(lines) - len(head) - len(tail)} lines "
                            f"omitted ...", ""] + tail
    flat = []
    for l in lines:
        flat.extend(wrap(l))
    body = "<br/>".join(esc(l) if l else "&nbsp;" for l in flat)
    blk.append(Spacer(1, 3))
    blk.append(box(body, "out", OUT_BG))
    blk.append(Spacer(1, 11))
    return blk


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(19 * mm, 12 * mm,
                      "Commands and their actual output "
                      "— auric-shift-rota-solver")
    canvas.drawRightString(191 * mm, 12 * mm, str(doc.page))
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(19 * mm, 16 * mm, 191 * mm, 16 * mm)
    canvas.restoreState()


def main():
    recs = json.load(io.open(SRC, encoding="utf-8"))

    FLOW.append(Paragraph("Commands and their output", S["title"]))
    FLOW.append(Paragraph(
        "Every documented command for <font face='Courier'>"
        "auric-shift-rota-solver</font>, run end to end, with exactly what it "
        "printed.", S["sub"]))

    total = round(sum(r["seconds"] for r in recs) / 60, 1)
    FLOW.append(box(
        "<b>How to read this.</b> Output is captured verbatim from a real run "
        "on Windows (Git Bash, Python 3.13.7) against the provided endpoint — "
        "nothing is transcribed or tidied. A green <b>exit 0</b> is the "
        "command's real exit status. Where a listing was too long for the "
        "page it is middle-truncated and says so at the cut. One command is "
        "marked <b>reduced run</b>: the full ablation grid takes about two "
        "hours, so a smaller but genuine invocation is shown and the note "
        "says what was changed. "
        f"<br/><br/>{len(recs)} commands, {total} minutes of wall time.",
        "out", colors.HexColor("#eef4f9"), pad=8))
    FLOW.append(Spacer(1, 8))

    FLOW.append(Paragraph(
        "<b>One trap worth knowing.</b> On Windows <font face='Courier'>"
        "python3</font> and <font face='Courier'>python</font> are often "
        "different interpreters — <font face='Courier'>python3</font> can be "
        "the Microsoft Store stub — so a dependency installed for one is "
        "missing for the other. The commands below are written as "
        "<font face='Courier'>python3</font> (correct on the graders' Linux "
        "box) but were executed with the interpreter that has the "
        "dependencies. If you see <font face='Courier'>ModuleNotFoundError: "
        "No module named 'openai'</font>, that is this, and the error message "
        "now names the interpreter and the exact pip command to fix it.",
        S["body"]))

    # A section heading must never be left stranded at the foot of a page, so
    # it travels with its first command rather than relying on keepWithNext,
    # which does not survive the KeepTogether around each command block.
    seen = set()
    for r in recs:
        blk = render(r)
        if r["section"] not in seen:
            seen.add(r["section"])
            blk = [Paragraph(r["section"], S["h1"])] + blk
        FLOW.append(KeepTogether(blk))

    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=19 * mm,
                          rightMargin=19 * mm, topMargin=15 * mm,
                          bottomMargin=20 * mm,
                          title="Commands and their output",
                          author="shoibahmad")
    doc.addPageTemplates([PageTemplate(
        id="all",
        frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)],
        onPage=footer)])
    doc.build(FLOW)
    print(f"wrote {OUT}")
    print(f"{os.path.getsize(OUT) / 1024:.0f} KB, {len(recs)} commands")


if __name__ == "__main__":
    main()
