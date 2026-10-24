"""Chia văn bản thành các đoạn (chunk) có chồng lấn, giữ thông tin trang + section."""
from __future__ import annotations

import re

from ..config import settings
from .pdf_parser import detect_section


def summary_chunk(title: str, abstract: str) -> dict:
    return {"idx": 0, "kind": "summary", "section": "Abstract", "page": 1,
            "text": f"{title}\n\n{abstract}".strip()}


def chunk_pages(pages: list[str], size: int | None = None, overlap: int | None = None,
                start_idx: int = 1) -> list[dict]:
    """Cửa sổ trượt theo số từ; một chunk không vượt qua ranh giới section mới."""
    size = size or settings.chunk_words
    overlap = overlap or settings.chunk_overlap
    # 1) gom từ thành dòng có gắn (page, section)
    words: list[tuple[str, int, str]] = []
    section = ""
    for pno, text in enumerate(pages, start=1):
        text = re.sub(r"-\n(\w)", r"\1", text)  # nối từ bị ngắt dòng
        for line in text.splitlines():
            sec = detect_section(line)
            if sec:
                section = sec
                words.append(("␞", pno, section))  # marker ranh giới section
                continue
            for w in line.split():
                words.append((w, pno, section))
    # 2) cửa sổ trượt
    chunks, buf, idx = [], [], start_idx

    def flush():
        nonlocal buf, idx
        text = " ".join(w for w, _, _ in buf).strip()
        if len(text.split()) >= 25:
            chunks.append({"idx": idx, "kind": "body", "page": buf[0][1], "section": buf[0][2], "text": text})
            idx += 1

    for item in words:
        if item[0] == "␞":
            if len(buf) > size // 3:
                flush()
                buf = []
            continue
        buf.append(item)
        if len(buf) >= size:
            flush()
            buf = buf[-overlap:]
    if buf and len(buf) > overlap:
        flush()
    return chunks
