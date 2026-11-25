
from sqlalchemy import select

from vaalikone.models.document import ContentType, Document
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceStatus, SourceType
from vaalikone.models.vote import Vote, VoteChoice


async def test_create_party(db_session):
    party = Party(
        name="Testipuolue",
        abbreviation="TEST",
        website="https://test.fi",
    )
    db_session.add(party)
    await db_session.flush()

    result = await db_session.execute(select(Party).where(Party.abbreviation == "TEST"))
    fetched = result.scalar_one()
    assert fetched.name == "Testipuolue"
    assert fetched.id is not None


async def test_create_representative_with_party(db_session):
    party = Party(name="Testipuolue2", abbreviation="TS2")
    db_session.add(party)
    await db_session.flush()

    rep = Representative(
        party_id=party.id,
        first_name="Matti",
        last_name="Meikäläinen",
        constituency="Helsinki",
    )
    db_session.add(rep)
    await db_session.flush()

    result = await db_session.execute(
        select(Representative).where(Representative.last_name == "Meikäläinen")
    )
    fetched = result.scalar_one()
    assert fetched.party_id == party.id
    assert fetched.first_name == "Matti"


async def test_create_source(db_session):
    source = Source(
        source_type=SourceType.WEBSITE,
        url="https://sdp.fi/vaaliohjelma",
        title="SDP Vaaliohjelma",
        status=SourceStatus.PENDING,
    )
    db_session.add(source)
    await db_session.flush()
    assert source.id is not None
    assert source.status == SourceStatus.PENDING


async def test_create_document(db_session):
    source = Source(
        source_type=SourceType.WEBSITE,
        url="https://test.fi/doc",
        title="Test doc",
        status=SourceStatus.INDEXED,
    )
    db_session.add(source)
    await db_session.flush()

    doc = Document(
        source_id=source.id,
        title="Test Document",
        content_text="Tämä on testidokumentti.",
        content_type=ContentType.MUU,
    )
    db_session.add(doc)
    await db_session.flush()
    assert doc.id is not None


async def test_create_vote(db_session):
    party = Party(name="Testipuolue3", abbreviation="TS3")
    db_session.add(party)
    await db_session.flush()

    rep = Representative(party_id=party.id, first_name="Liisa", last_name="Testaaja")
    db_session.add(rep)
    await db_session.flush()

    vote = Vote(
        representative_id=rep.id,
        session="2026",
        subject="Testi äänestys",
        vote=VoteChoice.JAA,
    )
    db_session.add(vote)
    await db_session.flush()
    assert vote.vote == VoteChoice.JAA
