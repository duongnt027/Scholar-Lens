# Công nghệ và phương pháp sử dụng trong ScholarLens

Mỗi mục gồm: **cách hoạt động**, **mục đích sử dụng**, và vị trí trong mã nguồn để tra cứu khi cần. Các con số (ngưỡng, tham số) là giá trị thực đang dùng trong code.

**Mục lục**

1. [Thu thập dữ liệu](#1-thu-thập-dữ-liệu): arXiv API · Kaggle arXiv snapshot
2. [Xử lý tài liệu](#2-xử-lý-tài-liệu): PyMuPDF · Băm SHA-256 · So khớp tiêu đề gần đúng · Chunking
3. [Biểu diễn văn bản](#3-biểu-diễn-văn-bản-embedding): Sentence embedding · multilingual-e5-base · Tăng tốc GPU
4. [Lưu trữ](#4-lưu-trữ): SQLite · ChromaDB · HNSW
5. [Tìm kiếm](#5-tìm-kiếm): BM25 · Tìm kiếm dense · Reciprocal Rank Fusion · Gộp về cấp bài báo
6. [Đồ thị tri thức](#6-đồ-thị-tri-thức): NetworkX · Trích khái niệm (KeyBERT + MMR) · Cạnh tương đồng · Cạnh trích dẫn · Điểm liên quan
7. [Chatbot](#7-chatbot): RAG · Graph RAG · Định tuyến · Viết lại câu hỏi · Trích dẫn [n] · Chế độ trích đoạn
8. [Mô hình ngôn ngữ](#8-mô-hình-ngôn-ngữ-llm): Qwen2.5 · Lượng tử hoá AWQ · vLLM · API tương thích OpenAI
9. [Ứng dụng và triển khai](#9-ứng-dụng-và-triển-khai): FastAPI + SSE · Giao diện web · Cloudflare Tunnel · Docker · Kaggle Notebook
10. [Đánh giá](#10-đánh-giá): Recall@k, MRR · Các giao thức đánh giá

---

## 1. Thu thập dữ liệu

### arXiv API

**Cách hoạt động:**
- arXiv cung cấp một địa chỉ truy vấn công khai (`export.arxiv.org/api/query`), trả về danh sách bài báo dạng XML (chuẩn Atom). Mỗi bài có mã arXiv, tiêu đề, tóm tắt, tác giả, chuyên mục, ngày đăng và link PDF.
- Câu truy vấn được ghép từ các điều kiện:
  - `all:"dense retrieval"`: cụm từ chính xác.
  - `cat:cs.IR`: chuyên mục.
  - `submittedDate:[20250101 TO …]`: khoảng ngày.
  - `id_list=…`: danh sách mã bài cụ thể.
- Kết quả được lấy theo trang, mỗi trang 100 bài. Giữa các lần gọi nghỉ 3 giây theo quy định của arXiv, và thử lại khi lỗi mạng.
- Bài đã có trong `data/raw/metadata.jsonl` thì bỏ qua.

**Mục đích sử dụng:**
- Nguồn dữ liệu chính của hệ thống: tự động lấy bài báo theo chủ đề cần theo dõi.
- Làm giàu thông tin khi người dùng tải PDF lên: tra mã arXiv để lấy tiêu đề, tác giả, chuyên mục chuẩn thay vì đoán từ file PDF.

**Trong mã:** [scholarlens/crawler/arxiv_client.py](../scholarlens/crawler/arxiv_client.py)

### Kaggle arXiv snapshot (Cornell-University/arxiv)

**Cách hoạt động:** đây là file JSON lines chứa thông tin khoảng 2,7 triệu bài arXiv, cập nhật định kỳ trên Kaggle. Hệ thống đọc tuần tự từng dòng, lọc theo chuyên mục và năm, rồi chuyển về cùng định dạng với dữ liệu lấy từ API.

**Mục đích sử dụng:** nạp dữ liệu quy mô lớn trong một lần (hàng chục nghìn bài) mà không phải gọi API hàng nghìn lần.

**Trong mã:** `Crawler.from_kaggle_snapshot` trong [arxiv_client.py](../scholarlens/crawler/arxiv_client.py)

---

## 2. Xử lý tài liệu

### PyMuPDF

**Cách hoạt động:** thư viện đọc PDF, trả về chữ của từng trang kèm vị trí và cỡ chữ của từng đoạn. Trên nền đó, hệ thống dùng các quy tắc (heuristic) để trích thông tin:
- **Tiêu đề:** dòng có cỡ chữ lớn nhất ở nửa trên trang 1. Hệ thống ghép theo dòng chứ không theo từng đoạn chữ, để giữ đúng tiêu đề viết kiểu chữ hoa nhỏ (small-caps).
- **Mã arXiv:** tìm tem dọc bên lề trang 1 (`arXiv:2310.06825v1 [cs.CL] …`) bằng biểu thức chính quy, hoặc lấy từ tên file.
- **Tóm tắt:** đoạn nằm giữa chữ "Abstract" và "Introduction".
- **Mục (section):** các dòng dạng "3 Method", "4.2 Results".
- **Tài liệu tham khảo:** mọi mã arXiv xuất hiện sau tiêu đề "References". Các mã này dùng để tạo cạnh trích dẫn trong đồ thị.

**Mục đích sử dụng:** biến file PDF người dùng tải lên thành văn bản có cấu trúc để tìm kiếm, trích dẫn đúng trang/mục, và nối quan hệ trích dẫn.

**Trong mã:** [scholarlens/ingest/pdf_parser.py](../scholarlens/ingest/pdf_parser.py)

### Băm SHA-256

**Cách hoạt động:** hàm băm biến toàn bộ nội dung file thành một chuỗi 64 ký tự. Hai file giống hệt nhau từng byte luôn cho cùng chuỗi; khác dù một byte thì chuỗi khác hoàn toàn.

**Mục đích sử dụng:** lớp kiểm tra trùng đầu tiên và rẻ nhất. Cùng một file tải lên lần thứ hai bị phát hiện ngay, không cần đọc nội dung PDF.

**Trong mã:** `file_sha256` trong [scholarlens/utils.py](../scholarlens/utils.py)

### So khớp tiêu đề gần đúng (fuzzy matching)

**Cách hoạt động:**
1. **Chuẩn hoá** tiêu đề: bỏ dấu, chữ thường, chỉ giữ chữ và số.
2. Khớp tuyệt đối tiêu đề đã chuẩn hoá.
3. Nếu không khớp tuyệt đối, coi là trùng khi thoả **một trong hai** tiêu chí:
   - Tỉ lệ ký tự giống nhau (thuật toán SequenceMatcher của thư viện `difflib`) ≥ 0,92. Tiêu chí này bắt được lỗi chính tả, khác dấu câu.
   - Đồng thời có **độ bao hàm từ** |A∩B| / min(|A|,|B|) ≥ 0,9 **và** **Jaccard** |A∩B| / |A∪B| ≥ 0,8, với tiêu đề ngắn hơn có ít nhất 6 từ. Tiêu chí này bắt được tiêu đề bị bỏ hoặc thêm một vài từ, ví dụ "(Extended Version)".

**Mục đích sử dụng:** phát hiện cùng một bài nhưng là file khác (bản khác, bản in lại) hoặc không có mã arXiv. Kết quả đo trên 492 bài: bắt được 95% tiêu đề bị biến đổi, không báo nhầm bài thật nào.

**Trong mã:** `title_similarity`, `title_near_duplicate` trong [utils.py](../scholarlens/utils.py); `find_duplicate` trong [metadata_db.py](../scholarlens/store/metadata_db.py)

### Chunking (chia đoạn)

**Cách hoạt động:**
- Mỗi bài có một **đoạn tóm tắt** (tiêu đề + abstract).
- Toàn văn được cắt bằng **cửa sổ trượt** dài 220 từ, hai đoạn liền nhau chồng lên nhau 40 từ.
- Đoạn không vượt qua ranh giới mục (section), và mỗi đoạn ghi lại số trang và tên mục.

**Mục đích sử dụng:**
- Mô hình embedding chỉ đọc được văn bản ngắn (tối đa 512 token với e5).
- Đoạn ngắn giúp tìm đúng chỗ chứa câu trả lời thay vì cả bài.
- Phần chồng lấn tránh cắt mất ý nằm ở ranh giới hai đoạn.
- Số trang và tên mục dùng để trích dẫn cụ thể.

**Trong mã:** [scholarlens/ingest/chunker.py](../scholarlens/ingest/chunker.py)

---

## 3. Biểu diễn văn bản (embedding)

### Sentence embedding (sentence-transformers)

**Cách hoạt động:** một mạng nơ-ron Transformer đọc đoạn văn và biến nó thành một vector số (ở đây 768 chiều). Mô hình được huấn luyện sao cho các câu cùng ý nghĩa có vector gần nhau, kể cả khi dùng từ khác nhau. Vector được chuẩn hoá về độ dài 1, nên tích vô hướng giữa hai vector chính là độ tương đồng cosine (từ −1 đến 1).

**Mục đích sử dụng:** cho phép tìm kiếm theo **ý nghĩa** chứ không chỉ theo từ. Câu hỏi "cách tìm tài liệu bằng vector" vẫn tìm được bài viết về "dense retrieval".

**Trong mã:** [scholarlens/embedding/embedder.py](../scholarlens/embedding/embedder.py)

### Mô hình intfloat/multilingual-e5-base

**Cách hoạt động:**
- Mô hình E5 khoảng 278 triệu tham số, huấn luyện đa ngôn ngữ (có tiếng Việt), cho vector 768 chiều.
- Phải thêm tiền tố `query:` cho câu hỏi và `passage:` cho văn bản. Mô hình được huấn luyện như vậy để phân biệt hai vai trò.
- Mô hình được chọn qua biến `SL_EMBED_MODEL`. Hệ thống tự nhận tiền tố cho họ E5 và BGE.

**Mục đích sử dụng:**
- Người dùng hỏi bằng **tiếng Việt** trên kho bài báo **tiếng Anh**: vector của câu hỏi tiếng Việt vẫn gần vector của đoạn tiếng Anh cùng ý.
- Nhờ vậy hệ thống vẫn tìm đúng kể cả khi không có LLM để dịch câu hỏi.

### Tăng tốc bằng GPU

**Cách hoạt động:**
- Hệ thống tự chọn thiết bị theo thứ tự CUDA → MPS (Mac) → CPU.
- Trên GPU, mô hình chạy ở dạng số thực 16 bit (fp16) và xử lý theo lô lớn gấp 4 lần.
- Module embedding chỉ xử lý các đoạn có `embedded = 0`, nên chạy lại bao nhiêu lần cũng không làm lại việc cũ.

**Mục đích sử dụng:** embedding hàng loạt trên GPU Kaggle nhanh hơn CPU nhiều lần. Đo trên máy demo, CPU chỉ đạt khoảng 1,4 đoạn/giây.

**Trong mã:** [scholarlens/embedding/pipeline.py](../scholarlens/embedding/pipeline.py)

---

## 4. Lưu trữ

### SQLite

**Cách hoạt động:**
- Cơ sở dữ liệu quan hệ nằm trong một file, không cần máy chủ.
- Có hai bảng: `papers` lưu thông tin bài, tài liệu tham khảo, khái niệm, trạng thái; `chunks` lưu nội dung đoạn, trang, mục, cờ đã embedding.
- Có chỉ mục trên mã arXiv, SHA-256 và tiêu đề chuẩn hoá để tra trùng nhanh.
- Bật chế độ WAL để vừa đọc vừa ghi được cùng lúc.

**Mục đích sử dụng:**
- Là "nguồn sự thật" của hệ thống; vector store và đồ thị đều dựng lại được từ SQLite.
- Kiểm tra trùng và hiển thị thư viện bài báo.
- Theo dõi trạng thái từng bài: `registered → embedded → graphed`. Nhờ đó mỗi module chạy độc lập được.

**Trong mã:** [scholarlens/store/metadata_db.py](../scholarlens/store/metadata_db.py)

### ChromaDB

**Cách hoạt động:**
- Cơ sở dữ liệu vector chạy nhúng trong ứng dụng, lưu xuống thư mục `data/chroma`.
- Mỗi bản ghi gồm vector, văn bản gốc và metadata (mã bài, năm, chuyên mục, trang, mục).
- Hỗ trợ tìm k vector gần nhất kèm điều kiện lọc, ví dụ chỉ trong bài đang hỏi, hoặc từ năm 2024 trở đi.
- Có hai collection: `chunks` (vector từng đoạn) và `papers` (một vector cho mỗi bài, từ tiêu đề + tóm tắt).

**Mục đích sử dụng:**
- Tìm kiếm ngữ nghĩa cho chatbot và tab tìm kiếm.
- Tìm các bài tương đồng khi thêm bài mới.

**Trong mã:** [scholarlens/store/vector_store.py](../scholarlens/store/vector_store.py)

### HNSW (Hierarchical Navigable Small World)

**Cách hoạt động:**
- Thuật toán tìm láng giềng gần nhất **xấp xỉ**, chính là thuật toán ChromaDB dùng bên dưới.
- Các vector được nối thành một đồ thị nhiều tầng: tầng trên ít nút với cạnh dài (như đường cao tốc), tầng dưới nhiều nút với cạnh ngắn.
- Khi tìm, thuật toán bắt đầu từ tầng trên, đi dần về phía gần câu hỏi nhất rồi xuống tầng dưới.
- Mỗi lần tìm chỉ ghé khoảng O(log N) nút thay vì so với cả N vector.
- Đổi lại, kết quả có thể sót một ít láng giềng thật (recall thường > 95%), và chỉ mục tốn thêm RAM.

**Mục đích sử dụng:** giữ thời gian tìm kiếm dưới 1 giây khi kho lớn lên hàng triệu đoạn. Hệ thống cấu hình độ đo cosine (`"hnsw:space": "cosine"`).

---

## 5. Tìm kiếm

### BM25 (Okapi BM25)

**Cách hoạt động:** chấm điểm một đoạn văn d theo các từ của câu hỏi q:

$$\text{BM25}(q,d) = \sum_{t \in q} \text{IDF}(t)\cdot\frac{f(t,d)\,(k_1+1)}{f(t,d) + k_1\left(1 - b + b\,\frac{|d|}{\text{avgdl}}\right)}$$

trong đó:
- **f(t,d)** là số lần từ t xuất hiện trong đoạn, nhưng điểm tăng chậm dần (bão hoà) khi từ lặp lại nhiều.
- **IDF(t)** cho từ hiếm điểm cao hơn từ phổ biến.
- **|d| / avgdl** phạt nhẹ các đoạn dài hơn độ dài trung bình.
- Tham số mặc định của thư viện rank-bm25: k₁ = 1,5, b = 0,75.

Trước khi chấm điểm, văn bản được tách từ đơn giản: chữ thường và bỏ các từ dừng (stopword). Chỉ mục nằm trong RAM và chỉ dựng lại khi có bài mới.

**Mục đích sử dụng:** bắt chính xác các thuật ngữ hiếm (tên mô hình, tên bộ dữ liệu như "HotpotQA") mà embedding đôi khi làm "mờ" đi. Tốc độ khoảng 1,4 ms mỗi truy vấn.

**Trong mã:** [scholarlens/store/bm25_index.py](../scholarlens/store/bm25_index.py)

### Tìm kiếm dense (vector)

**Cách hoạt động:** câu hỏi được embedding (có tiền tố `query:`), rồi ChromaDB trả về 50 đoạn có cosine cao nhất, có thể kèm điều kiện lọc.

**Mục đích sử dụng:** tìm theo ý nghĩa, xử lý được câu hỏi tiếng Việt và cách diễn đạt khác với văn bản gốc.

### Reciprocal Rank Fusion (RRF)

**Cách hoạt động:** gộp hai danh sách xếp hạng (BM25 và dense) chỉ dựa trên **thứ hạng**:

$$\text{RRF}(d) = \sum_{r \in \{\text{BM25},\ \text{dense}\}} \frac{1}{k + \text{rank}_r(d)}, \quad k = 60$$

Đoạn đứng cao ở cả hai danh sách được cộng điểm từ cả hai. Hằng số k = 60 làm giảm chênh lệch giữa hạng 1 và hạng 2, để một danh sách không lấn át danh sách kia (Cormack và cộng sự, 2009).

**Mục đích sử dụng:**
- Kết hợp ưu điểm của khớp từ khoá và khớp ý nghĩa.
- Không cần chuẩn hoá điểm, vì điểm BM25 không có giới hạn trên còn cosine nằm trong [−1, 1], hai thang đo không so sánh trực tiếp được.

**Trong mã:** `rrf`, `HybridRetriever.search_chunks` trong [scholarlens/retrieval/hybrid.py](../scholarlens/retrieval/hybrid.py)

### Gộp kết quả về cấp bài báo

**Cách hoạt động:**
- Các đoạn tìm được được nhóm theo bài.
- Điểm bài = điểm đoạn cao nhất + 0,3 × tổng điểm các đoạn còn lại của bài đó.

**Mục đích sử dụng:** người dùng cần danh sách **bài**, không phải danh sách đoạn rời rạc. Công thức thưởng nhẹ cho bài có nhiều đoạn liên quan, nhưng một đoạn rất khớp vẫn quyết định thứ hạng.

**Trong mã:** `HybridRetriever.search_papers` trong [hybrid.py](../scholarlens/retrieval/hybrid.py)

---

## 6. Đồ thị tri thức

### NetworkX (đồ thị có hướng, nhiều cạnh)

**Cách hoạt động:** thư viện Python biểu diễn đồ thị trong bộ nhớ. Hệ thống dùng `MultiDiGraph`, cho phép giữa hai nút có nhiều cạnh khác loại.
- **4 loại nút:** paper, author, concept (khái niệm), category (chuyên mục).
- **5 loại cạnh:** `CITES` (trích dẫn), `SIMILAR_TO` (tương đồng), `WRITTEN_BY` (viết bởi), `MENTIONS` (nhắc đến khái niệm), `IN_CATEGORY` (thuộc chuyên mục).
- Đồ thị được lưu ra file `data/graph.json` và cập nhật tăng dần khi thêm bài.

**Mục đích sử dụng:**
- Biểu diễn **quan hệ giữa các bài**, thứ mà tìm kiếm theo đoạn văn không thấy được.
- Là nền cho tính năng gợi ý bài liên quan có giải thích, và cho Graph RAG.

**Trong mã:** [scholarlens/graph/knowledge_graph.py](../scholarlens/graph/knowledge_graph.py), [builder.py](../scholarlens/graph/builder.py)

### Trích khái niệm: KeyBERT rút gọn + MMR

**Cách hoạt động:**
1. **Sinh ứng viên:** lấy các cụm 1–3 từ trong tiêu đề + tóm tắt, bỏ những cụm chứa từ dừng hoặc từ chung chung ("method", "propose"…). Giữ khoảng 40 cụm hay gặp nhất, và đưa danh từ về số ít.
2. **Xếp hạng:** embedding từng cụm, rồi tính cosine với vector của bài.
3. **Chọn đa dạng bằng MMR (Maximal Marginal Relevance):** chọn lần lượt cụm có giá trị lớn nhất theo công thức

   $$\text{MMR} = 0{,}5\cdot\text{sim}(\text{cụm},\text{bài}) - 0{,}5\cdot\max\ \text{sim}(\text{cụm},\text{cụm đã chọn})$$

   Kết quả là 6 khái niệm mỗi bài.

**Mục đích sử dụng:** tạo nút "khái niệm" để nối các bài cùng chủ đề. MMR tránh chọn 6 cụm gần như trùng nhau, ví dụ "retrieval model" và "retrieval models".

**Trong mã:** [scholarlens/graph/keywords.py](../scholarlens/graph/keywords.py)

### Cạnh tương đồng (SIMILAR_TO)

**Cách hoạt động:**
- Mỗi bài nối tới tối đa 5 bài có cosine giữa hai vector bài ≥ 0,75.
- Khi dựng toàn bộ đồ thị, hệ thống nhân ma trận vector theo từng khối 2048 bài. Đây là tính **chính xác**, chạy nhanh vì làm một lần trên GPU.
- Khi thêm một bài, hệ thống dùng truy vấn HNSW (xấp xỉ) cho nhanh.

**Mục đích sử dụng:** nối các bài cùng nội dung nhưng không có tác giả hay khái niệm chung.

### Cạnh trích dẫn (CITES)

**Cách hoạt động:**
- Các mã arXiv tìm thấy trong phần References của PDF được nối thành cạnh, nếu bài được trích dẫn có trong kho.
- Khi thêm bài mới, hệ thống nối **hai chiều**: bài mới trích dẫn bài cũ, và bài cũ trích dẫn bài mới (tra trong danh sách tham khảo của các bài cũ).

**Mục đích sử dụng:** quan hệ mạnh và đáng tin nhất giữa hai bài khoa học. Trong kho hiện có 19 cạnh, vì chỉ 12 bài có toàn văn PDF.

### Điểm liên quan giữa hai bài

**Cách hoạt động:** cộng dồn điểm theo các đường đi 1–2 bước trên đồ thị:

$$\text{score}(p,q) = \mathbb{1}[\text{CITES}] + \cos_{\text{SIMILAR}}(p,q) + \sum_{e \in N(p)\cap N(q)} \frac{w_{\text{loại}(e)}}{\log_2(2+\deg(e))}$$

- Trọng số w: cùng tác giả 0,6; cùng khái niệm 0,45; cùng chuyên mục 0,05.
- Thực thể có bậc deg cao (ví dụ khái niệm rất phổ biến) bị chia nhỏ điểm, vì ít giá trị phân biệt.
- Chuyên mục có hơn 300 bài thì bỏ qua; bài chỉ có chung chuyên mục thì không tính là liên quan.
- Mỗi kết quả kèm danh sách lý do, ví dụ "cùng tác giả Patrick Lewis · trích dẫn bài này".

**Mục đích sử dụng:** gợi ý bài liên quan **có giải thích được**. Đo trên kho: 37% bài liên quan cùng chuyên mục với bài gốc, gấp 2,7 lần chọn ngẫu nhiên (14%).

**Trong mã:** `KnowledgeGraph.related_papers` trong [knowledge_graph.py](../scholarlens/graph/knowledge_graph.py)

---

## 7. Chatbot

### RAG (Retrieval-Augmented Generation)

**Cách hoạt động:** thay vì để LLM trả lời từ trí nhớ, hệ thống tìm các đoạn liên quan rồi đưa chúng vào prompt làm **ngữ cảnh**. LLM chỉ được trả lời dựa trên ngữ cảnh đó.

**Mục đích sử dụng:**
- Trả lời đúng theo nội dung bài báo, kể cả bài mới đăng sau khi LLM được huấn luyện.
- Giảm hiện tượng "bịa" (hallucination).

### Graph RAG

**Cách hoạt động:** RAG thông thường cộng thêm một bước mở rộng trên đồ thị tri thức.
- **Khi không chọn bài cụ thể:**
  1. Tìm kiếm lai lấy 5 bài "hạt giống".
  2. Ba bài đầu được mở rộng sang 2 bài láng giềng trên đồ thị, hoặc 4 nếu câu hỏi có ý "liên quan / so sánh / trích dẫn".
- **Khi đang hỏi về một bài (focus):** lấy tóm tắt và 8 đoạn khớp nhất *trong chính bài đó*, cộng 4–8 bài liên quan của nó.
- Quan hệ trên đồ thị được viết thành câu ("A trích dẫn B", "A bàn về: …") và đưa vào ngữ cảnh. Ngữ cảnh giới hạn khoảng 24.000 ký tự.

**Mục đích sử dụng:** trả lời được câu hỏi **về quan hệ**, như "bài nào liên quan", "bài nào trích dẫn bài này", mà từng đoạn văn riêng lẻ không chứa thông tin.

**Trong mã:** [scholarlens/retrieval/graph_rag.py](../scholarlens/retrieval/graph_rag.py)

### Định tuyến chế độ Chat / Research

**Cách hoạt động:**
- Đang hỏi về một bài → Research.
- Câu chào hỏi ngắn (biểu thức chính quy: "xin chào", "cảm ơn"…, tối đa 8 từ) → Chat.
- Còn lại → Research.
- Người dùng có thể ép chọn chế độ bằng nút trên giao diện.

**Mục đích sử dụng:** câu xã giao được trả lời nhanh, không tốn công tìm kiếm; câu hỏi chuyên môn luôn có nguồn.

**Trong mã:** `Chatbot.route` trong [scholarlens/chat/chatbot.py](../scholarlens/chat/chatbot.py)

### Viết lại câu hỏi (query rewriting)

**Cách hoạt động:** LLM nhận 4 lượt hội thoại gần nhất cùng câu hỏi cuối, rồi viết lại thành **một câu truy vấn tiếng Anh độc lập**. Các đại từ như "bài này", "phương pháp đó" được thay bằng đối tượng cụ thể.

**Mục đích sử dụng:**
- Câu hỏi nối tiếp ("thế còn kết quả thì sao?") vẫn tìm đúng.
- Truy vấn tiếng Anh khớp tốt hơn với BM25 trên kho tiếng Anh.

### Prompt bắt buộc trích dẫn [n]

**Cách hoạt động:**
- Mỗi nguồn trong ngữ cảnh được đánh số [1], [2]… kèm vai trò (bài đang hỏi / tìm thấy / liên quan) và lý do liên quan.
- Prompt hệ thống yêu cầu: chỉ dùng thông tin trong ngữ cảnh, ghi [n] sau mỗi khẳng định, nói rõ khi không đủ thông tin, và trả lời bằng ngôn ngữ của người hỏi.
- Giao diện biến [n] thành nút bấm, mở ra đúng đoạn gốc.

**Mục đích sử dụng:** người dùng kiểm chứng được từng ý của câu trả lời.

**Trong mã:** [scholarlens/chat/prompts.py](../scholarlens/chat/prompts.py)

### Chế độ trích đoạn (extractive fallback)

**Cách hoạt động:** khi không có LLM hoặc LLM mất kết nối, hệ thống chọn 2 câu có nhiều từ trùng với câu hỏi nhất trong mỗi nguồn. Sau đó liệt kê các bài liên quan và các quan hệ trên đồ thị.

**Mục đích sử dụng:** hệ thống không bao giờ trả về câu trả lời trống. Tìm kiếm và gợi ý vẫn hoạt động khi máy chủ GPU tắt.

**Trong mã:** `extractive_answer` trong [chatbot.py](../scholarlens/chat/chatbot.py)

---

## 8. Mô hình ngôn ngữ (LLM)

### Qwen2.5-7B-Instruct

**Cách hoạt động:** mô hình ngôn ngữ mã nguồn mở 7 tỉ tham số của Alibaba, đã được tinh chỉnh để làm theo chỉ dẫn (instruct). Mô hình hỗ trợ nhiều ngôn ngữ, trong đó có tiếng Việt, với ngữ cảnh dài (đang cấu hình 16.384 token).

**Mục đích sử dụng:** đọc các đoạn tìm được rồi viết câu trả lời tiếng Việt có trích dẫn, đồng thời viết lại câu hỏi. Mô hình chạy được trên GPU miễn phí, không tốn phí API.

### Lượng tử hoá AWQ (Activation-aware Weight Quantization)

**Cách hoạt động:**
- Nén trọng số mô hình từ 16 bit xuống 4 bit.
- Phương pháp dựa vào độ lớn của activation để tìm khoảng 1% trọng số quan trọng nhất, rồi bảo vệ chúng bằng cách nhân hệ số tỉ lệ trước khi nén. Nhờ vậy độ chính xác giảm rất ít.

**Mục đích sử dụng:** mô hình 7B giảm từ khoảng 15 GB xuống khoảng 5 GB, vừa với 2 GPU T4 (16 GB mỗi GPU) và còn chỗ cho bộ nhớ đệm hội thoại.

### vLLM

**Cách hoạt động:** máy chủ phục vụ LLM hiệu năng cao.
- **PagedAttention:** quản lý bộ nhớ đệm attention (KV cache) theo từng "trang" nhỏ, giống bộ nhớ ảo của hệ điều hành, nên ít lãng phí VRAM.
- **Continuous batching:** ghép nhiều yêu cầu đang chạy vào cùng một lượt tính toán.
- **Tensor parallelism:** chia mỗi lớp của mô hình cho 2 GPU cùng tính (`--tensor-parallel-size 2`).
- **Prefix caching:** dùng lại phần prompt giống nhau giữa các lần gọi.
- Trên T4, hệ thống tự chọn `float16` (T4 không hỗ trợ bf16) và `--enforce-eager` để tiết kiệm VRAM.

**Mục đích sử dụng:** host LLM mã nguồn mở với tốc độ đủ cho chat streaming trên phần cứng miễn phí.

**Trong mã:** [scholarlens/llm_server/server.py](../scholarlens/llm_server/server.py), [notebooks/kaggle_llm_server.ipynb](../notebooks/kaggle_llm_server.ipynb)

### API tương thích OpenAI

**Cách hoạt động:** vLLM cung cấp các địa chỉ `/v1/models` và `/v1/chat/completions` theo đúng định dạng của OpenAI, kèm streaming. Ứng dụng dùng thư viện `openai` để gọi, chỉ cần đổi Base URL.

**Mục đích sử dụng:** một đoạn mã gọi được nhiều nhà cung cấp: vLLM tự host, Ollama, Gemini, Groq, OpenAI. Hệ thống cũng hỗ trợ Claude qua thư viện `anthropic`. Đổi mô hình không phải sửa code.

**Trong mã:** [scholarlens/chat/llm.py](../scholarlens/chat/llm.py)

---

## 9. Ứng dụng và triển khai

### FastAPI + Server-Sent Events (SSE)

**Cách hoạt động:**
- FastAPI là framework web Python, dùng để định nghĩa các API: tìm kiếm, tải PDF, chat, đồ thị, cấu hình LLM.
- Câu trả lời chat được gửi dần theo luồng SSE: máy chủ đẩy từng sự kiện `meta → status → query → sources → token… → done` qua một kết nối HTTP mở sẵn.
- Việc nạp PDF chạy ở luồng nền; giao diện hỏi trạng thái mỗi giây.

**Mục đích sử dụng:** người dùng thấy ngay tiến trình ("đang tìm kiếm…"), thấy nguồn trước, rồi thấy câu trả lời hiện dần từng chữ như ChatGPT/Claude.

**Trong mã:** [scholarlens/app/server.py](../scholarlens/app/server.py)

### Giao diện web (HTML/JS thuần, marked, DOMPurify, vis-network)

**Cách hoạt động:**
- Trang web không cần bước build.
- **marked** chuyển Markdown của câu trả lời thành HTML.
- **DOMPurify** lọc bỏ mã độc trong HTML trước khi hiển thị.
- **vis-network** vẽ đồ thị bằng mô phỏng lực hút–đẩy (force-directed): nút liên kết kéo lại gần nhau, nút không liên kết đẩy ra xa.
- Các thư viện được đóng gói sẵn trong `static/vendor`, nên chạy được khi không có mạng.

**Mục đích sử dụng:** giao diện chat quen thuộc, kéo-thả PDF, xem nguồn và đồ thị bên cạnh câu trả lời.

**Trong mã:** [scholarlens/app/static/](../scholarlens/app/static/)

### Cloudflare Tunnel (trycloudflare) + API key

**Cách hoạt động:**
- Chương trình `cloudflared` trên máy GPU mở một kết nối **đi ra** tới mạng Cloudflare. Cloudflare cấp một địa chỉ công khai `https://<ngẫu nhiên>.trycloudflare.com` và chuyển các yêu cầu từ địa chỉ đó về máy GPU qua kết nối này.
- Máy GPU không cần IP công khai hay mở cổng.
- vLLM bật `--api-key`, nên yêu cầu không có đúng khoá bị từ chối (HTTP 401).
- Địa chỉ thay đổi mỗi lần chạy lại. Vì vậy:
  - `keep_alive` kiểm tra mỗi 2 phút và tự mở tunnel mới khi lỗi 2 lần liên tiếp.
  - Ứng dụng cho đổi địa chỉ ngay trên giao diện (nút LLM).

**Mục đích sử dụng:** cho máy demo gọi được LLM chạy trong Kaggle, nơi không thể mở cổng mạng vào.

### Docker / Docker Compose

**Cách hoạt động:** đóng gói ứng dụng cùng mọi thư viện (Python 3.11, torch bản CPU, mô hình embedding tải sẵn) thành một image. Docker Compose chạy image với cổng 7860 và gắn thư mục `./data` vào container, nên dữ liệu không mất khi xoá container.

**Mục đích sử dụng:** máy demo chỉ cần cài Docker, chạy một lệnh `docker compose up -d`, không phải cài Python và thư viện thủ công.

**Trong mã:** [Dockerfile](../Dockerfile), [docker-compose.yml](../docker-compose.yml)

### Kaggle Notebook (GPU 2 × T4)

**Cách hoạt động:**
- Môi trường Jupyter miễn phí có GPU, mỗi phiên tối đa khoảng 12 giờ.
- Mã nguồn được tải lên dưới dạng Dataset.
- Notebook lần lượt: embedding và dựng đồ thị → đóng gói `data/` → cài vLLM → chạy mô hình → mở tunnel → giữ phiên sống.

**Mục đích sử dụng:** có GPU mạnh mà không tốn tiền, cho hai việc nặng nhất là embedding hàng loạt và chạy LLM.

**Trong mã:** [notebooks/kaggle_llm_server.ipynb](../notebooks/kaggle_llm_server.ipynb), [scripts/make_kaggle_bundle.py](../scripts/make_kaggle_bundle.py)

---

## 10. Đánh giá

### Recall@k và MRR

**Cách hoạt động:**
- **Recall@k:** tỉ lệ câu hỏi mà đáp án đúng nằm trong k kết quả đầu tiên.
- **MRR@10 (Mean Reciprocal Rank):** trung bình của 1 / (hạng của đáp án đúng); bằng 0 nếu đáp án không nằm trong top 10. Đáp án ở hạng 1 được 1 điểm, hạng 2 được 0,5, hạng 3 được 0,33…

**Mục đích sử dụng:** đo chất lượng tìm kiếm bằng con số, để so sánh BM25, dense và hybrid.

### Các giao thức đánh giá

**Cách hoạt động:**
- **Tìm bài theo tiêu đề (known-item):** câu hỏi là tiêu đề bài, kho tìm kiếm là các tóm tắt *không chứa tiêu đề*. Đáp án duy nhất là chính bài đó. Kết quả BM25: Recall@1 = 0,957, MRR@10 = 0,973.
- **Kiểm tra trùng:** 200 tiêu đề bị biến đổi ngẫu nhiên (chữ thường, bỏ dấu câu, bỏ 1 từ, thêm hậu tố), cộng kiểm tra báo nhầm trên toàn bộ 492 tiêu đề thật. Kết quả: bắt được 95%, báo nhầm 0%.
- **Đồ thị:** tỉ lệ bài liên quan (top-5) cùng chuyên mục với bài gốc, so với chọn ngẫu nhiên. Kết quả: 37% so với 14%.

**Mục đích sử dụng:** kiểm chứng từng thành phần một cách khách quan. Dòng dense/hybrid được điền khi chạy lại trên GPU.

**Trong mã:** [scripts/evaluate.py](../scripts/evaluate.py)
