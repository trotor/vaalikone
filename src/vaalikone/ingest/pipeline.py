import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.ingest.chunker import chunk_text
from vaalikone.ingest.embedder import get_embeddings_batch
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding


async def process_document(
    session: AsyncSession,
    document_id,
    content_text: str,
    embed_model: str = "text-embedding-3-small",
    chunk_size: int = 500,
    overlap: int = 50,
    batch_size: int = 10,
) -> int:
    """Chunk a document, generate embeddings, and store them."""
    chunks = chunk_text(content_text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    total_stored = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        vectors = await get_embeddings_batch(texts, model=embed_model)

        for chunk, vector in zip(batch, vectors):
            embedding = Embedding(
                document_id=document_id,
                chunk_index=chunk["index"],
                chunk_text=chunk["text"],
                embedding=vector,
                model_name=embed_model,
            )
            session.add(embedding)

        total_stored += len(batch)

    await session.commit()
    return total_stored


async def process_all_documents(
    session: AsyncSession,
    embed_model: str = "text-embedding-3-small",
    chunk_size: int = 500,
    overlap: int = 50,
    force: bool = False,
) -> tuple[int, int]:
    """Process all documents that don't have embeddings yet.
    Uses separate sessions per document to isolate failures."""
    from sqlalchemy import exists

    if force:
        query = select(Document.id, Document.title, Document.content_text).where(
            Document.content_text.isnot(None)
        )
    else:
        has_embeddings = exists(
            select(Embedding.id).where(Embedding.document_id == Document.id)
        )
        query = select(Document.id, Document.title, Document.content_text).where(
            Document.content_text.isnot(None),
            ~has_embeddings,
        )

    result = await session.execute(query)
    documents = result.all()

    # Use separate sessions per document to isolate failures
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_chunks = 0
    processed = 0
    for doc_id, title, content_text in documents:
        try:
            async with async_session_factory() as doc_session:
                n = await process_document(
                    doc_session,
                    doc_id,
                    content_text,
                    embed_model=embed_model,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                total_chunks += n
                processed += 1
                click.echo(f"  [{processed}/{len(documents)}] {title}: {n} chunks")
        except Exception as e:
            click.echo(f"  [{processed + 1}/{len(documents)}] {title}: ERROR - {type(e).__name__}: {e}")
            processed += 1

    await engine.dispose()
    return len(documents), total_chunks
