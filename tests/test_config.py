from vaalikone.core.config import Settings


def test_settings_defaults():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5435/db",
        REDIS_URL="redis://localhost:6382/0",
    )
    assert settings.DEFAULT_LLM_MODEL == "gpt-4o"
    assert settings.DEFAULT_EMBED_MODEL in ("text-embedding-3-small", "ollama/bge-m3")
    assert settings.KEYCLOAK_ENABLED is False
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"


def test_settings_custom_values():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5435/db",
        REDIS_URL="redis://localhost:6382/0",
        DEFAULT_LLM_MODEL="ollama/llama3",
        KEYCLOAK_ENABLED=True,
    )
    assert settings.DEFAULT_LLM_MODEL == "ollama/llama3"
    assert settings.KEYCLOAK_ENABLED is True
