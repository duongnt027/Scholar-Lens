"""Client cho arXiv API (Atom feed) + bộ crawl theo keyword / category / khoảng ngày / danh sách ID.

Tài liệu API: https://info.arxiv.org/help/api/user-manual.html
- Mỗi request tối đa 2000 kết quả, nên phân trang theo 100.
- arXiv yêu cầu nghỉ >= 3 giây giữa các request.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import requests

from ..config import settings
from ..utils import get_logger, strip_version, title_similarity

log = get_logger("crawler")
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom",
      "os": "http://a9.com/-/spec/opensearch/1.1/"}
USER_AGENT = "ScholarLens/1.0 (student mini-project; mailto:student@example.com)"


@dataclass
class ArxivPaper:
    arxiv_id: str
    version: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    pdf_url: str
    doi: str = ""
    comment: str = ""
    journal_ref: str = ""
    pdf_path: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(s: str | None) -> str:
    return " ".join((s or "").split())


def parse_feed(xml_text: str) -> tuple[list[ArxivPaper], int]:
    root = ET.fromstring(xml_text)
    total = int(root.findtext("os:totalResults", default="0", namespaces=NS) or 0)
    papers = []
    for e in root.findall("a:entry", NS):
        id_url = e.findtext("a:id", default="", namespaces=NS)
        if "/abs/" not in id_url:  # entry lỗi
            continue
        raw_id = id_url.split("/abs/")[-1]
        vid = strip_version(raw_id)
        version = raw_id[len(vid):] or "v1"
        pdf_url = ""
        for link in e.findall("a:link", NS):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{raw_id}"
        prim = e.find("arxiv:primary_category", NS)
        papers.append(ArxivPaper(
            arxiv_id=vid, version=version,
            title=_clean(e.findtext("a:title", namespaces=NS)),
            abstract=_clean(e.findtext("a:summary", namespaces=NS)),
            authors=[_clean(a.findtext("a:name", namespaces=NS)) for a in e.findall("a:author", NS)],
            categories=[c.get("term", "") for c in e.findall("a:category", NS)],
            primary_category=prim.get("term", "") if prim is not None else "",
            published=e.findtext("a:published", default="", namespaces=NS),
            updated=e.findtext("a:updated", default="", namespaces=NS),
            pdf_url=pdf_url,
            doi=_clean(e.findtext("arxiv:doi", namespaces=NS)),
            comment=_clean(e.findtext("arxiv:comment", namespaces=NS)),
            journal_ref=_clean(e.findtext("arxiv:journal_ref", namespaces=NS)),
        ))
    return papers, total


class ArxivClient:
    def __init__(self, delay: float | None = None):
        self.delay = settings.arxiv_delay if delay is None else delay
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _wait(self):
        dt = time.time() - self._last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last = time.time()

    def _get(self, params: dict, retries: int = 4) -> str:
        for attempt in range(retries):
            self._wait()
            try:
                r = self.session.get(settings.arxiv_api, params=params, timeout=60)
                if r.status_code == 200:
                    return r.text
                log.warning("arXiv HTTP %s, thử lại (%d)", r.status_code, attempt + 1)
            except requests.RequestException as exc:
                log.warning("Lỗi mạng %s, thử lại (%d)", exc, attempt + 1)
            time.sleep(self.delay * (attempt + 2))
        raise RuntimeError("Không gọi được arXiv API")

    # ---------- truy vấn ----------
    @staticmethod
    def build_query(keyword: str | None = None, category: str | None = None,
                    date_from: str | None = None, date_to: str | None = None,
                    title: str | None = None) -> str:
        parts = []
        if keyword:
            # cụm từ trong ngoặc kép => tìm chính xác cả cụm; các từ rời => AND từng từ
            terms = [f'all:"{ph}"' if ph else f"all:{w}"
                     for ph, w in re.findall(r'"([^"]+)"|(\S+)', keyword)]
            parts.append("(" + " AND ".join(terms) + ")")
        if title:
            parts.append(f'ti:"{title}"')
        if category:
            cats = [c.strip() for c in category.split(",") if c.strip()]
            parts.append("(" + " OR ".join(f"cat:{c}" for c in cats) + ")")
        if date_from or date_to:
            f = (date_from or "19910101").replace("-", "") + "0000"
            t = (date_to or "20991231").replace("-", "") + "2359"
            parts.append(f"submittedDate:[{f} TO {t}]")
        return " AND ".join(parts) if parts else "all:*"

    def search(self, query: str, max_results: int = 100, page_size: int = 100,
               sort_by: str = "submittedDate") -> Iterator[ArxivPaper]:
        start = 0
        while start < max_results:
            n = min(page_size, max_results - start)
            xml_text = self._get({"search_query": query, "start": start, "max_results": n,
                                  "sortBy": sort_by, "sortOrder": "descending"})
            papers, total = parse_feed(xml_text)
            log.info("query=%s start=%d nhận %d/%d", query, start, len(papers), total)
            if not papers:
                break
            yield from papers
            start += len(papers)
            if start >= total:
                break

    def fetch_by_ids(self, ids: Iterable[str]) -> list[ArxivPaper]:
        ids = [i for i in ids if i]
        out = []
        for i in range(0, len(ids), 100):
            xml_text = self._get({"id_list": ",".join(ids[i:i + 100]), "max_results": 100})
            out.extend(parse_feed(xml_text)[0])
        return out

    def find_by_title(self, title: str, threshold: float = 0.9) -> ArxivPaper | None:
        """Tra metadata của một bài theo tiêu đề (dùng khi PDF không có arXiv ID)."""
        safe = title.replace('"', " ").replace(":", " ")
        for p in self.search(self.build_query(title=safe), max_results=5, sort_by="relevance"):
            if title_similarity(p.title, title) >= threshold:
                return p
        return None

    def download_pdf(self, paper: ArxivPaper, out_dir: Path, retries: int = 3) -> str:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{paper.arxiv_id.replace('/', '_')}.pdf"
        if path.exists() and path.stat().st_size > 10_000:
            return str(path)
        for attempt in range(retries):
            self._wait()
            try:
                r = self.session.get(paper.pdf_url, timeout=120)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    path.write_bytes(r.content)
                    return str(path)
            except requests.RequestException as exc:
                log.warning("Tải PDF %s lỗi: %s", paper.arxiv_id, exc)
            time.sleep(self.delay * (attempt + 1))
        return ""


class Crawler:
    """Crawl và ghi kết quả vào data/raw/metadata.jsonl (append, không trùng ID)."""

    def __init__(self, out_jsonl: Path | None = None, client: ArxivClient | None = None):
        self.out = out_jsonl or settings.raw_dir / "metadata.jsonl"
        self.client = client or ArxivClient()
        self.seen = self._load_seen()

    def _load_seen(self) -> set[str]:
        seen = set()
        if self.out.exists():
            with open(self.out, encoding="utf-8") as f:
                for line in f:
                    try:
                        seen.add(json.loads(line)["arxiv_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
        return seen

    def _write(self, papers: Iterable[ArxivPaper], download_pdf: bool) -> int:
        n = 0
        self.out.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out, "a", encoding="utf-8") as f:
            for p in papers:
                if p.arxiv_id in self.seen:
                    continue
                if download_pdf:
                    p.pdf_path = self.client.download_pdf(p, settings.pdf_dir)
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
                f.flush()
                self.seen.add(p.arxiv_id)
                n += 1
        log.info("Đã ghi %d bài mới vào %s (tổng %d)", n, self.out, len(self.seen))
        return n

    def crawl(self, keyword: str | None = None, category: str | None = None,
              date_from: str | None = None, date_to: str | None = None,
              max_results: int = 100, download_pdf: bool = False) -> int:
        q = self.client.build_query(keyword, category, date_from, date_to)
        return self._write(self.client.search(q, max_results=max_results), download_pdf)

    def crawl_ids(self, ids: list[str], download_pdf: bool = False) -> int:
        return self._write(self.client.fetch_by_ids(ids), download_pdf)

    def from_kaggle_snapshot(self, snapshot_path: str, categories: list[str] | None = None,
                             year_from: int = 0, limit: int = 10_000) -> int:
        """Đọc file arxiv-metadata-oai-snapshot.json (Kaggle dataset Cornell-University/arxiv)."""
        def gen():
            count = 0
            with open(snapshot_path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    cats = r.get("categories", "").split()
                    if categories and not any(c in categories for c in cats):
                        continue
                    versions = r.get("versions") or [{"created": ""}]
                    created = versions[0].get("created", "")
                    upd = r.get("update_date", "")
                    if year_from and int((upd or "0")[:4] or 0) < year_from:
                        continue
                    authors = [" ".join(x for x in (a[1], a[0]) if x).strip()
                               for a in r.get("authors_parsed", [])] or [r.get("authors", "")]
                    yield ArxivPaper(
                        arxiv_id=r["id"], version=versions[-1].get("version", "v1"),
                        title=_clean(r.get("title")), abstract=_clean(r.get("abstract")),
                        authors=authors, categories=cats, primary_category=cats[0] if cats else "",
                        published=_to_iso(created) or upd, updated=upd,
                        pdf_url=f"https://arxiv.org/pdf/{r['id']}", doi=r.get("doi") or "",
                        comment=_clean(r.get("comments")), journal_ref=_clean(r.get("journal-ref")))
                    count += 1
                    if count >= limit:
                        return
        return self._write(gen(), download_pdf=False)


def _to_iso(created: str) -> str:
    """'Mon, 2 Apr 2007 19:18:42 GMT' -> '2007-04-02T19:18:42Z'."""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.strptime(created, "%a, %d %b %Y %H:%M:%S %Z"))
    except (ValueError, TypeError):
        return ""
