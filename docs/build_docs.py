"""Build docs/DOKUMENTACIO.docx and .pdf from docs/DOKUMENTACIO.md.

Small Markdown subset: #/##/### headings, paragraphs, - and 1. lists, tables, images,
fenced code, **bold**, `code`, HTML comments (dropped). PDF export uses Microsoft Word (COM).
Run: backend\\.venv\\Scripts\\python.exe docs\\build_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "DOKUMENTACIO.md"
OUT_DOCX = DOCS / "DOKUMENTACIO.docx"
OUT_PDF = DOCS / "DOKUMENTACIO.pdf"

INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def add_inline(par, text: str) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = par.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        else:
            par.add_run(part)


def shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def add_table(doc, rows: list[list[str]]) -> None:
    header, body = rows[0], rows[1:]
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        add_inline(cell.paragraphs[0], text)
        for run in cell.paragraphs[0].runs:
            run.bold = True
        shade(cell, "D9E7F0")
    for row in body:
        cells = table.add_row().cells
        for i, text in enumerate(row[: len(header)]):
            cells[i].text = ""
            add_inline(cells[i].paragraphs[0], text)
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9.5)
    doc.add_paragraph()


def parse_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def build() -> None:
    text = re.sub(r"<!--.*?-->", "", SRC.read_text(encoding="utf-8"), flags=re.S)
    lines = text.splitlines()
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    i = 0
    first_heading = True
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            p = doc.add_paragraph()
            run = p.add_run("\n".join(code))
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", lines[i].strip()):
                    rows.append(parse_row(lines[i]))
                i += 1
            add_table(doc, rows)
            continue
        m = re.match(r"^!\[(.*?)\]\((.*?)\)", stripped)
        if m:
            img = DOCS / m.group(2)
            if img.exists():
                doc.add_picture(str(img), width=Cm(16.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = cap.add_run(m.group(1))
                r.italic = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            else:
                print(f"warning: missing image {img}", file=sys.stderr)
                doc.add_paragraph(f"[Kép hiányzik: {m.group(2)}]")
            i += 1
            continue
        h = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if h:
            level = len(h.group(1))
            if first_heading and level == 1:
                t = doc.add_heading(h.group(2), level=0)
                first_heading = False
            else:
                t = doc.add_heading(h.group(2), level=level)
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            p = doc.add_paragraph(style="List Bullet")
            add_inline(p, re.sub(r"^[-*]\s+", "", stripped))
            i += 1
            continue
        n = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if n:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            add_inline(p, f"{n.group(1)}. {n.group(2)}")
            i += 1
            continue
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|```|[-*]\s|\d+\.\s)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        add_inline(p, " ".join(para))

    doc.save(OUT_DOCX)
    print(f"wrote {OUT_DOCX}")


def to_pdf() -> None:
    import win32com.client  # pywin32

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    try:
        d = word.Documents.Open(str(OUT_DOCX))
        d.SaveAs(str(OUT_PDF), FileFormat=17)
        d.Close(False)
    finally:
        word.Quit()
    print(f"wrote {OUT_PDF}")


if __name__ == "__main__":
    build()
    if "--no-pdf" not in sys.argv:
        to_pdf()
