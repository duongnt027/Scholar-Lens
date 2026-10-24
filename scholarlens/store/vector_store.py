"""Vector store dựa trên ChromaDB (HNSW, cosine), gồm 2 collection:

- `chunks`: vector của từng đoạn văn (phục vụ RAG)
- `papers`: vector cấp bài báo = embedding(tiêu đề + abstract) (phục vụ dedup ngữ nghĩa & cạnh SIMILAR)
"""
from __future__ import annotations

from pathlib import Path

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from ..config import settings

MAX_BATCH = 4000  # Chroma giới hạn kích thước mỗi lần add


def _clean_meta(m: dict) -> dict:
    out = {}
    for k, v in m.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return out


class VectorStore:
    def __init__(self, path: Path | None = None):
        self.client = chromadb.PersistentClient(
            path=str(path or settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False))
        self.chunks = self.client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})
        self.papers = self.client.get_or_create_collection("papers", metadata={"hnsw:space": "cosine"})

    # ---------- ghi ----------
    def upsert_chunks(self, ids, embeddings, documents, metadatas) -> None:
        for i in range(0, len(ids), MAX_BATCH):
            self.chunks.upsert(ids=ids[i:i + MAX_BATCH],
                               embeddings=np.asarray(embeddings[i:i + MAX_BATCH], dtype=np.float32),
                               documents=documents[i:i + MAX_BATCH],
                               metadatas=[_clean_meta(m) for m in metadatas[i:i + MAX_BATCH]])

    def upsert_papers(self, ids, embeddings, metadatas) -> None:
        for i in range(0, len(ids), MAX_BATCH):
            self.papers.upsert(ids=ids[i:i + MAX_BATCH],
                               embeddings=np.asarray(embeddings[i:i + MAX_BATCH], dtype=np.float32),
                               metadatas=[_clean_meta(m) for m in metadatas[i:i + MAX_BATCH]])

    def delete_paper(self, paper_id: str) -> None:
        self.chunks.delete(where={"paper_id": paper_id})
        self.papers.delete(ids=[paper_id])

    # ---------- đọc ----------
    def query_chunks(self, embedding, k: int = 50, paper_ids: list[str] | None = None,
                     where: dict | None = None) -> list[dict]:
        if self.chunks.count() == 0:
            return []
        conds = []
        if paper_ids:
            conds.append({"paper_id": {"$in": list(paper_ids)}} if len(paper_ids) > 1
                         else {"paper_id": paper_ids[0]})
        if where:
            conds.extend({k2: v} for k2, v in where.items())
        flt = None if not conds else conds[0] if len(conds) == 1 else {"$and": conds}
        res = self.chunks.query(query_embeddings=[np.asarray(embedding, dtype=np.float32)],
                                n_results=min(k, self.chunks.count()), where=flt,
                                include=["documents", "metadatas", "distances"])
        return [{"chunk_id": cid, "text": doc, "meta": meta, "score": 1.0 - dist}
                for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                                res["metadatas"][0], res["distances"][0])]

    def query_papers(self, embedding, k: int = 10, exclude: str | None = None) -> list[tuple[str, float]]:
        n = self.papers.count()
        if n == 0:
            return []
        res = self.papers.query(query_embeddings=[np.asarray(embedding, dtype=np.float32)],
                                n_results=min(k + 1, n), include=["distances"])
        return [(pid, 1.0 - d) for pid, d in zip(res["ids"][0], res["distances"][0]) if pid != exclude][:k]

    def paper_vectors(self, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        res = self.papers.get(ids=ids, include=["embeddings"]) if ids else self.papers.get(include=["embeddings"])
        embs = res["embeddings"]
        if embs is None or len(embs) == 0:
            return [], np.zeros((0, 0), dtype=np.float32)
        return list(res["ids"]), np.asarray(embs, dtype=np.float32)

    def stats(self) -> dict:
        return {"chunk_vectors": self.chunks.count(), "paper_vectors": self.papers.count()}
