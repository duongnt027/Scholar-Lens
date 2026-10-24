"""Chỉ mục từ vựng BM25 (Okapi) trong bộ nhớ, dựng lại lười (lazy) khi dữ liệu thay đổi."""
from __future__ import annotations

import threading

import numpy as np
from rank_bm25 import BM25Okapi

from ..utils import tokenize
from .metadata_db import MetadataDB


class BM25Index:
    def __init__(self, db: MetadataDB):
        self.db = db
        self._bm25: BM25Okapi | None = None
        self._ids: list[str] = []
        self._paper_of: list[str] = []
        self._dirty = True
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        self._dirty = True

    def _build(self) -> None:
        rows = self.db.all_chunks()
        self._ids = [r[0] for r in rows]
        self._paper_of = [r[1] for r in rows]
        corpus = [tokenize(r[2]) or ["_"] for r in rows]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._dirty = False

    def search(self, query: str, k: int = 50, paper_ids: list[str] | None = None) -> list[tuple[str, float]]:
        with self._lock:
            if self._dirty:
                self._build()
        if self._bm25 is None:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        if paper_ids:
            allowed = set(paper_ids)
            mask = np.array([p in allowed for p in self._paper_of])
            scores = np.where(mask, scores, -1.0)
        top = np.argsort(-scores)[:k]
        return [(self._ids[i], float(scores[i])) for i in top if scores[i] > 0]

    @property
    def size(self) -> int:
        return len(self._ids)
