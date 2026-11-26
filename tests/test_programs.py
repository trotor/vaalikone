from vaalikone.cli.ingest import KIND_TO_CONTENT_TYPE, _load_sources_yaml
from vaalikone.models.document import ContentType


def test_sources_yaml_loads_and_covers_all_parties():
    entries = _load_sources_yaml()
    assert len(entries) >= 16
    parties = {e.get("party", "") for e in entries}
    # EOP, VKK, FP, KRI, TP, HAMP ja SGP tulevat puoluerekisteristä / Pohtivasta
    expected = {
        "SDP", "KOK", "PS", "KESK", "VIHR", "VAS", "RKP", "KD", "LIIK",
        "PIR", "SKP", "LIB", "SML", "AP", "VAPL",
    }
    assert expected <= parties
    kinds = {e["kind"] for e in entries}
    assert {"vaaliohjelma", "puolueohjelma", "varjobudjetti"} <= kinds
    for e in entries:
        assert e["url"].startswith("https://")
        assert e["type"] in ("pdf", "web", "crawl")
        assert e["kind"] in KIND_TO_CONTENT_TYPE
        assert e.get("language", "fi") in ("fi", "sv")


def test_kind_mapping():
    assert KIND_TO_CONTENT_TYPE["vaaliohjelma"] == ContentType.VAALIOHJELMA
    assert KIND_TO_CONTENT_TYPE["puolueohjelma"] == ContentType.PUOLUEOHJELMA
    assert KIND_TO_CONTENT_TYPE["varjobudjetti"] == ContentType.VARJOBUDJETTI


def test_party_sources_point_to_party_domain():
    """Puolueen ohjelmarivin URL:n pitää olla puolueen omalla verkkotunnuksella."""
    from urllib.parse import urlparse

    from vaalikone.ingest.harvesters import load_parties_yaml

    domains = {
        p["abbreviation"]: urlparse(p["website"]).netloc.removeprefix("www.")
        for p in load_parties_yaml() if p.get("website")
    }
    for e in _load_sources_yaml():
        party = e.get("party")
        if not party:
            continue
        host = urlparse(e["url"]).netloc.removeprefix("www.")
        assert host.endswith(domains[party]), (party, e["url"])
