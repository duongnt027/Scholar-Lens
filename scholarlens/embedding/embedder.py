"""Sinh embedding bằng sentence-transformers, tự chọn GPU (CUDA) khi có — ví dụ trên Kaggle T4/P100."""
from __future__ import annotations

import threading
import time

import numpy as np

from ..config import settings
from ..utils import get_logger

log = get_logger("embedding")

# Một số model cần tiền tố khác nhau cho câu truy vấn và văn bản
QUERY_PREFIX = {
    "bge": "Represent this sentence for searching relevant passages: ",
    "e5": "query: ",
}
DOC_PREFIX = {"e5": "passage: "}


def _family(model_name: str) -> str:
    n = model_name.lower()
    if "bge" in n and "m3" not in n:
        return "bge"
    if "e5" in n:
        return "e5"
    return ""


def pick_device(pref: str = "auto") -> str:
    if pref != "auto":
        return pref
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class Embedder:
    _instance: "Embedder | None" = None
    _lock = threading.Lock()

    def __init__(self, model_name: str | None = None, device: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or settings.embed_model
        self.device = pick_device(device or settings.embed_device)
        t0 = time.time()
        self.model = SentenceTransformer(self.model_name, device=self.device)
        if self.device == "cuda":
            self.model.half()  # fp16 nhanh gấp ~2 lần trên T4
        self.dim = self.model.get_sentence_embedding_dimension()
        fam = _family(self.model_name)
        self.q_prefix = QUERY_PREFIX.get(fam, "")
        self.d_prefix = DOC_PREFIX.get(fam, "")
        log.info("Nạp %s trên %s (dim=%d) trong %.1fs", self.model_name, self.device, self.dim, time.time() - t0)

    @classmethod
    def get(cls) -> "Embedder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def encode_docs(self, texts: list[str], batch_size: int | None = None,
                    show_progress: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        bs = batch_size or (settings.embed_batch_size * (4 if self.device == "cuda" else 1))
        return self.model.encode([self.d_prefix + t for t in texts], batch_size=bs,
                                 normalize_embeddings=True, convert_to_numpy=True,
                                 show_progress_bar=show_progress).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        return self.model.encode([self.q_prefix + text], normalize_embeddings=True,
                                 convert_to_numpy=True)[0].astype(np.float32)

    def encode_phrases(self, phrases: list[str]) -> np.ndarray:
        """Cụm từ ngắn (keyword) — không thêm tiền tố."""
        if not phrases:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self.model.encode(phrases, batch_size=256, normalize_embeddings=True,
                                 convert_to_numpy=True).astype(np.float32)
