"""FSD Pohtiva — Poliittisten ohjelmien tietovaranto (Yhteiskuntatieteellinen tietoarkisto).

https://www.fsd.tuni.fi/pohtiva/ sisältää suomalaisten puolueiden voimassa olevat
ja entiset ohjelmat tekstimuodossa (yleis-, tavoite-, erityis- ja vaaliohjelmat).

- ``/pohtiva/ohjelmalistat`` — puoluekoodit (esim. SDP, SFP, VAS, AP, HAMP)
- ``/pohtiva/ohjelmalistat/{KOODI}`` — taulukko: otsikko, puolue, vuosi, tyyppi, kieli
- ``/pohtiva/ohjelmalistat/{KOODI}/{id}`` — ohjelman koko teksti (``div.platform``)

Viittaus: POHTIVAan tulee viitata normaalin tieteellisen käytännön mukaan
(ks. https://www.fsd.tuni.fi/pohtiva/lisatietoja).
"""

import asyncio
import re

import httpx
import lxml.html

from vaalikone.models.document import ContentType

POHTIVA_BASE = "https://www.fsd.tuni.fi/pohtiva/ohjelmalistat"
USER_AGENT = "vaalikone-harvester/1.0"
ATTRIBUTION = (
    "POHTIVA – Poliittisten ohjelmien tietovaranto. "
    "Yhteiskuntatieteellinen tietoarkisto (FSD), Tampereen yliopisto."
)

# Pohtivan puoluekoodi -> vaalikoneen lyhenne (vain poikkeavat)
POHTIVA_TO_ABBR = {"SFP": "RKP"}
ABBR_TO_POHTIVA = {v: k for k, v in POHTIVA_TO_ABBR.items()}

