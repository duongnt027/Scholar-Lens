"""Web app ScholarLens: FastAPI backend + giao diện chat kiểu Claude (static/).

Chạy:  python -m scholarlens.app   (mặc định http://127.0.0.1:7860)
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..chat.llm import OPENAI_COMPAT, current_llm_config, save_llm_config
from ..config import settings
from ..services import Services
from ..utils import get_logger

log = get_logger("app")
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="ScholarLens", version="1.0")
JOBS: dict[str, dict] = {}


def svc() -> Services:
    return Services.get()


@app.on_event("startup")
def _warmup():
    def run():
        s = svc()
        s.embedder()          # nạp model embedding
        s.bm25.search("warmup")  # dựng chỉ mục BM25
        log.info("Sẵn sàng: %s", s.db.stats())
    threading.Thread(target=run, daemon=True).start()


# ---------------- thông tin chung ----------------
@app.get("/api/stats")
def stats():
    s = svc()
    return {"db": s.db.stats(), "vectors": s.vs.stats(), "graph": s.kg.stats(), "llm": s.llm.name,
            "llm_model": getattr(s.llm, "model", ""), "embed_model": settings.embed_model}


# ---------------- cấu hình LLM (đổi được khi đang chạy) ----------------
class LLMConfig(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    model: str = ""
    api_key: str | None = None  # None = giữ khoá cũ


def _public_llm(cfg: dict) -> dict:
    key = cfg.get("api_key") or ""
    return {"provider": cfg.get("provider", "none"), "base_url": cfg.get("base_url", ""),
            "model": cfg.get("model", ""), "api_key_set": bool(key),
            "api_key_hint": (key[:3] + "…" + key[-4:]) if len(key) > 8 else ""}


@app.get("/api/llm")
def llm_get():
    s = svc()
    return {**_public_llm(current_llm_config()), "active": s.llm.name,
            "active_model": s.llm.model, "status": s.llm.status()}


@app.post("/api/llm")
def llm_set(req: LLMConfig):
    cfg = current_llm_config()
    base = req.base_url.strip().rstrip("/")
    if base and req.provider in OPENAI_COMPAT and not base.endswith("/v1") and "googleapis" not in base:
        base += "/v1"  # tiện khi dán thẳng URL trycloudflare
    cfg.update({"provider": req.provider, "base_url": base, "model": req.model.strip()})
    if req.api_key is not None:
        cfg["api_key"] = req.api_key.strip()
    s = svc()
    s.set_llm(cfg)
    st = s.llm.status()
    if req.provider in OPENAI_COMPAT and not cfg["model"] and s.llm.model:
        cfg["model"] = s.llm.model
    save_llm_config(cfg)
    return {**_public_llm(cfg), "active": s.llm.name, "active_model": s.llm.model, "status": st}


# ---------------- thư viện bài báo ----------------
@app.get("/api/papers")
def papers(q: str = "", limit: int = 50, offset: int = 0):
    rows = svc().db.list_papers(q, limit, offset)
    return [{k: p[k] for k in ("paper_id", "title", "authors", "year", "primary_category", "source",
                               "has_fulltext", "status", "keywords")} for p in rows]


@app.get("/api/papers/{paper_id:path}/pdf")
def paper_pdf(paper_id: str):
    p = svc().db.get_paper(paper_id)
    if not p or not p["pdf_path"] or not Path(p["pdf_path"]).exists():
        raise HTTPException(404, "Không có PDF")
    return FileResponse(p["pdf_path"], media_type="application/pdf")


@app.get("/api/papers/{paper_id:path}")
def paper_detail(paper_id: str):
    s = svc()
    p = s.db.get_paper(paper_id)
    if not p:
        raise HTTPException(404, "Không tìm thấy bài báo")
    p.pop("title_norm", None)
    return {"paper": p, "related": s.kg.related_papers(paper_id, k=10),
            "graph": s.kg.subgraph([paper_id], related_per_paper=8)}


# ---------------- tìm kiếm (không qua chatbot) ----------------
@app.get("/api/search")
def search(q: str, k: int = 10, mode: str = "hybrid", year_from: int | None = None):
    t0 = time.time()
    hits = svc().retriever.search_papers(q, k=k, mode=mode, year_from=year_from)
    return {"took_ms": round((time.time() - t0) * 1000), "mode": mode, "results": [
        {"paper_id": h["paper"]["paper_id"], "title": h["paper"]["title"], "authors": h["paper"]["authors"][:5],
         "year": h["paper"]["year"], "category": h["paper"]["primary_category"], "score": h["score"],
         "snippet": h["chunks"][0]["text"][:400] if h["chunks"] else "",
         "url": f"https://arxiv.org/abs/{h['paper']['arxiv_id']}" if h["paper"]["arxiv_id"] else ""}
        for h in hits]}


# ---------------- đồ thị ----------------
@app.get("/api/graph")
def graph(paper_id: str | None = None, limit: int = 60):
    kg = svc().kg
    return kg.subgraph([paper_id], related_per_paper=8) if paper_id else kg.overview(limit)


# ---------------- upload + ingest ----------------
def _run_job(job_id: str, files: list[Path]):
    s = svc()
    job = JOBS[job_id]
    for i, f in enumerate(files):
        item = job["items"][i]
        item["state"] = "running"

        def step(msg, item=item):
            item["steps"].append(msg)
            item["current"] = msg
        with s.ingest_lock:
            r = s.ingest.add_pdf(f, log_step=step)
        item.update({"state": r.status, "paper_id": r.paper_id, "title": r.title, "reason": r.reason,
                     "info": r.info, "current": ""})
        try:
            f.unlink()
        except OSError:
            pass
    job["done"] = True
    job["finished"] = time.time()


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    job_id = uuid.uuid4().hex[:10]
    saved = []
    items = []
    for uf in files:
        if not uf.filename.lower().endswith(".pdf"):
            items.append({"file": uf.filename, "state": "error", "reason": "Chỉ nhận file PDF", "steps": []})
            continue
        dest = settings.upload_dir / f"{job_id}_{Path(uf.filename).name}"
        with open(dest, "wb") as out:
            shutil.copyfileobj(uf.file, out)
        saved.append(dest)
        items.append({"file": uf.filename, "state": "queued", "steps": [], "current": ""})
    JOBS[job_id] = {"id": job_id, "items": [it for it in items if it["state"] != "error"] + [
        it for it in items if it["state"] == "error"], "done": not saved, "started": time.time()}
    if saved:
        threading.Thread(target=_run_job, args=(job_id, saved), daemon=True).start()
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404)
    return JOBS[job_id]


# ---------------- chat ----------------
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    mode: str = "auto"
    focus_ids: list[str] | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    def gen():
        try:
            for ev in svc().chatbot.respond(req.message, req.conversation_id, req.mode, req.focus_ids):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            log.exception("chat lỗi")
            yield f"data: {json.dumps({'type': 'token', 'text': f'*(Lỗi: {exc})*'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/conversations")
def conversations():
    return svc().chatbot.store.list()


@app.get("/api/conversations/{cid}")
def conversation(cid: str):
    c = svc().chatbot.store.get(cid)
    if not c:
        raise HTTPException(404)
    return c


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    svc().chatbot.store.delete(cid)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
