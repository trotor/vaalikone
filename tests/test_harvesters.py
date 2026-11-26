"""Puoluerekisteri- ja Pohtiva-harvesterien parserit ja apufunktiot (ei verkkoa)."""

import json
from pathlib import Path

from sqlalchemy import func, select

from vaalikone.cli.ingest import _store_document
from vaalikone.ingest.connectors.pohtiva import (
    classify,
    parse_party_codes,
    parse_program_list,
    parse_program_page,
)
from vaalikone.ingest.connectors.puoluerekisteri import parse_registered, platform_pdf_url
from vaalikone.ingest.harvesters import (
    containment,
    is_near_duplicate,
    load_parties_yaml,
    pohtiva_code_for,
    shingles,
)
from vaalikone.models.document import ContentType, Document
from vaalikone.models.embedding import Embedding
from vaalikone.models.source import Source, SourceType

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- puoluerekisteri ---


def test_parse_registered():
    parties = parse_registered(json.loads(_fixture("puoluerekisteri_registered.json")))
    assert [p["registry_id"] for p in parties] == [1, 23]
    sdp, kri = parties
    assert sdp["website"] == "https://www.sdp.fi"
    assert sdp["registered"] == "1969-01-31"
    assert sdp["registered_status"] is True
    assert kri["website"] is None
    assert kri["name"].startswith("Kristallipuolue")


def test_platform_pdf_url():
    assert platform_pdf_url(20) == (
        "https://puoluerekisteri.fi/publicapi/attachment/20/4/platform.pdf"
    )


def test_parties_yaml_registry_ids_unique_and_codes():
    parties = load_parties_yaml()
    ids = [p["registry_id"] for p in parties if p.get("registry_id")]
    assert len(ids) == len(set(ids)) == 20
    abbrs = [p["abbreviation"] for p in parties]
    assert len(abbrs) == len(set(abbrs))
    by_abbr = {p["abbreviation"]: p for p in parties}
    assert pohtiva_code_for(by_abbr["RKP"]) == "SFP"
    assert pohtiva_code_for(by_abbr["SDP"]) == "SDP"
    assert pohtiva_code_for(by_abbr["SGP"]) is None
    assert by_abbr["PIR"].get("registered") is False


# --- Pohtiva ---


def test_parse_party_codes():
    codes = parse_party_codes(_fixture("pohtiva_codes.html"))
    assert codes == {
        "VAS": "Vasemmistoliitto",
        "SFP": "Ruotsalainen kansanpuolue",
        "HAMP": "Hamppupuolue",
        "SIN": "Sininen tulevaisuus",
    }


def test_parse_program_list():
    rows = parse_program_list(_fixture("pohtiva_list_vas.html"))
    assert len(rows) == 3
    first = rows[0]
    assert first["url"] == "https://www.fsd.tuni.fi/pohtiva/ohjelmalistat/VAS/1559"
    assert first["pohtiva_id"] == 1559
    assert first["code"] == "VAS"
    assert first["title"] == "Vasemmistoliiton kunta- ja aluevaaliohjelma 2025"
    assert first["year"] == 2025
    assert first["type"] == "vaaliohjelma"
    assert first["language"] == "fi"


def test_parse_program_list_rejects_foreign_urls():
    html = _fixture("pohtiva_list_vas.html").replace(
        "https://www.fsd.tuni.fi/pohtiva/ohjelmalistat/VAS/1559",
        "https://www.sdp.fi/uploads/ohjelma.pdf",
    )
    rows = parse_program_list(html)
    assert len(rows) == 2
    assert all(r["url"].startswith("https://www.fsd.tuni.fi/pohtiva/ohjelmalistat/") for r in rows)


def test_parse_program_page():
    page = parse_program_page(_fixture("pohtiva_program.html"))
    assert page["party_name"] == "Vasemmistoliitto"
    assert page["year"] == 2025
    assert page["type"] == "vaaliohjelma"
    lines = page["text"].splitlines()
    assert lines[0] == "HUOLETONTA ARKEA KAIKILLE, EI HARVOILLE"
    assert "Pohtiva" not in page["text"]  # sivun navigaatio ei vuoda tekstiin
    assert len(page["text"]) > 500


def test_parse_program_page_without_platform():
    assert parse_program_page("<html><body><p>404</p></body></html>") is None


