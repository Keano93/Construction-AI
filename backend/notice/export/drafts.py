"""Export approved drafts to DOCX / PDF. Nothing is ever sent from Notice."""

from __future__ import annotations

import io

from ..models import Draft, Project


def to_docx(draft: Draft, project: Project) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    d.add_paragraph(f"To: {draft.recipient or ''}")
    d.add_paragraph(f"Project: {project.name}")
    p = d.add_paragraph()
    p.add_run(f"Subject: {draft.subject}").bold = True
    for para in draft.body.split("\n\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def to_pdf(draft: Draft, project: Project) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=draft.subject)

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    flow = [
        Paragraph(esc(f"To: {draft.recipient or ''}"), styles["Normal"]),
        Paragraph(esc(f"Project: {project.name}"), styles["Normal"]),
        Spacer(1, 8),
        Paragraph(f"<b>{esc(draft.subject)}</b>", styles["Normal"]),
        Spacer(1, 8),
    ]
    for para in draft.body.split("\n\n"):
        flow += [Paragraph(esc(para), styles["Normal"]), Spacer(1, 6)]
    doc.build(flow)
    return buf.getvalue()
