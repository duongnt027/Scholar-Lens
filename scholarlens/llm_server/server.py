"""Host một LLM trên Hugging Face bằng vLLM (OpenAI-compatible server) + tunnel public tuỳ chọn.

Luồng:
  1. Dò GPU -> chọn dtype (T4/P100 không hỗ trợ bf16 => float16) và tensor-parallel-size.
  2. Chạy `python -m vllm.entrypoints.openai.api_server` như tiến trình con, log ra file.
  3. Chờ GET /v1/models trả về 200.
  4. (tuỳ chọn) mở tunnel cloudflared / ngrok để máy demo gọi vào server trên Kaggle/Colab.
  5. In cấu hình .env để chatbot ScholarLens dùng: SL_LLM_PROVIDER=openai ...
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings
from ..utils import get_logger

log = get_logger("llm_server")

# Model gợi ý (đều có trên Hugging Face, kiến trúc vLLM hỗ trợ)
PRESETS = {
    "qwen2.5-7b-awq": dict(model="Qwen/Qwen2.5-7B-Instruct-AWQ", quantization="awq", max_model_len=16384),
    "qwen2.5-3b": dict(model="Qwen/Qwen2.5-3B-Instruct", max_model_len=16384),
    "qwen2.5-1.5b": dict(model="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=16384),
    "llama3.1-8b-awq": dict(model="hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4", quantization="awq",
                            max_model_len=16384),
    "qwen2.5-14b-awq": dict(model="Qwen/Qwen2.5-14B-Instruct-AWQ", quantization="awq", max_model_len=8192),
}
# Cloudflare chặn User-Agent mặc định "Python-urllib" (lỗi 1010) -> luôn gửi UA riêng
HTTP_HEADERS = {"User-Agent": "ScholarLens/1.0 (+llm_server)"}
_PROCS: dict[int, subprocess.Popen] = {}  # pid -> tiến trình con (vLLM, tunnel) để kiểm tra/kết thúc an toàn
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


@dataclass
class ServerConfig:
    model: str
    served_name: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    dtype: str = "auto"
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.90
    tensor_parallel_size: int = 0  # 0 = tự động theo số GPU
    quantization: str = ""
    api_key: str = ""
    enforce_eager: bool = False
    trust_remote_code: bool = False
    extra_args: list[str] = field(default_factory=list)


def gpu_info() -> list[dict]:
    try:
        import torch
        if not torch.cuda.is_available():
            return []
        out = []
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i)
            out.append({"name": p.name, "cc": p.major + p.minor / 10, "mem_gb": round(p.total_memory / 2**30, 1)})
        return out
    except ImportError:
        return []


def resolve_config(cfg: ServerConfig) -> ServerConfig:
    gpus = gpu_info()
    if not gpus:
        raise RuntimeError("Không thấy GPU CUDA. vLLM cần GPU (Kaggle: Settings → Accelerator → GPU T4 x2).")
    log.info("GPU: %s", gpus)
    if cfg.dtype == "auto":
        # bf16 cần compute capability >= 8.0 (Ampere); T4 = 7.5, P100 = 6.0
        cfg.dtype = "bfloat16" if min(g["cc"] for g in gpus) >= 8.0 else "float16"
    if cfg.tensor_parallel_size <= 0:
        cfg.tensor_parallel_size = 2 if len(gpus) >= 2 else 1
    if not cfg.served_name:
        cfg.served_name = cfg.model.split("/")[-1]
    if not cfg.api_key:
        cfg.api_key = os.environ.get("VLLM_API_KEY") or "sl-" + secrets.token_hex(12)
    if min(g["cc"] for g in gpus) < 8.0 and not cfg.enforce_eager:
        cfg.enforce_eager = True  # tiết kiệm VRAM cho CUDA graph trên T4
    return cfg


def build_command(cfg: ServerConfig) -> list[str]:
    cmd = [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
           "--model", cfg.model, "--served-model-name", cfg.served_name,
           "--host", cfg.host, "--port", str(cfg.port), "--dtype", cfg.dtype,
           "--max-model-len", str(cfg.max_model_len),
           "--gpu-memory-utilization", str(cfg.gpu_memory_utilization),
           "--tensor-parallel-size", str(cfg.tensor_parallel_size),
           "--api-key", cfg.api_key, "--enable-prefix-caching"]
    if cfg.quantization:
        cmd += ["--quantization", cfg.quantization]
    if cfg.enforce_eager:
        cmd.append("--enforce-eager")
    if cfg.trust_remote_code:
        cmd.append("--trust-remote-code")
    return cmd + cfg.extra_args


def _hint(log_tail: str) -> str:
    """Gợi ý cách sửa cho các lỗi môi trường hay gặp trên Kaggle/Colab."""
    hints = {
        "TorchAudio were compiled with different CUDA": "torchaudio cài sẵn lệch CUDA với torch mới: chạy "
                                                      "`!pip uninstall -y torchaudio` rồi chạy lại.",
        "TorchVision": "torchvision lệch phiên bản với torch: `!pip install -U torchvision` hoặc gỡ đi.",
        "out of memory": "Hết VRAM: giảm max_model_len / gpu_memory_utilization hoặc dùng preset nhỏ hơn "
                         "(qwen2.5-3b).",
        "Bfloat16 is only supported": "GPU không hỗ trợ bf16: đặt dtype='float16'.",
        "gated repo": "Model cần quyền truy cập: chấp nhận điều khoản trên Hugging Face và đặt HF_TOKEN.",
    }
    found = [h for k, h in hints.items() if k.lower() in log_tail.lower()]
    return ("\n\nGỢI Ý: " + " ".join(found)) if found else ""


def wait_ready(port: int, api_key: str, proc: subprocess.Popen, timeout: int = 1200) -> bool:
    url = f"http://127.0.0.1:{port}/v1/models"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        try:
            req = urllib.request.Request(url, headers={**HTTP_HEADERS, "Authorization": f"Bearer {api_key}"})
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def _cloudflared_bin() -> str:
    found = shutil.which("cloudflared")
    if found:
        return found
    dest = Path.home() / ".cache" / "scholarlens" / "cloudflared"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Tải cloudflared…")
        urllib.request.urlretrieve(CLOUDFLARED_URL, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    return str(dest)


def open_tunnel(kind: str, port: int, log_dir: Path) -> tuple[str, subprocess.Popen | None]:
    """Trả về (public_url, tiến trình tunnel)."""
    if kind == "cloudflared":
        logf = open(log_dir / "cloudflared.log", "w")
        proc = subprocess.Popen([_cloudflared_bin(), "tunnel", "--url", f"http://localhost:{port}",
                                 "--no-autoupdate"], stdout=logf, stderr=subprocess.STDOUT)
        _PROCS[proc.pid] = proc
        for _ in range(60):
            time.sleep(1)
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", (log_dir / "cloudflared.log").read_text())
            if m:
                return m.group(0), proc
        raise RuntimeError("Không lấy được URL cloudflared, xem cloudflared.log")
    if kind == "ngrok":
        from pyngrok import ngrok  # pip install pyngrok ; cần NGROK_AUTHTOKEN
        if os.environ.get("NGROK_AUTHTOKEN"):
            ngrok.set_auth_token(os.environ["NGROK_AUTHTOKEN"])
        return ngrok.connect(port, "http").public_url, None
    return "", None


def env_snippet(base_url: str, cfg: ServerConfig) -> str:
    return (f"SL_LLM_PROVIDER=openai\nSL_LLM_BASE_URL={base_url.rstrip('/')}/v1\n"
            f"SL_LLM_MODEL={cfg.served_name}\nSL_LLM_API_KEY={cfg.api_key}\n")


def smoke_test(base_url: str, cfg: ServerConfig) -> str:
    import openai
    client = openai.OpenAI(base_url=base_url.rstrip("/") + "/v1", api_key=cfg.api_key)
    r = client.chat.completions.create(model=cfg.served_name, max_tokens=64, messages=[
        {"role": "user", "content": "Giải thích ngắn gọn Retrieval-Augmented Generation trong 1 câu."}])
    return r.choices[0].message.content


def serve(cfg: ServerConfig, tunnel: str = "none", test: bool = True, detach: bool = False) -> dict:
    cfg = resolve_config(cfg)
    log_dir = settings.data_dir / "llm_server"
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(cfg)
    log.info("Chạy: %s", " ".join(c if c != cfg.api_key else "***" for c in cmd))
    logf = open(log_dir / "vllm.log", "w")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env={**os.environ})
    _PROCS[proc.pid] = proc
    (log_dir / "vllm.pid").write_text(str(proc.pid))
    log.info("Đang nạp model (có thể mất vài phút để tải trọng số từ Hugging Face)… log: %s", log_dir / "vllm.log")
    if not wait_ready(cfg.port, cfg.api_key, proc):
        tail = (log_dir / "vllm.log").read_text(errors="ignore")[-3000:]
        proc.terminate()
        raise RuntimeError("vLLM không khởi động được:\n" + tail + _hint(tail))
    local = f"http://127.0.0.1:{cfg.port}"
    public, tproc = open_tunnel(tunnel, cfg.port, log_dir) if tunnel != "none" else ("", None)
    if public:
        log.info("Tunnel %s — chờ DNS có hiệu lực…", public)
        if not wait_public(public + "/v1", cfg.api_key):
            log.warning("URL công khai chưa phản hồi sau 120 s; vẫn in ra, thử lại sau ít phút")
    base = public or local
    info = {"local_url": local + "/v1", "public_url": (public + "/v1") if public else "",
            "model": cfg.served_name, "api_key": cfg.api_key, "pid": proc.pid,
            "tunnel": tunnel, "tunnel_pid": tproc.pid if tproc else None, "port": cfg.port}
    snippet = env_snippet(base, cfg)
    (log_dir / "llm.env").write_text(snippet)
    print("\n================ vLLM sẵn sàng ================")
    print(f"Model : {cfg.model}  (served as '{cfg.served_name}', dtype={cfg.dtype}, tp={cfg.tensor_parallel_size})")
    print(f"Local : {info['local_url']}")
    if public:
        print(f"Public: {info['public_url']}")
    print("Trên máy demo: bấm nút LLM (góc phải ô chat) và dán Base URL + API key ở trên,\n"
          "hoặc dán 4 dòng sau vào file .env rồi `docker compose up -d`:\n" + snippet)
    if public:
        print("Lưu ý: URL trycloudflare đổi mỗi lần chạy lại tunnel. Đặt VLLM_API_KEY cố định để chỉ phải đổi URL.")
    if test:
        try:
            print("Thử gọi:", smoke_test(local, cfg))
        except Exception as exc:
            print("Smoke test lỗi:", exc)
    if detach:
        return info
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        if tproc:
            tproc.terminate()
    return info


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    if pid in _PROCS:
        return _PROCS[pid].poll() is None
    if os.name == "nt":  # trên Windows os.kill(pid, 0) không phải phép thử an toàn
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate(pid: int | None) -> None:
    try:
        if pid in _PROCS:
            _PROCS.pop(pid).terminate()
        elif pid and os.name != "nt":
            os.kill(pid, 15)
    except OSError:
        pass


def _url_ok(url: str, api_key: str, timeout: int = 10) -> bool:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/models",
                                     headers={**HTTP_HEADERS, "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wait_public(url: str, api_key: str, timeout: int = 120) -> bool:
    """Chờ URL tunnel mới gọi được (DNS trycloudflare cần vài giây đến ~1 phút)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _url_ok(url, api_key, timeout=8):
            return True
        time.sleep(4)
    return False


