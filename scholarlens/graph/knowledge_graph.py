"""Đồ thị tri thức học thuật (NetworkX MultiDiGraph), lưu ra JSON.

Nút:  paper:<id> | author:<tên chuẩn hoá> | category:<cs.IR> | concept:<cụm từ>
Cạnh: CITES (paper->paper), SIMILAR_TO (paper->paper, weight=cosine),
      WRITTEN_BY (paper->author), IN_CATEGORY (paper->category), MENTIONS (paper->concept)
"""
from __future__ import annotations

import json
import math
import threading
from collections import defaultdict
from pathlib import Path

import networkx as nx
import numpy as np

from ..config import settings
from ..utils import normalize_title

CITES, SIMILAR, WROTE, IN_CAT, MENTIONS = "CITES", "SIMILAR_TO", "WRITTEN_BY", "IN_CATEGORY", "MENTIONS"
ENTITY_WEIGHT = {WROTE: 0.6, MENTIONS: 0.45, IN_CAT: 0.05}


def P(pid: str) -> str:
    return f"paper:{pid}"


class KnowledgeGraph:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or settings.graph_path)
        self.g = nx.MultiDiGraph()
        self.lock = threading.RLock()
        if self.path.exists():
            self.load()

    # ---------- lưu / nạp ----------
    def save(self) -> None:
        with self.lock:
            data = {"nodes": [{"id": n, **a} for n, a in self.g.nodes(data=True)],
                    "edges": [{"s": u, "t": v, "k": k, **a} for u, v, k, a in self.g.edges(keys=True, data=True)]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        g = nx.MultiDiGraph()
        for n in data["nodes"]:
            nid = n.pop("id")
            g.add_node(nid, **n)
        for e in data["edges"]:
            g.add_edge(e.pop("s"), e.pop("t"), key=e.pop("k"), **e)
        self.g = g

    # ---------- xây dựng ----------
    def _entity(self, kind: str, label: str) -> str:
        key = normalize_title(label) if kind != "category" else label
        nid = f"{kind}:{key}"
        if nid not in self.g:
            self.g.add_node(nid, type=kind, label=label)
        return nid

    def add_paper(self, paper: dict, similar: list[tuple[str, float]] = (),
                  cited_by: list[str] = ()) -> None:
        pid = paper["paper_id"]
        node = P(pid)
        with self.lock:
            if node in self.g:  # cập nhật: xoá cạnh đi ra cũ
                self.g.remove_edges_from(list(self.g.out_edges(node, keys=True)))
            self.g.add_node(node, type="paper", label=paper["title"], year=paper.get("year") or 0,
                            category=paper.get("primary_category") or "",
                            authors=", ".join(paper.get("authors", [])[:4]))
            for a in paper.get("authors", [])[:15]:
                if a:
                    self.g.add_edge(node, self._entity("author", a), key=WROTE)
            for c in paper.get("categories", [])[:5]:
                if c:
                    self.g.add_edge(node, self._entity("category", c), key=IN_CAT)
            for kw in paper.get("keywords", []):
                self.g.add_edge(node, self._entity("concept", kw), key=MENTIONS)
            for ref in paper.get("refs", []):
                if P(ref) in self.g and ref != pid:
                    self.g.add_edge(node, P(ref), key=CITES)
            for src in cited_by:
                if P(src) in self.g and src != pid:
                    self.g.add_edge(P(src), node, key=CITES)
            for other, score in similar:
                if P(other) in self.g and other != pid:
                    self.g.add_edge(node, P(other), key=SIMILAR, weight=round(float(score), 4))

    def remove_paper(self, pid: str) -> None:
        with self.lock:
            if P(pid) in self.g:
                self.g.remove_node(P(pid))

    def add_similarity_edges(self, ids: list[str], vecs: np.ndarray, top_k: int | None = None,
                             min_score: float | None = None, block: int = 2048) -> int:
        """Cạnh SIMILAR_TO cho toàn bộ kho: top-k láng giềng cosine (ma trận theo khối)."""
        top_k = top_k or settings.similar_top_k
        min_score = settings.similar_min_score if min_score is None else min_score
        n_edges = 0
        with self.lock:
            for u, v, k in [e for e in self.g.edges(keys=True) if e[2] == SIMILAR]:
                self.g.remove_edge(u, v, key=k)
            for i in range(0, len(ids), block):
                sims = vecs[i:i + block] @ vecs.T
                for r, row in enumerate(sims):
                    row[i + r] = -1
                    best = np.argpartition(-row, min(top_k, len(row) - 1))[:top_k]
                    for j in best:
                        if row[j] >= min_score:
                            a, b = P(ids[i + r]), P(ids[j])
                            if not self.g.has_edge(b, a, key=SIMILAR):
                                self.g.add_edge(a, b, key=SIMILAR, weight=round(float(row[j]), 4))
                                n_edges += 1
        return n_edges

    # ---------- truy vấn ----------
    def related_papers(self, pid: str, k: int = 8) -> list[dict]:
        """Xếp hạng bài liên quan qua 1-2 bước nhảy, kèm lý do (giải thích được)."""
        node = P(pid)
        if node not in self.g:
            return []
        score: dict[str, float] = defaultdict(float)
        why: dict[str, list[str]] = defaultdict(list)
        g = self.g
        with self.lock:
            for u, v, key, data in list(g.out_edges(node, keys=True, data=True)) + \
                    list(g.in_edges(node, keys=True, data=True)):
                other = v if u == node else u
                otype = g.nodes[other].get("type")
                if otype == "paper":
                    if key == CITES:
                        score[other] += 1.0
                        why[other].append("bài này trích dẫn" if u == node else "trích dẫn bài này")
                    elif key == SIMILAR:
                        score[other] += data.get("weight", 0.5)
                        why[other].append(f"nội dung tương đồng ({data.get('weight', 0):.2f})")
                else:
                    papers = [p for p, _, kk in g.in_edges(other, keys=True) if kk == key and p != node]
                    deg = len(papers)
                    if deg == 0 or (key == IN_CAT and deg > 300):
                        continue
                    w = ENTITY_WEIGHT.get(key, 0.1) / math.log2(2 + deg)
                    label = g.nodes[other].get("label", "")
                    for p in papers:
                        score[p] += w
                        if key == WROTE:
                            why[p].append(f"cùng tác giả {label}")
                        elif key == MENTIONS:
                            why[p].append(f"cùng khái niệm “{label}”")
            ranked = sorted(score.items(), key=lambda x: -x[1])
            out = []
            for n, s in ranked:
                reasons = [r for r in dict.fromkeys(why[n])]  # bỏ trùng, giữ thứ tự
                if not reasons:  # chỉ chung category -> quá yếu
                    continue
                out.append({"paper_id": n.split(":", 1)[1], "score": round(s, 4), "reasons": reasons[:4],
                            "title": g.nodes[n].get("label", "")})
                if len(out) >= k:
                    break
            return out

    def facts(self, pids: list[str], max_facts: int = 25) -> list[str]:
        """Diễn đạt các cạnh quanh các bài thành câu (đưa vào ngữ cảnh LLM)."""
        out = []
        g = self.g
        pset = {P(p) for p in pids}
        with self.lock:
            for node in pset:
                if node not in g:
                    continue
                t = g.nodes[node].get("label", "")
                concepts = [g.nodes[v]["label"] for _, v, k in g.out_edges(node, keys=True) if k == MENTIONS]
                if concepts:
                    out.append(f"“{t}” bàn về: {', '.join(concepts)}.")
                for _, v, k in g.out_edges(node, keys=True):
                    if k == CITES:
                        out.append(f"“{t}” trích dẫn “{g.nodes[v].get('label', '')}”.")
                for u, _, k in g.in_edges(node, keys=True):
                    if k == CITES:
                        out.append(f"“{g.nodes[u].get('label', '')}” trích dẫn “{t}”.")
        return list(dict.fromkeys(out))[:max_facts]

    def subgraph(self, pids: list[str], related_per_paper: int = 6, max_nodes: int = 90) -> dict:
        """Đồ thị con để trực quan hoá: các bài + bài liên quan + thực thể nối chúng."""
        g = self.g
        with self.lock:
            focus = [P(p) for p in pids if P(p) in g]
            papers = list(dict.fromkeys(focus))
            for p in focus:
                for r in self.related_papers(p.split(":", 1)[1], k=related_per_paper):
                    papers.append(P(r["paper_id"]))
            papers = list(dict.fromkeys(papers))[:max_nodes // 2]
            nodes = set(papers)
            pset = set(papers)
            # thực thể chung của >= 2 bài trong tập (hoặc của bài focus)
            ent_count: dict[str, int] = defaultdict(int)
            for p in papers:
                for _, v, k in g.out_edges(p, keys=True):
                    if k != IN_CAT and g.nodes[v].get("type") != "paper":
                        ent_count[v] += 1 + (p in focus)
            for e, c in sorted(ent_count.items(), key=lambda x: -x[1]):
                if c >= 2 and len(nodes) < max_nodes:
                    nodes.add(e)
            edges = []
            for u, v, k, d in g.edges(keys=True, data=True):
                if u in nodes and v in nodes:
                    edges.append({"from": u, "to": v, "label": k, "weight": d.get("weight")})
            node_list = []
            for n in nodes:
                a = g.nodes[n]
                node_list.append({"id": n, "label": a.get("label", n), "type": a.get("type"),
                                  "year": a.get("year"), "focus": n in focus,
                                  "paper_id": n.split(":", 1)[1] if a.get("type") == "paper" else None})
            return {"nodes": node_list, "edges": edges}

    def overview(self, max_papers: int = 60) -> dict:
        with self.lock:
            papers = [n for n, a in self.g.nodes(data=True) if a.get("type") == "paper"]
            papers.sort(key=lambda n: -self.g.degree(n))
        return self.subgraph([p.split(":", 1)[1] for p in papers[:max_papers]], related_per_paper=0,
                             max_nodes=max_papers * 2)

    def stats(self) -> dict:
        with self.lock:
            types: dict[str, int] = defaultdict(int)
            for _, a in self.g.nodes(data=True):
                types[a.get("type", "?")] += 1
            rels: dict[str, int] = defaultdict(int)
            for _, _, k in self.g.edges(keys=True):
                rels[k] += 1
            return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges(),
                    "node_types": dict(types), "edge_types": dict(rels)}
