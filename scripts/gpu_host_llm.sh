#!/usr/bin/env bash
# Chạy trên MÁY GPU: host LLM bằng vLLM + public qua trycloudflare.
#   bash scripts/gpu_host_llm.sh                       # preset mặc định qwen2.5-7b-awq
#   bash scripts/gpu_host_llm.sh --model Qwen/Qwen2.5-3B-Instruct
#   VLLM_API_KEY=my-secret bash scripts/gpu_host_llm.sh  # cố định API key giữa các lần chạy
# Kết thúc sẽ in URL https://<ngẫu-nhiên>.trycloudflare.com/v1 + API key:
# dán vào nút LLM trên giao diện app (hoặc file .env của máy demo).
set -euo pipefail
cd "$(dirname "$0")/.."

python -c "import vllm" 2>/dev/null || pip install -q vllm
python -c "import openai, dotenv" 2>/dev/null || pip install -q openai python-dotenv

if [ "$#" -eq 0 ]; then
  set -- --preset qwen2.5-7b-awq
fi
exec python -m scholarlens.llm_server "$@" --tunnel cloudflared
