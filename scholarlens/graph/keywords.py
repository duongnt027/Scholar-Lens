"""Trích khái niệm (keyphrase) theo kiểu KeyBERT rút gọn:
ứng viên = n-gram (1-3 từ) không chứa stopword -> xếp hạng theo cosine với embedding tài liệu
-> chọn đa dạng bằng Maximal Marginal Relevance (MMR).
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

GENERIC = set("""paper approach method methods model models results result propose proposed show shows
work task tasks performance framework existing new novel using based study problem data experiments
significantly state art outperforms demonstrate effectiveness extensive approach approaches""".split())


def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def normalize_concept(phrase: str) -> str:
    words = phrase.lower().split()
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def candidates(text: str, max_n: int = 3, limit: int = 40) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text)
    low = [t.lower() for t in tokens]
    cands: dict[str, int] = {}
    for n in range(1, max_n + 1):
        for i in range(len(low) - n + 1):
            gram = low[i:i + n]
            if any(g in ENGLISH_STOP_WORDS or g in GENERIC or len(g) < 3 for g in gram):
                continue
            key = normalize_concept(" ".join(gram))
            cands[key] = cands.get(key, 0) + 1
    # ưu tiên cụm nhiều từ & lặp lại
    ranked = sorted(cands, key=lambda c: (-(cands[c] * (1 + 0.5 * c.count(" "))), c))
    return ranked[:limit]


def mmr(doc_vec: np.ndarray, cand_vecs: np.ndarray, cands: list[str], top_n: int, diversity: float = 0.5):
    if not cands:
        return []
    sim_doc = cand_vecs @ doc_vec
    sim_cc = cand_vecs @ cand_vecs.T
    chosen = [int(np.argmax(sim_doc))]
    while len(chosen) < min(top_n, len(cands)):
        rest = [i for i in range(len(cands)) if i not in chosen]
        score = [(1 - diversity) * sim_doc[i] - diversity * max(sim_cc[i, chosen]) for i in rest]
        chosen.append(rest[int(np.argmax(score))])
    return [cands[i] for i in chosen]


def extract_keywords_batch(texts: list[str], embedder, doc_vecs: np.ndarray | None = None,
                           top_n: int = 6) -> list[list[str]]:
    all_cands = [candidates(t) for t in texts]
    flat = sorted({c for cs in all_cands for c in cs})
    if not flat:
        return [[] for _ in texts]
    vecs = embedder.encode_phrases(flat)
    index = {c: i for i, c in enumerate(flat)}
    if doc_vecs is None:
        doc_vecs = embedder.encode_docs(texts)
    out = []
    for cs, dv in zip(all_cands, doc_vecs):
        if not cs:
            out.append([])
            continue
        cv = vecs[[index[c] for c in cs]]
        out.append(mmr(dv, cv, cs, top_n))
    return out
