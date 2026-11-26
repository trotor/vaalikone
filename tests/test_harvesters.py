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
    group_code,
    group_name,
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


def test_group_code_prefers_group_at_speech_time():
    puhuja = {
        "lisatieto": "ps",
        "eduskuntaryhma_tunnus": "SD01~SOSIALIDEMOKRAATTINEN EDUSKUNTARYHMÄ",
    }
    assert group_code(puhuja) == "sd"
    assert group_name(puhuja) == "Sosialidemokraattinen eduskuntaryhmä"
    assert group_code({"lisatieto": "kok", "eduskuntaryhma_tunnus": None}) == "kok"
    assert group_code({"eduskuntaryhma_tunnus": "UV01~SININEN EDUSKUNTARYHMÄ"}) == "uv"
    assert group_code({}) is None


# --- vaalirahoitus ---


def test_parse_finance_csv_quoted_utf8():
    from vaalikone.ingest.connectors.vaalirahoitus import parse_finance_csv

    text = (
        "'Tukija';'Tukijan y-tunnus/yhdistysrekisterinumero jos on';'Tukijan etunimet';"
        "'Tukijan sukunimi';'Tukijan kotikunta jos on';'Tukilahteen lomakenumerot';"
        "'Lainan nimi';'Lainan takaisinmaksuaika/laina-aika';'Tuen maara';"
        "'Tuen saajan etunimet';'Tuen saajan Sukunimi';'Vaalipiiri / Kunta';"
        "'Tuen saajan puolue';\n"
        "'Alajärven Sosialidemokraatit ry';'3028070-1';'';'';'';'2.6';'';'';'1 830,05';"
        "'Jukka Pekka';'Matintupa';'Alajärvi';'SDP'\n"
    )
    [row] = parse_finance_csv(text, "u")
    assert row["donor_name"] == "Alajärven Sosialidemokraatit ry"
    assert row["amount"] == 1830.05
    assert row["recipient_last_name"] == "Matintupa"
    assert row["constituency"] == "Alajärvi"
    assert row["party_abbr"] == "SDP"
    assert row["donor_first_names"] is None


def test_parse_finance_listing_picks_rahoitusrivit_only():
    from vaalikone.ingest.connectors.vaalirahoitus import parse_finance_listing

    base = "/fi/index/vaalirahoitus/haetietoavaalirahoitusilmoituksista/tutkitietoaineistoja"
    html = (
        f'<a href="{base}/kuntavaalit2025/E_VI_kuntavaalit2025.csv?dl=1">x</a>'
        f'<a href="{base}/kuntavaalit2025/RAHOITUSRIVIT_E_VI_kuntavaalit2025.csv?dl=2">x</a>'
        f'<a href="{base}/kuntavaalit2025/RAHOITUSRIVIT_E_EI_kuntavaalit2025.csv?dl=3">x</a>'
        f'<a href="{base}/aluevaalit2025/RAHOITUSRIVIT_E_VI_aluevaalit2025.csv?dl=4">x</a>'
    )
    files = parse_finance_listing(html, "kuntavaalit", 2025)
    assert set(files) == {"vaalirahoitusilmoitus", "ennakkoilmoitus"}
    assert files["vaalirahoitusilmoitus"].endswith("RAHOITUSRIVIT_E_VI_kuntavaalit2025.csv?dl=2")
    assert files["vaalirahoitusilmoitus"].startswith("https://www.vaalirahoitusvalvonta.fi/")


# --- äänestykset (api.eduskunta.fi, aanestys) ---


def _voting_fixture() -> dict:
    return json.loads(_fixture("eduskunta_aanestys.json"))["results"][0]["aanestys"]


def test_map_vote_has_no_silent_default():
    from vaalikone.ingest.votes import map_vote
    from vaalikone.models.vote import VoteChoice

    assert map_vote("Jaa") == VoteChoice.JAA
    assert map_vote(" Tyhjää ") == VoteChoice.TYHJA
    assert map_vote("Poissa") == VoteChoice.POISSA
    assert map_vote("Ja") is None  # ruotsinkielinen / tuntematon arvo ei ole "poissa"
    assert map_vote(None) is None


def test_parse_voting_groups_and_consistency():
    from vaalikone.ingest.votes import parse_voting, subject_title
    from vaalikone.models.vote import VoteChoice

    parsed = parse_voting(_voting_fixture())
    v = parsed["voting"]
    assert v["voting_id"] == "2025-130-4"
    assert v["session"] == "2025-130"
    assert v["year"] == 2025 and v["number"] == 4
    assert v["document_ref"] == "HE 156/2025 vp" and v["document_type"] == "HE"
    assert v["voted_at"].year == 2025
    assert v["result"] == {"jaa": 3, "ei": 1, "tyhja": 0, "poissa": 0, "yhteensa": 4}
    groups = v["group_results"]
    assert groups["kok"]["party"] == "KOK" and groups["kok"]["jaa"] == 1
    assert groups["sd"]["party"] == "SDP" and groups["sd"]["ei"] == 1
    assert groups["erk"]["party"] is None  # ryhmään kuulumaton: ei puoluetta
    assert "Hallitusryhmät" in v["government_opposition"]
    assert parsed["consistent"] and not parsed["unknown_votes"]
    assert [m["vote"] for m in parsed["members"]].count(VoteChoice.JAA) == 3
    assert subject_title(v).startswith("HE 156/2025 vp: Hallituksen esitys")

    broken = _voting_fixture()
    broken["aanestystapahtumat"][1]["kayttaytyminen"] = {"fi": "Nej"}
    parsed = parse_voting(broken)
    assert parsed["unknown_votes"] == ["Nej"]
    assert not parsed["consistent"]


