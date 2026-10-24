# ScholarLens

Hệ thống truy xuất thông tin và hỏi đáp cho bài báo khoa học **arXiv**: tìm kiếm lai (BM25 + vector), đồ thị tri thức (Graph RAG) và chatbot trả lời có trích dẫn. Mini-project học phần *Khai phá dữ liệu và Học máy*.

- Hỏi bằng tiếng Việt hoặc tiếng Anh trên kho bài báo tiếng Anh (embedding đa ngôn ngữ `multilingual-e5-base`).
- Thêm PDF bằng kéo-thả. Hệ thống tự kiểm tra trùng (SHA-256 → mã arXiv → tiêu đề gần giống), tra metadata trên arXiv, chia đoạn, embedding và cập nhật đồ thị.
- Câu trả lời có trích dẫn `[n]` tới đúng bài; xem được bài liên quan kèm lý do (trích dẫn, cùng tác giả, cùng khái niệm, nội dung tương đồng) trên đồ thị.
- LLM mã nguồn mở (Qwen2.5) tự host bằng **vLLM** trên GPU Kaggle, public qua **Cloudflare Tunnel**. Hệ thống vẫn chạy (chế độ trích đoạn) khi không có LLM.

## Kiến trúc

```
┌────────── Máy GPU (Kaggle 2×T4) ──────────┐            ┌──────── Máy demo (Docker / Python) ────────┐
│ crawl → ingest → embedding → graph        │ ─ data/ ─▶ │ SQLite · ChromaDB · BM25 · đồ thị           │
│ vLLM · Qwen2.5-7B-Instruct-AWQ            │            │ Hybrid search + Graph RAG + chatbot         │
│ cloudflared → https://….trycloudflare.com │ ◀─ HTTPS ─ │ Web app FastAPI  ← trình duyệt người dùng   │
└───────────────────────────────────────────┘            └─────────────────────────────────────────────┘
```

## Chạy nhanh

Hướng dẫn đầy đủ từng bước (Kaggle, Docker, lỗi thường gặp): **[HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md)**.

```bash
pip install -r requirements.txt

# 1. Dữ liệu: crawl → đưa vào kho → embedding (nên chạy trên GPU) → đồ thị
python -m scholarlens.crawler keyword "\"retrieval augmented generation\"" --max 200
python -m scholarlens.ingest all

# 2. App: http://127.0.0.1:7860  (hoặc: docker compose up -d --build)
python -m scholarlens.app

# 3. LLM trên máy GPU (Kaggle: notebooks/kaggle_llm_server.ipynb), rồi dán URL vào dòng "LLM" ở thanh bên của app
VLLM_API_KEY=<khoá-bí-mật> bash scripts/gpu_host_llm.sh
```

PDF để demo thao tác thêm bài: `python scripts/download_demo_pdfs.py` (tải về `demo_pdfs/`).

## Các module

Mỗi module chạy độc lập bằng `python -m scholarlens.<module>`.

| Module | Chức năng |
|---|---|
| `crawler` | Thu thập từ arXiv API theo keyword / category + ngày / mã bài, hoặc từ Kaggle arXiv snapshot |
| `ingest` | Đọc PDF (PyMuPDF), kiểm tra trùng, làm giàu metadata, chia đoạn → SQLite |
| `embedding` | Sinh vector (tự dùng GPU nếu có) → ChromaDB; trích khái niệm cho đồ thị |
| `graph` | Dựng / truy vấn đồ thị tri thức (NetworkX) |
| `chat` | Chatbot dòng lệnh (định tuyến Chat / Research, Graph RAG) |
| `llm_server` | Host LLM Hugging Face bằng vLLM + tunnel trycloudflare + giữ phiên |
| `app` | Web app FastAPI + giao diện chat (streaming, lịch sử, nguồn, đồ thị) |

## Cấu trúc thư mục

```
scholarlens/
  config.py  utils.py  services.py
  crawler/     arxiv_client.py                 # arXiv API, Kaggle snapshot
  ingest/      pdf_parser.py chunker.py pipeline.py
  embedding/   embedder.py pipeline.py         # sentence-transformers, GPU/fp16
  store/       metadata_db.py vector_store.py bm25_index.py
  graph/       knowledge_graph.py keywords.py builder.py
  retrieval/   hybrid.py graph_rag.py          # BM25 + dense + RRF, Graph RAG
  chat/        llm.py prompts.py chatbot.py
  llm_server/  server.py                       # vLLM + cloudflared
  app/         server.py static/
notebooks/     kaggle_llm_server.ipynb  kaggle_pipeline.ipynb
scripts/       evaluate.py  make_kaggle_bundle.py  gpu_host_llm.sh  download_demo_pdfs.py
reports/       BaoCao_LaTeX/  BaoCao_ScholarLens.pdf  CONG_NGHE.md  ScholarLens_edited.pptx/.pdf
Dockerfile  docker-compose.yml  requirements.txt  requirements-app.txt
```

## Tài liệu

- [HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md): cách chạy server và app.
- [reports/CONG_NGHE.md](reports/CONG_NGHE.md): giải thích các công nghệ và phương pháp (cách hoạt động, mục đích sử dụng).
- [reports/BaoCao_ScholarLens.pdf](reports/BaoCao_ScholarLens.pdf): báo cáo (mẫu Đại học Phenikaa). Mã nguồn LaTeX ở
  [reports/BaoCao_LaTeX/](reports/BaoCao_LaTeX/); biên dịch bằng XeLaTeX (Overleaf: Menu → Compiler → XeLaTeX).
- [reports/ScholarLens_edited.pdf](reports/ScholarLens_edited.pdf) / [.pptx](reports/ScholarLens_edited.pptx): slide thuyết trình.

## Đánh giá (492 bài)

| Thành phần | Kết quả |
|---|---|
| Tìm bài theo tiêu đề, BM25 | Recall@1 = 0,957 · MRR@10 = 0,973 |
| Kiểm tra trùng | bắt 95% tiêu đề bị biến đổi, báo nhầm 0% trên tiêu đề thật |
| Đồ thị | 37% bài liên quan cùng chuyên mục (ngẫu nhiên: 14%) |

Chạy lại: `python scripts/evaluate.py --n 500 --models intfloat/multilingual-e5-base BAAI/bge-base-en-v1.5`.

## Cấu hình

Sao chép `.env.example` thành `.env`. Các biến chính:
- `SL_EMBED_MODEL`: model embedding.
- `SL_LLM_PROVIDER` / `SL_LLM_BASE_URL` / `SL_LLM_MODEL` / `SL_LLM_API_KEY`: cấu hình LLM.

Cấu hình LLM đặt từ giao diện được lưu ở `data/llm_config.json` và ghi đè `.env`. Không commit `.env` và thư mục `data/` (đã có trong `.gitignore`).
