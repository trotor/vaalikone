import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.ingest.chunker import chunk_text
from vaalikone.ingest.embedder import get_embeddings_batch
from vaalikone.models.document import Document
from vaalikone.models.embedding import Embedding


async def process_document(
    session: AsyncSession,
    document: Document,
    embed_model: str = "text-embedding-3-small",
    chunk_size: int = 500,
    overlap: int = 50,
    batch_size: int = 20,
) -> int:
    """Chunk a document, generate embeddings, and store them."""
    if not document.content_text:
        return 0

    chunks = chunk_text(document.content_text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    total_stored = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        vectors = await get_embeddings_batch(texts, model=embed_model)

        for chunk, vector in zip(batch, vectors):
            embedding = Embedding(
                document_id=document.id,
                chunk_index=chunk["index"],
                chunk_text=chunk["text"],
                embedding=vector,
                model_name=embed_model,
            )
            session.add(embedding)

        total_stored += len(batch)

    await session.flush()
    return total_stored


async def process_all_documents(
    session: AsyncSession,
    embed_model: str = "text-embedding-3-small",
    chunk_size: int = 500,
    overlap: int = 50,
    force: bool = False,
) -> tuple[int, int]:
    """Process all documents that don't have embeddings yet."""
    if force:
        query = select(Document).where(Document.content_text.isnot(None))
    else:
        # Only documents without embeddings
        from sqlalchemy import exists

        has_embeddings = exists(
            select(Embedding.id).where(Embedding.document_id == Document.id)
        )
        query = select(Document).where(
            Document.content_text.isnot(None),
            ~has_embeddings,
        )

    result = await session.execute(query)
    documents = result.scalars().all()

    total_chunks = 0
    for doc in documents:
        try:
            n = await process_document(
                session,
                doc,
                embed_model=embed_model,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            await session.commit()
            total_chunks += n
            click.echo(f"  {doc.title}: {n} chunks")
        except Exception as e:
            await session.rollback()
            click.echo(f"  {doc.title}: ERROR - {e}")

    return len(documents), total_chunks
