"""Graph RAG đơn giản = truy xuất lai (seed) + mở rộng trên đồ thị tri thức + dựng ngữ cảnh có đánh số.

Hai chế độ:
- Có `focus_ids` (người dùng đang hỏi về bài cụ thể): đoạn văn lấy trong bài đó,
  bài liên quan lấy từ láng giềng đồ thị của bài đó.
- Không focus: seed = top bài theo hybrid search, mở rộng mỗi seed sang láng giềng đồ thị.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..graph import KnowledgeGraph
from ..store import MetadataDB
from .hybrid import HybridRetriever

RELATED_RE = re.compile(r"liên quan|tương tự|giống|cùng chủ đề|related|similar|cite|trích dẫn|so sánh|compare"
                        r"|khác (?:gì|nhau)|kế thừa|follow[- ]?up|bài (?:nào|khác)", re.I)


@dataclass
class Source:
    n: int
    paper: dict
    excerpts: list[dict] = field(default_factory=list)
    role: str = "retrieved"  # focus | retrieved | related
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_public(self) -> dict:
        p = self.paper
        return {"n": self.n, "paper_id": p["paper_id"], "title": p["title"], "authors": p["authors"][:6],
                "year": p["year"], "category": p["primary_category"], "role": self.role,
                "reasons": self.reasons, "score": round(self.score, 4),
                "url": f"https://arxiv.org/abs/{p['arxiv_id']}" if p.get("arxiv_id") else "",
                "has_pdf": bool(p.get("pdf_path")),
                "excerpts": [{"text": e["text"][:700], "page": e.get("page"), "section": e.get("section")}
                             for e in self.excerpts[:3]]}


@dataclass
class RAGContext:
    sources: list[Source]
    facts: list[str]
    subgraph: dict
    wants_related: bool

    def to_prompt(self, max_chars: int = 24000) -> str:
        parts, used = [], 0
        for s in self.sources:
            p = s.paper
            head = (f"[{s.n}] “{p['title']}” — {', '.join(p['authors'][:4])}"
                    f"{' et al.' if len(p['authors']) > 4 else ''} ({p['year'] or 'n.d.'}, "
                    f"arXiv:{p['arxiv_id'] or p['paper_id']}) | vai trò: {s.role}")
            if s.reasons:
                head += f" | liên quan vì: {'; '.join(s.reasons)}"
            body = []
            if p.get("keywords"):
                body.append(f"Khái niệm chính: {', '.join(p['keywords'])}")
            for e in s.excerpts:
                loc = f"(tr.{e.get('page')}, {e.get('section') or '—'})" if e.get("kind") != "summary" else "(abstract)"
                body.append(f"{loc} {e['text']}")
            block = head + "\n" + "\n".join(body)
            if used + len(block) > max_chars:
                block = block[:max(0, max_chars - used)]
            parts.append(block)
            used += len(block)
            if used >= max_chars:
                break
        if self.facts:
            parts.append("QUAN HỆ TRÊN ĐỒ THỊ:\n" + "\n".join(f"- {f}" for f in self.facts))
        return "\n\n".join(parts)


class GraphRAG:
    def __init__(self, retriever: HybridRetriever, kg: KnowledgeGraph, db: MetadataDB):
        self.r, self.kg, self.db = retriever, kg, db

    def _summary_excerpt(self, p: dict) -> dict:
        return {"text": f"{p['title']}\n\n{p['abstract']}", "kind": "summary", "page": 1, "section": "Abstract"}

    def retrieve(self, question: str, focus_ids: list[str] | None = None, k_chunks: int = 8,
                 n_seeds: int = 5, n_related: int = 4) -> RAGContext:
        wants_related = bool(RELATED_RE.search(question))
        sources: list[Source] = []
        index: dict[str, Source] = {}

        def add(pid: str, role: str, excerpt: dict | None = None, reasons=None, score: float = 0.0):
            if pid not in index:
                p = self.db.get_paper(pid)
                if not p:
                    return None
                index[pid] = Source(n=len(sources) + 1, paper=p, role=role, reasons=reasons or [], score=score)
                sources.append(index[pid])
            s = index[pid]
            if excerpt and all(e.get("text") != excerpt["text"] for e in s.excerpts):
                s.excerpts.append(excerpt)
            return s

        if focus_ids:
            # 1) đoạn văn từ chính bài đang hỏi
            for pid in focus_ids:
                p = self.db.get_paper(pid)
                if p:
                    add(pid, "focus", self._summary_excerpt(p))
            for c in self.r.search_chunks(question, k=k_chunks, paper_ids=focus_ids):
                if c["kind"] != "summary":
                    add(c["paper_id"], "focus", c)
            # 2) láng giềng đồ thị của bài
            n_rel = n_related * (2 if wants_related else 1)
            for pid in focus_ids:
                for rel in self.kg.related_papers(pid, k=n_rel):
                    rp = self.db.get_paper(rel["paper_id"])
                    if rp:
                        add(rel["paper_id"], "related", self._summary_excerpt(rp), rel["reasons"], rel["score"])
        else:
            hits = self.r.search_papers(question, k=n_seeds)
            for h in hits:
                for c in h["chunks"][:2]:
                    add(h["paper"]["paper_id"], "retrieved", c, score=h["score"])
            seeds = [h["paper"]["paper_id"] for h in hits[:3]]
            n_rel = n_related if wants_related else 2
            for pid in seeds:
                for rel in self.kg.related_papers(pid, k=n_rel):
                    if rel["paper_id"] in index:
                        continue
                    rp = self.db.get_paper(rel["paper_id"])
                    if rp:
                        add(rel["paper_id"], "related", self._summary_excerpt(rp),
                            [f"liên quan tới [{index[pid].n}]: " + rel["reasons"][0]] + rel["reasons"][1:],
                            rel["score"])
        ids = [s.paper["paper_id"] for s in sources]
        focus_or_seed = focus_ids or ids[:3]
        return RAGContext(sources=sources, facts=self.kg.facts(ids),
                          subgraph=self.kg.subgraph(focus_or_seed, related_per_paper=n_related),
                          wants_related=wants_related)