async def test_store_voting_is_idempotent(db_session):
    from vaalikone.ingest.votes import _store_voting, parse_voting
    from vaalikone.models.representative import Representative
    from vaalikone.models.vote import Vote
    from vaalikone.models.voting import Voting

    parsed = parse_voting(_voting_fixture())
    reps: dict = {}
    for _ in range(2):
        stats = {"votings": 0, "member_votes": 0, "new_representatives": 0,
                 "unknown_votes": 0, "inconsistent": []}
        await _store_voting(db_session, parsed, reps, True, stats)
        await db_session.flush()
    assert stats["member_votes"] == 4
    assert await _count(db_session, Voting, Voting.voting_id == "2025-130-4") == 1
    assert await _count(db_session, Vote, Vote.subject == "2025-130-4") == 4
    assert await _count(
        db_session, Representative, Representative.person_id.in_(list(reps))
    ) == 4


def test_parse_voting_group_from_name_when_code_missing():
    from vaalikone.ingest.votes import parse_voting

    a = _voting_fixture()
    a["aanestystapahtumat"][3]["edkryhmalyhenne"] = None
    a["aanestystapahtumat"][3]["eduskuntaryhma"] = {"fi": "Eduskuntaryhmä Valta kuuluu kansalle"}
    groups = parse_voting(a)["voting"]["group_results"]
    assert groups["vkk"]["party"] == "VKK"
    assert "?" not in groups


def test_voting_document_text_and_url():
    from vaalikone.ingest.votes import (
        parse_voting,
        vote_document_url,
        voting_document_text,
    )
    from vaalikone.models.voting import Voting

    v = Voting(**parse_voting(_voting_fixture())["voting"])
    text = voting_document_text([v])
    assert text.startswith("Eduskunnan täysistuntoäänestykset — HE 156/2025 vp: Hallituksen")
    assert "Tulos: jaa 3, ei 1, tyhjä 0, poissa 0" in text
    assert "- SDP: ei (ei 1)" in text
    assert "- KOK: jaa (jaa 1)" in text
    # ryhmään kuulumaton näkyy ryhmän nimellä
    assert "- Eduskuntaryhmään kuulumaton: jaa (jaa 1)" in text
    url = vote_document_url("HE 156/2025 vp", v.item_title)
    assert url.startswith("https://api.eduskunta.fi/aanestykset/HE%20156%2F2025%20vp/")
    assert url == vote_document_url("HE 156/2025 vp", v.item_title)
    assert url != vote_document_url("HE 156/2025 vp", "Pääluokka 28")


async def _add_votings(db_session, ref: str, item: str, n: int, year: int = 2022):
    from datetime import datetime

    from vaalikone.models.voting import Voting

    vs = []
    for i in range(n):
        v = Voting(
            voting_id=f"{year}-9{len(ref)}-{i}", session=f"{year}-9", year=year, number=i,
            voted_at=datetime(year, 5, 1 + i), title=f"Äänestys {i}", item_title=item,
            document_ref=ref, cancelled=False, result={}, group_results={},
        )
        db_session.add(v)
        vs.append(v)
    await db_session.flush()
    return vs


async def test_find_votings_text_hits_capped_per_matter(db_session, monkeypatch):
    from vaalikone.query import votes as qv

    await _add_votings(db_session, "HE 1/2022 vp", "Laki kissojen verotuksesta", 5)
    await _add_votings(db_session, "HE 22/2022 vp", "Kissojen rokotuslaki", 1)

    async def boom(*a, **k):  # tekstiosumilla semanttista hakua ei tehdä
        raise AssertionError("semantic search should not run")

    monkeypatch.setattr("vaalikone.ingest.embedder.get_embedding", boom)
    hits = await qv.find_votings(db_session, "kissojen", limit=10)
    refs = [h.voting.document_ref for h in hits]
    assert refs.count("HE 1/2022 vp") == 3 and refs.count("HE 22/2022 vp") == 1
    assert all(h.match == "teksti" for h in hits)
    # uusimmat ensin
    assert hits[0].voting.voted_at.day == 5


async def test_find_votings_semantic_maps_documents_to_votings(db_session, monkeypatch):
    from vaalikone.query import votes as qv

    vs = await _add_votings(db_session, "HE 315/2033 vp", "Pohjois-Atlantin sopimus", 4, 2033)
    ok = await _store_document(
        db_session, source_type=SourceType.API, url="https://api.eduskunta.fi/aanestykset/t",
        title="Äänestykset: HE 315/2033 vp", text="x", content_type=ContentType.AANESTYS,
        metadata={"voting_ids": [v.voting_id for v in vs]},
    )
    assert ok
    await db_session.flush()
    doc_id = (await db_session.execute(
        select(Document.id).join(Source).where(Source.url.like("%/aanestykset/t"))
    )).scalar_one()

    async def fake_embedding(text, model=None):
        return [0.1, 0.2]

    async def fake_semantic(session, vec, **kw):
        assert kw["content_type"] == ContentType.AANESTYS and kw["chunk_index"] == 0
        return [
            {"document_id": str(doc_id), "similarity": 0.43},
            {"document_id": "00000000-0000-0000-0000-000000000000", "similarity": 0.30},
        ]

    monkeypatch.setattr("vaalikone.ingest.embedder.get_embedding", fake_embedding)
    monkeypatch.setattr("vaalikone.query.hybrid_search.semantic_search", fake_semantic)
    hits = await qv.find_votings(db_session, "Nato", limit=10)
    # 3 uusinta äänestystä; heikko osuma (yli marginaalin) karsittu
    assert [h.voting.voting_id for h in hits] == [v.voting_id for v in reversed(vs)][:3]
    assert all(h.match == "semanttinen" and h.similarity == 0.43 for h in hits)
