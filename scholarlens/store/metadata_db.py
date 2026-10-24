"""Kho metadata quan hệ (SQLite): bảng papers, chunks, trạng thái pipeline, kiểm tra trùng lặp."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterator

from ..config import settings
from ..utils import normalize_title, title_near_duplicate

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id         TEXT PRIMARY KEY,      -- arXiv ID không version, hoặc 'local:<sha12>'
    arxiv_id         TEXT,
    version          TEXT,
    title            TEXT NOT NULL,
    title_norm       TEXT NOT NULL,
    authors          TEXT DEFAULT '[]',     -- JSON list
    abstract         TEXT DEFAULT '',
    categories       TEXT DEFAULT '[]',     -- JSON list
    primary_category TEXT DEFAULT '',
    published        TEXT DEFAULT '',
    updated          TEXT DEFAULT '',
    year             INTEGER DEFAULT 0,
    doi              TEXT DEFAULT '',
    journal_ref      TEXT DEFAULT '',
    pdf_url          TEXT DEFAULT '',
    pdf_path         TEXT DEFAULT '',
    file_sha256      TEXT DEFAULT '',
    source           TEXT DEFAULT 'crawl',  -- crawl | upload | snapshot
    has_fulltext     INTEGER DEFAULT 0,
    refs             TEXT DEFAULT '[]',     -- arXiv ID được trích dẫn trong toàn văn
    keywords         TEXT DEFAULT '[]',
    status           TEXT DEFAULT 'registered', -- registered -> embedded -> graphed
    n_chunks         INTEGER DEFAULT 0,
    added_at         REAL
);
CREATE INDEX IF NOT EXISTS ix_papers_title_norm ON papers(title_norm);
CREATE INDEX IF NOT EXISTS ix_papers_sha ON papers(file_sha256);
CREATE INDEX IF NOT EXISTS ix_papers_arxiv ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS ix_papers_status ON papers(status);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,             -- <paper_id>::<idx>
    paper_id  TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    idx       INTEGER NOT NULL,
    kind      TEXT DEFAULT 'body',          -- summary (tiêu đề + abstract) | body
    section   TEXT DEFAULT '',
    page      INTEGER DEFAULT 0,
    text      TEXT NOT NULL,
    embedded  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_chunks_paper ON chunks(paper_id);
CREATE INDEX IF NOT EXISTS ix_chunks_embedded ON chunks(embedded);
"""

JSON_COLS = ("authors", "categories", "refs", "keywords")
PAPER_COLS = ("paper_id", "arxiv_id", "version", "title", "title_norm", "authors", "abstract",
              "categories", "primary_category", "published", "updated", "year", "doi",
              "journal_ref", "pdf_url", "pdf_path", "file_sha256", "source", "has_fulltext",
              "refs", "keywords", "status", "n_chunks", "added_at")


