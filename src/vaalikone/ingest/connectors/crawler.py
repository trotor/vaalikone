"""Recursive web crawler with political relevance filtering.

Crawls a website starting from a seed URL, following internal links
up to a configurable depth. Uses a local LLM (Ollama) or simple heuristics
to filter out non-political content.
"""

import re
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from vaalikone.ingest.url_validation import UnsafeURLError, validate_public_url

# Keywords that indicate political content (Finnish)
POLITICAL_KEYWORDS = {
    "ohjelma", "vaaliohjelma", "puolueohjelma", "periaateohjelma", "politiikka",
    "linjaus", "kannanotto", "tavoite", "budjetti", "varjobudjetti",
    "vaihtoehtobudjetti", "eduskunta", "hallitus", "oppositio", "lakialoite",
    "verotus", "vero", "sosiaaliturva", "terveydenhuolto", "koulutus",
    "maahanmuutto", "ilmasto", "energia", "turvallisuus", "puolustus",
    "työllisyys", "talous", "eläke", "asuminen", "liikenne", "ympäristö",
    "oikeus", "tasa-arvo", "kulttuuri", "maatalous", "metsä",
    "program", "politik", "valprogram", "partiprogram",  # Swedish
    # Additional Finnish political terms
    "puolue", "liike", "kansanliike", "puoluekokous", "vaali", "äänestys",
    "kansanedustaja", "ministeri", "yhteiskunta", "hyvinvointi", "uudistus",
    "feminismi", "tasa-arvo", "ihmisoikeus", "demokratia", "kansallinen",
    "sosialismi", "kommunismi", "vasemmisto", "oikeisto", "keskusta",
    "ohjelmajulistus", "periaatteet", "tavoitteet", "jäsen", "liity",
}

# URL patterns to skip
SKIP_PATTERNS = {
    "/wp-content/uploads/",  # raw files (handled separately)
    "/wp-json/", "/feed/", "/rss", "/tag/", "/author/",
    "/login", "/kirjaudu", "/cart", "/ostoskori", "/kauppa", "/verkkokauppa",
    "/en/", "/sv/",  # skip non-Finnish versions (except RKP which is Swedish)
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi",
    ".zip", ".tar", ".gz",
    "facebook.com", "twitter.com", "instagram.com", "youtube.com",
    "linkedin.com", "tiktok.com",
}


def _is_same_domain(url: str, base_url: str) -> bool:
    """Check if URL is on the same domain as base."""
    return urlparse(url).netloc == urlparse(base_url).netloc


def _should_skip(url: str) -> bool:
    """Check if URL should be skipped."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SKIP_PATTERNS)


def _is_likely_political(text: str, url: str) -> bool:
    """Quick heuristic check if content is likely political.
    Returns True if text or URL contains political keywords."""
    combined = (text[:2000] + " " + url).lower()
    matches = sum(1 for kw in POLITICAL_KEYWORDS if kw in combined)
    # Need at least 1 keyword match to be considered political
    return matches >= 1


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract all internal links from HTML anchor tags only."""
    links = set()
    # Only match <a href="..."> tags to avoid CSS/font/media links
    for match in re.finditer(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = match.group(1)
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = urljoin(base_url, href)
        if _is_same_domain(absolute, base_url) and not _should_skip(absolute):
            # Normalize: remove fragment, trailing slash
            parsed = urlparse(absolute)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if normalized.endswith("/"):
                normalized = normalized.rstrip("/") or normalized
            links.add(normalized)
    return list(links)


async def crawl_site(
    seed_url: str,
    max_depth: int = 2,
    max_pages: int = 50,
    min_content_length: int = 200,
    use_llm_filter: bool = False,
    callback=None,
) -> list[dict]:
    """Crawl a website recursively, extracting political content.

    Args:
        seed_url: Starting URL
        max_depth: How many links deep to follow (0 = seed only)
        max_pages: Maximum pages to fetch
        min_content_length: Minimum text length to keep
        use_llm_filter: Use Ollama LLM for relevance filtering (slower but better)
        callback: Optional async callback(url, title, chars) for progress

    Returns:
        List of {"url", "title", "text"} dicts for relevant pages
    """
    validate_public_url(seed_url)
    visited = set()
    results = []
    queue = [(seed_url, 0)]  # (url, depth)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)

            # Normalize URL
            parsed = urlparse(url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if normalized in visited:
                continue
            visited.add(normalized)

            # SSRF guard: skip links that are not public http(s) URLs
            try:
                validate_public_url(url)
            except UnsafeURLError:
                continue

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
            except Exception:
                continue

            # Extract text
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                output_format="txt",
            )

            if text and len(text) >= min_content_length:
                # Check political relevance
                is_relevant = _is_likely_political(text, url)

                if is_relevant and use_llm_filter:
                    is_relevant = await _llm_relevance_check(text[:1500])

                if is_relevant:
                    metadata = trafilatura.extract_metadata(html)
                    title = metadata.title if metadata and metadata.title else url
                    results.append({
                        "url": url,
                        "title": title,
                        "text": text,
                    })
                    if callback:
                        await callback(url, title, len(text))

            # Follow links if not at max depth
            if depth < max_depth:
                links = _extract_links(html, seed_url)
                for link in links:
                    if link not in visited:
                        queue.append((link, depth + 1))

    return results


async def _llm_relevance_check(text: str) -> bool:
    """Use local Ollama model to check if text is politically relevant."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:3b",
                    "prompt": (
                        "Onko seuraava teksti poliittisesti relevanttia suomalaisen "
                        "puoluepolitiikan kannalta? Vastaa vain 'KYLLA' tai 'EI'.\n\n"
                        f"Teksti: {text[:1000]}\n\nVastaus:"
                    ),
                    "stream": False,
                },
            )
            resp.raise_for_status()
            answer = resp.json().get("response", "").strip().upper()
            return "KYLLA" in answer or "KYLLÄ" in answer
    except Exception:
        # If LLM fails, fall back to keyword heuristic
        return True
