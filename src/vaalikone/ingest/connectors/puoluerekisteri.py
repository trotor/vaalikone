"""Oikeusministeriön puoluerekisteri (puoluerekisteri.fi).

Julkinen JSON-rajapinta (sama jota puoluerekisteri.fi:n Angular-sovellus käyttää):

- ``GET /publicapi/party/registered`` — rekisteröidyt puolueet (nimi, kotisivu,
  rekisteröintipäivä, rekisteri-id)
- ``GET /publicapi/attachment/{id}/4/platform.pdf`` — puolueen rekisteriin
  toimittama yleisohjelma (PDF). Liitekategoriat: 2 = säännöt, 4 = yleisohjelma,
  3/5 = vaihtoehtoiset kieliversiot. Liite on 11/2026 vain 10 puolueella 20:stä
  (AP, KRI, VKK, VAPL, TP, LIB, EOP, HAMP, SML, SGP); muilla palvelin vastaa 500.
"""

import httpx

PUOLUEREKISTERI_BASE = "https://puoluerekisteri.fi"
REGISTERED_URL = f"{PUOLUEREKISTERI_BASE}/publicapi/party/registered"
STATUS_REGISTERED = 13
ATTACHMENT_PLATFORM = 4
ATTACHMENT_RULES = 2
USER_AGENT = "vaalikone-harvester/1.0"


def platform_pdf_url(registry_id: int) -> str:
    return (
        f"{PUOLUEREKISTERI_BASE}/publicapi/attachment/"
        f"{registry_id}/{ATTACHMENT_PLATFORM}/platform.pdf"
    )


def _normalize_url(url: str | None) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def parse_registered(data: list[dict]) -> list[dict]:
    """Muunna /publicapi/party/registered -vastaus kevyiksi dicteiksi."""
    parties = []
    for p in data:
        site = p.get("siteInfo") or {}
        parties.append({
            "registry_id": p["id"],
            "name": (p.get("name") or "").strip(),
            "website": _normalize_url(site.get("url")),
            "registered": site.get("registered"),
            "registered_status": p.get("status") == STATUS_REGISTERED,
            "city": site.get("city"),
        })
    return parties


async def fetch_registered_parties() -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(REGISTERED_URL, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return parse_registered(resp.json())


async def fetch_platform_pdf(registry_id: int) -> bytes | None:
    """Lataa puolueen yleisohjelma-PDF. Palauttaa None jos liitettä ei ole."""
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(
            platform_pdf_url(registry_id), headers={"User-Agent": USER_AGENT}
        )
    # Palvelin vastaa 500 (tai 404) kun yleisohjelmaa ei ole tallennettu
    if resp.status_code in (404, 500) or not resp.content:
        return None
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        return None
    return resp.content
