"""Luồng embedding: lấy các chunk chưa vector hoá trong SQLite -> encode -> ghi ChromaDB.

Đồng thời sinh vector cấp bài báo (tiêu đề + abstract) và trích keyword cho đồ thị.
"""
from __future__ import annotations

import time

from ..config import settings
from ..graph.keywords import extract_keywords_batch
from ..store import MetadataDB, VectorStore
from ..utils import get_logger
from .embedder import Embedder

log = get_logger("embedding")


def embed_pending(db: MetadataDB, vs: VectorStore, embedder: Embedder | None = None,
                  paper_ids: list[str] | None = None, batch: int = 4096,
                  progress=None) -> dict:
    """Embedding mọi chunk có embedded=0 (hoặc chỉ của `paper_ids`). Trả về thống kê."""
    embedder = embedder or Embedder.get()
    t0 = time.time()
    n_chunks, touched = 0, set()
    while True:
        rows = db.pending_chunks(limit=batch, paper_ids=paper_ids)
        if not rows:
            break
        vecs = embedder.encode_docs([r["text"] for r in rows], show_progress=len(rows) > 512)
        vs.upsert_chunks(
            ids=[r["chunk_id"] for r in rows], embeddings=vecs,
            documents=[r["text"] for r in rows],
            metadatas=[{"paper_id": r["paper_id"], "idx": r["idx"], "kind": r["kind"],
                        "section": r["section"], "page": r["page"], "title": r["title"],
                        "year": r["year"] or 0, "category": r["primary_category"] or ""} for r in rows])
        db.mark_chunks_embedded([r["chunk_id"] for r in rows])
        n_chunks += len(rows)
        touched.update(r["paper_id"] for r in rows)
        if progress:
            progress(n_chunks)
        log.info("Đã embedding %d chunk (%.1f chunk/s)", n_chunks, n_chunks / max(time.time() - t0, 1e-6))

    # vector cấp bài báo + keyword cho các bài vừa xử lý (hoặc còn ở trạng thái registered)
    targets = sorted(touched | {p["paper_id"] for p in db.iter_papers(status="registered")
                                if not paper_ids or p["paper_id"] in paper_ids})
    papers = db.get_papers(targets)
    for i in range(0, len(targets), 1024):
        part = [papers[p] for p in targets[i:i + 1024] if p in papers]
        texts = [f"{p['title']}. {p['abstract']}" for p in part]
        vecs = embedder.encode_docs(texts)
        vs.upsert_papers(ids=[p["paper_id"] for p in part], embeddings=vecs,
                         metadatas=[{"title": p["title"], "year": p["year"] or 0,
                                     "category": p["primary_category"] or ""} for p in part])
        kws = extract_keywords_batch(texts, embedder, doc_vecs=vecs, top_n=settings.keywords_per_paper)
        for p, kw in zip(part, kws):
            db.set_keywords(p["paper_id"], kw)
        db.set_status([p["paper_id"] for p in part], "embedded")
    dt = time.time() - t0
    log.info("Hoàn tất: %d chunk, %d bài, %.1fs trên %s", n_chunks, len(targets), dt, embedder.device)
    return {"chunks": n_chunks, "papers": len(targets), "seconds": round(dt, 1), "device": embedder.device}
