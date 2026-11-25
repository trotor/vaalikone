from vaalikone.cli.ingest import KIND_TO_CONTENT_TYPE, _load_sources_yaml
from vaalikone.models.document import ContentType


def test_sources_yaml_loads_and_covers_all_parties():
    entries = _load_sources_yaml()
    assert len(entries) >= 16
    parties = {e["party"] for e in entries}
    expected = {
        "SDP", "KOK", "PS", "KESK", "VIHR", "VAS", "RKP", "KD", "LIIK",
        "PIR", "EOP", "FP", "VKK", "SKP", "LIB", "SML",
    }
    assert expected <= parties
    kinds = {e["kind"] for e in entries}
    assert {"vaaliohjelma", "puolueohjelma", "varjobudjetti"} <= kinds
    for e in entries:
        assert e["url"].startswith("https://")
        assert e["type"] in ("pdf", "web", "crawl")


def test_kind_mapping():
    assert KIND_TO_CONTENT_TYPE["vaaliohjelma"] == ContentType.VAALIOHJELMA
    assert KIND_TO_CONTENT_TYPE["puolueohjelma"] == ContentType.PUOLUEOHJELMA
    assert KIND_TO_CONTENT_TYPE["varjobudjetti"] == ContentType.VARJOBUDJETTI
