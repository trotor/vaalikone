import httpx
import pymupdf  # PyMuPDF


async def fetch_and_extract_pdf(url: str) -> dict | None:
    """Download a PDF from URL and extract text using PyMuPDF."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        pdf_bytes = resp.content

    return extract_pdf_bytes(pdf_bytes, url)


def extract_pdf_bytes(pdf_bytes: bytes, source_url: str = "") -> dict | None:
    """Extract text from PDF bytes."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    text_parts = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            text_parts.append(text)

    doc.close()

    full_text = "\n\n".join(text_parts)
    if not full_text.strip():
        return None

    # Try to get title from metadata
    metadata = pymupdf.open(stream=pdf_bytes, filetype="pdf").metadata
    title = metadata.get("title", "") if metadata else ""
    if not title:
        title = source_url.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")

    return {
        "text": full_text,
        "title": title,
        "url": source_url,
        "pages": len(text_parts),
    }
