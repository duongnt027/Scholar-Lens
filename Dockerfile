# ScholarLens web app — chạy trên máy demo (CPU). LLM nằm ở máy GPU, gọi qua URL trycloudflare.
#   docker compose up -d --build      ->  http://localhost:7860
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    SL_DATA_DIR=/app/data \
    SL_EMBED_DEVICE=cpu

WORKDIR /app

# torch bản CPU (~200 MB thay vì vài GB bản CUDA)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-app.txt .
RUN pip install -r requirements-app.txt

# Tải sẵn model embedding vào image: demo không cần mạng để nạp model.
# Phải trùng với model đã dùng khi embedding trên máy GPU.
ARG EMBED_MODEL=intfloat/multilingual-e5-base
ENV SL_EMBED_MODEL=${EMBED_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('${EMBED_MODEL}')"
ENV HF_HUB_OFFLINE=1

COPY scholarlens ./scholarlens

EXPOSE 7860
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/stats', timeout=4)"

CMD ["python", "-m", "scholarlens.app", "--host", "0.0.0.0", "--port", "7860"]
