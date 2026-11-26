"""Täysistuntojen äänestykset api.eduskunta.fi:n hakurajapinnasta (kategoria ``aanestys``).

CLI: ``vaalikone ingest votes``.

- ``votings``: yksi rivi äänestystä kohden (otsikko, asia, käsittelyvaihe, tulos ja
  eduskuntaryhmien jakaumat äänestyshetken ryhmän mukaan).
- ``votes``: edustajakohtaiset äänet (``subject`` = äänestyksen tunniste). Rivejä
  on ~200 äänestystä kohden, joten oletuksena ne haetaan vain kuluvalta
  vaalikaudelta (``--member-votes-since``), äänestykset koko jaksolta.

Vanha ``avoindata.eduskunta.fi``-taulu (SaliDBAanestysEdustaja) on poistumassa;
sen rivien tunnisteet (numeerinen AanestysId) eivät vastaa uusia, ks. ``--drop-legacy``.
"""

import asyncio
import re
from datetime import datetime

import click
import httpx
from sqlalchemy import delete, func, insert, or_, select

from vaalikone.models.representative import Representative
from vaalikone.models.vote import Vote, VoteChoice
from vaalikone.models.voting import Voting

DEFAULT_VOTINGS_SINCE = 2019
DEFAULT_MEMBER_VOTES_SINCE = 2023  # vaalikausi 2023–2027
PAGE_SIZE = 100  # palvelun yläraja
MAX_PASSES = 3

# Osasta äänestyksiä puuttuu edkryhmalyhenne; ryhmä tunnistetaan silloin nimestä
GROUP_NAME_CODES = {"eduskuntaryhmä valta kuuluu kansalle": "vkk"}

VOTING_ID_RE = re.compile(r"^\d{4}-\d+-\d+$")
_CHOICES = {
    "jaa": VoteChoice.JAA,
    "ei": VoteChoice.EI,
    "tyhjää": VoteChoice.TYHJA,
    "tyhjaa": VoteChoice.TYHJA,
    "poissa": VoteChoice.POISSA,
}
_COUNT_KEY = {
    VoteChoice.JAA: "jaa", VoteChoice.EI: "ei",
    VoteChoice.TYHJA: "tyhja", VoteChoice.POISSA: "poissa",
}


def _fi(value) -> str | None:
    if isinstance(value, dict):
        value = value.get("fi")
    return value.strip() if isinstance(value, str) and value.strip() else None


def map_vote(value: str | None) -> VoteChoice | None:
    """'Jaa'/'Ei'/'Tyhjää'/'Poissa' -> VoteChoice. Tuntematon -> None (ei oletusta)."""
    return _CHOICES.get((value or "").strip().lower())


def _counts(d: dict | None) -> dict:
    d = d or {}
    return {
        "jaa": d.get("jaa"), "ei": d.get("ei"), "tyhja": d.get("tyhjia"),
        "poissa": d.get("poissa"), "yhteensa": d.get("yhteensa"),
    }


def _parse_dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_voting(a: dict) -> dict:
    """Hakutuloksen ``aanestys``-objekti -> {voting, members, unknown_votes, consistent}.

    Ryhmäjakaumat lasketaan edustajien äänistä (``edkryhmalyhenne`` äänestyshetkellä),
    koska rajapinnan ``eduskuntaryhmaJakaumat`` sisältää vain ryhmän nimen.
    """
    from vaalikone.cli.ingest import PARTY_MAP

    members, groups, unknown = [], {}, []
    for t in a.get("aanestystapahtumat") or []:
        raw = _fi(t.get("kayttaytyminen"))
        choice = map_vote(raw)
        if choice is None:
            unknown.append(raw)
            continue
        code = (_fi(t.get("edkryhmalyhenne")) or "").lower() or GROUP_NAME_CODES.get(
            (_fi(t.get("eduskuntaryhma")) or "").lower()
        )
        members.append({
            "person_id": str(t.get("henkilonumero") or "").strip() or None,
            "first_name": (t.get("etunimi") or "").strip(),
            "last_name": (t.get("sukunimi") or "").strip(),
            "constituency": _fi(t.get("vaalipiiri")),
            "group_code": code,
            "vote": choice,
        })
        g = groups.setdefault(code or "?", {
            "name": _fi(t.get("eduskuntaryhma")),
            "party": PARTY_MAP.get(code or ""),
            "jaa": 0, "ei": 0, "tyhja": 0, "poissa": 0,
        })
        g[_COUNT_KEY[choice]] += 1

    result = _counts(a.get("aanestystulos"))
    totals = {k: sum(g[k] for g in groups.values()) for k in ("jaa", "ei", "tyhja", "poissa")}
    consistent = all(result.get(k) in (None, v) for k, v in totals.items()) and (
        result.get("yhteensa") in (None, len(members))
    )
    kohta = a.get("kohta") or {}
    docs = kohta.get("asiakirjat") or {}
    year = str(a.get("istuntovpvuosi") or "")
    number = str(a.get("aanestysnumero") or "")
    return {
        "voting": {
            "voting_id": a.get("id"),
            "session": a.get("istunnonTunniste"),
            "year": int(year) if year.isdigit() else None,
            "number": int(number) if number.isdigit() else None,
            "voted_at": _parse_dt(a.get("aanestysalkuaika")),
            "title": _fi(a.get("aanestysotsikko")),
            "item_title": _fi(kohta.get("otsikko")),
            "stage": _fi(kohta.get("kasittelyvaihenimi")),
            "document_ref": _fi(docs.get("paaasiakirjaEduskuntatunnus")),
            "document_type": docs.get("paaasiakirjaAsiatyyppi"),
            "cancelled": bool(a.get("aanestysmitatoity")),
            "result": result,
            "group_results": groups,
            "government_opposition": {
                _fi(j.get("nimi")) or "?": _counts(j)
                for j in a.get("hallitusoppositioJakaumat") or []
            },
        },
        "members": members,
        "unknown_votes": unknown,
        "consistent": consistent,
    }