def test_classify():
    assert classify("Kokoomuksen EU-vaaliohjelma 2024", "vaaliohjelma") == (
        ContentType.EUROVAALIOHJELMA, "europarlamenttivaalit",
    )
    assert classify("Ihmisten Eurooppa", "vaaliohjelma")[0] == ContentType.EUROVAALIOHJELMA
    assert classify("RKP:n vaaliohjelma aluevaaleissa 2025", "vaaliohjelma")[0] == (
        ContentType.KUNTAVAALIOHJELMA
    )
    assert classify("SFP:s valprogram för kommunalvalet 2025", "vaaliohjelma")[0] == (
        ContentType.KUNTAVAALIOHJELMA
    )
    assert classify("Suojele elämää - eduskuntavaaliohjelma 2023", "vaaliohjelma") == (
        ContentType.VAALIOHJELMA, "eduskuntavaalit",
    )
    # "yhteiskunta" ei saa tulkita kuntavaaliksi
    assert classify("Reilu yhteiskunta kaikille", "vaaliohjelma")[1] == "eduskuntavaalit"
    assert classify("SDP:n seurakuntavaaliohjelma 2022", "vaaliohjelma")[1] == "seurakuntavaalit"
    assert classify("Vihreiden periaateohjelma", "yleisohjelma") == (
        ContentType.PUOLUEOHJELMA, None,
    )


# --- duplikaattitunnistus ---

_TEXT = " ".join(f"sana{i} on osa pitkää ohjelmatekstiä numero {i}." for i in range(200))


def test_shingles_join_hyphenated_line_breaks():
    assert shingles("maahanmuutto-\npolitiikka on   epäonnistunut") == shingles(
        "Maahanmuuttopolitiikka on epäonnistunut."
    )


def test_near_duplicate_detects_pdf_formatted_copy():
    # Sama teksti PDF-tyyliin: rivinvaihdot, isot kirjaimet, sivuylätunnisteet välissä
    pdf = "\n".join(
        ("3 | OHJELMA 2023\n" if n % 40 == 0 else "") + line
        for n, line in enumerate(_TEXT.upper().split(". "))
    )
    assert containment(shingles(_TEXT), shingles(pdf)) > 0.9
    assert is_near_duplicate(shingles(_TEXT), shingles(pdf))


def test_near_duplicate_rejects_partial_reuse():
    # Uusi ohjelma, joka kierrättää neljänneksen vanhasta tekstistä
    words = _TEXT.split()
    reused = " ".join(words[: len(words) // 4])
    fresh = " ".join(f"uusi{i} linjaus tälle kaudelle {i}." for i in range(150))
    assert not is_near_duplicate(shingles(fresh + " " + reused), shingles(_TEXT))


def test_short_text_duplicate():
    short = "Hamppupuolue pyrkii purkamaan cannabis-sukuisten kasvien hyödyntämisen esteitä."
    assert is_near_duplicate(shingles(short), shingles("Yleisohjelma\n" + short + "\nPj"))
    assert not is_near_duplicate(set(), shingles(short))


# --- _store_document: kieli ja refresh ---


async def _count(db_session, model, *where):
    return (await db_session.execute(select(func.count()).select_from(model).where(*where))
            ).scalar_one()


async def test_store_document_language_and_replace(db_session):
    url = "https://example.org/ohjelma-testi"
    ok = await _store_document(
        db_session, source_type=SourceType.WEBSITE, url=url, title="Ohut",
        text="laskeutumissivu", content_type=ContentType.PUOLUEOHJELMA, language="sv",
    )
    assert ok
    await db_session.flush()
    doc = (await db_session.execute(
        select(Document).join(Source).where(Source.url == url)
    )).scalar_one()
    assert doc.language == "sv"
    db_session.add(Embedding(
        document_id=doc.id, chunk_index=0, chunk_text="x", embedding=[0.1, 0.2],
        model_name="test",
    ))
    await db_session.flush()

    # Ilman replacea: ohitetaan
    assert not await _store_document(
        db_session, source_type=SourceType.WEBSITE, url=url, title="Uusi",
        text="koko ohjelma", content_type=ContentType.PUOLUEOHJELMA,
    )
    # replace=True: vanha lähde, dokumentti ja embedding poistuvat
    assert await _store_document(
        db_session, source_type=SourceType.WEBSITE, url=url, title="Uusi",
        text="koko ohjelma", content_type=ContentType.PUOLUEOHJELMA, replace=True,
    )
    await db_session.flush()
    assert await _count(db_session, Source, Source.url == url) == 1
    docs = (await db_session.execute(
        select(Document).join(Source).where(Source.url == url)
    )).scalars().all()
    assert [d.title for d in docs] == ["Uusi"]
    assert await _count(db_session, Embedding, Embedding.document_id == doc.id) == 0
