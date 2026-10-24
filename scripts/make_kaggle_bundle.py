"""Đóng gói dự án thành 1 file zip để tải lên Kaggle Datasets.

  python scripts/make_kaggle_bundle.py              # chỉ mã nguồn  -> dist/scholarlens-code.zip
  python scripts/make_kaggle_bundle.py --with-data  # + data/ đã crawl/đăng ký (để embedding trên Kaggle)

Trên Kaggle: Datasets -> New Dataset -> kéo file zip vào -> đặt tên "scholarlens-code" -> Create.
Kaggle tự giải nén; notebook tìm thư mục chứa `scholarlens/` trong /kaggle/input.
"""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["scholarlens", "scripts", "notebooks", "requirements.txt", "requirements-app.txt", "README.md",
           ".env.example"]
SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints"}
# phần dữ liệu sinh lại được hoặc chỉ dùng ở máy demo
SKIP_DATA = {"chroma", "uploads", "conversations", "llm_server"}
SKIP_FILES = {"llm_config.json", "graph.json"}


def add_tree(z: zipfile.ZipFile, path: Path, skip_dirs: set[str], skip_files: set[str] = frozenset()) -> int:
    n = 0
    if path.is_file():
        z.write(path, path.relative_to(ROOT).as_posix())
        return 1
    for p in sorted(path.rglob("*")):
        rel = p.relative_to(ROOT)
        if any(part in skip_dirs for part in rel.parts) or p.name in skip_files or p.suffix in (".pyc",):
            continue
        if p.is_file():
            z.write(p, rel.as_posix())
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-data", action="store_true")
    a = ap.parse_args()
    out = ROOT / "dist" / ("scholarlens-code-data.zip" if a.with_data else "scholarlens-code.zip")
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        n = sum(add_tree(z, ROOT / x, SKIP_DIRS) for x in INCLUDE if (ROOT / x).exists())
        if a.with_data:
            # checkpoint WAL vào file chính trước khi nén
            import sqlite3
            db = ROOT / "data" / "scholarlens.sqlite"
            if db.exists():
                c = sqlite3.connect(db)
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.close()
            n += add_tree(z, ROOT / "data", SKIP_DIRS | SKIP_DATA,
                          SKIP_FILES | {"scholarlens.sqlite-wal", "scholarlens.sqlite-shm"})
    print(f"{out}  ({n} file, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