class MetadataDB:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or settings.sqlite_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    # ---------- chuyển đổi ----------
    @staticmethod
    def _row_to_paper(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for c in JSON_COLS:
            d[c] = json.loads(d.get(c) or "[]")
        return d

    # ---------- kiểm tra trùng ----------
    def find_duplicate(self, *, arxiv_id: str = "", sha256: str = "", title: str = "",
                       threshold: float | None = None, exclude: str = "") -> tuple[str, str] | None:
        """Trả về (paper_id, lý do) nếu bài đã tồn tại, ngược lại None.

        Thứ tự kiểm tra: arXiv ID -> SHA-256 file -> tiêu đề chuẩn hoá -> tiêu đề gần đúng.
        """
        threshold = threshold or settings.dedup_title_threshold
        with self.lock:
            cur = self.conn.cursor()
            if arxiv_id:
                r = cur.execute("SELECT paper_id FROM papers WHERE arxiv_id=? OR paper_id=?",
                                (arxiv_id, arxiv_id)).fetchone()
                if r:
                    return r[0], f"trùng arXiv ID {arxiv_id}"
            if sha256:
                r = cur.execute("SELECT paper_id FROM papers WHERE file_sha256=?", (sha256,)).fetchone()
                if r:
                    return r[0], "trùng nội dung file (SHA-256)"
            norm = normalize_title(title)
            if len(norm) >= 12:
                r = cur.execute("SELECT paper_id FROM papers WHERE title_norm=? AND paper_id<>?",
                                (norm, exclude)).fetchone()
                if r:
                    return r[0], "trùng tiêu đề"
                # fuzzy: chỉ so với các tiêu đề cùng tiền tố để giữ tốc độ
                for pid, t in cur.execute("SELECT paper_id, title FROM papers WHERE title_norm LIKE ? "
                                          "AND paper_id<>?", (norm[:6] + "%", exclude)):
                    dup, s = title_near_duplicate(title, t, threshold)
                    if dup:
                        return pid, f"tiêu đề gần trùng ({s:.2f})"
        return None

    # ---------- ghi ----------
    def upsert_paper(self, paper: dict) -> None:
        p = {c: paper.get(c) for c in PAPER_COLS}
        p["title_norm"] = normalize_title(p["title"] or "")
        p["added_at"] = p["added_at"] or time.time()
        for c in JSON_COLS:
            p[c] = json.dumps(p[c] or [], ensure_ascii=False)
        defaults = {"version": "", "abstract": "", "primary_category": "", "published": "",
                    "updated": "", "year": 0, "doi": "", "journal_ref": "", "pdf_url": "",
                    "pdf_path": "", "file_sha256": "", "source": "crawl", "has_fulltext": 0,
                    "status": "registered", "n_chunks": 0, "arxiv_id": ""}
        for k, v in defaults.items():
            if p[k] is None:
                p[k] = v
        cols = ",".join(PAPER_COLS)
        qs = ",".join("?" for _ in PAPER_COLS)
        upd = ",".join(f"{c}=excluded.{c}" for c in PAPER_COLS if c not in ("paper_id", "added_at"))
        with self.lock, self.conn:
            self.conn.execute(f"INSERT INTO papers ({cols}) VALUES ({qs}) "
                              f"ON CONFLICT(paper_id) DO UPDATE SET {upd}",
                              [p[c] for c in PAPER_COLS])

    def replace_chunks(self, paper_id: str, chunks: list[dict]) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM chunks WHERE paper_id=?", (paper_id,))
            self.conn.executemany(
                "INSERT INTO chunks (chunk_id, paper_id, idx, kind, section, page, text) "
                "VALUES (?,?,?,?,?,?,?)",
                [(f"{paper_id}::{c['idx']}", paper_id, c["idx"], c.get("kind", "body"),
                  c.get("section", ""), c.get("page", 0), c["text"]) for c in chunks])
            self.conn.execute("UPDATE papers SET n_chunks=? WHERE paper_id=?", (len(chunks), paper_id))

    def set_status(self, paper_ids: list[str], status: str) -> None:
        with self.lock, self.conn:
            self.conn.executemany("UPDATE papers SET status=? WHERE paper_id=?",
                                  [(status, p) for p in paper_ids])

    def set_keywords(self, paper_id: str, keywords: list[str]) -> None:
        with self.lock, self.conn:
            self.conn.execute("UPDATE papers SET keywords=? WHERE paper_id=?",
                              (json.dumps(keywords, ensure_ascii=False), paper_id))

    def mark_chunks_embedded(self, chunk_ids: list[str]) -> None:
        with self.lock, self.conn:
            self.conn.executemany("UPDATE chunks SET embedded=1 WHERE chunk_id=?",
                                  [(c,) for c in chunk_ids])

    def delete_paper(self, paper_id: str) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM chunks WHERE paper_id=?", (paper_id,))
            self.conn.execute("DELETE FROM papers WHERE paper_id=?", (paper_id,))

    # ---------- đọc ----------
    def get_paper(self, paper_id: str) -> dict | None:
        with self.lock:
            return self._row_to_paper(self.conn.execute(
                "SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone())

    def get_papers(self, paper_ids: list[str]) -> dict[str, dict]:
        if not paper_ids:
            return {}
        out = {}
        with self.lock:
            for i in range(0, len(paper_ids), 500):
                part = paper_ids[i:i + 500]
                q = ",".join("?" for _ in part)
                for r in self.conn.execute(f"SELECT * FROM papers WHERE paper_id IN ({q})", part):
                    out[r["paper_id"]] = self._row_to_paper(r)
        return out

    def list_papers(self, q: str = "", limit: int = 50, offset: int = 0,
                    order: str = "added_at DESC") -> list[dict]:
        sql, args = "SELECT * FROM papers", []
        if q:
            sql += " WHERE title LIKE ? OR authors LIKE ? OR paper_id LIKE ?"
            args = [f"%{q}%"] * 3
        sql += f" ORDER BY {order} LIMIT ? OFFSET ?"
        with self.lock:
            return [self._row_to_paper(r) for r in self.conn.execute(sql, args + [limit, offset])]

    def iter_papers(self, status: str | None = None) -> Iterator[dict]:
        sql = "SELECT * FROM papers" + (" WHERE status=?" if status else "")
        with self.lock:
            rows = self.conn.execute(sql, (status,) if status else ()).fetchall()
        for r in rows:
            yield self._row_to_paper(r)

    def pending_chunks(self, limit: int = 2048, paper_ids: list[str] | None = None) -> list[dict]:
        sql = ("SELECT c.chunk_id, c.paper_id, c.idx, c.kind, c.section, c.page, c.text, "
               "p.title, p.year, p.primary_category FROM chunks c JOIN papers p USING(paper_id) "
               "WHERE c.embedded=0")
        args: list = []
        if paper_ids:
            sql += f" AND c.paper_id IN ({','.join('?' for _ in paper_ids)})"
            args += paper_ids
        sql += " ORDER BY c.paper_id, c.idx LIMIT ?"
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args + [limit])]

    def chunks_of(self, paper_id: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM chunks WHERE paper_id=? ORDER BY idx", (paper_id,))]

    def get_chunks(self, chunk_ids: list[str]) -> dict[str, dict]:
        out = {}
        with self.lock:
            for i in range(0, len(chunk_ids), 500):
                part = chunk_ids[i:i + 500]
                q = ",".join("?" for _ in part)
                for r in self.conn.execute(f"SELECT * FROM chunks WHERE chunk_id IN ({q})", part):
                    out[r["chunk_id"]] = dict(r)
        return out

    def all_chunks(self) -> list[tuple[str, str, str]]:
        """(chunk_id, paper_id, text) của mọi chunk đã embedding — dùng dựng chỉ mục BM25."""
        with self.lock:
            return [tuple(r) for r in self.conn.execute(
                "SELECT chunk_id, paper_id, text FROM chunks WHERE embedded=1")]

    def papers_citing(self, arxiv_id: str) -> list[str]:
        with self.lock:
            return [r[0] for r in self.conn.execute(
                "SELECT paper_id FROM papers WHERE refs LIKE ?", (f'%"{arxiv_id}"%',))]

    def stats(self) -> dict:
        with self.lock:
            c = self.conn
            return {
                "papers": c.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
                "fulltext": c.execute("SELECT COUNT(*) FROM papers WHERE has_fulltext=1").fetchone()[0],
                "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "embedded_chunks": c.execute("SELECT COUNT(*) FROM chunks WHERE embedded=1").fetchone()[0],
                "by_status": dict(c.execute("SELECT status, COUNT(*) FROM papers GROUP BY status").fetchall()),
                "top_categories": c.execute(
                    "SELECT primary_category, COUNT(*) n FROM papers GROUP BY primary_category "
                    "ORDER BY n DESC LIMIT 8").fetchall(),
            }
