import litellm


async def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Get embedding vector for a single text using LiteLLM."""
    response = await litellm.aembedding(model=model, input=[text])
    return response.data[0]["embedding"]


async def get_embeddings_batch(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    response = await litellm.aembedding(model=model, input=texts)
    return [item["embedding"] for item in response.data]
