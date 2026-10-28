import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm: str = os.getenv("CIEL_LLM", "ollama")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model: str = os.getenv("CIEL_MODEL", "qwen3:8b")
    think: bool = _bool(os.getenv("CIEL_THINK", "false"))
    # render the Qwen3 (ChatML) prompt ourselves and call /api/generate raw — keeps the prompt cache across turns
    raw_prompt: bool = _bool(os.getenv("CIEL_RAW_PROMPT", "true"))
    temperature: float = float(os.getenv("CIEL_TEMPERATURE", "0.7"))
    num_ctx: int = int(os.getenv("CIEL_NUM_CTX", "8192"))
    keep_alive: str = os.getenv("CIEL_KEEP_ALIVE", "-1")  # -1 = keep the model loaded forever
    num_predict: int = int(os.getenv("CIEL_NUM_PREDICT", "150"))
    max_history: int = int(os.getenv("CIEL_MAX_HISTORY", "20"))
    # the model is fine-tuned on training/: it gets the short system prompt it was
    # trained with and no example chats (Persona.tuned_prompt)
    tuned: bool = _bool(os.getenv("CIEL_TUNED", "false"))
    persona_path: Path = ROOT / os.getenv("CIEL_PERSONA", "persona/ciel.yaml")
    host: str = os.getenv("CIEL_HOST", "127.0.0.1")
    port: int = int(os.getenv("CIEL_PORT", "47080"))
    password: str = os.getenv("CIEL_PASSWORD", "")
    tts: str = os.getenv("CIEL_TTS", "edge")
    auto_update: bool = _bool(os.getenv("CIEL_AUTO_UPDATE", "false"))
    update_branch: str = os.getenv("CIEL_UPDATE_BRANCH", "main")
    update_interval: int = int(os.getenv("CIEL_UPDATE_INTERVAL", "60"))


settings = Settings()
