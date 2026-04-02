import trafilatura
import httpx


async def fetch_and_extract(url: str) -> dict | None:
    """Fetch a URL and extract clean text content using trafilatura."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    result = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )

    if not result:
        return None

    title = trafilatura.extract_metadata(html)

    return {
        "text": result,
        "title": title.title if title and title.title else url,
        "url": url,
    }
