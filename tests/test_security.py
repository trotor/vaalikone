import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.ingest.url_validation import UnsafeURLError, validate_public_url
from vaalikone.query.hybrid_search import escape_ilike

# --- ILIKE escaping ---

def test_escape_ilike_escapes_wildcards():
    assert escape_ilike("100%") == "100\\%"
    assert escape_ilike("a_b") == "a\\_b"
    assert escape_ilike("c\\d") == "c\\\\d"
    assert escape_ilike("normaali") == "normaali"


# --- SSRF URL validation ---

def test_validate_public_url_accepts_https():
    assert validate_public_url("https://www.eduskunta.fi/asiat", resolve_dns=False) == (
        "https://www.eduskunta.fi/asiat"
    )


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://localhost/admin",
    "http://127.0.0.1:8080/",
    "http://169.254.169.254/latest/meta-data",  # cloud metadata
    "http://10.0.0.5/internal",
    "http://[::1]/",
    "http://0.0.0.0/",
    "notaurl",
])
def test_validate_public_url_rejects_dangerous(url):
    with pytest.raises(UnsafeURLError):
        validate_public_url(url, resolve_dns=False)


def test_validate_public_url_rejects_localhost_dns():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://foo.localhost/", resolve_dns=False)
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://localhost.localdomain/", resolve_dns=False)


# --- API key auth ---

async def test_api_key_required_when_configured(monkeypatch):
    import vaalikone.api.deps as deps
    from vaalikone.core.config import get_settings

    monkeypatch.setenv("VAALIKONE_API_KEY", "testiavain")
    get_settings.cache_clear()
    try:
        from vaalikone.api.app import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/api/v1/stats")
            assert r.status_code == 401
            r = await ac.get("/api/v1/stats", headers={"X-API-Key": "vaara-avain"})
            assert r.status_code == 401
            r = await ac.get("/api/v1/stats", headers={"X-API-Key": "testiavain"})
            assert r.status_code == 200
            # health stays open
            r = await ac.get("/health")
            assert r.status_code == 200
    finally:
        monkeypatch.delenv("VAALIKONE_API_KEY")
        get_settings.cache_clear()
        deps.get_settings.cache_clear()


# --- Model allowlist ---

async def test_chat_rejects_model_not_in_allowlist(monkeypatch):
    from vaalikone.core.config import get_settings

    monkeypatch.setenv("CHAT_ALLOWED_MODELS", "gpt-4o,__text_only__")
    # Ei read-only-tilaa riippumatta .env:stä (CI:ssä ei ole LLM-avainta)
    monkeypatch.setenv("READ_ONLY_MODE", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-dummy-key")
    get_settings.cache_clear()
    try:
        from vaalikone.api.app import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # __text_only__ is in the allowlist -> 200 without an LLM call
            r = await ac.post(
                "/api/v1/chat", json={"question": "verotus", "model": "__text_only__"}
            )
            assert r.status_code == 200
            r = await ac.post("/api/v1/chat", json={"question": "test", "model": "evil-model"})
            assert r.status_code == 400
            assert "not allowed" in r.json()["detail"]
    finally:
        monkeypatch.delenv("CHAT_ALLOWED_MODELS")
        get_settings.cache_clear()


async def test_read_only_mode_blocks_llm_and_allows_text_only(monkeypatch):
    """Read-only mode: only __text_only__ chat, no LLM calls without API key."""
    from vaalikone.core.config import get_settings, is_read_only

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    get_settings.cache_clear()
    try:
        assert is_read_only() is True
        from vaalikone.api.app import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # LLM-malli kielletty
            r = await ac.post("/api/v1/chat", json={"question": "test", "model": "gpt-6-luna"})
            assert r.status_code == 403
            assert "Read-only" in r.json()["detail"]
            # __text_only__ toimii
            r = await ac.post(
                "/api/v1/chat", json={"question": "verotus", "model": "__text_only__"}
            )
            assert r.status_code == 200
            assert r.json()["model"] == "text-only"
            # oletusmalli menee read-onlyssä text-onlyksi
            r = await ac.post("/api/v1/chat", json={"question": "verotus"})
            assert r.status_code == 200
            # suggestions toimii ilman LLM:ää
            r = await ac.get("/api/v1/suggestions")
            assert r.status_code == 200
            assert len(r.json()["suggestions"]) > 0
            # connectivity näyttää read_only
            r = await ac.get("/api/v1/connectivity")
            assert r.json()["read_only"] is True
            assert r.json()["allowed_models"] == ["__text_only__"]
    finally:
        monkeypatch.delenv("READ_ONLY_MODE")
        get_settings.cache_clear()
