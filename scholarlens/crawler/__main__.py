"""CLI crawl dữ liệu arXiv (chạy độc lập).

Ví dụ:
  python -m scholarlens.crawler keyword "retrieval augmented generation" --max 200
  python -m scholarlens.crawler keyword '"graph neural network"' --category cs.LG --pdf --max 50
  python -m scholarlens.crawler category cs.IR,cs.CL --from 2025-01-01 --to 2025-06-30 --max 500
  python -m scholarlens.crawler ids 1706.03762 2005.11401 --pdf
  python -m scholarlens.crawler snapshot /kaggle/input/arxiv/arxiv-metadata-oai-snapshot.json --categories cs.IR cs.CL --year-from 2023 --limit 20000
"""
import argparse

from .arxiv_client import Crawler


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.crawler", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="file JSONL đầu ra (mặc định data/raw/metadata.jsonl)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keyword", help="crawl theo từ khoá")
    k.add_argument("keyword")
    k.add_argument("--category")
    c = sub.add_parser("category", help="crawl độc lập theo category / khoảng ngày")
    c.add_argument("category")
    for p in (k, c):
        p.add_argument("--from", dest="date_from")
        p.add_argument("--to", dest="date_to")
        p.add_argument("--max", type=int, default=100)
        p.add_argument("--pdf", action="store_true", help="tải cả file PDF")

    i = sub.add_parser("ids", help="crawl theo danh sách arXiv ID")
    i.add_argument("ids", nargs="+")
    i.add_argument("--pdf", action="store_true")

    s = sub.add_parser("snapshot", help="nạp từ Kaggle arXiv metadata snapshot")
    s.add_argument("path")
    s.add_argument("--categories", nargs="*")
    s.add_argument("--year-from", type=int, default=0)
    s.add_argument("--limit", type=int, default=10000)

    a = ap.parse_args()
    from pathlib import Path
    cr = Crawler(Path(a.out) if a.out else None)
    if a.cmd == "keyword":
        cr.crawl(keyword=a.keyword, category=a.category, date_from=a.date_from,
                 date_to=a.date_to, max_results=a.max, download_pdf=a.pdf)
    elif a.cmd == "category":
        cr.crawl(category=a.category, date_from=a.date_from, date_to=a.date_to,
                 max_results=a.max, download_pdf=a.pdf)
    elif a.cmd == "ids":
        cr.crawl_ids(a.ids, download_pdf=a.pdf)
    else:
        cr.from_kaggle_snapshot(a.path, a.categories, a.year_from, a.limit)


if __name__ == "__main__":
    main()