def keep_alive(info: dict, every: int = 120, max_hours: float = 11.5) -> None:
    """Giữ phiên notebook (Kaggle/Colab) hoạt động và tự mở lại tunnel nếu nó chết.

    In trạng thái định kỳ; khi URL công khai đổi thì in to URL mới để dán vào nút LLM trên app.
    """
    log_dir = settings.data_dir / "llm_server"
    t_end = time.time() + max_hours * 3600
    fails = 0
    while time.time() < t_end:
        if not _alive(info["pid"]):
            tail = (log_dir / "vllm.log").read_text(errors="ignore")[-2000:]
            print("vLLM đã dừng! Log cuối:\n" + tail)
            return
        local_ok = _url_ok(info["local_url"], info["api_key"])
        pub_ok = _url_ok(info["public_url"], info["api_key"]) if info.get("public_url") else True
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] vLLM {'OK' if local_ok else 'LỖI'} · tunnel {'OK' if pub_ok else 'LỖI'} · "
              f"{info.get('public_url') or info['local_url']}", flush=True)
        fails = 0 if pub_ok else fails + 1
        if info.get("tunnel") not in (None, "none") and fails >= 2:
            print("Tunnel không phản hồi — mở tunnel mới…", flush=True)
            try:
                _terminate(info.get("tunnel_pid"))
                public, tproc = open_tunnel(info["tunnel"], info["port"], log_dir)
                info.update(public_url=public + "/v1", tunnel_pid=tproc.pid if tproc else None)
                wait_public(info["public_url"], info["api_key"])
                (log_dir / "llm.env").write_text(
                    f"SL_LLM_PROVIDER=openai\nSL_LLM_BASE_URL={info['public_url']}\n"
                    f"SL_LLM_MODEL={info['model']}\nSL_LLM_API_KEY={info['api_key']}\n")
                print("\n" + "=" * 60 + f"\nURL MỚI: {info['public_url']}\n(dán vào nút LLM trên app)\n" + "=" * 60,
                      flush=True)
                fails = 0
            except Exception as exc:
                print("Mở lại tunnel lỗi:", exc, flush=True)
        time.sleep(every)
    print("Hết thời gian giữ phiên.")


def stop() -> None:
    pid_file = settings.data_dir / "llm_server" / "vllm.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text()), 15)
            print("Đã dừng vLLM pid", pid_file.read_text())
        except (ProcessLookupError, ValueError):
            pass
        pid_file.unlink()
