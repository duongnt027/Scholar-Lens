"""Luồng nạp tài liệu.

register_pdf()      : PDF -> parse -> kiểm tra trùng -> làm giàu metadata (arXiv API) -> lưu SQLite + chunks
register_record()   : bản ghi crawl (JSONL) -> (PDF nếu có) -> SQLite + chunks
IngestService.add_pdf(): toàn bộ luồng cho 1 file khi demo: register -> embedding -> vector DB -> graph
"""
from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from ..config import settings
from ..utils import file_sha256, get_logger, title_similarity, year_of
from .chunker import chunk_pages, summary_chunk
from .pdf_parser import parse_pdf

log = get_logger("ingest")


@dataclass
class IngestResult:
    file: str
    status: str  # added | duplicate | error
    paper_id: str = ""
    title: str = ""
    reason: str = ""
    steps: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_name(pid: str) -> str:
    return pid.replace("/", "_").replace(":", "_")


def _build_chunks(title: str, abstract: str, body_pages: list[str] | None) -> list[dict]:
    chunks = [summary_chunk(title, abstract)]
    if body_pages:
        chunks += chunk_pages(body_pages, start_idx=1)
    return chunks


def register_pdf(db, pdf_path: str | Path, source: str = "upload", client=None,
                 enrich: bool | None = None, log_step: Callable[[str], None] | None = None) -> IngestResult:
    step = log_step or (lambda s: None)
    pdf_path = Path(pdf_path)
    res = IngestResult(file=pdf_path.name, status="error")
    try:
        step("Tính SHA-256 và kiểm tra trùng nội dung file")
        sha = file_sha256(pdf_path)
        dup = db.find_duplicate(sha256=sha)
        if dup:
            return _dup(res, db, dup)

        step("Trích xuất văn bản, tiêu đề, arXiv ID, tài liệu tham khảo từ PDF")
        parsed = parse_pdf(pdf_path)
        res.title = parsed.title
        dup = db.find_duplicate(arxiv_id=parsed.arxiv_id, title=parsed.title)
        if dup:
            return _dup(res, db, dup)

        meta = None
        enrich = settings.enrich_metadata if enrich is None else enrich
        if enrich:
            step("Tra cứu metadata chuẩn trên arXiv API")
            try:
                from ..crawler import ArxivClient
                client = client or ArxivClient(delay=1.0)
                if parsed.arxiv_id:
                    found = client.fetch_by_ids([parsed.arxiv_id])
                    meta = found[0] if found else None
                elif parsed.title:
                    meta = client.find_by_title(parsed.title)
            except Exception as exc:  # mạng lỗi -> dùng kết quả parse
                log.warning("Không làm giàu được metadata: %s", exc)
            if meta and parsed.title and title_similarity(meta.title, parsed.title) < 0.5 and not parsed.arxiv_id:
                meta = None
            if meta:
                dup = db.find_duplicate(arxiv_id=meta.arxiv_id, title=meta.title)
                if dup:
                    return _dup(res, db, dup)

        if meta:
            paper = {"paper_id": meta.arxiv_id, "arxiv_id": meta.arxiv_id, "version": meta.version,
                     "title": meta.title, "authors": meta.authors, "abstract": meta.abstract or parsed.abstract,
                     "categories": meta.categories, "primary_category": meta.primary_category,
                     "published": meta.published, "updated": meta.updated, "year": year_of(meta.published),
                     "doi": meta.doi, "journal_ref": meta.journal_ref, "pdf_url": meta.pdf_url}
        else:
            pid = parsed.arxiv_id or f"local:{sha[:12]}"
            paper = {"paper_id": pid, "arxiv_id": parsed.arxiv_id, "title": parsed.title or pdf_path.stem,
                     "authors": parsed.authors, "abstract": parsed.abstract, "categories": [],
                     "primary_category": "", "year": 0}
        if not paper["abstract"]:
            paper["abstract"] = " ".join(" ".join(parsed.body_pages[:1]).split()[:200])

        dest = settings.pdf_dir / f"{_safe_name(paper['paper_id'])}.pdf"
        if pdf_path.resolve() != dest.resolve():
            shutil.copyfile(pdf_path, dest)
        paper.update({"pdf_path": str(dest), "file_sha256": sha, "source": source, "has_fulltext": 1,
                      "refs": parsed.references_arxiv, "status": "registered"})

        step("Chia đoạn (chunking) theo section/trang")
        chunks = _build_chunks(paper["title"], paper["abstract"], parsed.body_pages)
        db.upsert_paper(paper)
        db.replace_chunks(paper["paper_id"], chunks)
        res.status, res.paper_id, res.title = "added", paper["paper_id"], paper["title"]
        res.info = {"chunks": len(chunks), "pages": parsed.n_pages, "refs_arxiv": len(parsed.references_arxiv),
                    "metadata": "arXiv API" if meta else "trích từ PDF"}
        return res
    except Exception as exc:
        log.exception("Lỗi nạp %s", pdf_path)
        res.reason = f"{type(exc).__name__}: {exc}"
        return res


