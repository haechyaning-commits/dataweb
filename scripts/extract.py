# -*- coding: utf-8 -*-
"""
Document text extraction for the audit-document corpus.

Supported formats:
  .pdf   - digital PDFs (PyMuPDF). Scanned/image-only PDFs yield no text
           unless OCR is enabled (ENABLE_OCR=1 + pytesseract + Korean traineddata).
  .hwpx  - Hancom Office HWPX (a zip of XML); text lives in Contents/section*.xml.
  .hwp   - Hancom Office HWP 5.x (an OLE compound file); BodyText/Section*
           streams hold zlib-compressed records; PARA_TEXT records carry the text.
  .txt / .md - read as UTF-8 (cp949 fallback).

Every extractor returns a plain unicode string. Callers do the chunking.
"""

from __future__ import annotations

import os
import re
import zlib
import struct
import zipfile
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def extract_pdf(path: str) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PyMuPDF is required for PDF extraction. Install with: pip install pymupdf"
        ) from e

    enable_ocr = os.getenv("ENABLE_OCR", "0").strip().lower() in ("1", "true", "yes")
    pages: list[str] = []
    doc = fitz.open(path)
    try:
        for page in doc:
            text = page.get_text().strip()
            if not text and enable_ocr:
                text = _ocr_page(page)
            if text:
                pages.append(text)
    finally:
        doc.close()
    # Running headers/footers repeat on most pages and pollute every chunk they
    # land in; drop lines that recur across many pages before joining. (DIAGNOSIS E)
    return "\n".join(_strip_repeated_lines(pages))


def _ocr_page(page) -> str:
    """Best-effort OCR of a single PDF page. Requires pytesseract + Korean data."""
    try:
        import io
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    lang = os.getenv("OCR_LANG", "kor+eng")
    try:
        return pytesseract.image_to_string(img, lang=lang).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# HWPX  (Hancom XML, zip container)
# ---------------------------------------------------------------------------
# Text runs are <hp:t> elements; the "hp" namespace URI varies between builds,
# so we match on the local tag name and ignore the namespace.
def extract_hwpx(path: str) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        section_names = sorted(
            n for n in zf.namelist()
            if re.match(r"Contents/section\d+\.xml$", n)
        )
        if not section_names:
            # Fall back to the (truncated) preview text if there are no sections.
            if "Preview/PrvText.txt" in zf.namelist():
                return zf.read("Preview/PrvText.txt").decode("utf-8", "ignore")
            return ""
        for name in section_names:
            root = ET.fromstring(zf.read(name))
            for elem in root.iter():
                if _localname(elem.tag) == "t":
                    parts.append("".join(elem.itertext()))
                elif _localname(elem.tag) in ("lineBreak", "linesegarray"):
                    parts.append("\n")
    text = "".join(parts)
    return _tidy(text)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# ---------------------------------------------------------------------------
# HWP  (binary OLE compound file, HWP 5.x)
# ---------------------------------------------------------------------------
HWPTAG_BEGIN = 0x10
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51  # 67

# Control-char classes inside PARA_TEXT (values are UTF-16 code units).
_CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}   # occupy 1 wchar
_INLINE_CONTROLS = {4, 5, 6, 7, 8, 9, 19, 20}                  # occupy 8 wchars
_EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}  # 8 wchars


def extract_hwp(path: str) -> str:
    try:
        import olefile
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "olefile is required for HWP extraction. Install with: pip install olefile"
        ) from e

    ole = olefile.OleFileIO(path)
    try:
        compressed = _hwp_is_compressed(ole)
        streams = sorted(
            (s for s in ole.listdir() if s and s[0] == "BodyText"),
            key=lambda s: _section_index(s),
        )
        out: list[str] = []
        for stream in streams:
            raw = ole.openstream(stream).read()
            data = zlib.decompress(raw, -15) if compressed else raw
            out.append(_hwp_parse_records(data))
        return _tidy("\n".join(out))
    finally:
        ole.close()