_BLOCK_TAGS = ("p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "div", "blockquote")

# \b sanan alussa: "yhteiskunta" ei saa osua "kunta"-sanaan
_LOCAL_RE = re.compile(
    r"\b(kunta|kunnall|alue|sote|hyvinvointialue|kommunal|välfärdsområde|landskap|maakunta)",
    re.IGNORECASE,
)
_EU_RE = re.compile(r"\b(eu\b|euro|europa)", re.IGNORECASE)
_PARISH_RE = re.compile(r"\b(seurakunta|församling)", re.IGNORECASE)
_PRESIDENT_RE = re.compile(r"\b(presidentin|presidentval)", re.IGNORECASE)


_PROGRAM_URL_RE = re.compile(re.escape(POHTIVA_BASE) + r"/([A-Za-z0-9_-]+)/(\d+)/?")


def party_list_url(code: str) -> str:
    return f"{POHTIVA_BASE}/{code}"


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_party_codes(html: str) -> dict[str, str]:
    """Ohjelmalistat-etusivu -> {koodi: puolueen nimi}."""
    doc = lxml.html.fromstring(html)
    codes = {}
    for a in doc.xpath("//a[@href]"):
        m = re.search(r"/pohtiva/ohjelmalistat/([A-Za-z0-9_-]+)/?$", a.get("href"))
        if m:
            name = _clean(a.text_content()).lstrip("⤷").strip()
            if name and name not in ("Takaisin", "Ohjelmalistat"):
                codes[m.group(1)] = name
    return codes


def parse_program_list(html: str) -> list[dict]:
    """Puolueen ohjelmalista -> [{url, pohtiva_id, title, party_name, year, type, language}]."""
    doc = lxml.html.fromstring(html)
    rows = []
    for tr in doc.xpath("//table[@id='sortable-table']//tr[td]"):
        tds = tr.xpath("./td")
        if len(tds) < 5:
            continue
        links = tds[0].xpath(".//a[@href]")
        if not links:
            continue
        url = links[0].get("href").strip()
        # Hyväksy vain Pohtivan omat ohjelmasivut: URL:ia käytetään hakuun ja
        # --refresh-tilassa saman URL:n lähteen poistoon.
        m = _PROGRAM_URL_RE.fullmatch(url)
        if not m:
            continue
        year_txt = _clean(tds[2].text_content())
        rows.append({
            "url": url,
            "code": m.group(1),
            "pohtiva_id": int(m.group(2)),
            "title": _clean(links[0].text_content()),
            "party_name": _clean(tds[1].text_content()),
            "year": int(year_txt) if year_txt.isdigit() else None,
            "type": _clean(tds[3].text_content()).lower(),
            "language": _clean(tds[4].text_content()).lower() or "fi",
        })
    return rows


def parse_program_page(html: str) -> dict | None:
    """Ohjelmasivu -> {party_name, title, year, type, text}. None jos tekstiä ei ole."""
    doc = lxml.html.fromstring(html)
    meta = {}
    for li in doc.xpath("//ul[contains(@class,'no-bullet')]/li[b]"):
        key = _clean(li.xpath("./b")[0].text_content()).rstrip(":").lower()
        val = _clean(li.text_content())
        val = val.split(":", 1)[1].strip() if ":" in val else val
        meta[key] = val

    platforms = doc.xpath(
        "//div[contains(concat(' ', normalize-space(@class), ' '), ' platform ')]"
    )
    if not platforms:
        return None
    div = platforms[0]
    for el in div.iter(*_BLOCK_TAGS):
        el.tail = "\n" + (el.tail or "")
    lines = [_clean(line) for line in div.text_content().splitlines()]
    text = "\n".join(line for line in lines if line)
    if not text:
        return None

    year = meta.get("vuosi", "")
    return {
        "party_name": meta.get("puolue"),
        "title": meta.get("otsikko"),
        "year": int(year) if year.isdigit() else None,
        "type": (meta.get("ohjelmatyyppi") or "").lower(),
        "text": text,
    }


def classify(title: str, pohtiva_type: str) -> tuple[ContentType, str | None]:
    """Pohtivan ohjelmatyyppi + otsikko -> (ContentType, vaalityyppi).

    Pohtivan "vaaliohjelma" kattaa eduskunta-, kunta-, alue-, EU-, seurakunta-
    ja presidentinvaalit, joten vaalityyppi päätellään otsikosta.
    """
    if pohtiva_type != "vaaliohjelma":
        return ContentType.PUOLUEOHJELMA, None
    if _PARISH_RE.search(title):
        return ContentType.VAALIOHJELMA, "seurakuntavaalit"
    if _PRESIDENT_RE.search(title):
        return ContentType.VAALIOHJELMA, "presidentinvaali"
    if _EU_RE.search(title):
        return ContentType.EUROVAALIOHJELMA, "europarlamenttivaalit"
    if _LOCAL_RE.search(title):
        return ContentType.KUNTAVAALIOHJELMA, "kunta- ja aluevaalit"
    return ContentType.VAALIOHJELMA, "eduskuntavaalit"


class PohtivaClient:
    """Kohtelias HTTP-asiakas: yksi yhteys, viive pyyntöjen välissä."""

    def __init__(self, delay: float = 1.0, timeout: float = 30.0):
        self.delay = delay
        self._client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self._first = True

    async def _get(self, url: str) -> str:
        if not self._first:
            await asyncio.sleep(self.delay)
        self._first = False
        for attempt in range(3):
            resp = await self._client.get(url)
            if resp.status_code in (429, 502, 503) and attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.text
        raise RuntimeError(f"Pohtiva: liian monta yritystä {url}")

    async def party_codes(self) -> dict[str, str]:
        return parse_party_codes(await self._get(POHTIVA_BASE))

    async def program_list(self, code: str) -> list[dict]:
        return parse_program_list(await self._get(party_list_url(code)))

    async def program(self, url: str) -> dict | None:
        return parse_program_page(await self._get(url))

    async def aclose(self):
        await self._client.aclose()