def subject_title(v: dict | Voting) -> str:
    """Luettava otsikko: 'HE 109/2024 vp: <asia> — <äänestysotsikko>'."""
    get = v.get if isinstance(v, dict) else lambda k: getattr(v, k)
    head = ": ".join(x for x in (get("document_ref"), get("item_title")) if x)
    return " — ".join(x for x in (head, get("title")) if x)


async def _ensure_schema(engine) -> None:
    """SQLite-kannoissa ei ole Alembicia: luo votings-taulu ja votes.subject-indeksi."""
    if engine.dialect.name != "sqlite":
        return
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Voting.__table__.create(c, checkfirst=True))
        for index in Vote.__table__.indexes:
            await conn.run_sync(lambda c, ix=index: ix.create(c, checkfirst=True))


async def _search_page(client, year: int, start: int) -> dict:
    for attempt in range(3):
        try:
            return await client.search_votings(year, max_results=PAGE_SIZE, start_from=start)
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


async def ingest_votes(
    since: int = DEFAULT_VOTINGS_SINCE,
    until: int | None = None,
    member_votes_since: int = DEFAULT_MEMBER_VOTES_SINCE,
    refresh: bool = False,
    drop_legacy: bool = False,
    update_parties: bool = True,
) -> dict:
    """Hae äänestykset vuosittain ja tallenna ``votings`` + edustajakohtaiset ``votes``.

    Idempotentti: jo tallennetut äänestykset ohitetaan (``refresh`` korvaa ne).
    Tulosjärjestys ei ole vakaa, joten vuotta haetaan uudelleen (enintään
    ``MAX_PASSES`` kertaa), kunnes kaikki ``totalResultCount``-tunnisteet on nähty.
    """
    from vaalikone.cli.ingest import PARTY_MAP, _get_session
    from vaalikone.ingest.connectors.eduskunta import EduskuntaClient
    from vaalikone.models.party import Party

    client = EduskuntaClient()
    until = until or datetime.now().year
    stats = {
        "votings": 0, "existing": 0, "member_votes": 0, "new_representatives": 0,
        "unknown_votes": 0, "inconsistent": [], "incomplete_years": {}, "legacy_deleted": 0,
        "representatives_party_updated": 0,
    }
    engine, async_session = await _get_session()
    await _ensure_schema(engine)
    latest_group: dict[str, tuple[datetime, str | None]] = {}
    try:
        async with async_session() as session:
            if drop_legacy:
                res = await session.execute(
                    delete(Vote).where(or_(Vote.subject.is_(None), ~Vote.subject.like("____-%-%")))
                    .execution_options(synchronize_session=False)
                )
                stats["legacy_deleted"] = res.rowcount or 0
                await session.commit()
                click.echo(f"Poistettu {stats['legacy_deleted']} vanhan rajapinnan äänestysriviä.")

            existing = set((await session.execute(select(Voting.voting_id))).scalars())
            reps = dict((await session.execute(
                select(Representative.person_id, Representative.id)
                .where(Representative.person_id.isnot(None))
            )).all())

            for year in range(since, until + 1):
                with_members = year >= member_votes_since
                seen: set[str] = set()
                total = None
                for _ in range(MAX_PASSES):
                    start = 0
                    while total is None or start < total:
                        data = await _search_page(client, year, start)
                        total = data.get("searchMetadata", {}).get("totalResultCount", 0)
                        batch = data.get("results") or []
                        if not batch:
                            break
                        start += len(batch)
                        for r in batch:
                            a = r.get("aanestys") or {}
                            vid = a.get("id")
                            if not vid or not VOTING_ID_RE.match(vid) or vid in seen:
                                continue
                            seen.add(vid)
                            parsed = parse_voting(a)
                            for m in parsed["members"]:
                                pid, at = m["person_id"], parsed["voting"]["voted_at"]
                                if pid and at and (
                                    pid not in latest_group or latest_group[pid][0] < at
                                ):
                                    latest_group[pid] = (at, m["group_code"])
                            if vid in existing and not refresh:
                                stats["existing"] += 1
                                continue
                            await _store_voting(
                                session, parsed, reps, with_members, stats,
                            )
                            existing.add(vid)
                        await session.commit()
                    if len(seen) >= (total or 0):
                        break
                click.echo(
                    f"  {year}: {len(seen)}/{total} äänestystä"
                    f"{' + edustajien äänet' if with_members else ''}"
                )
                if total and len(seen) < total:
                    stats["incomplete_years"][year] = (len(seen), total)

            # Vain kun ajo ulottuu kuluvaan vuoteen: muuten "viimeisin" ääni voi olla vanha
            if update_parties and latest_group and until >= datetime.now().year:
                # Edustajan puolue = ryhmä viimeisimmässä äänestyksessä (tv/erk -> ei puoluetta)
                parties = dict((await session.execute(
                    select(Party.abbreviation, Party.id)
                )).all())
                for pid, (_, code) in latest_group.items():
                    rep_id = reps.get(pid)
                    party_id = parties.get(PARTY_MAP.get(code or ""))
                    if rep_id is None:
                        continue
                    rep = await session.get(Representative, rep_id)
                    if rep is not None and rep.party_id != party_id:
                        rep.party_id = party_id
                        stats["representatives_party_updated"] += 1
                await session.commit()
            stats["votes_in_db"] = (await session.execute(
                select(func.count()).select_from(Vote)
            )).scalar_one()
    finally:
        await engine.dispose()

    click.echo(
        f"\nValmis: {stats['votings']} uutta äänestystä ({stats['existing']} jo kannassa), "
        f"{stats['member_votes']} edustajan ääntä, {stats['new_representatives']} uutta "
        f"edustajaa, {stats['representatives_party_updated']} edustajan puolue päivitetty."
    )
    if stats["unknown_votes"]:
        click.echo(f"VAROITUS: {stats['unknown_votes']} tuntematonta äänivalintaa ohitettu.")
    if stats["inconsistent"]:
        click.echo(
            f"VAROITUS: {len(stats['inconsistent'])} äänestyksen äänet eivät täsmää "
            f"tulokseen: {stats['inconsistent'][:10]}"
        )
    if stats["incomplete_years"]:
        click.echo(f"VAROITUS: vajaat vuodet {stats['incomplete_years']}")
    return stats