def _dup(res: IngestResult, db, dup: tuple[str, str]) -> IngestResult:
    pid, reason = dup
    p = db.get_paper(pid) or {}
    res.status, res.paper_id, res.reason = "duplicate", pid, reason
    res.title = p.get("title", res.title)
    return res


def register_record(db, rec: dict, use_pdf: bool = True) -> str:
    """Nạp 1 bản ghi crawl. Trả về 'added' | 'duplicate'."""
    if db.find_duplicate(arxiv_id=rec["arxiv_id"]):
        return "duplicate"
    body, refs, sha, has_full = None, [], "", 0
    pdf = rec.get("pdf_path") or ""
    if use_pdf and pdf and Path(pdf).exists():
        try:
            parsed = parse_pdf(pdf)
            body, refs, sha, has_full = parsed.body_pages, parsed.references_arxiv, file_sha256(pdf), 1
        except Exception as exc:
            log.warning("Parse PDF %s lỗi: %s — chỉ dùng abstract", pdf, exc)
    paper = {"paper_id": rec["arxiv_id"], "arxiv_id": rec["arxiv_id"], "version": rec.get("version", ""),
             "title": rec["title"], "authors": rec.get("authors", []), "abstract": rec.get("abstract", ""),
             "categories": rec.get("categories", []), "primary_category": rec.get("primary_category", ""),
             "published": rec.get("published", ""), "updated": rec.get("updated", ""),
             "year": year_of(rec.get("published")), "doi": rec.get("doi", ""),
             "journal_ref": rec.get("journal_ref", ""), "pdf_url": rec.get("pdf_url", ""),
             "pdf_path": pdf if has_full else "", "file_sha256": sha, "source": "crawl",
             "has_fulltext": has_full, "refs": refs, "status": "registered"}
    db.upsert_paper(paper)
    db.replace_chunks(paper["paper_id"], _build_chunks(paper["title"], paper["abstract"], body))
    return "added"


class IngestService:
    """Gói toàn bộ luồng nạp + embedding + đồ thị cho web app."""

    def __init__(self, db, vs, kg, bm25, embedder_getter):
        self.db, self.vs, self.kg, self.bm25 = db, vs, kg, bm25
        self.embedder_getter = embedder_getter

    def add_pdf(self, pdf_path: str | Path, log_step: Callable[[str], None] | None = None) -> IngestResult:
        from ..embedding.pipeline import embed_pending
        from ..graph.builder import add_paper_to_graph

        steps: list[str] = []

        def step(s: str) -> None:
            steps.append(s)
            if log_step:
                log_step(s)

        res = register_pdf(self.db, pdf_path, log_step=step)
        res.steps = steps
        if res.status != "added":
            return res
        try:
            step("Sinh embedding và ghi vào vector DB (ChromaDB)")
            stats = embed_pending(self.db, self.vs, self.embedder_getter(), paper_ids=[res.paper_id])
            step("Cập nhật đồ thị tri thức (tác giả, khái niệm, trích dẫn, tương đồng)")
            g = add_paper_to_graph(self.db, self.vs, self.kg, res.paper_id)
            self.bm25.invalidate()
            res.info.update({"embedded_chunks": stats["chunks"], "device": stats["device"], "graph": g,
                             "keywords": self.db.get_paper(res.paper_id)["keywords"]})
        except Exception as exc:
            log.exception("Lỗi embedding/graph")
            res.status, res.reason = "error", f"{type(exc).__name__}: {exc}"
        return res