def _hwp_is_compressed(ole) -> bool:
    if not ole.exists("FileHeader"):
        return True  # assume compressed; most HWP files are
    header = ole.openstream("FileHeader").read()
    # Byte 36 is a bit-field; bit 0 = compressed.
    return bool(header[36] & 0x01) if len(header) > 36 else True


def _section_index(stream) -> int:
    m = re.search(r"(\d+)$", stream[-1])
    return int(m.group(1)) if m else 0


def _hwp_parse_records(data: bytes) -> str:
    """Walk the record stream and pull text out of every PARA_TEXT record."""
    parts: list[str] = []
    i, n = 0, len(data)
    while i + 4 <= n:
        header = struct.unpack_from("<I", data, i)[0]
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:  # extended size in the following 4 bytes
            size = struct.unpack_from("<I", data, i)[0]
            i += 4
        payload = data[i:i + size]
        i += size
        if tag_id == HWPTAG_PARA_TEXT:
            parts.append(_hwp_decode_paratext(payload))
    return "\n".join(p for p in parts if p)


def _hwp_decode_paratext(payload: bytes) -> str:
    """Decode a PARA_TEXT payload (UTF-16LE text interleaved with controls)."""
    chars: list[str] = []
    j, m = 0, len(payload) - (len(payload) % 2)
    while j < m:
        code = payload[j] | (payload[j + 1] << 8)
        if code in _INLINE_CONTROLS or code in _EXTENDED_CONTROLS:
            j += 16  # 8 wchars
            continue
        if code in _CHAR_CONTROLS:
            if code in (10, 13):
                chars.append("\n")
            j += 2
            continue
        chars.append(chr(code))
        j += 2
    return "".join(chars)


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------
def extract_txt(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return _tidy(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return _tidy(raw.decode("utf-8", "ignore"))


# ---------------------------------------------------------------------------
# Dispatch + helpers
# ---------------------------------------------------------------------------
_EXTRACTORS = {
    ".pdf": extract_pdf,
    ".hwpx": extract_hwpx,
    ".hwp": extract_hwp,
    ".txt": extract_txt,
    ".md": extract_txt,
}

SUPPORTED_EXTENSIONS = tuple(_EXTRACTORS.keys())


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    extractor = _EXTRACTORS.get(ext)
    if extractor is None:
        raise ValueError(f"Unsupported file type: {ext} ({path})")
    return extractor(path)


# A line that, once stripped, is nothing but a page marker: "12", "- 12 -",
# "12/34", "12 페이지", "- 3 -". These carry no meaning and add noise to chunks.
_PAGE_NUM_RE = re.compile(
    r"^(?:[-–—]\s*)?\d{1,4}(?:\s*[-–—])?$"     # 12  /  - 12 -
    r"|^\d{1,4}\s*/\s*\d{1,4}$"                 # 12/34
    r"|^\d{1,4}\s*(?:페이지|쪽|page)$",          # 12 페이지
    re.IGNORECASE,
)


def _strip_repeated_lines(pages: list[str], min_ratio: float = 0.5) -> list[str]:
    """Remove running headers/footers: short lines that repeat across many pages."""
    if len(pages) < 3:
        return pages
    from collections import Counter
    counts: Counter[str] = Counter()
    for page in pages:
        # A header/footer appears once per page; count distinct lines per page.
        seen = {ln.strip() for ln in page.split("\n") if ln.strip()}
        counts.update(seen)
    threshold = max(2, int(len(pages) * min_ratio))
    boilerplate = {
        line for line, c in counts.items()
        if c >= threshold and len(line) <= 40  # long lines are unlikely to be chrome
    }
    if not boilerplate:
        return pages
    cleaned: list[str] = []
    for page in pages:
        kept = [ln for ln in page.split("\n") if ln.strip() not in boilerplate]
        cleaned.append("\n".join(kept))
    return cleaned


def _tidy(text: str) -> str:
    """Collapse runaway whitespace, drop page-number lines, keep paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if not _PAGE_NUM_RE.match(ln)]
    return "\n".join(lines).strip()


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print("=" * 70)
        print(p)
        print("=" * 70)
        print(extract_text(p)[:2000])
