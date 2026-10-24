"""Dựng / cập nhật đồ thị từ SQLite + vector store."""
from __future__ import annotations

from ..config import settings
from ..store import MetadataDB, VectorStore
from ..utils import get_logger
from .knowledge_graph import KnowledgeGraph

log = get_logger("graph")


def build_graph(db: MetadataDB, vs: VectorStore, kg: KnowledgeGraph | None = None) -> KnowledgeGraph:
    """Dựng lại toàn bộ đồ thị (dùng sau khi embedding hàng loạt, ví dụ trên Kaggle)."""
    kg = kg or KnowledgeGraph()
    kg.g.clear()
    papers = [p for p in db.iter_papers() if p["status"] in ("embedded", "graphed")]
    for p in papers:  # lượt 1: thêm nút
        kg.add_paper(p)
    for p in papers:  # lượt 2: cạnh CITES (lúc này mọi nút đã tồn tại)
        kg.add_paper(p)
    ids, vecs = vs.paper_vectors()
    n_sim = kg.add_similarity_edges(ids, vecs) if len(ids) > 1 else 0
    db.set_status([p["paper_id"] for p in papers], "graphed")
    kg.save()
    log.info("Đồ thị: %s (cạnh SIMILAR mới: %d)", kg.stats(), n_sim)
    return kg


def add_paper_to_graph(db: MetadataDB, vs: VectorStore, kg: KnowledgeGraph, paper_id: str) -> dict:
    """Thêm tăng dần một bài: cạnh tới tác giả/khái niệm, trích dẫn 2 chiều, láng giềng ngữ nghĩa."""
    paper = db.get_paper(paper_id)
    _, vec = vs.paper_vectors([paper_id])
    similar = []
    if len(vec):
        similar = [(pid, s) for pid, s in vs.query_papers(vec[0], k=settings.similar_top_k, exclude=paper_id)
                   if s >= settings.similar_min_score]
    cited_by = db.papers_citing(paper["arxiv_id"]) if paper.get("arxiv_id") else []
    kg.add_paper(paper, similar=similar, cited_by=cited_by)
    db.set_status([paper_id], "graphed")
    kg.save()
    return {"similar": len(similar), "cited_by": len(cited_by),
            "cites": sum(1 for r in paper["refs"] if f"paper:{r}" in kg.g)}
