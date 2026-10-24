"""Hàm tiện ích dùng chung: chuẩn hoá tiêu đề, nhận diện arXiv ID, băm file, logging."""
from __future__ import annotations

import hashlib
import logging
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

# arXiv ID kiểu mới (2007+): 2310.06825v2 ; kiểu cũ: cs.IR/0701001 hoặc hep-th/9901001
NEW_ID = r"(\d{4}\.\d{4,5})(v\d+)?"
OLD_ID = r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?"
ARXIV_STAMP_RE = re.compile(r"arXiv:\s*(?:" + NEW_ID + "|" + OLD_ID + ")", re.I)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?:" + NEW_ID + "|" + OLD_ID + ")", re.I)
BARE_NEW_ID_RE = re.compile(r"(?<![\d.])" + NEW_ID + r"(?![\d])")

_STOPWORDS = set("""a an and are as at be by for from has have in into is it its of on or that the this
to was were will with we our their they these those which via using based towards toward""".split())


def get_logger(name: str) -> logging.Logger:
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định không phải UTF-8
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "huggingface_hub", "sentence_transformers", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(name)


def normalize_title(title: str) -> str:
    """Chuẩn hoá tiêu đề để so khớp: bỏ dấu, chữ thường, chỉ giữ chữ-số."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(a: str, b: str) -> float:
    """Tỉ lệ ký tự giống nhau (difflib) giữa hai tiêu đề đã chuẩn hoá."""
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    m = SequenceMatcher(None, a, b)
    if m.real_quick_ratio() < 0.6 or m.quick_ratio() < 0.6:
        return 0.0
    return m.ratio()


def title_near_duplicate(a: str, b: str, threshold: float = 0.92) -> tuple[bool, float]:
    """Hai tiêu đề có phải cùng một bài không.

    Tiêu chí 1: tỉ lệ ký tự >= threshold (bắt lỗi chính tả, dấu câu, chữ hoa).
    Tiêu chí 2: bao hàm từ |A∩B|/min >= 0,9 VÀ Jaccard >= 0,8, với tiêu đề ngắn hơn >= 6 từ
                (bắt bỏ/thêm 1-2 từ như "(Extended Version)" mà không nhận nhầm "<A> for X Revisited").
    """
    r = title_similarity(a, b)
    if r >= threshold:
        return True, r
    ta, tb = set(normalize_title(a).split()), set(normalize_title(b).split())
    if min(len(ta), len(tb)) >= 6:
        inter = len(ta & tb)
        jac = inter / len(ta | tb)
        if inter / min(len(ta), len(tb)) >= 0.9 and jac >= 0.8:
            return True, jac
    return False, r


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def find_arxiv_ids(text: str, stamped_only: bool = False) -> list[str]:
    """Tìm mọi arXiv ID xuất hiện trong văn bản (đã bỏ hậu tố version), giữ thứ tự."""
    found: list[str] = []
    patterns = [ARXIV_STAMP_RE, ARXIV_URL_RE] + ([] if stamped_only else [BARE_NEW_ID_RE])
    for pat in patterns:
        for m in pat.finditer(text or ""):
            raw = next(g for g in m.groups() if g and not g.startswith("v"))
            found.append(strip_version(raw))
    seen, out = set(), []
    for x in found:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tokenize(text: str) -> list[str]:
    """Tokenizer đơn giản cho BM25."""
    return [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (text or "").lower())
            if w not in _STOPWORDS and len(w) > 1]


def year_of(date_str: str | None) -> int:
    m = re.match(r"(\d{4})", date_str or "")
    return int(m.group(1)) if m else 0
