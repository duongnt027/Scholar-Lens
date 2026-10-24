"""Dựng slide thuyết trình ScholarLens (python-pptx). Số liệu đọc trực tiếp từ data/ và reports/eval_results.json.

  python reports/build_slides.py  ->  reports/ScholarLens_slides.pptx
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "ScholarLens_slides.pptx"

# ---------- palette: đất nung (terracotta) của giao diện + than chì ----------
INK = RGBColor(0x26, 0x26, 0x24)       # nền tối / chữ chính
TEXT = RGBColor(0x2F, 0x2C, 0x24)
MUTED = RGBColor(0x6E, 0x69, 0x5C)
ACCENT = RGBColor(0xC9, 0x64, 0x42)    # terracotta
ACCENT_SOFT = RGBColor(0xF6, 0xE5, 0xDC)
CARD = RGBColor(0xF4, 0xF3, 0xEF)      # thẻ xám ấm rất nhạt trên nền trắng
LINE = RGBColor(0xD9, 0xD5, 0xC8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLUE = RGBColor(0x5B, 0x7F, 0xB8)
GREEN = RGBColor(0x5E, 0x8C, 0x59)
HEAD, BODY = "Cambria", "Calibri"

W, H = Inches(13.333), Inches(7.5)
MX = Inches(0.6)


# ---------- số liệu ----------
def load_numbers() -> dict:
    n = {"papers": 0, "fulltext": 0, "chunks": 0, "nodes": 0, "edges": 0, "node_types": {}, "edge_types": {}}
    db = ROOT / "data" / "scholarlens.sqlite"
    if db.exists():
        c = sqlite3.connect(db)
        n["papers"] = c.execute("select count(*) from papers").fetchone()[0]
        n["fulltext"] = c.execute("select count(*) from papers where has_fulltext=1").fetchone()[0]
        n["chunks"] = c.execute("select count(*) from chunks").fetchone()[0]
    g = ROOT / "data" / "graph.json"
    if g.exists():
        d = json.loads(g.read_text(encoding="utf-8"))
        n["nodes"], n["edges"] = len(d["nodes"]), len(d["edges"])
        for x in d["nodes"]:
            n["node_types"][x.get("type")] = n["node_types"].get(x.get("type"), 0) + 1
        for e in d["edges"]:
            n["edge_types"][e["k"]] = n["edge_types"].get(e["k"], 0) + 1
    ev = ROOT / "reports" / "eval_results.json"
    n["eval"] = json.loads(ev.read_text(encoding="utf-8")) if ev.exists() else None
    return n


def fmt(x: int) -> str:
    return f"{x:,}".replace(",", ".")


# ---------- primitive ----------
def text(slide, x, y, w, h, s, size=16, color=TEXT, bold=False, font=BODY, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False, name=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = line if isinstance(line, list) else [(line, {})]
        for r_text, opt in runs if isinstance(runs[0], tuple) else [(runs, {})]:
            r = p.add_run()
            r.text = r_text
            f = r.font
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("bold", bold)
            f.italic = opt.get("italic", italic)
            f.name = opt.get("font", font)
            f.color.rgb = opt.get("color", color)
        if i:
            p.space_before = Pt(opt.get("space", 6) if runs else 6)
    return tb


def bullets(slide, x, y, w, h, items, size=16, color=TEXT, gap=8):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Inches(0.25)))
        pPr.set("indent", str(-Inches(0.25)))
        bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        clr = pPr.makeelement(qn("a:buClr"), {})
        srgb = clr.makeelement(qn("a:srgbClr"), {"val": "C96442"})
        clr.append(srgb)
        pPr.append(clr)
        pPr.append(bu)
        p.space_after = Pt(gap)
        parts = it if isinstance(it, list) else [(it, {})]
        for t, opt in parts:
            r = p.add_run()
            r.text = t
            r.font.size = Pt(opt.get("size", size))
            r.font.bold = opt.get("bold", False)
            r.font.name = BODY
            r.font.color.rgb = opt.get("color", color)
    return tb


def box(slide, x, y, w, h, fill=CARD, line=None, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=None):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if name:
        s.name = name
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1.25)
    s.shadow.inherit = False
    return s


def circle_num(slide, x, y, d, label, fill=ACCENT, color=WHITE, size=14):
    c = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = p.add_run()
    r.text = label
    r.font.size, r.font.bold, r.font.name, r.font.color.rgb = Pt(size), True, BODY, color
    return c


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    return c


def card(slide, x, y, w, h, title, body, num=None, title_size=17, body_size=14, fill=CARD):
    box(slide, x, y, w, h, fill=fill)
    pad = Inches(0.22)
    tx = x + pad
    if num:
        circle_num(slide, x + pad, y + pad, Inches(0.42), num, size=13)
        tx = x + pad + Inches(0.55)
    text(slide, tx, y + pad + Inches(0.04), x + w - tx - pad, Inches(0.4), title, size=title_size, bold=True,
         font=HEAD, color=TEXT)
    if body:
        if isinstance(body, list):
            bullets(slide, x + pad, y + pad + Inches(0.6), w - 2 * pad, h - Inches(0.8), body, size=body_size, gap=4)
        else:
            text(slide, x + pad, y + pad + Inches(0.6), w - 2 * pad, h - Inches(0.8), body, size=body_size, color=MUTED)


def new_slide(prs, title=None, dark=False, notes=""):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = INK if dark else WHITE
    if title:
        text(s, MX, Inches(0.45), W - 2 * MX, Inches(0.8), title, size=34, bold=True, font=HEAD,
             color=WHITE if dark else TEXT, name="Title")
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def footer(s, idx, dark=False):
    text(s, MX, H - Inches(0.42), Inches(6), Inches(0.3), "ScholarLens · Graph RAG cho bài báo arXiv", size=10,
         color=MUTED)
    text(s, W - MX - Inches(1), H - Inches(0.42), Inches(1), Inches(0.3), str(idx), size=10, color=MUTED,
         align=PP_ALIGN.RIGHT)


def graph_motif(s, x0, y0, scale=1.0):
    """Hoạ tiết đồ thị nhỏ (nút + cạnh) cho slide tiêu đề."""
    pts = [(0.0, 1.2), (1.3, 0.3), (1.6, 1.9), (2.9, 1.0), (3.1, 2.6), (0.9, 3.0), (2.2, 3.6), (3.9, 2.0)]
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (2, 4), (2, 5), (5, 6), (4, 6), (3, 7), (4, 7), (1, 2)]
    P = [(x0 + Inches(px * scale), y0 + Inches(py * scale)) for px, py in pts]
    for a, b in edges:
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, P[a][0], P[a][1], P[b][0], P[b][1])
        c.line.color.rgb = RGBColor(0x5A, 0x57, 0x50)
        c.line.width = Pt(1.5)
    for i, (px, py) in enumerate(P):
        d = Inches((0.42 if i == 2 else 0.26) * scale)
        fill = ACCENT if i == 2 else (BLUE if i in (1, 6) else (GREEN if i in (5, 7) else RGBColor(0xE9, 0xC9, 0xB8)))
        box(s, px - d // 2, py - d // 2, d, d, fill=fill, shape=MSO_SHAPE.OVAL)


# ---------- slides ----------
def build():
    N = load_numbers()
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    idx = 0

    # 1. Tiêu đề
    s = new_slide(prs, dark=True, notes="Giới thiệu đề tài: hệ thống truy xuất thông tin cho bài báo khoa học arXiv, "
                  "tích hợp đồ thị tri thức và chatbot hỏi đáp có trích dẫn.")
    text(s, MX, Inches(1.9), Inches(7.5), Inches(1.2), "ScholarLens", size=60, bold=True, font=HEAD, color=WHITE)
    text(s, MX, Inches(3.05), Inches(7.4), Inches(1.2),
         "Hệ thống truy xuất bài báo arXiv với tìm kiếm lai, Graph RAG và chatbot hỏi đáp",
         size=22, color=RGBColor(0xE8, 0xE6, 0xDC))
    text(s, MX, Inches(4.6), Inches(7.4), Inches(0.9),
         ["Mini-project · Khai phá dữ liệu và Học máy (cao học)", "Tháng 10/2026"], size=15,
         color=RGBColor(0xA0, 0x9C, 0x90))
    graph_motif(s, Inches(8.6), Inches(1.6), scale=1.05)

    # 2. Nội dung
    idx += 2
    s = new_slide(prs, "Nội dung trình bày", notes="Bố cục bám theo 7 yêu cầu của đề bài.")
    items = [("Phát biểu bài toán", "Tình huống sử dụng, yêu cầu chức năng và phi chức năng"),
             ("Nguồn dữ liệu", "arXiv API, PDF, snapshot Kaggle"),
             ("Tổ chức dữ liệu", "SQLite · ChromaDB · BM25 · Knowledge Graph"),
             ("Hệ thống tìm kiếm", "BM25 + embedding đa ngôn ngữ, gộp RRF"),
             ("Chatbot", "Chat / Research, Graph RAG, host LLM bằng vLLM"),
             ("Đánh giá & kỹ thuật", "Recall@k, MRR, kiểm tra trùng, đồ thị"),
             ("Demo giải pháp", "Thêm PDF, hỏi bài, hỏi bài liên quan")]
    cw, ch = Inches(5.8), Inches(1.05)
    for i, (t, d) in enumerate(items):
        col, row = i % 2, i // 2
        x = MX + col * (cw + Inches(0.5))
        y = Inches(1.55) + row * (ch + Inches(0.25))
        circle_num(s, x, y + Inches(0.18), Inches(0.62), str(i + 1), size=18)
        text(s, x + Inches(0.85), y + Inches(0.12), cw - Inches(0.9), Inches(0.4), t, size=19, bold=True, font=HEAD)
        text(s, x + Inches(0.85), y + Inches(0.52), cw - Inches(0.9), Inches(0.4), d, size=14, color=MUTED)
    footer(s, idx)

    # 3. Bài toán
    idx += 1
    s = new_slide(prs, "Bài toán: tìm đúng bài, hỏi đúng chỗ",
                  notes="arXiv nhận hơn 20.000 bài mỗi tháng. Tìm theo từ khoá bỏ sót cách diễn đạt khác; "
                        "chatbot LLM thuần dễ bịa trích dẫn. Hệ thống kết hợp truy xuất ngữ nghĩa, quan hệ giữa "
                        "các bài và LLM để trả lời có nguồn.")
    text(s, MX, Inches(1.45), Inches(4.1), Inches(4.8),
         [[("Hơn 20.000", {"size": 40, "bold": True, "color": ACCENT, "font": HEAD})],
          [("bài mới trên arXiv mỗi tháng", {"size": 16, "color": MUTED})],
          [("Tìm theo từ khoá bỏ sót cách diễn đạt khác; LLM thuần dễ bịa nguồn. Cần truy xuất ngữ nghĩa + quan hệ "
            "giữa các bài + câu trả lời có trích dẫn.", {"size": 16, "color": TEXT, "space": 18})]])
    ucs = [("Tìm bằng câu hỏi", "Kết quả xếp hạng, có tác giả, năm, link arXiv"),
           ("Thêm 1 PDF", "Tự kiểm tra trùng, tự embedding và cập nhật đồ thị"),
           ("Thêm hàng loạt PDF", "Trạng thái riêng từng file: mới / trùng / lỗi"),
           ("Hỏi về một bài", "Trả lời từ chính bài đó, trích dẫn [n]"),
           ("Hỏi bài liên quan", "Láng giềng trên đồ thị kèm lý do liên quan"),
           ("Trò chuyện chung", "Chế độ Chat, không cần truy xuất")]
    gx, gy, cw, ch = Inches(5.1), Inches(1.45), Inches(3.7), Inches(1.5)
    for i, (t, d) in enumerate(ucs):
        x = gx + (i % 2) * (cw + Inches(0.25))
        y = gy + (i // 2) * (ch + Inches(0.22))
        card(s, x, y, cw, ch, t, d, num=f"UC{i + 1}" if False else str(i + 1), title_size=15, body_size=13)
    footer(s, idx)

    # 4. Yêu cầu
    idx += 1
    s = new_slide(prs, "Yêu cầu hệ thống",
                  notes="8 yêu cầu chức năng phủ toàn bộ vòng đời dữ liệu; yêu cầu phi chức năng tập trung vào "
                        "tốc độ, tính module và khả năng chạy không cần LLM.")
    text(s, MX, Inches(1.4), Inches(5.8), Inches(0.4), "Chức năng", size=20, bold=True, font=HEAD, color=ACCENT)
    bullets(s, MX, Inches(1.95), Inches(5.9), Inches(4.8), [
        "Crawl arXiv theo keyword / category / ngày / ID",
        "Nạp PDF: tiêu đề, tác giả, abstract, arXiv ID, tham khảo",
        "Kiểm tra trùng: SHA-256 → arXiv ID → tiêu đề → tiêu đề gần đúng",
        "Chunking + embedding + lưu vector DB và đồ thị, tự động",
        "Tìm kiếm lai BM25 + dense, gộp RRF, lọc theo năm",
        "Graph RAG: tác giả, khái niệm, trích dẫn, tương đồng",
        "Chatbot Chat / Research, nhớ hội thoại, hỏi theo bài",
        "Web app: streaming, kéo-thả PDF, nguồn, đồ thị"], size=15, gap=6)
    text(s, Inches(7.0), Inches(1.4), Inches(5.6), Inches(0.4), "Phi chức năng", size=20, bold=True, font=HEAD,
         color=ACCENT)
    nfr = [("Hiệu năng", "Tìm kiếm < 1 s; HNSW + BM25 trong RAM"),
           ("Mở rộng", "Embedding hàng loạt trên GPU Kaggle"),
           ("Module", "Mỗi module có CLI riêng, chạy độc lập"),
           ("Đúng đắn", "Bắt buộc trích dẫn [n], không bịa nguồn"),
           ("Linh hoạt", "Đổi LLM / embedding qua .env"),
           ("Khả dụng", "Chạy offline ở chế độ trích đoạn")]
    for i, (k, v) in enumerate(nfr):
        y = Inches(1.95) + i * Inches(0.78)
        box(s, Inches(7.0), y, Inches(5.7), Inches(0.66), fill=CARD)
        text(s, Inches(7.2), y, Inches(1.5), Inches(0.66), k, size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, Inches(8.75), y, Inches(3.85), Inches(0.66), v, size=14, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
    footer(s, idx)

    # 5. Kiến trúc
    idx += 1
    s = new_slide(prs, "Kiến trúc: 7 module chạy độc lập quanh 4 kho dữ liệu",
                  notes="Mỗi module có lệnh python -m riêng. Kaggle lo phần nặng (embedding GPU, host LLM), laptop "
                        "chạy web app với cùng thư mục data/.")
    mods = [("crawler", "arXiv API, snapshot"), ("ingest", "parse PDF, dedup, chunk"),
            ("embedding", "e5 đa ngôn ngữ, GPU"), ("graph", "NetworkX, keyphrase")]
    bw, bh = Inches(2.7), Inches(1.0)
    for i, (t, d) in enumerate(mods):
        x = MX + i * (bw + Inches(0.42))
        box(s, x, Inches(1.5), bw, bh, fill=ACCENT_SOFT)
        text(s, x, Inches(1.6), bw, Inches(0.4), t, size=17, bold=True, align=PP_ALIGN.CENTER, color=ACCENT)
        text(s, x, Inches(2.0), bw, Inches(0.4), d, size=13, color=MUTED, align=PP_ALIGN.CENTER)
        if i < 3:
            arrow(s, x + bw + Inches(0.04), Inches(2.0), x + bw + Inches(0.38), Inches(2.0))
    # kho dữ liệu
    box(s, MX, Inches(2.95), W - 2 * MX, Inches(1.35), fill=CARD)
    text(s, MX + Inches(0.25), Inches(3.05), Inches(3), Inches(0.35), "Kho dữ liệu (data/)", size=14, bold=True,
         color=MUTED)
    stores = ["SQLite · papers, chunks", "ChromaDB · vector HNSW", "BM25 · từ vựng", "Graph · JSON"]
    sw = (W - 2 * MX - Inches(0.5) - Inches(0.3) * 3) / 4
    for i, t in enumerate(stores):
        x = MX + Inches(0.25) + i * (sw + Inches(0.3))
        box(s, int(x), Inches(3.45), int(sw), Inches(0.65), fill=WHITE, line=LINE)
        text(s, int(x), Inches(3.45), int(sw), Inches(0.65), t, size=14, bold=True, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, Inches(6.67), Inches(2.5), Inches(6.67), Inches(2.92))
    # tầng trên
    tops = [("retrieval", "hybrid search + Graph RAG"), ("chat", "Chat / Research, SSE"),
            ("app", "FastAPI + giao diện web"), ("llm_server", "vLLM trên Kaggle GPU")]
    for i, (t, d) in enumerate(tops):
        x = MX + i * (bw + Inches(0.42))
        box(s, x, Inches(4.8), bw, bh, fill=INK if t != "llm_server" else WHITE, line=None if t != "llm_server" else ACCENT)
        text(s, x, Inches(4.9), bw, Inches(0.4), t, size=17, bold=True, align=PP_ALIGN.CENTER,
             color=WHITE if t != "llm_server" else ACCENT)
        text(s, x, Inches(5.3), bw, Inches(0.4), d, size=13, align=PP_ALIGN.CENTER,
             color=RGBColor(0xC9, 0xC5, 0xB8) if t != "llm_server" else MUTED)
    arrow(s, Inches(6.67), Inches(4.33), Inches(6.67), Inches(4.77))
    arrow(s, MX + bw + Inches(0.04), Inches(5.3), MX + bw + Inches(0.38), Inches(5.3))
    arrow(s, MX + 2 * bw + Inches(0.46), Inches(5.3), MX + 2 * bw + Inches(0.8), Inches(5.3))
    arrow(s, MX + 3 * (bw + Inches(0.42)) - Inches(0.04), Inches(5.3), MX + 3 * bw + Inches(0.88), Inches(5.3))
    text(s, MX, Inches(6.1), W - 2 * MX, Inches(0.4),
         "llm_server phục vụ API tương thích OpenAI; chat cũng dùng được Claude, Gemini, Ollama hoặc không cần LLM.",
         size=13, color=MUTED)
    footer(s, idx)

    # 6. Dữ liệu
    idx += 1
    s = new_slide(prs, "Dữ liệu: arXiv qua 3 kênh thu thập",
                  notes="Crawl lịch sự: 3 giây/lượt, 100 kết quả/trang, ghi nối JSONL không trùng ID. Kaggle "
                        "snapshot cho quy mô hàng trăm nghìn bài.")
    stats = [(fmt(N["papers"]), "bài báo trong kho"), (fmt(N["fulltext"]), "bài có toàn văn PDF"),
             (fmt(N["chunks"]), "đoạn văn (chunk)"),
             (fmt(N["nodes"]), "nút đồ thị") if N["nodes"] else ("6", "truy vấn crawl")]
    sw = (W - 2 * MX - Inches(0.3) * 3) / 4
    for i, (v, l) in enumerate(stats):
        x = int(MX + i * (sw + Inches(0.3)))
        box(s, x, Inches(1.45), int(sw), Inches(1.45), fill=CARD)
        text(s, x, Inches(1.55), int(sw), Inches(0.8), v, size=40, bold=True, font=HEAD, color=ACCENT,
             align=PP_ALIGN.CENTER)
        text(s, x, Inches(2.35), int(sw), Inches(0.4), l, size=14, color=MUTED, align=PP_ALIGN.CENTER)
    srcs = [("arXiv API", "Keyword (cụm \"...\" + AND), category, khoảng ngày, danh sách ID; 100 kết quả/trang, "
                          "nghỉ 3 s, thử lại khi lỗi"),
            ("PDF arxiv.org", "Toàn văn, section, danh sách tham khảo → cạnh CITES; kiểm tra chữ ký %PDF"),
            ("Kaggle snapshot", "Cornell-University/arxiv: ~2,7 triệu metadata, lọc theo category và năm"),
            ("Người dùng tải lên", "Kéo-thả 1 hoặc nhiều PDF; tự tra arXiv API để chuẩn hoá metadata")]
    for i, (t, d) in enumerate(srcs):
        y = Inches(3.35) + i * Inches(0.92)
        circle_num(s, MX, y + Inches(0.08), Inches(0.45), str(i + 1), size=13)
        text(s, MX + Inches(0.65), y + Inches(0.1), Inches(2.6), Inches(0.5), t, size=16, bold=True)
        text(s, MX + Inches(3.3), y + Inches(0.1), Inches(8.7), Inches(0.6), d, size=14, color=MUTED)
    footer(s, idx)

    # 7. Tổ chức dữ liệu
    idx += 1
    s = new_slide(prs, "Tổ chức dữ liệu: mỗi kho trả lời một kiểu truy vấn",
                  notes="SQLite là nguồn sự thật; ChromaDB và đồ thị có thể dựng lại hoàn toàn từ SQLite.")
    cards = [("SQLite", ["papers: metadata, refs, keywords, trạng thái",
                         "chunks: đoạn, trang, section, embedded", "Chỉ mục: arxiv_id, sha256, title_norm"]),
             ("ChromaDB", ["Collection chunks: vector đoạn văn", "Collection papers: vector tiêu đề + abstract",
                           "HNSW cosine, lọc theo paper_id / năm"]),
             ("BM25 Okapi", ["Chỉ mục từ vựng trong RAM", "Dựng lại lười khi có bài mới",
                             "Bắt thuật ngữ hiếm, tên mô hình"]),
             ("Đồ thị (KG)", ["Nút: paper, author, category, concept",
                                  "Cạnh: CITES, SIMILAR_TO, WRITTEN_BY, MENTIONS", "Lưu JSON, cập nhật tăng dần"])]
    cw = (W - 2 * MX - Inches(0.3) * 3) / 4
    for i, (t, b) in enumerate(cards):
        card(s, int(MX + i * (cw + Inches(0.3))), Inches(1.5), int(cw), Inches(3.3), t, b, num=str(i + 1),
             body_size=14)
    box(s, MX, Inches(5.1), W - 2 * MX, Inches(1.25), fill=ACCENT_SOFT)
    text(s, MX + Inches(0.3), Inches(5.2), W - 2 * MX - Inches(0.6), Inches(1.05),
         [[("Trạng thái pipeline mỗi bài: ", {"bold": True}),
           ("registered → embedded → graphed. ", {}),
           ("Nhờ cột trạng thái, từng module chạy lại độc lập: embedding chỉ xử lý chunk có embedded = 0, "
            "graph build chỉ lấy bài đã embedded.", {"color": MUTED})]], size=15, anchor=MSO_ANCHOR.MIDDLE)
    footer(s, idx)

    # 8. Luồng thêm PDF
    idx += 1
    s = new_slide(prs, "Thêm PDF: 3 lần kiểm tra trùng trước khi embedding",
                  notes="Kiểm tra rẻ trước (băm file), đắt sau (parse, gọi API). Bài trùng được báo lý do và gắn làm "
                        "focus để hỏi ngay.")
    steps = [("SHA-256", "trùng nội dung file?"), ("Parse PDF", "tiêu đề, arXiv ID, refs"),
             ("ID / tiêu đề", "trùng ID, tiêu đề, fuzzy ≥ 0,92?"), ("arXiv API", "metadata chuẩn, kiểm tra lần 3"),
             ("Chunk + embed", "ChromaDB + BM25"), ("Đồ thị", "tác giả, khái niệm, trích dẫn")]
    sw = Inches(1.82)
    gap = (W - 2 * MX - 6 * sw) / 5
    for i, (t, d) in enumerate(steps):
        x = int(MX + i * (sw + gap))
        gate = i in (0, 2, 3)
        box(s, x, Inches(1.8), int(sw), Inches(1.3), fill=ACCENT_SOFT if gate else CARD)
        text(s, x, Inches(1.92), int(sw), Inches(0.4), t, size=16, bold=True, align=PP_ALIGN.CENTER,
             color=ACCENT if gate else TEXT)
        text(s, x + Inches(0.1), Inches(2.35), int(sw) - Inches(0.2), Inches(0.7), d, size=13, color=MUTED,
             align=PP_ALIGN.CENTER)
        if i < 5:
            arrow(s, x + int(sw) + Inches(0.03), Inches(2.45), x + int(sw) + int(gap) - Inches(0.03), Inches(2.45))
    box(s, MX, Inches(3.55), Inches(5.9), Inches(2.0), fill=CARD)
    text(s, MX + Inches(0.3), Inches(3.7), Inches(5.4), Inches(0.4), "Nếu trùng", size=17, bold=True, font=HEAD,
         color=ACCENT)
    bullets(s, MX + Inches(0.3), Inches(4.2), Inches(5.4), Inches(1.9), [
        "Dừng ngay, không embedding lại",
        "Báo lý do: SHA-256 / arXiv ID / tiêu đề (độ giống)",
        "Gắn bài sẵn có làm focus để hỏi tiếp"], size=15, gap=6)
    box(s, Inches(6.83), Inches(3.55), Inches(5.9), Inches(2.0), fill=CARD)
    text(s, Inches(7.13), Inches(3.7), Inches(5.4), Inches(0.4), "Nếu là bài mới", size=17, bold=True, font=HEAD,
         color=ACCENT)
    bullets(s, Inches(7.13), Inches(4.2), Inches(5.4), Inches(1.9), [
        "Lưu PDF, metadata, refs vào SQLite",
        "Embedding đoạn + vector cấp bài, trích khái niệm (MMR)",
        "Thêm cạnh CITES hai chiều và SIMILAR_TO top-5"], size=15, gap=6)
    footer(s, idx)

    # 9. Tìm kiếm lai
    idx += 1
    s = new_slide(prs, "Tìm kiếm lai: BM25 + vector, gộp bằng RRF",
                  notes="RRF chỉ dùng thứ hạng nên không phải chuẩn hoá thang điểm giữa BM25 và cosine.")
    lanes = [("Câu hỏi", "tiếng Việt hoặc Anh"), ("BM25 top-50", "khớp từ vựng"), ("Dense top-50", "multilingual-e5")]
    box(s, MX, Inches(2.55), Inches(2.3), Inches(1.1), fill=INK)
    text(s, MX, Inches(2.65), Inches(2.3), Inches(0.4), "Câu hỏi", size=17, bold=True, color=WHITE,
         align=PP_ALIGN.CENTER)
    text(s, MX, Inches(3.05), Inches(2.3), Inches(0.4), "Việt hoặc Anh", size=13, color=RGBColor(0xC9, 0xC5, 0xB8),
         align=PP_ALIGN.CENTER)
    for j, (t, d) in enumerate(lanes[1:]):
        y = Inches(1.6) + j * Inches(1.9)
        box(s, Inches(3.5), y, Inches(2.6), Inches(1.1), fill=CARD)
        text(s, Inches(3.5), y + Inches(0.12), Inches(2.6), Inches(0.4), t, size=17, bold=True, align=PP_ALIGN.CENTER)
        text(s, Inches(3.5), y + Inches(0.52), Inches(2.6), Inches(0.4), d, size=13, color=MUTED, align=PP_ALIGN.CENTER)
        arrow(s, MX + Inches(2.33), Inches(3.1), Inches(3.47), y + Inches(0.55))
        arrow(s, Inches(6.13), y + Inches(0.55), Inches(7.07), Inches(3.1))
    box(s, Inches(7.1), Inches(2.5), Inches(2.4), Inches(1.2), fill=ACCENT_SOFT)
    text(s, Inches(7.1), Inches(2.6), Inches(2.4), Inches(0.4), "RRF, k = 60", size=17, bold=True, color=ACCENT,
         align=PP_ALIGN.CENTER)
    text(s, Inches(7.1), Inches(3.0), Inches(2.4), Inches(0.5), "Σ 1 / (k + rank)", size=15, color=TEXT,
         align=PP_ALIGN.CENTER, font=HEAD)
    arrow(s, Inches(9.53), Inches(3.1), Inches(10.07), Inches(3.1))
    box(s, Inches(10.1), Inches(2.5), Inches(2.63), Inches(1.2), fill=CARD)
    text(s, Inches(10.1), Inches(2.6), Inches(2.63), Inches(0.4), "Cấp bài báo", size=17, bold=True,
         align=PP_ALIGN.CENTER)
    text(s, Inches(10.2), Inches(3.0), Inches(2.43), Inches(0.6), "max + 0,3 × tổng còn lại", size=13, color=MUTED,
         align=PP_ALIGN.CENTER)
    bullets(s, MX, Inches(4.95), W - 2 * MX, Inches(1.4), [
        [("Chunk tóm tắt ", {"bold": True}), ("(tiêu đề + abstract) giúp bài không có PDF vẫn tìm được; chunk nội dung "
                                              "220 từ, chồng 40, gắn trang + section để trích dẫn.", {})],
        [("Embedding đa ngôn ngữ ", {"bold": True}), ("cho phép hỏi bằng tiếng Việt trên kho tiếng Anh; GPU fp16 trên "
                                                     "Kaggle, CPU khi demo.", {})]], size=15, gap=6)
    footer(s, idx)

    # 10. Đồ thị
    idx += 1
    nt, et = N["node_types"], N["edge_types"]
    s = new_slide(prs, "Đồ thị tri thức: bài liên quan có lý do giải thích được",
                  notes="Điểm liên quan cộng dồn theo đường đi 1–2 bước; thực thể phổ biến bị giảm trọng số theo log bậc.")
    erows = [("CITES", et.get("CITES", 0)), ("SIMILAR_TO", et.get("SIMILAR_TO", 0)),
             ("WRITTEN_BY", et.get("WRITTEN_BY", 0)), ("MENTIONS", et.get("MENTIONS", 0)),
             ("IN_CATEGORY", et.get("IN_CATEGORY", 0))]
    have = N["nodes"] > 0
    rows = [("paper", "bài báo", nt.get("paper", 0), ACCENT), ("author", "tác giả", nt.get("author", 0), BLUE),
            ("concept", "khái niệm (keyphrase)", nt.get("concept", 0), GREEN),
            ("category", "chuyên mục arXiv", nt.get("category", 0), MUTED)]
    text(s, MX, Inches(1.45), Inches(4.3), Inches(0.4), "4 loại nút", size=18, bold=True, font=HEAD, color=ACCENT)
    for i, (k, d, v, c) in enumerate(rows):
        y = Inches(1.95) + i * Inches(0.55)
        box(s, MX, y + Inches(0.1), Inches(0.26), Inches(0.26), fill=c, shape=MSO_SHAPE.OVAL)
        text(s, MX + Inches(0.42), y + Inches(0.04), Inches(1.3), Inches(0.4), k, size=15, bold=True)
        text(s, MX + Inches(1.65), y + Inches(0.05), Inches(2.0), Inches(0.4), d, size=14, color=MUTED)
        if have:
            text(s, MX + Inches(3.4), y + Inches(0.04), Inches(0.9), Inches(0.4), fmt(v), size=15, bold=True,
                 align=PP_ALIGN.RIGHT)
    text(s, MX, Inches(4.25), Inches(4.3), Inches(0.4), "5 loại cạnh", size=18, bold=True, font=HEAD, color=ACCENT)
    edesc = {"CITES": "paper → paper", "SIMILAR_TO": "cosine ≥ 0,75", "WRITTEN_BY": "paper → author",
             "MENTIONS": "paper → concept", "IN_CATEGORY": "paper → category"}
    for i, (k, v) in enumerate(erows):
        y = Inches(4.72) + i * Inches(0.33)
        text(s, MX, y, Inches(1.7), Inches(0.33), k, size=13, bold=True)
        text(s, MX + Inches(1.75), y, Inches(1.8), Inches(0.33), edesc[k], size=13, color=MUTED)
        if have:
            text(s, MX + Inches(3.4), y, Inches(0.9), Inches(0.33), fmt(v), size=13, bold=True, align=PP_ALIGN.RIGHT)
    box(s, Inches(5.2), Inches(1.5), Inches(7.53), Inches(4.85), fill=CARD)
    text(s, Inches(5.5), Inches(1.65), Inches(7), Inches(0.45), "Điểm liên quan của q với p", size=18, bold=True,
         font=HEAD)
    text(s, Inches(5.5), Inches(2.2), Inches(7), Inches(0.6),
         "score = 1[CITES] + cos(SIMILAR) + Σ w(e) / log₂(2 + deg e)", size=18, font=HEAD, color=ACCENT)
    bullets(s, Inches(5.5), Inches(2.95), Inches(6.9), Inches(3.3), [
        [("Trích dẫn ", {"bold": True}), ("(2 chiều, từ arXiv ID trong References): +1", {})],
        [("Tương đồng nội dung ", {"bold": True}), ("top-5 cosine ≥ 0,75 giữa vector bài", {})],
        [("Cùng tác giả ", {"bold": True}), ("w = 0,6 · cùng khái niệm w = 0,45 · cùng category 0,05", {})],
        [("Khái niệm ", {"bold": True}), ("trích bằng KeyBERT rút gọn: n-gram → cosine với bài → MMR", {})],
        [("Kết quả kèm lý do: ", {"bold": True}), ("“trích dẫn bài này · cùng khái niệm dense retrieval”", {})]],
        size=15, gap=8)
    footer(s, idx)

    # 11. Chatbot
    idx += 1
    s = new_slide(prs, "Chatbot: hai chế độ, một luồng Graph RAG",
                  notes="Auto: có focus thì Research, câu chào ngắn thì Chat. Câu hỏi được viết lại thành truy vấn "
                        "tiếng Anh độc lập trước khi truy xuất.")
    card(s, MX, Inches(1.5), Inches(3.9), Inches(2.3), "Chat", [
        "Trò chuyện, giải thích khái niệm", "Không truy xuất, phản hồi nhanh", "Gợi ý chuyển Research khi cần nguồn"],
        body_size=14)
    card(s, MX, Inches(4.05), Inches(3.9), Inches(2.3), "Research", [
        "Graph RAG + trích dẫn [n] bắt buộc", "Hỏi theo bài focus và bài liên quan",
        "Không đủ ngữ cảnh → nói rõ, không bịa"], body_size=14, fill=ACCENT_SOFT)
    flow = [("1", "Định tuyến", "focus / chào hỏi / mặc định"), ("2", "Viết lại câu hỏi", "truy vấn tiếng Anh độc lập"),
            ("3", "Hybrid search", "5 bài seed, 2 đoạn mỗi bài"), ("4", "Mở rộng đồ thị", "láng giềng + quan hệ thành câu"),
            ("5", "Sinh câu trả lời", "streaming SSE, trích dẫn [n]"), ("6", "Lưu hội thoại", "kèm nguồn và đồ thị con")]
    for i, (n_, t, d) in enumerate(flow):
        y = Inches(1.5) + i * Inches(0.81)
        circle_num(s, Inches(5.0), y + Inches(0.1), Inches(0.5), n_, size=14)
        text(s, Inches(5.7), y + Inches(0.05), Inches(3), Inches(0.4), t, size=17, bold=True)
        text(s, Inches(8.7), y + Inches(0.1), Inches(4.0), Inches(0.4), d, size=14, color=MUTED)
        if i < 5:
            c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(5.25), y + Inches(0.62), Inches(5.25),
                                       y + Inches(0.89))
            c.line.color.rgb = LINE
            c.line.width = Pt(1.5)
    footer(s, idx)

    # 12. vLLM
    idx += 1
    s = new_slide(prs, "Host LLM mã nguồn mở bằng vLLM trên Kaggle",
                  notes="Module llm_server: dò GPU, chọn float16 cho T4, tensor-parallel 2, chờ server sẵn sàng, mở "
                        "tunnel cloudflared và in 4 dòng .env cho laptop.")
    box(s, MX, Inches(1.5), Inches(6.6), Inches(1.0), fill=INK)
    text(s, MX + Inches(0.3), Inches(1.5), Inches(6.2), Inches(1.0),
         "python -m scholarlens.llm_server --preset qwen2.5-7b-awq --tunnel cloudflared",
         size=14, color=RGBColor(0xF0, 0xC8, 0xB4), font="Courier New", anchor=MSO_ANCHOR.MIDDLE)
    vsteps = [("Dò GPU", "T4 (cc 7.5) → float16; 2 GPU → tensor-parallel 2"),
              ("Chạy vLLM", "OpenAI API, prefix caching, enforce-eager trên T4"),
              ("Chờ sẵn sàng", "GET /v1/models trả 200, log ra data/llm_server"),
              ("Mở tunnel", "cloudflared hoặc ngrok → URL công khai"),
              ("In cấu hình", "4 dòng .env + gọi thử một câu")]
    for i, (t, d) in enumerate(vsteps):
        y = Inches(2.85) + i * Inches(0.7)
        circle_num(s, MX, y + Inches(0.05), Inches(0.45), str(i + 1), size=13)
        text(s, MX + Inches(0.65), y + Inches(0.07), Inches(1.8), Inches(0.4), t, size=16, bold=True)
        text(s, MX + Inches(2.5), y + Inches(0.09), Inches(4.2), Inches(0.5), d, size=14, color=MUTED)
    text(s, Inches(7.7), Inches(1.5), Inches(5), Inches(0.4), "Model gợi ý (preset)", size=18, bold=True, font=HEAD,
         color=ACCENT)
    presets = [("qwen2.5-7b-awq", "Qwen2.5-7B-Instruct-AWQ", "2×T4"), ("qwen2.5-3b", "Qwen2.5-3B-Instruct", "1×T4"),
               ("qwen2.5-1.5b", "Qwen2.5-1.5B-Instruct", "1×T4"),
               ("llama3.1-8b-awq", "Llama-3.1-8B-Instruct AWQ", "2×T4, HF_TOKEN"),
               ("qwen2.5-14b-awq", "Qwen2.5-14B-Instruct-AWQ", "2×T4, 8k ctx")]
    tbl = s.shapes.add_table(len(presets) + 1, 3, Inches(7.7), Inches(2.05), Inches(5.03), Inches(3.0)).table
    tbl.columns[0].width, tbl.columns[1].width, tbl.columns[2].width = Inches(1.5), Inches(2.13), Inches(1.4)
    for j, h in enumerate(["preset", "repo Hugging Face", "GPU"]):
        c = tbl.cell(0, j)
        c.text = h
    for i, row in enumerate(presets, 1):
        for j, v in enumerate(row):
            tbl.cell(i, j).text = v
    for i in range(len(presets) + 1):
        for j in range(3):
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = ACCENT if i == 0 else (CARD if i % 2 else WHITE)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(12.5)
                    r.font.name = BODY
                    r.font.bold = i == 0
                    r.font.color.rgb = WHITE if i == 0 else TEXT
    text(s, Inches(7.7), Inches(5.35), Inches(5.03), Inches(0.9),
         "Bất kỳ repo Hugging Face nào vLLM hỗ trợ: --model <repo>; tham số lạ sau -- được chuyển thẳng cho vLLM.",
         size=13, color=MUTED)
    footer(s, idx)

    # 13. Giao diện
    idx += 1
    s = new_slide(prs, "Giao diện: chat, nguồn và đồ thị cạnh nhau",
                  notes="Kéo-thả PDF vào cửa sổ; trích dẫn [n] bấm được mở đoạn gốc; tab Đồ thị vẽ vis-network.")
    shot = ROOT / "reports" / "img" / "app_research.png"
    if shot.exists():
        from PIL import Image
        im = Image.open(shot)
        iw, ih = im.size
        maxw, maxh = Inches(8.4), Inches(5.0)
        sc = min(maxw / iw, maxh / ih)
        pic = s.shapes.add_picture(str(shot), MX, Inches(1.45), int(iw * sc), int(ih * sc))
        pic.line.color.rgb = LINE
        px = MX + int(iw * sc) + Inches(0.35)
    else:
        box(s, MX, Inches(1.45), Inches(8.4), Inches(5.0), fill=CARD)
        px = MX + Inches(8.75)
    feats = [("Kéo-thả PDF", "tiến trình từng bước, từng file"), ("Chat / Research", "chuyển chế độ một chạm"),
             ("Trích dẫn [n]", "bấm để xem đoạn gốc"), ("Đồ thị", "bài, tác giả, khái niệm"),
             ("Thư viện + tìm kiếm", "BM25 / Dense / Hybrid")]
    for i, (t, d) in enumerate(feats):
        y = Inches(1.5) + i * Inches(0.98)
        text(s, px, y, W - MX - px, Inches(0.4), t, size=16, bold=True, color=ACCENT)
        text(s, px, y + Inches(0.38), W - MX - px, Inches(0.5), d, size=14, color=MUTED)
    footer(s, idx)

    # 14. Đánh giá
    idx += 1
    ev = N["eval"] or {}
    r = ev.get("retrieval", {})
    full = len(r) > 1
    s = new_slide(prs, "Đánh giá: truy xuất, kiểm tra trùng và đồ thị" if not full else
                  "Đánh giá: tìm kiếm lai cho kết quả tốt nhất",
                  notes="Known-item: truy vấn = tiêu đề, kho = abstract không chứa tiêu đề. Dedup: biến đổi tiêu đề "
                        "(chữ thường, bỏ dấu câu, bỏ 1 từ, thêm hậu tố) và kiểm tra nhầm trên toàn bộ tiêu đề thật.")
    if full:
        names = list(r.keys())
        short = [n.replace("Hybrid RRF", "Hybrid").replace("multilingual-e5-base", "e5").replace(
            "bge-base-en-v1.5", "bge") for n in names]
        cd = CategoryChartData()
        cd.categories = short
        cd.add_series("Recall@1", [r[n]["R@1"] for n in names])
        cd.add_series("Recall@10", [r[n]["R@10"] for n in names])
        cd.add_series("MRR@10", [r[n]["MRR@10"] for n in names])
        gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MX, Inches(1.4), Inches(8.1), Inches(4.9), cd)
        ch = gf.chart
        ch.has_title = True
        ch.chart_title.text_frame.text = f"Known-item retrieval, {ev['n_papers']} bài (truy vấn = tiêu đề)"
        tp = ch.chart_title.text_frame.paragraphs[0]
        tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.name = Pt(14), True, BODY
        tp.runs[0].font.color.rgb = TEXT
        ch.has_legend = True
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
        ch.legend.font.size, ch.legend.font.name = Pt(12), BODY
        for ser, col in zip(ch.plots[0].series, [RGBColor(0xE9, 0xC9, 0xB8), ACCENT, INK]):
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = col
        pl = ch.plots[0]
        pl.gap_width = 60
        pl.has_data_labels = True
        dl = pl.data_labels
        dl.number_format, dl.number_format_is_linked = "0.00", False
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        dl.font.size, dl.font.name = Pt(10), BODY
        dl.font.color.rgb = MUTED
        va = ch.value_axis
        va.maximum_scale, va.minimum_scale = 1.0, 0
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = LINE
        va.tick_labels.font.size, va.tick_labels.font.name = Pt(11), BODY
        va.tick_labels.font.color.rgb = MUTED
        va.format.line.fill.background()
        ca = ch.category_axis
        ca.tick_labels.font.size, ca.tick_labels.font.name = Pt(11), BODY
        ca.tick_labels.font.color.rgb = MUTED
        ca.format.line.color.rgb = LINE
    else:
        # chưa có kết quả dense/hybrid: hiện baseline BM25 + giao thức đánh giá
        bm = r.get("BM25")
        text(s, MX, Inches(1.45), Inches(8), Inches(0.4), f"Truy xuất known-item · {ev.get('n_papers', 0)} bài",
             size=18, bold=True, font=HEAD, color=ACCENT)
        if bm:
            for i, (k, l) in enumerate([("R@1", "Recall@1"), ("R@10", "Recall@10"), ("MRR@10", "MRR@10")]):
                x = MX + i * Inches(2.75)
                box(s, x, Inches(2.0), Inches(2.5), Inches(1.5), fill=CARD)
                text(s, x, Inches(2.1), Inches(2.5), Inches(0.8), f"{bm[k]:.3f}", size=36, bold=True, font=HEAD,
                     color=ACCENT, align=PP_ALIGN.CENTER)
                text(s, x, Inches(2.95), Inches(2.5), Inches(0.4), f"BM25 · {l}", size=13, color=MUTED,
                     align=PP_ALIGN.CENTER)
        bullets(s, MX, Inches(3.85), Inches(8.0), Inches(2.5), [
            [("Giao thức: ", {"bold": True}), ("truy vấn = tiêu đề, kho = abstract (không chứa tiêu đề), "
                                             "đáp án duy nhất là chính bài đó", {})],
            [("So sánh: ", {"bold": True}), ("BM25 · Dense (multilingual-e5, bge-base) · Hybrid RRF", {})],
            [("Dense / Hybrid: ", {"bold": True}), ("chạy scripts/evaluate.py trên máy GPU, rồi chạy lại "
                                                   "reports/build_slides.py để slide tự điền biểu đồ", {})]],
            size=15, gap=8)
    d, g = ev.get("dedup", {}), ev.get("graph")
    side = []
    if d:
        side += [(f"{d['detect_mutated_title'] * 100:.0f}%", "bắt được tiêu đề bị biến đổi (dedup)"),
                 (f"{d['false_positive_real_titles'] * 100:.0f}%", f"báo trùng nhầm trên {d['n_real']} tiêu đề thật")]
    if g:
        side.append((f"{g['same_category@5'] * 100:.0f}%", f"bài liên quan cùng category (ngẫu nhiên "
                                                           f"{g['random_baseline'] * 100:.0f}%)"))
    elif d:
        side.append((f"{d['detect_by_id'] * 100:.0f}%", "phát hiện trùng theo arXiv ID"))
    for i, (v, l) in enumerate(side):
        y = Inches(1.5) + i * Inches(1.6)
        box(s, Inches(9.0), y, Inches(3.73), Inches(1.4), fill=CARD)
        text(s, Inches(9.2), y + Inches(0.1), Inches(3.4), Inches(0.7), v, size=34, bold=True, font=HEAD,
             color=ACCENT)
        text(s, Inches(9.2), y + Inches(0.82), Inches(3.4), Inches(0.5), l, size=13, color=MUTED)
    footer(s, idx)

    # 15. Demo
    idx += 1
    s = new_slide(prs, "Kịch bản demo",
                  notes="Chuẩn bị: python -m scholarlens.app; 4 PDF trong demo_pdfs/ chưa có trong kho.")
    demo = [("Thêm 1 bài", "Kéo GraphRAG (2404.16130) vào cửa sổ → theo dõi 6 bước, bài tự thành focus"),
            ("Hỏi về bài", "“Tóm tắt bài này”, “Phương pháp chính là gì?” → trả lời có [n], bấm xem đoạn gốc"),
            ("Bài liên quan", "“Các bài liên quan đến bài này?” → danh sách + lý do, mở tab Đồ thị"),
            ("Thêm trùng", "Kéo lại cùng file → “đã có (trùng SHA-256)”, không embedding lại"),
            ("Thêm hàng loạt", "Chọn 3 PDF còn lại → bảng trạng thái từng file, rồi “So sánh các bài vừa thêm”")]
    for i, (t, d) in enumerate(demo):
        y = Inches(1.5) + i * Inches(0.98)
        box(s, MX, y, W - 2 * MX, Inches(0.82), fill=CARD if i % 2 == 0 else WHITE, line=None if i % 2 == 0 else LINE)
        circle_num(s, MX + Inches(0.2), y + Inches(0.16), Inches(0.5), str(i + 1), size=15)
        text(s, MX + Inches(0.9), y, Inches(2.6), Inches(0.82), t, size=17, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, MX + Inches(3.5), y, Inches(8.4), Inches(0.82), d, size=15, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
    footer(s, idx)

    # 16. Kết luận
    idx += 1
    s = new_slide(prs, "Kết luận và hướng phát triển", dark=True,
                  notes="Tóm tắt đóng góp, nêu hạn chế thật và hướng mở rộng.")
    text(s, MX, Inches(1.45), Inches(5.8), Inches(0.4), "Đã làm được", size=20, bold=True, font=HEAD, color=ACCENT)
    bullets(s, MX, Inches(2.0), Inches(5.8), Inches(4.4), [
        "7 module độc lập: crawl → ingest → embed → graph → chat → app, cộng host LLM bằng vLLM",
        "Thêm PDF tự động với 3 lần kiểm tra trùng",
        "Tìm kiếm lai + Graph RAG trả lời có trích dẫn, giải thích được bài liên quan",
        "Chạy được cả khi không có LLM (chế độ trích đoạn)"], size=16, color=RGBColor(0xE8, 0xE6, 0xDC), gap=10)
    text(s, Inches(7.0), Inches(1.45), Inches(5.7), Inches(0.4), "Hạn chế → hướng tiếp", size=20, bold=True,
         font=HEAD, color=ACCENT)
    bullets(s, Inches(7.0), Inches(2.0), Inches(5.7), Inches(4.4), [
        "Parse PDF bằng heuristic → GROBID / Nougat cho bảng, công thức",
        "Trích dẫn chỉ qua arXiv ID → khớp tiêu đề tài liệu tham khảo, Semantic Scholar API",
        "Khái niệm bằng n-gram → trích thực thể, quan hệ bằng LLM (GraphRAG đầy đủ)",
        "Chưa có reranker → cross-encoder bge-reranker cho top-20"], size=16,
        color=RGBColor(0xE8, 0xE6, 0xDC), gap=10)
    text(s, MX, H - Inches(0.9), W - 2 * MX, Inches(0.4), "Cảm ơn thầy cô và các bạn đã lắng nghe",
         size=16, color=RGBColor(0xA0, 0x9C, 0x90), italic=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print("Đã lưu", OUT, "—", len(prs.slides), "slide")


if __name__ == "__main__":
    build()
