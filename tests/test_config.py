from vaalikone.core.config import Settings


def test_settings_defaults():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5435/db",
        REDIS_URL="redis://localhost:6382/0",
    )
    assert settings.DEFAULT_LLM_MODEL == "gpt-6-luna"
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


def test_generic_llm_key_helpers(monkeypatch):
    from vaalikone.core.config import effective_api_key, get_settings

    monkeypatch.setenv("LLM_API_KEY", "testi-avain")
    monkeypatch.setenv("LLM_API_KEY_ENV", "MISTRAL_API_KEY")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert effective_api_key() == "testi-avain"
        assert get_settings().LLM_API_KEY_ENV == "MISTRAL_API_KEY"
    finally:
        get_settings.cache_clear()