async def _store_voting(session, parsed: dict, reps: dict, with_members: bool, stats: dict):
    v = parsed["voting"]
    vid = v["voting_id"]
    stats["unknown_votes"] += len(parsed["unknown_votes"])
    if not parsed["consistent"]:
        stats["inconsistent"].append(vid)

    await session.execute(
        delete(Voting).where(Voting.voting_id == vid).execution_options(synchronize_session=False)
    )
    await session.execute(
        delete(Vote).where(Vote.subject == vid).execution_options(synchronize_session=False)
    )
    session.add(Voting(**v))
    stats["votings"] += 1
    if not with_members:
        return

    rows = []
    for m in parsed["members"]:
        pid = m["person_id"]
        if not pid:
            continue
        if pid not in reps:
            rep = Representative(
                person_id=pid, first_name=m["first_name"], last_name=m["last_name"],
                constituency=m["constituency"],
            )
            session.add(rep)
            await session.flush()
            reps[pid] = rep.id
            stats["new_representatives"] += 1
        rows.append({
            "representative_id": reps[pid],
            "session": v["session"],
            "subject": vid,
            "subject_title": None,  # otsikko on votings-taulussa (join subject = voting_id)
            "vote": m["vote"],
            "voted_at": v["voted_at"],
        })
    if rows:
        await session.execute(insert(Vote), rows)
        stats["member_votes"] += len(rows)
