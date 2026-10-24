"""Lớp trừu tượng LLM với 3 backend:

- anthropic : Claude qua Anthropic SDK (mặc định model claude-opus-5-5)
- openai    : mọi endpoint tương thích OpenAI — vLLM (module scholarlens.llm_server), Ollama,
              Gemini (https://generativelanguage.googleapis.com/v1beta/openai/), Groq, OpenAI...
- none      : không dùng LLM — chatbot trả lời theo kiểu trích đoạn (extractive)
"""
from __future__ import annotations

from typing import Iterator

from ..config import settings
from ..utils import get_logger

log = get_logger("llm")


class BaseLLM:
    name = "base"
    available = True
    model = ""

    def status(self) -> dict:
        return {"ok": self.available}

    def stream(self, system: str, messages: list[dict], effort: str = "medium",
               max_tokens: int | None = None) -> Iterator[str]:
        raise NotImplementedError

    def complete(self, system: str, messages: list[dict], effort: str = "low", max_tokens: int = 512) -> str:
        return "".join(self.stream(system, messages, effort=effort, max_tokens=max_tokens))


class NoLLM(BaseLLM):
    name = "none"
    available = False

    def stream(self, system, messages, effort="medium", max_tokens=None):
        yield ""


class AnthropicLLM(BaseLLM):
    name = "anthropic"

    def __init__(self, model: str = "", api_key: str = ""):
        import anthropic

        self.anthropic = anthropic
        # Không truyền api_key thì SDK tự đọc ANTHROPIC_API_KEY / profile `ant auth login`
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model or "claude-opus-5-5"

    def stream(self, system, messages, effort="medium", max_tokens=None):
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=max_tokens or settings.llm_max_tokens,
                system=system,
                messages=messages,
                output_config={"effort": effort},
                # tự chuyển sang model dự phòng nếu bộ lọc an toàn từ chối
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    yield text
                final = stream.get_final_message()
                if final.stop_reason == "refusal":
                    yield "\n\n*(Mô hình từ chối trả lời yêu cầu này.)*"
                elif final.stop_reason == "max_tokens":
                    yield "\n\n*(Câu trả lời bị cắt do giới hạn độ dài.)*"
        except self.anthropic.RateLimitError:
            yield "\n\n*(Lỗi: vượt giới hạn tốc độ API, thử lại sau ít giây.)*"
        except self.anthropic.APIStatusError as exc:
            yield f"\n\n*(Lỗi API {exc.status_code}: {exc.message})*"
        except self.anthropic.APIConnectionError:
            yield "\n\n*(Lỗi: không kết nối được Anthropic API.)*"


class OpenAICompatLLM(BaseLLM):
    name = "openai"

    def __init__(self, model: str, base_url: str = "", api_key: str = ""):
        import openai

        self.openai = openai
        self.base_url = base_url
        # endpoint ở xa (vLLM qua trycloudflare) có thể mất kết nối: timeout ngắn, thử lại 1 lần
        self.client = openai.OpenAI(base_url=base_url or None, api_key=api_key or "EMPTY",
                                    timeout=120, max_retries=1)
        self.model = model or self._first_model()

    def _first_model(self) -> str:
        try:  # vLLM / Ollama: lấy model đang được phục vụ
            return self.client.with_options(timeout=8, max_retries=0).models.list().data[0].id
        except Exception:
            return ""

    def status(self) -> dict:
        """Ping endpoint: {'ok': bool, 'models': [...], 'error': str}."""
        try:
            models = [m.id for m in self.client.with_options(timeout=6, max_retries=0).models.list().data]
            if not self.model and models:
                self.model = models[0]
            return {"ok": True, "models": models[:10]}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    def stream(self, system, messages, effort="medium", max_tokens=None):
        try:
            resp = self.client.chat.completions.create(
                model=self.model or self._first_model(), stream=True, temperature=0.3,
                max_tokens=max_tokens or min(settings.llm_max_tokens, 2048),
                messages=[{"role": "system", "content": system}] + messages)
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except self.openai.APIConnectionError:
            yield ("\n\n*(Không kết nối được LLM tại " + (self.base_url or "endpoint") +
                   ". Tunnel trycloudflare có thể đã đổi địa chỉ — cập nhật ở nút LLM trên giao diện.)*")
        except self.openai.APIError as exc:
            yield f"\n\n*(Lỗi LLM: {exc})*"
        except Exception as exc:  # đứt kết nối giữa chừng khi đang stream
            yield f"\n\n*(Mất kết nối LLM: {type(exc).__name__})*"


OPENAI_COMPAT = ("openai", "vllm", "ollama", "gemini", "groq")


def llm_config_path():
    return settings.data_dir / "llm_config.json"


def current_llm_config() -> dict:
    """Cấu hình LLM hiệu lực: data/llm_config.json (đặt từ giao diện) ghi đè biến môi trường."""
    import json

    cfg = {"provider": settings.llm_provider, "base_url": settings.llm_base_url,
           "model": settings.llm_model, "api_key": settings.llm_api_key}
    p = llm_config_path()
    if p.exists():
        try:
            cfg.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k in cfg})
        except (ValueError, OSError) as exc:
            log.warning("Bỏ qua %s: %s", p, exc)
    return cfg


def save_llm_config(cfg: dict) -> None:
    import json

    llm_config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def get_llm(cfg: dict | None = None) -> BaseLLM:
    cfg = cfg or current_llm_config()
    prov = (cfg.get("provider") or "none").lower()
    try:
        if prov == "anthropic":
            return AnthropicLLM(cfg.get("model", ""), cfg.get("api_key", ""))
        if prov in OPENAI_COMPAT:
            return OpenAICompatLLM(cfg.get("model", ""), cfg.get("base_url", ""), cfg.get("api_key", ""))
    except Exception as exc:
        log.warning("Không khởi tạo được LLM %s: %s — chuyển sang chế độ trích đoạn", prov, exc)
    return NoLLM()
