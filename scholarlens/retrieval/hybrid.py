"""Tìm kiếm lai: BM25 (từ vựng) + dense (ngữ nghĩa), gộp bằng Reciprocal Rank Fusion.

RRF(d) = Σ_r 1 / (k + rank_r(d)),  k = 60   (Cormack et al., 2009)
"""
from __future__ import annotations

from collections import defaultdict

from ..store import BM25Index, MetadataDB, VectorStore

RRF_K = 60


def rrf(rankings: list[list[str]], k: int = RRF_K, weights: list[float] | None = None) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    weights = weights or [1.0] * len(rankings)
    for w, ranking in zip(weights, rankings):
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] += w / (k + rank)
    return scores


class HybridRetriever:
    def __init__(self, db: MetadataDB, vs: VectorStore, bm25: BM25Index, embedder_getter):
        self.db, self.vs, self.bm25 = db, vs, bm25
        self.embedder_getter = embedder_getter

    def search_chunks(self, query: str, k: int = 10, paper_ids: list[str] | None = None,
                      mode: str = "hybrid", pool: int = 50, year_from: int | None = None) -> list[dict]:
        """Trả về chunk đã xếp hạng: {chunk_id, paper_id, text, score, dense_rank, bm25_rank}."""
        dense, lex = [], []
        if mode in ("hybrid", "dense"):
            qv = self.embedder_getter().encode_query(query)
            where = {"year": {"$gte": year_from}} if year_from else None
            dense = self.vs.query_chunks(qv, k=pool, paper_ids=paper_ids, where=where)
        if mode in ("hybrid", "bm25"):
            lex = self.bm25.search(query, k=pool, paper_ids=paper_ids)
        d_ids = [d["chunk_id"] for d in dense]
        l_ids = [c for c, _ in lex]
        fused = rrf([d_ids, l_ids]) if mode == "hybrid" else {c: 1.0 / (RRF_K + i)
                                                               for i, c in enumerate(d_ids or l_ids, 1)}
        top = sorted(fused, key=lambda c: -fused[c])[:k]
        rows = self.db.get_chunks(top)
        d_rank = {c: i for i, c in enumerate(d_ids, 1)}
        l_rank = {c: i for i, c in enumerate(l_ids, 1)}
        out = []
        for c in top:
            r = rows.get(c)
            if not r:
                continue
            if year_from and mode == "bm25":
                p = self.db.get_paper(r["paper_id"])
                if p and p["year"] < year_from:
                    continue
            out.append({"chunk_id": c, "paper_id": r["paper_id"], "text": r["text"], "page": r["page"],
                        "section": r["section"], "kind": r["kind"], "score": round(fused[c], 5),
                        "dense_rank": d_rank.get(c), "bm25_rank": l_rank.get(c)})
        return out

    def search_papers(self, query: str, k: int = 10, mode: str = "hybrid", **kw) -> list[dict]:
        """Gộp chunk về cấp bài báo: điểm = max + 0.3 * tổng các chunk còn lại."""
        chunks = self.search_chunks(query, k=k * 6, mode=mode, **kw)
        by_paper: dict[str, list[dict]] = defaultdict(list)
        for c in chunks:
            by_paper[c["paper_id"]].append(c)
        scored = []
        for pid, cs in by_paper.items():
            s = sorted((c["score"] for c in cs), reverse=True)
            scored.append((s[0] + 0.3 * sum(s[1:]), pid))
        scored.sort(reverse=True)
        papers = self.db.get_papers([pid for _, pid in scored[:k]])
        out = []
        for score, pid in scored[:k]:
            p = papers.get(pid)
            if p:
                out.append({"paper": p, "score": round(score, 5), "chunks": by_paper[pid][:3]})
        return out
