"""Export the hand-edited final DOKUMENTACIO.docx to DOKUMENTACIO.pdf and DOKUMENTACIO.md.

The .docx is the source of truth for the final submission (edited by hand in Word).
Do NOT run build_docs.py afterwards: it regenerates the .docx from Markdown and would
overwrite the manual edits.
Run: backend\\.venv\\Scripts\\python.exe docs\\export_from_docx.py
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "DOKUMENTACIO.docx"
OUT_MD = DOCS / "DOKUMENTACIO.md"
OUT_PDF = DOCS / "DOKUMENTACIO.pdf"
IMG_DIR = DOCS / "img"


def is_code(run) -> bool:
    return (run.font.name or "").lower().startswith("consolas")


def inline_md(par: Paragraph) -> str:
    out = []
    for run in par.runs:
        text = run.text
        if not text:
            continue
        if is_code(run):
            out.append(f"`{text}`")
        elif run.bold and text.strip():
            lead = text[: len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            out.append(f"{lead}**{text.strip()}**{trail}")
        else:
            out.append(text)
    return re.sub(r"\*\*\*\*", "", "".join(out)).strip()


def image_ids(par: Paragraph) -> list[str]:
    return [b.get(qn("r:embed")) for b in par._p.iter(qn("a:blip"))]


def main() -> None:
    doc = Document(str(SRC))
    old_imgs = re.findall(r"!\[[^\]]*\]\((img/[^)]+)\)", OUT_MD.read_text(encoding="utf-8")) if OUT_MD.exists() else []
    total_imgs = sum(len(image_ids(p)) for p in doc.paragraphs)
    reuse_names = len(old_imgs) == total_imgs
    lines: list[str] = []
    img_index = 0
    pending_img: str | None = None

    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:tbl"):
            table = Table(child, doc)
            rows = [[" ".join(inline_md(p) for p in c.paragraphs).replace("|", "\\|") for c in r.cells] for r in table.rows]
            if rows:
                lines.append("| " + " | ".join(rows[0]) + " |")
                lines.append("|" + "---|" * len(rows[0]))
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                lines.append("")
            continue
        if child.tag != qn("w:p"):
            continue
        par = Paragraph(child, doc)
        rids = image_ids(par)
        if rids:
            for rid in rids:
                img_index += 1
                if reuse_names:
                    rel = old_imgs[img_index - 1]
                else:
                    part = doc.part.related_parts[rid]
                    ext = Path(part.partname).suffix or ".png"
                    rel = f"img/docx_{img_index:02d}{ext}"
                    (DOCS / rel).write_bytes(part.blob)
                pending_img = rel
            continue
        text = inline_md(par)
        style = par.style.name if par.style is not None else ""
        if pending_img:
            caption = par.text.strip() if par.runs and all(r.italic for r in par.runs if r.text.strip()) else ""
            lines += [f"![{caption}]({pending_img})", ""]
            pending_img = None
            if caption:
                continue
        if not text:
            continue
        if style == "Title":
            lines += [f"# {par.text.strip()}", ""]
        elif style.startswith("Heading"):
            level = int(re.sub(r"\D", "", style) or 1)
            lines += [f"{'#' * min(max(level, 2), 6)} {par.text.strip()}", ""]
        elif "List" in style:
            lines.append(f"- {text}")
        elif par.runs and all(is_code(r) for r in par.runs if r.text):
            lines += ["```", par.text, "```", ""]
        else:
            lines += [text, ""]
    if pending_img:
        lines += [f"![]({pending_img})", ""]

    md = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    md = re.sub(r"(\n- [^\n]*)\n(?=[^\n-])", r"\1\n\n", md)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"wrote {OUT_MD} ({img_index} images, reused names: {reuse_names})")

    import win32com.client

    import shutil
    import tempfile

    # Export from a copy: the original may be open (locked) in the user's Word window.
    tmp = Path(tempfile.mkdtemp()) / "export_copy.docx"
    shutil.copy2(SRC, tmp)
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(tmp), False, True, False)
        d.ExportAsFixedFormat(str(OUT_PDF), 17)
        d.Close(False)
    finally:
        word.Quit()
    print(f"wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
