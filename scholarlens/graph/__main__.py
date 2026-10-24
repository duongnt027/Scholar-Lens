"""CLI đồ thị tri thức.

  python -m scholarlens.graph build              # dựng lại toàn bộ từ SQLite + ChromaDB
  python -m scholarlens.graph stats
  python -m scholarlens.graph related 2005.11401 # bài liên quan + lý do
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.graph", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("stats")
    r = sub.add_parser("related")
    r.add_argument("paper_id")
    r.add_argument("-k", type=int, default=8)
    a = ap.parse_args()

    from ..store import MetadataDB, VectorStore
    from .builder import build_graph
    from .knowledge_graph import KnowledgeGraph

    if a.cmd == "build":
        kg = build_graph(MetadataDB(), VectorStore())
    else:
        kg = KnowledgeGraph()
    if a.cmd in ("build", "stats"):
        print(json.dumps(kg.stats(), indent=2, ensure_ascii=False))
    else:
        for x in kg.related_papers(a.paper_id, a.k):
            print(f"{x['score']:.3f}  {x['paper_id']:<12} {x['title'][:70]}\n        ↳ {'; '.join(x['reasons'])}")


if __name__ == "__main__":
    main()
