"""Cấu hình tập trung cho toàn bộ hệ thống ScholarLens.

Mọi giá trị đều đọc được từ biến môi trường (hoặc file `.env` ở thư mục gốc),
nhờ vậy cùng một mã nguồn chạy được trên Kaggle (GPU) và trên máy demo (CPU).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv là tuỳ chọn
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # --- Thư mục dữ liệu ---
    data_dir: Path = Path(_env("SL_DATA_DIR", str(ROOT_DIR / "data")))

    # --- Embedding ---
    embed_model: str = _env("SL_EMBED_MODEL", "intfloat/multilingual-e5-base")
    embed_device: str = _env("SL_EMBED_DEVICE", "auto")  # auto | cuda | cpu | mps
    embed_batch_size: int = int(_env("SL_EMBED_BATCH", "64"))

    # --- Chunking ---
    chunk_words: int = int(_env("SL_CHUNK_WORDS", "220"))
    chunk_overlap: int = int(_env("SL_CHUNK_OVERLAP", "40"))

    # --- Kiểm tra trùng lặp ---
    dedup_title_threshold: float = float(_env("SL_DEDUP_TITLE", "0.92"))

    # --- Đồ thị ---
    similar_top_k: int = int(_env("SL_SIMILAR_TOPK", "5"))
    similar_min_score: float = float(_env("SL_SIMILAR_MIN", "0.75"))
    keywords_per_paper: int = int(_env("SL_KEYWORDS", "6"))

    # --- LLM ---
    # anthropic | openai (mọi API tương thích OpenAI: Gemini, Groq, Ollama, vLLM...) | none
    llm_provider: str = _env("SL_LLM_PROVIDER", "none")
    llm_model: str = _env("SL_LLM_MODEL", "")
    llm_base_url: str = _env("SL_LLM_BASE_URL", "")
    llm_api_key: str = _env("SL_LLM_API_KEY", "")
    llm_max_tokens: int = int(_env("SL_LLM_MAX_TOKENS", "4096"))

    # --- Mạng ---
    arxiv_api: str = _env("SL_ARXIV_API", "https://export.arxiv.org/api/query")
    arxiv_delay: float = float(_env("SL_ARXIV_DELAY", "3.0"))  # arXiv yêu cầu >= 3 giây/lượt
    enrich_metadata: bool = _env("SL_ENRICH", "1") == "1"  # tra arXiv API khi thêm PDF

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdfs"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "scholarlens.sqlite"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def graph_path(self) -> Path:
        return self.data_dir / "graph.json"

    @property
    def conversations_dir(self) -> Path:
        return self.data_dir / "conversations"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.raw_dir, self.pdf_dir, self.upload_dir,
                  self.chroma_dir, self.conversations_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
