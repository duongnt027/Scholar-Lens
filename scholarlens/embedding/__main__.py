"""CLI embedding (chạy độc lập, tự dùng GPU nếu có).

  python -m scholarlens.embedding                 # embedding mọi chunk chưa xử lý
  python -m scholarlens.embedding --device cuda --batch-size 128
  python -m scholarlens.embedding --rebuild       # xoá vector cũ, embedding lại toàn bộ
"""
import argparse

from ..config import settings


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.embedding", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default=None, help="auto | cuda | cpu | mps")
    ap.add_argument("--model", default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if a.batch_size:
        settings.embed_batch_size = a.batch_size

    from ..store import MetadataDB, VectorStore
    from .embedder import Embedder
    from .pipeline import embed_pending

    db, vs = MetadataDB(), VectorStore()
    if a.rebuild:
        vs.client.delete_collection("chunks")
        vs.client.delete_collection("papers")
        vs = VectorStore()
        with db.conn:
            db.conn.execute("UPDATE chunks SET embedded=0")
            db.conn.execute("UPDATE papers SET status='registered'")
    Embedder._instance = Embedder(a.model, a.device)
    print(embed_pending(db, vs))
    print(vs.stats())


if __name__ == "__main__":
    main()
