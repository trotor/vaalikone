from vaalikone.ingest.chunker import chunk_text


def test_chunk_basic():
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    assert chunks[0]["index"] == 0
    assert chunks[1]["index"] == 1
    # Check overlap exists
    words_0 = set(chunks[0]["text"].split()[-50:])
    words_1 = set(chunks[1]["text"].split()[:50])
    assert len(words_0 & words_1) > 0


def test_chunk_short_text():
    text = "This is a short text"
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0]["text"] == text


def test_chunk_empty():
    chunks = chunk_text("", chunk_size=500, overlap=50)
    assert len(chunks) == 0
