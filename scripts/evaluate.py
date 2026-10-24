"""Đánh giá ScholarLens trên kho dữ liệu hiện có.

1. Truy xuất "known-item": truy vấn = tiêu đề bài, kho = abstract (KHÔNG chứa tiêu đề) -> bài đúng là chính nó.
   So sánh BM25 / Dense / Hybrid-RRF với nhiều model embedding. Độ đo: Recall@1/5/10, MRR@10.
2. Kiểm tra trùng: biến đổi tiêu đề (chữ thường, bỏ dấu câu, bỏ 1 từ, thêm hậu tố) -> tỉ lệ phát hiện đúng;
   tiêu đề của bài KHÔNG có trong kho -> tỉ lệ báo trùng nhầm.
3. Đồ thị: tỉ lệ bài liên quan (top-5) cùng primary category, so với chọn ngẫu nhiên.

  python scripts/evaluate.py --n 500 --models intfloat/multilingual-e5-base BAAI/bge-base-en-v1.5
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scholarlens.config import settings  # noqa: E402
from scholarlens.graph import KnowledgeGraph  # noqa: E402
from scholarlens.retrieval.hybrid import rrf  # noqa: E402
from scholarlens.store import MetadataDB  # noqa: E402
from scholarlens.utils import tokenize  # noqa: E402


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    r = lambda k: sum(1 for x in ranks if x is not None and x <= k) / n
    mrr = sum(1 / x for x in ranks if x is not None and x <= 10) / n
    return {"R@1": round(r(1), 4), "R@5": round(r(5), 4), "R@10": round(r(10), 4), "MRR@10": round(mrr, 4)}


def rank_of(target: int, order) -> int | None:
    pos = np.where(np.asarray(order[:100]) == target)[0]
    return int(pos[0]) + 1 if len(pos) else None


def eval_retrieval(papers: list[dict], models: list[str]) -> dict:
    docs = [p["abstract"] for p in papers]
    queries = [p["title"] for p in papers]
    out = {}
    t0 = time.time()
    bm25 = BM25Okapi([tokenize(d) or ["_"] for d in docs])
    bm_orders = [np.argsort(-bm25.get_scores(tokenize(q)))[:100] for q in queries]
    out["BM25"] = metrics([rank_of(i, o) for i, o in enumerate(bm_orders)])
    out["BM25"]["ms_per_query"] = round((time.time() - t0) * 1000 / len(queries), 2)

    from scholarlens.embedding.embedder import Embedder
    for m in [m for m in models if m.lower() != "none"]:
        emb = Embedder(m)
        t0 = time.time()
        D = emb.encode_docs(docs, show_progress=True)
        Q = np.stack([emb.encode_query(q) for q in queries])
        dt = time.time() - t0
        S = Q @ D.T
        d_orders = [np.argsort(-row)[:100] for row in S]
        short = m.split("/")[-1]
        out[f"Dense ({short})"] = metrics([rank_of(i, o) for i, o in enumerate(d_orders)])
        out[f"Dense ({short})"]["encode_s"] = round(dt, 1)
        h_ranks = []
        for i, (do, bo) in enumerate(zip(d_orders, bm_orders)):
            fused = rrf([list(map(int, do[:50])), list(map(int, bo[:50]))])
            order = sorted(fused, key=lambda d: -fused[d])
            h_ranks.append(rank_of(i, order))
        out[f"Hybrid RRF ({short})"] = metrics(h_ranks)
        del emb
    return out


def mutate(title: str, rng: random.Random) -> str:
    w = title.split()
    kind = rng.choice(["lower", "punct", "drop", "suffix"])
    if kind == "lower":
        return title.lower()
    if kind == "punct":
        return title.replace(":", "").replace("-", " ").replace(",", "")
    if kind == "drop" and len(w) > 6:
        w.pop(rng.randrange(1, len(w) - 1))
        return " ".join(w)
    return title + " (Extended Version)"


def eval_dedup(db: MetadataDB, papers: list[dict], rng: random.Random) -> dict:
    sample = rng.sample(papers, min(200, len(papers)))
    hit = sum(1 for p in sample if (d := db.find_duplicate(title=mutate(p["title"], rng))) and d[0] == p["paper_id"])
    exact_id = sum(1 for p in sample if db.find_duplicate(arxiv_id=p["arxiv_id"]))
    fake = [f"{a['title'].split(':')[0]} for {b['title'].split()[-1]} Revisited"
            for a, b in zip(sample, reversed(sample))]
    adv_fp = sum(1 for t in fake if db.find_duplicate(title=t))
    # thực tế: mỗi bài thật có bị nhận nhầm là bản trùng của một bài KHÁC trong kho không?
    allp = list(db.iter_papers())
    real_fp = [(p["title"], d) for p in allp if (d := db.find_duplicate(title=p["title"], exclude=p["paper_id"]))]
    return {"n": len(sample), "detect_by_id": round(exact_id / len(sample), 4),
            "detect_mutated_title": round(hit / len(sample), 4),
            "false_positive_real_titles": round(len(real_fp) / len(allp), 4), "n_real": len(allp),
            "real_fp_examples": [f"{t[:70]} ~ {d[0]} ({d[1]})" for t, d in real_fp[:5]],
            "false_positive_adversarial": round(adv_fp / len(fake), 4)}


def eval_graph(kg: KnowledgeGraph, papers: list[dict], rng: random.Random) -> dict | None:
    if kg.g.number_of_nodes() == 0:
        return None  # chưa build graph
    cat = {p["paper_id"]: p["primary_category"] for p in papers}
    same, total, with_rel = 0, 0, 0
    for p in papers:
        rel = kg.related_papers(p["paper_id"], k=5)
        if rel:
            with_rel += 1
        for r in rel:
            if r["paper_id"] in cat:
                total += 1
                same += cat[r["paper_id"]] == p["primary_category"]
    ids = list(cat)
    base = sum(cat[rng.choice(ids)] == cat[i] for i in ids for _ in range(5)) / (5 * len(ids))
    return {"papers_with_related": round(with_rel / len(papers), 4),
            "same_category@5": round(same / max(total, 1), 4), "random_baseline": round(base, 4),
            **kg.stats()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--models", nargs="+", default=[settings.embed_model],
                    help="'none' = chỉ BM25 (không cần embedding)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "reports" / "eval_results.json"))
    a = ap.parse_args()
    rng = random.Random(42)
    db = MetadataDB()
    papers = [p for p in db.iter_papers() if len(p["abstract"]) > 200 and len(p["title"]) > 10]
    papers = rng.sample(papers, min(a.n, len(papers)))
    print(f"Đánh giá trên {len(papers)} bài")
    res = {"n_papers": len(papers), "retrieval": eval_retrieval(papers, a.models),
           "dedup": eval_dedup(db, papers, rng), "graph": eval_graph(KnowledgeGraph(), papers, rng)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
