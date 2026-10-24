# Hướng dẫn chạy ScholarLens

Hệ thống gồm hai phần chạy trên hai máy:

| Phần | Chạy ở đâu | Làm gì |
|---|---|---|
| **Server** | Kaggle (GPU 2×T4), hoặc máy Linux có GPU | Chạy mô hình AI (Qwen2.5 qua vLLM), mở địa chỉ công khai `https://….trycloudflare.com`; tuỳ chọn embedding dữ liệu |
| **App** | Máy của bạn (Windows) | Giao diện chat, kho dữ liệu, tìm kiếm, đồ thị, thêm PDF |

Thứ tự mỗi buổi demo: **bật server → bật app → dán URL server vào app**.

---

## Phần 1. Server trên Kaggle

### 1.1. Chuẩn bị (chỉ làm một lần)

1. **Đóng gói mã nguồn** trên máy bạn (mở `cmd` trong thư mục dự án):
   ```bat
   python scripts\make_kaggle_bundle.py --with-data
   ```
   Lệnh tạo file `dist\scholarlens-code-data.zip`. Bỏ `--with-data` nếu chỉ cần chạy LLM, không cần embedding.
2. **Tạo Dataset trên Kaggle:** vào *Datasets → New Dataset*, kéo file zip vào, đặt tên `scholarlens-code`, rồi bấm *Create*.
3. **Tạo Notebook:** vào *Create → New Notebook → File → Import Notebook*, chọn `notebooks\kaggle_llm_server.ipynb`.
4. Trong notebook, bấm *Add Input* và chọn dataset `scholarlens-code`.
5. Vào *Settings*:
   - **Accelerator:** GPU T4 x2
   - **Internet:** On (tài khoản Kaggle phải đã xác minh số điện thoại)
6. Vào *Add-ons → Secrets* và thêm:
   - `VLLM_API_KEY`: một chuỗi bí mật tự đặt, dùng làm mật khẩu của server. Có thể sinh bằng lệnh
     `python -c "import secrets; print('sl-' + secrets.token_hex(16))"`.
   - `HF_TOKEN`: chỉ cần nếu dùng model có giới hạn truy cập (ví dụ Llama).

   Nhớ bật **Attached** cho notebook này.

> Sửa code xong muốn đưa lên Kaggle: chạy lại lệnh đóng gói ở bước 1, mở dataset `scholarlens-code` → *New Version* → tải file zip mới lên, rồi trong notebook cập nhật input lên version mới.

### 1.2. Chạy server (mỗi buổi)

1. Mở notebook, kiểm tra ô cấu hình đầu tiên:
   ```python
   PRESET        = "qwen2.5-7b-awq"   # model; hết VRAM thì đổi "qwen2.5-3b"
   RUN_EMBEDDING = True               # False nếu data đã embedding rồi
   VLLM_VERSION  = ""                 # "" = bản mới nhất; lỗi thì thử "0.29.0"
   ```
2. Bấm **Run All**. Lần đầu mất khoảng 5–10 phút (cài vLLM, tải model).
3. Khi chạy xong, notebook in một bảng gồm:
   - **Base URL:** `https://<ngẫu nhiên>.trycloudflare.com/v1`
   - **API key:** khoá `VLLM_API_KEY` của bạn

   Notebook chỉ in URL sau khi đã gọi thử thành công qua URL đó (DNS có thể mất tới khoảng 1 phút).
4. **Để ô cuối (`keep_alive`) chạy suốt buổi demo** và giữ tab Kaggle mở. Mỗi 2 phút, ô này in một dòng:
   ```
   [15:37:23] vLLM OK · tunnel OK · https://….trycloudflare.com/v1
   ```
   Nếu tunnel chết, nó tự mở tunnel mới và in **URL MỚI**. Khi đó dán URL mới vào app (mục 2.3).
5. Nếu bật `RUN_EMBEDDING`: tải file `scholarlens_data.zip` ở panel phải → *Output*, rồi làm mục 2.1.
6. Demo xong, bấm **Stop session** để không tốn hạn mức GPU. Mỗi phiên dài tối đa khoảng 12 giờ.

### 1.3. Lỗi thường gặp trên Kaggle

| Thông báo | Cách sửa |
|---|---|
| `PyTorch and TorchAudio were compiled with different CUDA versions` | Thêm một ô, chạy `!pip uninstall -y -q torchaudio`, rồi chạy lại ô khởi động server. Bản notebook mới đã tự làm bước này. |
| `vLLM không khởi động được` kèm dòng **GỢI Ý** | Làm theo gợi ý in ra; log đầy đủ ở `data/llm_server/vllm.log` |
| Hết VRAM (`out of memory`) | Đổi `PRESET = "qwen2.5-3b"` → *Restart session* → *Run All* |
| Lỗi liên quan GPU (`no kernel image`, `compute capability`) | Đặt `VLLM_VERSION = "0.29.0"` → *Restart session* → *Run All* |
| `Không thấy mã nguồn` | Chưa *Add Input* dataset `scholarlens-code` |

### 1.4. (Thay thế) Server trên máy Linux có GPU riêng

```bash
pip install -r requirements.txt
VLLM_API_KEY=chuoi-bi-mat bash scripts/gpu_host_llm.sh                 # mặc định qwen2.5-7b-awq
VLLM_API_KEY=chuoi-bi-mat bash scripts/gpu_host_llm.sh --model Qwen/Qwen2.5-3B-Instruct
```
Script in ra URL trycloudflare và API key giống như trên Kaggle. Nhấn `Ctrl+C` để dừng.

---

## Phần 2. App trên máy của bạn

### 2.1. Chuẩn bị dữ liệu

