def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    """Split text into overlapping chunks of approximately chunk_size tokens.

    Uses simple word-based splitting (not tiktoken) for speed.
    Returns list of {"index": int, "text": str}
    """
    words = text.split()
    chunks = []
    chunk_idx = 0
    i = 0

    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunk_text_str = " ".join(chunk_words)
        if chunk_text_str.strip():
            chunks.append({"index": chunk_idx, "text": chunk_text_str})
            chunk_idx += 1
        i += chunk_size - overlap

    return chunks
