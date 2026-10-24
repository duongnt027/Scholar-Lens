"""Trích xuất văn bản + metadata từ PDF bài báo khoa học bằng PyMuPDF.

Heuristic:
- Tiêu đề: dòng có cỡ chữ lớn nhất ở nửa trên trang 1 (bỏ dòng tem arXiv), fallback metadata PDF.
- arXiv ID: tem bên lề trang 1 ("arXiv:2310.06825v1 [cs.CL] ..."), URL arxiv.org, hoặc tên file.
- Abstract: đoạn giữa "Abstract" và "Introduction"/"Keywords".
- Section: dòng đánh số "3 Method", "4.2 Results" hoặc các tiêu đề quen thuộc.
- Tham chiếu: mọi arXiv ID trong phần References.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from ..utils import find_arxiv_ids

SECTION_RE = re.compile(
    r"^(?:(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][A-Za-z0-9 ,:&\-()/]{2,80})"
    r"|(Abstract|Introduction|Related Work|Background|Method(?:s|ology)?|Approach|Experiments?"
    r"|Results|Discussion|Conclusions?|Limitations|References|Bibliography|Appendix|Acknowledg(?:e)?ments?))\s*$")
REF_HEAD_RE = re.compile(r"^\s*(References|Bibliography|REFERENCES)\s*$", re.M)


@dataclass
class ParsedPDF:
    path: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    arxiv_id: str = ""
    pages: list[str] = field(default_factory=list)
    body_pages: list[str] = field(default_factory=list)  # đã cắt phần References
    references_arxiv: list[str] = field(default_factory=list)
    n_pages: int = 0

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages)


def _clean_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_title(page: fitz.Page) -> tuple[str, float]:
    """Lấy các DÒNG chứa span cỡ chữ lớn nhất ở nửa trên trang đầu.

    Làm theo dòng (không theo span) để giữ nguyên tiêu đề viết small-caps,
    nơi chữ hoa và chữ thường nằm ở các span có cỡ khác nhau.
    """
    d = page.get_text("dict")
    h = page.rect.height
    lines = []  # (max_size, y0, x0, text)
    for b in d.get("blocks", []):
        for line in b.get("lines", []):
            if line.get("dir", (1, 0))[0] < 0.9:  # bỏ chữ xoay dọc (tem arXiv bên lề)
                continue
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = spans[0]["text"]
            for prev, s in zip(spans, spans[1:]):
                gap = s["bbox"][0] - prev["bbox"][2]
                sep = " " if gap > 0.15 * s["size"] and not text.endswith(" ") else ""
                text += sep + s["text"]
            text = _clean_line(text)
            y0 = line["bbox"][1]
            if y0 > h * 0.5 or len(text) < 2 or re.search(r"arxiv|preprint|conference|proceedings|workshop",
                                                          text, re.I):
                continue
            lines.append((max(s["size"] for s in spans), y0, line["bbox"][0], text))
    if not lines:
        return "", 0.0
    max_size = max(l[0] for l in lines)
    picked = sorted((l for l in lines if l[0] >= max_size * 0.9), key=lambda l: (round(l[1]), l[2]))
    # chỉ giữ cụm dòng liền nhau quanh dòng lớn nhất đầu tiên
    group, last_y = [], None
    for sz, y, x, t in picked:
        if last_y is not None and y - last_y > max_size * 2.5:
            break
        group.append(t)
        last_y = y
    return _clean_line(" ".join(group)), last_y or 0.0


def _extract_authors(first_page_text: str, title: str) -> list[str]:
    """Lấy các dòng giữa tiêu đề và 'Abstract', lọc ra những dòng giống tên người."""
    txt = first_page_text
    end = re.search(r"\bAbstract\b", txt, re.I)
    head = txt[:end.start()] if end else txt[:1500]
    if title:
        idx = head.lower().find(title.split()[-1].lower())
        if idx >= 0:
            head = head[idx + len(title.split()[-1]):]
    names = []
    for raw in re.split(r"[\n,]| and ", head):
        s = re.sub(r"[\d*†‡§¶∗♠♣♥♦]+", "", raw).strip()
        if re.fullmatch(r"(?:[A-Z][a-zA-Z'\-]+\.?\s){1,3}[A-Z][a-zA-Z'\-]+", s) and not re.search(
                r"University|Institute|Lab|Department|School|Inc|Research|Google|Microsoft|Meta|College", s):
            names.append(s)
    return names[:20]


def _extract_abstract(text: str) -> str:
    m = re.search(r"\bA\s?BSTRACT\b|\bAbstract\b", text)
    if not m:
        return ""
    rest = text[m.end():m.end() + 5000]
    stop = re.search(r"\n\s*(?:1\.?\s*|I\.\s*)?(?:Introduction|INTRODUCTION)\b|\n\s*(?:Keywords|Index Terms|CCS Concepts)",
                     rest)
    abstract = rest[:stop.start()] if stop else rest[:2000]
    abstract = re.sub(r"-\n(\w)", r"\1", abstract)
    return _clean_line(abstract.lstrip(":.—- "))


def parse_pdf(path: str | Path, max_pages: int = 60) -> ParsedPDF:
    path = str(path)
    doc = fitz.open(path)
    out = ParsedPDF(path=path, n_pages=doc.page_count)
    try:
        pages = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pages.append(page.get_text("text"))
        out.pages = pages
        first = pages[0] if pages else ""

        # arXiv ID: tem trang đầu > tên file > URL bất kỳ trên trang đầu
        ids = find_arxiv_ids(first, stamped_only=True)
        if not ids:
            ids = find_arxiv_ids(Path(path).stem)
        out.arxiv_id = ids[0] if ids else ""

        title, _ = _extract_title(doc[0]) if doc.page_count else ("", 0)
        meta_title = (doc.metadata or {}).get("title", "") or ""
        if (not title or len(title) < 8) and len(meta_title) > 8:
            title = meta_title
        out.title = title
        meta_author = (doc.metadata or {}).get("author", "") or ""
        out.authors = ([a.strip() for a in re.split(r";|,| and ", meta_author) if a.strip()]
                       if meta_author else _extract_authors(first, title))
        out.abstract = _extract_abstract("\n".join(pages[:2]))

        # tách phần References
        full = "\n".join(pages)
        ref_pos = None
        for m in REF_HEAD_RE.finditer(full):
            ref_pos = m.start()  # lấy lần xuất hiện cuối cùng
        refs_text = full[ref_pos:] if ref_pos is not None else ""
        out.references_arxiv = [x for x in find_arxiv_ids(refs_text) if x != out.arxiv_id]
        if ref_pos is not None:
            body, acc = [], 0
            for p in pages:
                if acc + len(p) + 1 <= ref_pos:
                    body.append(p)
                else:
                    body.append(p[:max(0, ref_pos - acc)])
                    break
                acc += len(p) + 1
            out.body_pages = body
        else:
            out.body_pages = pages
    finally:
        doc.close()
    return out


def detect_section(line: str) -> str | None:
    line = line.strip()
    if len(line) > 90:
        return None
    m = SECTION_RE.match(line)
    if not m:
        return None
    return _clean_line(" ".join(g for g in m.groups() if g))