App cần thư mục `data\` **đã embedding**, tức file `scholarlens_data.zip` tải từ Kaggle. Đặt file vào thư mục dự án rồi giải nén vào `data\` (trong `cmd`):
```bat
cd <thư mục dự án>
mkdir data
tar -xf scholarlens_data.zip -C data
```
Thiếu bước này thì app vẫn mở được, nhưng tìm kiếm không ra kết quả.

> Hai máy phải dùng **cùng model embedding** (mặc định `intfloat/multilingual-e5-base`) và **cùng phiên bản `chromadb`** (1.5.9).

### 2.2. Chạy app

**Cách A — Python** (máy đã cài sẵn thư viện):
```bat
pip install -r requirements.txt
python -m scholarlens.app
```
Đợi khoảng 20 giây cho model embedding nạp xong, rồi mở **http://127.0.0.1:7860**. Nhấn `Ctrl+C` trong cửa sổ `cmd` để tắt.

**Cách B — Docker** (máy chỉ cần cài [Docker Desktop](https://www.docker.com/products/docker-desktop/)):
```bat
docker compose up -d --build
```
Lần đầu build mất khoảng 5–10 phút. Mở **http://localhost:7860**.

| Việc | Lệnh |
|---|---|
| Xem log | `docker compose logs -f app` |
| Tắt | `docker compose down` |
| Sửa code xong | `docker compose up -d --build` |

### 2.3. Kết nối app với server

1. Ở **cuối thanh bên trái**, bấm vào dòng **`● LLM: …`**.
2. Dán **Base URL** (`https://….trycloudflare.com/v1`) và **API key** vào hai ô, rồi bấm **Kết nối**.
3. Chấm **xanh** kèm tên model là đã kết nối. Ô nhập tự thu gọn lại.

App lưu cấu hình vào `data\llm_config.json`, lần sau không phải nhập lại. **URL đổi** (Kaggle chạy lại hoặc tunnel mở lại) thì chỉ cần dán URL mới; để trống ô API key thì app giữ khoá cũ.

### 2.4. Sử dụng

| Muốn | Làm |
|---|---|
| Hỏi | Gõ câu hỏi (tiếng Việt hoặc Anh), nhấn Enter |
| Xem nguồn | Bấm `[n]` trong câu trả lời, hoặc dòng **N nguồn** bên dưới |
| Xem đồ thị bài liên quan | Bấm **◎ Đồ thị** dưới câu trả lời; **⤢ Mở rộng** để xem toàn màn hình (Esc để đóng) |
| Thêm bài | Bấm 📎 cạnh ô nhập, hoặc kéo-thả PDF vào cửa sổ (chọn được nhiều file). Bài vừa thêm thành "Đang hỏi về: …" |
| Hỏi về bài vừa thêm | Hỏi tiếp ngay, ví dụ "Tóm tắt bài này", "Các bài liên quan đến bài này?" |
| Bỏ chọn bài | Bấm ✕ ở dòng "Đang hỏi về" |
| Mở lại hội thoại cũ | Bấm vào hội thoại trong mục **Lịch sử** |
| Thu gọn thanh bên | Nút ⊏ cạnh chữ ScholarLens; mở lại bằng nút ⊐ ở góc trên trái |
| Mở thẳng một đồ thị (khi demo) | `http://127.0.0.1:7860/#c=<mã hội thoại>&graph=full` |

Bộ PDF để demo nằm trong thư mục `demo_pdfs\`: GraphRAG, RAG Survey, LightRAG, Agentic RAG. Cả bốn bài **chưa có** trong kho.

### 2.5. Lỗi thường gặp ở app

| Hiện tượng | Nguyên nhân / cách sửa |
|---|---|
| `● LLM: mất kết nối` (chấm đỏ) | Server Kaggle đã tắt hoặc URL đã đổi: xem ô `keep_alive` trên Kaggle, dán URL mới |
| Câu trả lời là các câu tiếng Anh, có dòng *"Chưa kết nối LLM…"* | App chưa kết nối server, đang ở chế độ trích đoạn: làm mục 2.3 |
| Hỏi gì cũng *"Kho dữ liệu chưa có bài báo nào phù hợp"* | `data\` chưa được embedding: làm mục 2.1 |
| Giao diện không đổi sau khi cập nhật code | Nhấn **Ctrl + F5** để tải lại trang |
| `address already in use` / cổng 7860 bận | App đang chạy ở cửa sổ khác: tắt cửa sổ đó, hoặc chạy `python -m scholarlens.app --port 7861` |
| Thêm PDF lâu (khoảng 30 giây) | Bình thường: máy demo embedding bằng CPU |

---

## Phụ lục: các lệnh chạy riêng từng module

Chạy trong thư mục dự án. Dùng khi cần làm lại một bước mà không chạy cả hệ thống.

```bat
:: Thu thập bài từ arXiv
python -m scholarlens.crawler keyword "\"dense retrieval\"" --max 200 --pdf
python -m scholarlens.crawler category cs.IR --from 2025-01-01 --max 500

:: Đưa bài đã crawl vào kho, tạo vector, dựng đồ thị (embedding nên chạy trên GPU)
python -m scholarlens.ingest jsonl
python -m scholarlens.embedding
python -m scholarlens.graph build

:: Thêm cả thư mục PDF bằng dòng lệnh
python -m scholarlens.ingest dir demo_pdfs --embed --graph

:: Chatbot dòng lệnh, bài liên quan, đánh giá
python -m scholarlens.chat --mode research
python -m scholarlens.graph related 2005.11401
python scripts\evaluate.py --n 500 --models intfloat/multilingual-e5-base BAAI/bge-base-en-v1.5
```
