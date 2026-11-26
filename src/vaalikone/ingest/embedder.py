import httpx
import litellm

from vaalikone.core.config import ensure_llm_env, llm_api_base

ensure_llm_env()


async def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Get embedding vector for a single text."""
    if model.startswith("ollama/"):
        return await _ollama_embed(text, model.removeprefix("ollama/"))
    response = await litellm.aembedding(model=model, input=[text], api_base=llm_api_base())
    return response.data[0]["embedding"]


async def get_embeddings_batch(
    texts: list[str], model: str = "text-embedding-3-small"
) -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    if model.startswith("ollama/"):
        # Ollama doesn't support true batching well via LiteLLM, call one by one
        return [await _ollama_embed(t, model.removeprefix("ollama/")) for t in texts]
    response = await litellm.aembedding(model=model, input=texts, api_base=llm_api_base())
    return [item["embedding"] for item in response.data]


class _ContextTooLongError(Exception):
    pass


async def _ollama_embed(text: str, model_name: str) -> list[float]:
    """Direct Ollama API call for embeddings.

    Jos teksti ylittää mallin kontekstin (esim. saamenkielinen teksti tokenisoituu
    hyvin tiheästi), se jaetaan kahtia ja puolikkaiden upotukset keskiarvoistetaan.
    """
    # Truncate very long texts to ~2000 words to avoid OOM
    words = text.split()
    if len(words) > 2000:
        text = " ".join(words[:2000])
    try:
        return await _ollama_embed_once(text, model_name)
    except _ContextTooLongError:
        words = text.split()
        if len(words) < 2:
            raise
        mid = len(words) // 2
        left = await _ollama_embed(" ".join(words[:mid]), model_name)
        right = await _ollama_embed(" ".join(words[mid:]), model_name)
        return [(a + b) / 2 for a, b in zip(left, right)]


async def _ollama_embed_once(text: str, model_name: str) -> list[float]:
    import asyncio

    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(3):
            try:
                resp = await client.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": model_name, "prompt": text},
                )
                if resp.status_code == 500 and "context length" in resp.text:
                    raise _ContextTooLongError(resp.text)
                resp.raise_for_status()
                return resp.json()["embedding"]
            except (httpx.HTTPStatusError, httpx.ConnectError):
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                raise
