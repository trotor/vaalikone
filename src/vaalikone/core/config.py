import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6382/0"

    # Vanha OpenAI-avain toimii yhä (fallback)
    OPENAI_API_KEY: str | None = None

    # Yleinen LLM-konfiguraatio: mikä tahansa LiteLLM-provideri
    # (esim. mistral/mistral-small-latest, gpt-6-luna, ollama/qwen2.5:14b).
    # LLM_API_KEY_ENV kertoo mille ympäristömuuttujalle avain viedään
    # (litellm lukee esim. MISTRAL_API_KEY tai OPENAI_API_KEY automaattisesti).
    LLM_API_KEY: str | None = None
    LLM_API_KEY_ENV: str = "OPENAI_API_KEY"
    LLM_API_BASE: str | None = None  # valinnainen oma endpoint (esim. oma gateway)

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "gpt-6-luna"
    DEFAULT_EMBED_MODEL: str = "text-embedding-3-small"
    # Halpa malli kysymyssuggestioille ja muille pienille tehtäville
    CHEAP_LLM_MODEL: str = "gpt-6-luna"

    # If set, all /api/v1/* endpoints require the "X-API-Key" header with this value.
    VAALIKONE_API_KEY: str | None = None

    # Read-only mode: no LLM calls, no writes — only search/compare/stats.
    # Auto-enabled when no API key is configured and the default model is not local (ollama/).
    READ_ONLY_MODE: bool = False

    # Comma-separated allowlist of LLM models accepted by /api/v1/chat.
    # "__text_only__" (search results without an LLM) is always allowed.
    CHAT_ALLOWED_MODELS: str = ""

    # Eduskunnan avoimen datan osoitteet (vanha avoindata.eduskunta.fi siirtyy
    # uuteen palveluun vuoden 2027 alusta — vaihda tänne uusi osoite)
    EDUSKUNTA_API_URL: str = "https://avoindata.eduskunta.fi"
    EDUSKUNTA_SEARCH_URL: str = "https://api.eduskunta.fi"

    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_URL: str = "http://localhost:8083"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def allowed_chat_models(self) -> list[str]:
        """Parsed allowlist of chat models. Empty list = only DEFAULT_LLM_MODEL + __text_only__."""
        if not self.CHAT_ALLOWED_MODELS.strip():
            return [self.DEFAULT_LLM_MODEL, "__text_only__"]
        return [m.strip() for m in self.CHAT_ALLOWED_MODELS.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def effective_api_key() -> str | None:
    """LLM_API_KEY jos asetettu, muuten vanha OPENAI_API_KEY. Tyhjä = ei avainta."""
    s = get_settings()
    key = (s.LLM_API_KEY or s.OPENAI_API_KEY or "").strip()
    return key or None


def ensure_llm_env() -> None:
    """Vie API-avaimen oikeaan ympäristömuuttujaan, jonka litellm lukee."""
    key = effective_api_key()
    if key:
        os.environ.setdefault(get_settings().LLM_API_KEY_ENV, key)


def llm_api_base() -> str | None:
    """Mahdollinen oma API-endpoint (litellm:n api_base)."""
    return get_settings().LLM_API_BASE


def is_read_only() -> bool:
    """True when running without an LLM: explicit READ_ONLY_MODE, or no API key
    and the default model is not a local ollama/ model."""
    s = get_settings()
    if s.READ_ONLY_MODE:
        return True
    return effective_api_key() is None and not s.DEFAULT_LLM_MODEL.startswith("ollama/")
