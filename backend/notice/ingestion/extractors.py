"""Text extraction for every supported source type.

Each extractor returns the full document text plus a list of atomic items
(messages / entries) with character offsets into that text, so every citation
can point at an exact passage.
"""

from __future__ import annotations

import email
import email.policy
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Dublin")
MESSAGE_KINDS = {"email", "whatsapp", "diary", "letter"}


@dataclass
class ItemSpec:
    text: str
    char_start: int
    char_end: int
    author: str | None = None
    recipients: str | None = None
    subject: str | None = None
    timestamp: datetime | None = None
    kind: str | None = None


@dataclass
class Extracted:
    text: str
    method: str  # text | ocr | none
    kind: str
    mime: str
    items: list[ItemSpec] = field(default_factory=list)
    author: str | None = None
    timestamp: datetime | None = None
    meta: dict = field(default_factory=dict)


class ExtractionError(ValueError):
    pass


# --- helpers -------------------------------------------------------------

def _ocr_image_path(path: Path) -> str:
    if not shutil.which("tesseract"):
        raise ExtractionError("OCR requested but tesseract is not installed")
    out = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng"], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise ExtractionError(f"tesseract failed: {out.stderr[:200]}")
    return out.stdout


def _ocr_pdf(data: bytes) -> tuple[str, list[int]]:
    if not shutil.which("pdftoppm"):
        raise ExtractionError("OCR fallback needs pdftoppm (poppler-utils)")
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "in.pdf"
        pdf.write_bytes(data)
        subprocess.run(["pdftoppm", "-r", "200", "-png", str(pdf), str(Path(td) / "p")], check=True, timeout=600)
        pages = sorted(Path(td).glob("p-*.png"))
        texts, offsets, pos = [], [], 0
        for p in pages:
            t = _ocr_image_path(p).strip() + "\n\n"
            offsets.append(pos)
            texts.append(t)
            pos += len(t)
        return "".join(texts), offsets


def _whole_doc_item(text: str, kind: str, author=None, ts=None, subject=None) -> list[ItemSpec]:
    return [ItemSpec(text=text, char_start=0, char_end=len(text), author=author, timestamp=ts, subject=subject, kind=kind)]


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html))


# --- PDF -----------------------------------------------------------------

def extract_pdf(data: bytes) -> tuple[str, str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    texts, offsets, pos = [], [], 0
    for page in reader.pages:
        t = (page.extract_text() or "").strip() + "\n\n"
        offsets.append(pos)
        texts.append(t)
        pos += len(t)
    text = "".join(texts)
    n = max(len(reader.pages), 1)
    if len(text.strip()) / n < 40:  # scanned / image-only PDF
        text, offsets = _ocr_pdf(data)
        return text, "ocr", {"pages": len(offsets), "page_offsets": offsets}
    return text, "text", {"pages": len(offsets), "page_offsets": offsets}


# --- Office --------------------------------------------------------------

def extract_docx(data: bytes) -> str:
    import docx

    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts).strip() + "\n"


