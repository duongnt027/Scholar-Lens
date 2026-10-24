"""CLI nạp dữ liệu vào SQLite (đăng ký + chunking). Thêm --embed / --graph để chạy tiếp các bước sau.

  python -m scholarlens.ingest jsonl data/raw/metadata.jsonl            # bản ghi crawl
  python -m scholarlens.ingest pdf paper1.pdf paper2.pdf --embed --graph
  python -m scholarlens.ingest dir demo_pdfs/ --embed --graph
  python -m scholarlens.ingest all                                      # jsonl mặc định + embed + graph
"""
import argparse
import json
from pathlib import Path

from ..config import settings


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.ingest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("jsonl")
    j.add_argument("path", nargs="?", default=str(settings.raw_dir / "metadata.jsonl"))
    j.add_argument("--no-pdf", action="store_true", help="bỏ qua PDF đã tải, chỉ dùng abstract")
    p = sub.add_parser("pdf")
    p.add_argument("files", nargs="+")
    d = sub.add_parser("dir")
    d.add_argument("folder")
    sub.add_parser("all")
    for x in (j, p, d):
        x.add_argument("--embed", action="store_true")
        x.add_argument("--graph", action="store_true")
        x.add_argument("--no-enrich", action="store_true", help="không tra arXiv API")
    a = ap.parse_args()

    from ..store import MetadataDB, VectorStore
    from .pipeline import register_pdf, register_record

    db = MetadataDB()
    if a.cmd == "all":
        a.path, a.no_pdf, a.embed, a.graph, a.no_enrich = str(settings.raw_dir / "metadata.jsonl"), False, True, True, False
        a.cmd = "jsonl"
    if getattr(a, "no_enrich", False):
        settings.enrich_metadata = False

    counts: dict[str, int] = {}
    if a.cmd == "jsonl":
        with open(a.path, encoding="utf-8") as f:
            for line in f:
                st = register_record(db, json.loads(line), use_pdf=not a.no_pdf)
                counts[st] = counts.get(st, 0) + 1
    else:
        files = a.files if a.cmd == "pdf" else sorted(str(x) for x in Path(a.folder).glob("*.pdf"))
        for fpath in files:
            r = register_pdf(db, fpath, source="upload")
            counts[r.status] = counts.get(r.status, 0) + 1
            print(f"[{r.status:9}] {Path(fpath).name}: {r.title[:70]} {r.reason}")
    print("Kết quả đăng ký:", counts)

    if a.embed or a.graph:
        vs = VectorStore()
        if a.embed:
            from ..embedding.pipeline import embed_pending
            print(embed_pending(db, vs))
        if a.graph:
            from ..graph.builder import build_graph
            print(build_graph(db, vs).stats())
    print(db.stats())


if __name__ == "__main__":
    main()
