"""Luồng chatbot: định tuyến chế độ -> (viết lại câu hỏi) -> Graph RAG -> sinh câu trả lời streaming.

Mỗi lượt trả lời là một chuỗi sự kiện (dùng cho SSE ở web app và cho CLI):
  meta | status | query | sources | token | done
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Iterator

from ..config import settings
from ..retrieval import GraphRAG
from ..utils import tokenize
from .llm import BaseLLM
from .prompts import CHAT_SYSTEM, CONDENSE_SYSTEM, RESEARCH_SYSTEM, language_reminder, research_user_message

CHITCHAT_RE = re.compile(r"^\s*(xin chào|chào|hello|hi|hey|cảm ơn|thanks|thank you|bạn là ai|bạn tên|"
                         r"bạn khỏe|good (morning|evening)|ok|oke|tạm biệt|bye)\b", re.I)
HISTORY_TURNS = 8


class ConversationStore:
    def __init__(self):
        self.dir = settings.conversations_dir

    def _path(self, cid: str):
        return self.dir / f"{re.sub(r'[^a-zA-Z0-9_-]', '', cid)}.json"

    def get(self, cid: str) -> dict | None:
        p = self._path(cid)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def create(self, title: str = "Cuộc trò chuyện mới") -> dict:
        conv = {"id": uuid.uuid4().hex[:12], "title": title, "created": time.time(),
                "updated": time.time(), "messages": [], "focus": []}
        self.save(conv)
        return conv

    def save(self, conv: dict) -> None:
        conv["updated"] = time.time()
        self._path(conv["id"]).write_text(json.dumps(conv, ensure_ascii=False), encoding="utf-8")

    def list(self) -> list[dict]:
        convs = []
        for p in self.dir.glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
                convs.append({"id": c["id"], "title": c["title"], "updated": c["updated"],
                              "n": len(c["messages"])})
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(convs, key=lambda c: -c["updated"])

    def delete(self, cid: str) -> None:
        p = self._path(cid)
        if p.exists():
            p.unlink()


class Chatbot:
    def __init__(self, rag: GraphRAG, llm: BaseLLM, store: ConversationStore | None = None):
        self.rag, self.llm = rag, llm
        self.store = store or ConversationStore()

    # ---------- định tuyến ----------
    @staticmethod
    def route(message: str, mode: str, focus: list[str]) -> str:
        if mode in ("chat", "research"):
            return mode
        if focus:
            return "research"
        if CHITCHAT_RE.match(message) and len(message.split()) <= 8:
            return "chat"
        return "research"

    def _history(self, conv: dict) -> list[dict]:
        msgs = [{"role": m["role"], "content": m["content"]} for m in conv["messages"] if m["content"]]
        return msgs[-HISTORY_TURNS * 2:]

    def _condense(self, question: str, history: list[dict]) -> str:
        """Viết lại câu hỏi thành truy vấn tiếng Anh độc lập (kho bài báo là tiếng Anh)."""
        if not self.llm.available:
            return question
        convo = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-4:])
        out = self.llm.complete(CONDENSE_SYSTEM,
                                [{"role": "user", "content": f"Hội thoại:\n{convo}\n\nCâu hỏi cuối: {question}"}],
                                effort="low", max_tokens=120).strip().strip('"')
        return out if 3 <= len(out) <= 400 and not out.startswith("*(") else question

    # ---------- trả lời ----------
    def respond(self, message: str, conversation_id: str | None = None, mode: str = "auto",
                focus_ids: list[str] | None = None) -> Iterator[dict]:
        conv = (self.store.get(conversation_id) if conversation_id else None) or self.store.create()
        if not conv["messages"]:
            conv["title"] = message[:60]
        if focus_ids is not None:
            conv["focus"] = focus_ids
        focus = conv.get("focus") or []
        history = self._history(conv)
        route = self.route(message, mode, focus)
        yield {"type": "meta", "conversation_id": conv["id"], "mode": route, "title": conv["title"],
               "llm": self.llm.name}

        conv["messages"].append({"role": "user", "content": message, "mode": route, "ts": time.time(),
                                 "focus": focus})
        answer, sources_pub, graph = "", [], None

        if route == "chat":
            if self.llm.available:
                for t in self.llm.stream(CHAT_SYSTEM, history + [{"role": "user", "content": message + language_reminder(message)}],
                                         effort="low"):
                    answer += t
                    yield {"type": "token", "text": t}
            else:
                answer = ("Xin chào! Mình là **ScholarLens** — trợ lý tìm kiếm và hỏi đáp bài báo arXiv. "
                          "Hiện chưa cấu hình LLM nên chế độ Chat chỉ trả lời mẫu; hãy chuyển sang **Research** "
                          "để tìm kiếm và trích dẫn từ kho bài báo, hoặc kéo-thả file PDF để thêm bài mới.")
                yield {"type": "token", "text": answer}
        else:
            yield {"type": "status", "text": "Đang phân tích câu hỏi…"}
            query = self._condense(message, history) if (history or self.llm.available) else message
            if query != message:
                yield {"type": "query", "text": query}
            yield {"type": "status", "text": "Đang tìm kiếm lai (BM25 + vector) và mở rộng trên đồ thị…"}
            ctx = self.rag.retrieve(query + ("" if query == message else " " + message), focus_ids=focus or None)
            sources_pub = [s.to_public() for s in ctx.sources]
            graph = ctx.subgraph
            yield {"type": "sources", "sources": sources_pub, "graph": graph, "facts": ctx.facts}
            if not ctx.sources:
                answer = "Kho dữ liệu chưa có bài báo nào phù hợp với câu hỏi này. Bạn có thể thêm PDF để mở rộng kho."
                yield {"type": "token", "text": answer}
            elif self.llm.available:
                yield {"type": "status", "text": f"Đang tổng hợp câu trả lời từ {len(ctx.sources)} nguồn…"}
                msgs = history + [{"role": "user", "content": research_user_message(message, ctx.to_prompt())
                                    + language_reminder(message)}]
                for t in self.llm.stream(RESEARCH_SYSTEM, msgs, effort="medium"):
                    answer += t
                    yield {"type": "token", "text": t}
                if answer.strip().startswith("*("):  # LLM không phản hồi -> vẫn trả lời bằng trích đoạn
                    fallback = "\n\n" + extractive_answer(query, ctx)
                    answer += fallback
                    yield {"type": "token", "text": fallback}
            else:
                answer = extractive_answer(query, ctx)
                yield {"type": "token", "text": answer}

        conv["messages"].append({"role": "assistant", "content": answer, "mode": route, "ts": time.time(),
                                 "sources": sources_pub, "graph": graph})
        self.store.save(conv)
        yield {"type": "done", "conversation_id": conv["id"]}


def _best_sentences(text: str, query: str, n: int = 2) -> str:
    q = set(tokenize(query))
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 30 < len(s.strip()) < 600]
    if not sents:
        return text[:300]
    ranked = sorted(sents, key=lambda s: -len(q & set(tokenize(s))))
    keep = set(ranked[:n])
    return " ".join(s for s in sents if s in keep)


def extractive_answer(query: str, ctx) -> str:
    """Câu trả lời không cần LLM: trích các câu khớp nhất từ mỗi nguồn + danh sách bài liên quan."""
    main = [s for s in ctx.sources if s.role in ("focus", "retrieved")]
    related = [s for s in ctx.sources if s.role == "related"]
    lines = ["*(Chưa kết nối LLM nên đây là các câu trích nguyên văn từ bài báo (tiếng Anh). "
             "Bấm nút LLM cạnh ô chat để kết nối — câu trả lời sẽ được viết bằng tiếng Việt.)*", ""]
    if main:
        lines.append("### Thông tin liên quan nhất")
        for s in main[:5]:
            best = sorted(s.excerpts, key=lambda e: -len(set(tokenize(query)) & set(tokenize(e["text"]))))
            body = best[0]["text"].split("\n\n", 1)[-1]  # chunk tóm tắt bắt đầu bằng tiêu đề
            lines.append(f"- **{s.paper['title']}** ({s.paper['year'] or 'n.d.'}): "
                         f"{_best_sentences(body, query)} [{s.n}]")
    if related:
        lines += ["", "### Bài báo liên quan (từ đồ thị tri thức)"]
        for s in related[:8]:
            lines.append(f"- **{s.paper['title']}** ({s.paper['year'] or 'n.d.'}) — {'; '.join(s.reasons[:3])} [{s.n}]")
    if ctx.facts:
        lines += ["", "### Quan hệ trên đồ thị"] + [f"- {f}" for f in ctx.facts[:6]]
    return "\n".join(lines)