def extract_xlsx(data: bytes) -> tuple[str, dict]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out, sheets = [], []
    for ws in wb.worksheets:
        sheets.append(ws.title)
        out.append(f"## Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            if any(v is not None and str(v).strip() for v in row):
                out.append("\t".join("" if v is None else str(v) for v in row).rstrip())
        out.append("")
    return "\n".join(out) + "\n", {"sheets": sheets}


# --- Email ---------------------------------------------------------------

def _fmt_addrs(v: str | None) -> str | None:
    if not v:
        return None
    return ", ".join(f"{n} <{a}>" if n else a for n, a in getaddresses([v]))


def extract_eml(data: bytes) -> Extracted:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        body = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            body = _strip_html(body)
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    ts = None
    if msg["Date"]:
        try:
            ts = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            ts = None
    sender, to, cc, subject = _fmt_addrs(msg["From"]), _fmt_addrs(msg["To"]), _fmt_addrs(msg["Cc"]), str(msg["Subject"] or "")
    header = f"From: {sender or ''}\nTo: {to or ''}\n" + (f"Cc: {cc}\n" if cc else "") + f"Date: {msg['Date'] or ''}\nSubject: {subject}\n\n"
    body = body.replace("\r\n", "\n").strip() + "\n"
    text = header + body
    item = ItemSpec(
        text=body, char_start=len(header), char_end=len(text), author=sender,
        recipients=", ".join(x for x in (to, cc) if x) or None, subject=subject, timestamp=ts, kind="email",
    )
    return Extracted(text=text, method="text", kind="email", mime="message/rfc822", items=[item], author=sender,
                     timestamp=ts, meta={"attachments": attachments, "message_id": str(msg["Message-ID"] or "")})


def extract_msg(data: bytes) -> Extracted:
    import extract_msg

    with tempfile.NamedTemporaryFile(suffix=".msg") as f:
        f.write(data)
        f.flush()
        m = extract_msg.Message(f.name)
        try:
            sender, to, subject = m.sender, m.to, m.subject or ""
            body = (m.body or "").replace("\r\n", "\n").strip() + "\n"
            ts = m.date if isinstance(m.date, datetime) else None
        finally:
            m.close()
    header = f"From: {sender or ''}\nTo: {to or ''}\nDate: {ts.isoformat() if ts else ''}\nSubject: {subject}\n\n"
    text = header + body
    item = ItemSpec(text=body, char_start=len(header), char_end=len(text), author=sender, recipients=to,
                    subject=subject, timestamp=ts, kind="email")
    return Extracted(text=text, method="text", kind="email", mime="application/vnd.ms-outlook", items=[item],
                     author=sender, timestamp=ts)


# --- WhatsApp ------------------------------------------------------------

# Android: "17/08/2026, 07:42 - Name: text"   iOS: "[17/08/2026, 07:42:10] Name: text"
_WA_LINE = re.compile(
    r"^‎?\[?(?P<d>\d{1,2}/\d{1,2}/\d{2,4}),? (?P<t>\d{1,2}:\d{2}(?::\d{2})?)(?:\s?[AaPp][Mm])?\]?(?: -)? (?P<who>[^:]{1,80}?): (?P<msg>.*)$"
)


def looks_like_whatsapp(text: str) -> bool:
    lines = [ln for ln in text.splitlines()[:30] if ln.strip()]
    return bool(lines) and sum(1 for ln in lines if _WA_LINE.match(ln)) >= max(2, len(lines) // 3)


def _wa_dt(d: str, t: str) -> datetime | None:
    day, month, year = d.split("/")
    year = int(year) + (2000 if len(year) == 2 else 0)
    parts = [int(x) for x in t.split(":")]
    try:
        return datetime(year, int(month), int(day), parts[0], parts[1], parts[2] if len(parts) > 2 else 0, tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def extract_whatsapp(text: str) -> list[ItemSpec]:
    items: list[ItemSpec] = []
    pos = 0
    current: ItemSpec | None = None
    for line in text.splitlines(keepends=True):
        m = _WA_LINE.match(line.rstrip("\n"))
        if m:
            if current:
                items.append(current)
            msg_start = pos + m.start("msg")
            current = ItemSpec(text=m.group("msg"), char_start=msg_start, char_end=pos + len(line.rstrip("\n")),
                               author=m.group("who").strip(), timestamp=_wa_dt(m.group("d"), m.group("t")), kind="whatsapp")
        elif current is not None and line.strip():
            current.char_end = pos + len(line.rstrip("\n"))
            current.text = text[current.char_start:current.char_end]
        pos += len(line)
    if current:
        items.append(current)
    return [i for i in items if "<Media omitted>" not in i.text and i.text.strip()]


# --- Site diary ----------------------------------------------------------

_DIARY_HDR = re.compile(r"^SITE DIARY\s*[—–-]\s*(?P<date>\d{4}-\d{2}-\d{2})(?:\s*[—–-]\s*(?P<who>.+))?$", re.M)


def looks_like_diary(text: str) -> bool:
    return bool(_DIARY_HDR.search(text[:2000]))


def extract_diary(text: str) -> list[ItemSpec]:
    heads = list(_DIARY_HDR.finditer(text))
    items = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body_start = h.end() + 1
        body = text[body_start:end].rstrip()
        y, mo, d = map(int, h.group("date").split("-"))
        items.append(ItemSpec(text=body, char_start=body_start, char_end=body_start + len(body),
                              author=(h.group("who") or "").strip() or None,
                              timestamp=datetime(y, mo, d, 17, 0, tzinfo=LOCAL_TZ), kind="diary",
                              subject=f"Site diary {h.group('date')}"))
    return items


# --- dispatcher ----------------------------------------------------------

EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def guess_kind(filename: str, text: str) -> str:
    name = filename.lower()
    for key, kind in (
        ("contract", "contract"), ("conditions", "contract"), ("register", "drawing_register"),
        ("spec", "spec"), ("quote", "quote"), ("tender", "quote"), ("insurance", "compliance"),
        ("rct", "compliance"), ("safe pass", "compliance"), ("safepass", "compliance"), ("rams", "compliance"),
    ):
        if key in name:
            return kind
    if re.search(r"\b[a-z]{1,4}-[a-z]{1,4}-\d{2,4}\b", name):
        return "drawing"
    if looks_like_whatsapp(text):
        return "whatsapp"
    if looks_like_diary(text):
        return "diary"
    return "other"


def extract(filename: str, data: bytes, kind: str | None = None) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext not in EXT_MIME:
        raise ExtractionError(f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(EXT_MIME))}")
    mime = EXT_MIME[ext]
    if ext == ".eml":
        return extract_eml(data)
    if ext == ".msg":
        return extract_msg(data)

    meta: dict = {}
    method = "text"
    if ext == ".pdf":
        text, method, meta = extract_pdf(data)
    elif ext == ".docx":
        text = extract_docx(data)
    elif ext == ".xlsx":
        text, meta = extract_xlsx(data)
    elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        with tempfile.NamedTemporaryFile(suffix=ext) as f:
            f.write(data)
            f.flush()
            text = _ocr_image_path(Path(f.name))
        method = "ocr"
    else:
        text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")

    kind = kind or guess_kind(filename, text)
    if kind == "whatsapp":
        items = extract_whatsapp(text)
        ts = items[0].timestamp if items else None
        meta["chat"] = Path(filename).stem
        return Extracted(text=text, method=method, kind=kind, mime=mime, items=items, timestamp=ts, meta=meta)
    if kind == "diary":
        items = extract_diary(text)
        return Extracted(text=text, method=method, kind=kind, mime=mime, items=items,
                         timestamp=items[0].timestamp if items else None, meta=meta)
    return Extracted(text=text, method=method if text.strip() else "none", kind=kind, mime=mime,
                     items=_whole_doc_item(text, kind), meta=meta)
