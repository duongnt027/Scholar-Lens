"""Khởi tạo một lần các thành phần dùng chung (DB, vector store, graph, retriever, chatbot)."""
from __future__ import annotations

import threading

from .chat.chatbot import Chatbot, ConversationStore
from .chat.llm import get_llm
from .embedding import Embedder
from .graph import KnowledgeGraph
from .ingest import IngestService
from .retrieval import GraphRAG, HybridRetriever
from .store import BM25Index, MetadataDB, VectorStore


class Services:
    _inst: "Services | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self.db = MetadataDB()
        self.vs = VectorStore()
        self.kg = KnowledgeGraph()
        self.bm25 = BM25Index(self.db)
        self.embedder = Embedder.get
        self.retriever = HybridRetriever(self.db, self.vs, self.bm25, self.embedder)
        self.rag = GraphRAG(self.retriever, self.kg, self.db)
        self.llm = get_llm()
        self.chatbot = Chatbot(self.rag, self.llm, ConversationStore())
        self.ingest = IngestService(self.db, self.vs, self.kg, self.bm25, self.embedder)
        self.ingest_lock = threading.Lock()  # embedding tuần tự để tránh tranh chấp GPU/CPU

    def set_llm(self, cfg: dict) -> None:
        """Đổi LLM khi app đang chạy (ví dụ URL trycloudflare mới) — không cần khởi động lại."""
        self.llm = get_llm(cfg)
        self.chatbot.llm = self.llm

    @classmethod
    def get(cls) -> "Services":
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst
