"""Tải 4 PDF dùng để demo thao tác "thêm bài" (không có sẵn trong kho) vào demo_pdfs/.

  python scripts/download_demo_pdfs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scholarlens.crawler import ArxivClient  # noqa: E402

DEMO_IDS = {
    "2404.16130": "From Local to Global: A Graph RAG Approach (GraphRAG)",
    "2312.10997": "Retrieval-Augmented Generation for LLMs: A Survey",
    "2410.05779": "LightRAG: Simple and Fast Retrieval-Augmented Generation",
    "2501.09136": "Agentic Retrieval-Augmented Generation: A Survey",
}


def main():
    out = ROOT / "demo_pdfs"
    client = ArxivClient()
    for paper in client.fetch_by_ids(list(DEMO_IDS)):
        path = client.download_pdf(paper, out)
        print(("OK   " if path else "LỖI ") + f"{paper.arxiv_id}  {paper.title[:70]}")


if __name__ == "__main__":
    main()
