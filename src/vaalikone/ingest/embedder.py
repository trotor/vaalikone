import httpx
import litellm


async def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Get embedding vector for a single text."""
    if model.startswith("ollama/"):
        return await _ollama_embed(text, model.removeprefix("ollama/"))
    response = await litellm.aembedding(model=model, input=[text])
    return response.data[0]["embedding"]


async def get_embeddings_batch(
    texts: list[str], model: str = "text-embedding-3-small"
) -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    if model.startswith("ollama/"):
        # Ollama doesn't support true batching well via LiteLLM, call one by one
        return [await _ollama_embed(t, model.removeprefix("ollama/")) for t in texts]
    response = await litellm.aembedding(model=model, input=texts)
    return [item["embedding"] for item in response.data]


async def _ollama_embed(text: str, model_name: str) -> list[float]:
    """Direct Ollama API call for embeddings."""
    # Truncate very long texts to ~2000 words to avoid OOM
    words = text.split()
    if len(words) > 2000:
        text = " ".join(words[:2000])

    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(3):
            try:
                resp = await client.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": model_name, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(2)
                    continue
                raise
