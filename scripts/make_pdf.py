"""Render architecture.md to architecture.pdf (max 3 pages) with reportlab."""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer)

SRC = "/home/sandbox/aisignal-pipeline/architecture.md"
DST = "/home/sandbox/aisignal-pipeline/architecture.pdf"

h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, spaceAfter=8, spaceBefore=4)
h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, spaceAfter=5, spaceBefore=10)
body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, leading=12.3, spaceAfter=5)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=3)
code = ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=9.2,
                      backColor="#f2f2f2", leftIndent=8, spaceAfter=6)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(t):
    t = esc(t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8.4">\1</font>', t)
    return t


story, in_code, buf = [], False, []
for line in open(SRC):
    raw = line.rstrip("\n")
    if raw.startswith("```"):
        if in_code:
            story.append(Preformatted("\n".join(buf), code)); buf = []
        in_code = not in_code
        continue
    if in_code:
        buf.append(raw); continue
    if raw.startswith("# "):
        story.append(Paragraph(inline(raw[2:]), h1))
    elif raw.startswith("## "):
        story.append(Paragraph(inline(raw[3:]), h2))
    elif raw.startswith("- "):
        story.append(Paragraph(inline(raw[2:]), bullet, bulletText="\u2022"))
    elif raw.strip():
        story.append(Paragraph(inline(raw), body))

doc = SimpleDocTemplate(DST, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                        title="FrontierAtlas Architecture")
doc.build(story)
print("pdf written")
