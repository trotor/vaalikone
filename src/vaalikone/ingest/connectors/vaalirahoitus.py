"""Vaalirahoitusvalvonnan tutkittavat aineistot (CSV).

Lähde: https://www.vaalirahoitusvalvonta.fi — RAHOITUSRIVIT-alkuiset CSV:t,
UTF-8, puolipiste-erotin, kentät heittomerkeissä ('Tukija';'...').

Tiedostot haetaan listaussivulta, koska URL:n ``?dl=``-versioparametri vaihtuu
aina kun aineistoa päivitetään. ``E_VI`` = vaalirahoitusilmoitus (vaalien jälkeen),
``E_EI`` = ennakkoilmoitus.
"""

import csv
import io
import re

import httpx

from vaalikone.ingest.connectors.http import HARVESTER_HEADERS

VAALIRAHOITUS_ROOT = "https://www.vaalirahoitusvalvonta.fi"
VAALIRAHOITUS_BASE = (
    f"{VAALIRAHOITUS_ROOT}/fi/index/vaalirahoitus/"
    "haetietoavaalirahoitusilmoituksista/tutkitietoaineistoja"
)
LISTING_URL = f"{VAALIRAHOITUS_BASE}.html"
FILE_LABELS = {"VI": "vaalirahoitusilmoitus", "EI": "ennakkoilmoitus"}


def parse_finance_listing(html: str, election: str, year: int) -> dict[str, str]:
    """Listaussivu -> {label: url} vaalin RAHOITUSRIVIT-tiedostoille (uusin versio)."""
    pattern = re.compile(
        rf'href="([^"]*/{election}{year}/RAHOITUSRIVIT_E_(VI|EI)_{election}{year}\.csv[^"]*)"'
    )
    files = {}
    for href, kind in pattern.findall(html):
        url = href if href.startswith("http") else VAALIRAHOITUS_ROOT + href
        files[FILE_LABELS[kind]] = url.replace("&amp;", "&")
    return files


async def discover_finance_files(election: str, year: int) -> dict[str, str]:
    async with httpx.AsyncClient(
        timeout=60.0, follow_redirects=True, headers=HARVESTER_HEADERS
    ) as client:
        resp = await client.get(LISTING_URL)
        resp.raise_for_status()
    return parse_finance_listing(resp.text, election, year)


def _amount(value: str) -> float | None:
    try:
        return float(value.replace(" ", "").replace("\xa0", "").replace(",", "."))
    except ValueError:
        return None


def parse_finance_csv(text: str, source_url: str = "") -> list[dict]:
    """RAHOITUSRIVIT-CSV -> rivit. Kentät ovat heittomerkeissä, erotin ';'."""
    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar="'")
    header = [h.strip() for h in next(reader)]
    rows = []
    for raw in reader:
        if not raw or all(not c.strip() for c in raw):
            continue
        row = {k: (v or "").strip() for k, v in zip(header, raw)}
        rows.append({
            "donor_name": row.get("Tukija") or None,
            "donor_business_id": row.get("Tukijan y-tunnus/yhdistysrekisterinumero jos on") or None,
            "donor_first_names": row.get("Tukijan etunimet") or None,
            "donor_last_name": row.get("Tukijan sukunimi") or None,
            "donor_municipality": row.get("Tukijan kotikunta jos on") or None,
            "form_numbers": row.get("Tukilahteen lomakenumerot") or None,
            "loan_name": row.get("Lainan nimi") or None,
            "loan_term": row.get("Lainan takaisinmaksuaika/laina-aika") or None,
            "amount": _amount(row.get("Tuen maara", "")),
            "recipient_first_name": row.get("Tuen saajan etunimet") or None,
            "recipient_last_name": row.get("Tuen saajan Sukunimi") or None,
            "constituency": row.get("Vaalipiiri / Kunta") or None,
            "party_abbr": row.get("Tuen saajan puolue") or None,
            "source_url": source_url,
        })
    return rows


async def fetch_finance_rows(url: str) -> list[dict]:
    """Lataa ja parsii yhden RAHOITUSRIVIT-CSV:n riveiksi (dict)."""
    async with httpx.AsyncClient(
        timeout=120.0, follow_redirects=True, headers=HARVESTER_HEADERS
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    try:
        text = resp.content.decode("utf-8-sig")
    except UnicodeDecodeError:  # vanhemmat aineistot
        text = resp.content.decode("latin-1")
    return parse_finance_csv(text, url)
