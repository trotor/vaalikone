from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6382/0"

    OPENAI_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "gpt-6-luna"
    DEFAULT_EMBED_MODEL: str = "text-embedding-3-small"
    # Halpa malli kysymyssuggestioille ja muille pienille tehtäville
    CHEAP_LLM_MODEL: str = "gpt-6-luna"

    # If set, all /api/v1/* endpoints require the "X-API-Key" header with this value.
    VAALIKONE_API_KEY: str | None = None

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
