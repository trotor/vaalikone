from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6382/0"

    OPENAI_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    DEFAULT_EMBED_MODEL: str = "text-embedding-3-small"

    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_URL: str = "http://localhost:8083"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
