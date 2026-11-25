"""Vaalirahoitusvalvonnan tutkittavat aineistot (CSV).

Lähde: https://www.vaalirahoitusvalvonta.fi — RAHOITUSRIVIT-alkuiset CSV:t,
latin1-koodaus, puolipiste-erotin.
"""

import csv
import io

import httpx

VAALIRAHOITUS_BASE = (
    "https://www.vaalirahoitusvalvonta.fi/fi/index/vaalirahoitus/"
    "haetietoavaalirahoitusilmoituksista/tutkitietoaineistoja"
)

# Eduskuntavaalit 2023: ennakkoilmoitukset (E_VI) ja muut ilmoitukset (E_EI)
EDUSKUNTAVAALIT_2023_FILES = {
    "ennakko": f"{VAALIRAHOITUS_BASE}/eduskuntavaalit2023/"
                "RAHOITUSRIVIT_E_VI_eduskuntavaalit2023.csv?dl=20231001_171320",
    "muut": f"{VAALIRAHOITUS_BASE}/eduskuntavaalit2023/"
            "RAHOITUSRIVIT_E_EI_eduskuntavaalit2023.csv?dl=20230505_193017",
}


async def fetch_finance_rows(url: str) -> list[dict]:
    """Lataa ja parsii yhden RAHOITUSRIVIT-CSV:n riveiksi (dict)."""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "vaalikone-bot/1.0"})
        resp.raise_for_status()
    text = resp.content.decode("latin-1")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader)
    rows = []
    for raw in reader:
        if not raw or all(not c.strip() for c in raw):
            continue
        row = dict(zip(header, raw))
        try:
            amount = float(
                row.get("Tuen maara", "").replace(" ", "").replace(",", ".").strip()
            )
        except ValueError:
            amount = None
        rows.append({
            "donor_name": row.get("Tukija", "").strip() or None,
            "donor_business_id": (
                row.get("Tukijan y-tunnus/yhdistysrekisterinumero jos on", "").strip() or None
            ),
            "donor_first_names": row.get("Tukijan etunimet", "").strip() or None,
            "donor_last_name": row.get("Tukijan sukunimi", "").strip() or None,
            "donor_municipality": row.get("Tukijan kotikunta jos on", "").strip() or None,
            "form_numbers": row.get("Tukilahteen lomakenumerot", "").strip() or None,
            "loan_name": row.get("Lainan nimi", "").strip() or None,
            "loan_term": row.get("Lainan takaisinmaksuaika/laina-aika", "").strip() or None,
            "amount": amount,
            "recipient_first_name": row.get("Tuen saajan etunimet", "").strip() or None,
            "recipient_last_name": row.get("Tuen saajan Sukunimi", "").strip() or None,
            "constituency": row.get("Vaalipiiri / Kunta", "").strip() or None,
            "party_abbr": row.get("Tuen saajan puolue", "").strip() or None,
            "source_url": url,
        })
    return rows
