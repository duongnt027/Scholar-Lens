"""Host LLM Hugging Face bằng vLLM (chạy độc lập, cần GPU).

  pip install vllm                     # Kaggle: GPU T4 x2
  python -m scholarlens.llm_server --preset qwen2.5-7b-awq --tunnel cloudflared
  python -m scholarlens.llm_server --model Qwen/Qwen2.5-3B-Instruct --max-model-len 8192
  python -m scholarlens.llm_server --model <repo HF bất kỳ vLLM hỗ trợ> --detach   # chạy nền (notebook)
  python -m scholarlens.llm_server stop
  python -m scholarlens.llm_server presets

Model gated (Llama...) cần biến môi trường HF_TOKEN. Tham số lạ (sau `--`) được chuyển thẳng cho vLLM.
"""
import argparse
import sys

from .server import PRESETS, ServerConfig, serve, stop


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["stop"]:
        return stop()
    if argv[:1] == ["presets"]:
        for k, v in PRESETS.items():
            print(f"{k:18} {v['model']}")
        return
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="scholarlens.llm_server", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="repo Hugging Face, ví dụ Qwen/Qwen2.5-7B-Instruct-AWQ")
    ap.add_argument("--preset", choices=list(PRESETS))
    ap.add_argument("--served-name", default="")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--dtype", default="auto")
    ap.add_argument("--max-model-len", type=int)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--tp", type=int, default=0, help="tensor parallel size (0 = tự động)")
    ap.add_argument("--quantization", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--trust-remote-code", action="store_true")
    ap.add_argument("--tunnel", default="none", choices=["none", "cloudflared", "ngrok"])
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--detach", action="store_true", help="trả về ngay sau khi server sẵn sàng")
    a = ap.parse_args(argv)
    if not a.model and not a.preset:
        ap.error("cần --model hoặc --preset")
    p = PRESETS.get(a.preset, {})
    cfg = ServerConfig(model=a.model or p["model"], served_name=a.served_name, port=a.port, dtype=a.dtype,
                       max_model_len=a.max_model_len or p.get("max_model_len", 8192),
                       gpu_memory_utilization=a.gpu_mem, tensor_parallel_size=a.tp,
                       quantization=a.quantization or p.get("quantization", ""), api_key=a.api_key,
                       trust_remote_code=a.trust_remote_code, extra_args=extra)
    serve(cfg, tunnel=a.tunnel, test=not a.no_test, detach=a.detach)


if __name__ == "__main__":
    main()
