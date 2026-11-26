"""Puoluedatan harvesterit: puoluerekisteri.fi ja FSD Pohtiva.

CLI: ``vaalikone ingest party-register`` ja ``vaalikone ingest pohtiva``.
"""

import re
from datetime import datetime
from pathlib import Path

import click
import yaml
from sqlalchemy import select

from vaalikone.ingest.connectors import pohtiva as pohtiva_mod
from vaalikone.ingest.connectors import puoluerekisteri
from vaalikone.ingest.connectors.pdf import extract_pdf_bytes
from vaalikone.models.document import ContentType, Document
from vaalikone.models.party import Party
from vaalikone.models.source import Source, SourceType

PARTIES_YAML = "config/parties.yaml"
MIN_REGISTER_PLATFORM_CHARS = 300  # Hamppupuolueen yleisohjelma on ~540 merkkiä
MIN_POHTIVA_CHARS = 300
DEFAULT_POHTIVA_SINCE = 2019


def load_parties_yaml(path: str = PARTIES_YAML) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p) as f:
        data = yaml.safe_load(f) or {}
    return data.get("parties", [])


def pohtiva_code_for(entry: dict) -> str | None:
    """parties.yaml-rivin Pohtiva-koodi. ``pohtiva: null`` = ei Pohtivassa."""
    if "pohtiva" in entry:
        return entry["pohtiva"]
    abbr = entry["abbreviation"]
    return pohtiva_mod.ABBR_TO_POHTIVA.get(abbr, abbr)


# --- Lähes-duplikaattien tunnistus -------------------------------------------------

_WORD_RE = re.compile(r"[0-9a-zåäöüéè]+")


def normalize_words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


_HYPHEN_BREAK_RE = re.compile(r"(\w)-[ \t]*\n\s*(\w)")


def shingles(text: str) -> set[tuple[str, str, str]]:
    """Tekstin 3 sanan jonot (tavutetut rivinvaihdot yhdistetty, kirjainkoko ja välimerkit pois).

    Joukkona järjestyksestä riippumaton: PDF:n sivuylätunnisteet ja palstat eivät
    rikko vertailua kuin murto-osalta.
    """
    words = normalize_words(_HYPHEN_BREAK_RE.sub(r"\1\2", text or ""))
    return set(zip(words, words[1:], words[2:]))


def containment(candidate: set, existing: set) -> float:
    """Kuinka suuri osa ehdokkaan 3-sanajonoista löytyy olemassa olevasta tekstistä."""
    if not candidate:
        return 0.0
    return len(candidate & existing) / len(candidate)


# Mitattu oikealla datalla (Pohtiva vs. puolueiden omat PDF:t/sivut): sama ohjelma
# 0,65–0,83, eri ohjelma joka kierrättää kappaleita ≤ 0,21.
DUPLICATE_CONTAINMENT = 0.5


def is_near_duplicate(candidate: set, existing: set) -> bool:
    return containment(candidate, existing) >= DUPLICATE_CONTAINMENT


# --- puoluerekisteri.fi ------------------------------------------------------------


async def ingest_party_register(
    programs: bool = True, refresh: bool = False, parties_yaml: str = PARTIES_YAML
) -> dict:
    """Synkronoi puolueet puoluerekisteristä ja hae niiden yleisohjelmat (PDF).

    Puolueiden lyhenteet ja kuvaukset tulevat config/parties.yaml:sta
    (``registry_id``-kenttä yhdistää rekisteriin). Rekisterin puolue, jota ei
    löydy yaml:sta, raportoidaan — lisää se yaml:iin lyhenteen kanssa.
    """
    from vaalikone.cli.ingest import _get_session, _store_document

    yaml_parties = load_parties_yaml(parties_yaml)
    by_registry = {p["registry_id"]: p for p in yaml_parties if p.get("registry_id")}

    click.echo(f"Haetaan rekisteröidyt puolueet: {puoluerekisteri.REGISTERED_URL}")
    registered = await puoluerekisteri.fetch_registered_parties()
    registered_ids = {r["registry_id"] for r in registered}
    click.echo(f"Puoluerekisterissä {len(registered)} puoluetta.")

    stats = {
        "registered": len(registered), "parties_added": 0, "unmapped": 0,
        "programs_stored": 0, "programs_missing": 0, "programs_skipped": 0, "failed": 0,
    }

    engine, async_session = await _get_session()
    try:
        async with async_session() as session:
            for reg in registered:
                entry = by_registry.get(reg["registry_id"])
                if not entry:
                    click.echo(
                        f"  [uusi rekisterissä] id={reg['registry_id']} {reg['name']} "
                        f"({reg['website'] or '-'}) — lisää {parties_yaml}:iin"
                    )
                    stats["unmapped"] += 1
                    continue
                abbr = entry["abbreviation"]
                existing = (
                    await session.execute(select(Party).where(Party.abbreviation == abbr))
                ).scalar_one_or_none()
                if existing is None:
                    session.add(Party(
                        name=entry["name"],
                        abbreviation=abbr,
                        website=entry.get("website") or reg["website"],
                        ideology=entry.get("ideology"),
                        founded=entry.get("founded"),
                    ))
                    stats["parties_added"] += 1
                    click.echo(f"  [lisätty] {abbr} {entry['name']}")
                else:
                    # Täydennä vain puuttuvat kentät; käsin muokattuja arvoja ei ylikirjoiteta
                    for field, value in (
                        ("website", entry.get("website") or reg["website"]),
                        ("ideology", entry.get("ideology")),
                        ("founded", entry.get("founded")),
                    ):
                        if value and not getattr(existing, field):
                            setattr(existing, field, value)
            await session.commit()

        for p in yaml_parties:
            if p.get("registry_id") and p["registry_id"] not in registered_ids:
                click.echo(
                    f"  [huom] {p['abbreviation']} (registry_id={p['registry_id']}) ei ole enää "
                    "rekisterissä — merkitse parties.yaml:iin registered: false"
                )

        if not programs:
            return stats

        click.echo("\nHaetaan yleisohjelmat (publicapi/attachment/{id}/4/platform.pdf)...")
        for reg in registered:
            entry = by_registry.get(reg["registry_id"])
            if not entry:
                continue
            abbr = entry["abbreviation"]
            url = puoluerekisteri.platform_pdf_url(reg["registry_id"])
            try:
                async with async_session() as session:
                    if not refresh:
                        exists = (
                            await session.execute(select(Source.id).where(Source.url == url))
                        ).first()
                        if exists:
                            stats["programs_skipped"] += 1
                            click.echo(f"  [skip exists] {abbr}")
                            continue
                    pdf = await puoluerekisteri.fetch_platform_pdf(reg["registry_id"])
                    if pdf is None:
                        stats["programs_missing"] += 1
                        click.echo(f"  [ei liitettä] {abbr}")
                        continue
                    content = extract_pdf_bytes(pdf, url)
                    text = (content or {}).get("text", "")
                    if len(text.strip()) < MIN_REGISTER_PLATFORM_CHARS:
                        raise ValueError(f"PDF:stä vain {len(text.strip())} merkkiä tekstiä")
                    party = (
                        await session.execute(select(Party).where(Party.abbreviation == abbr))
                    ).scalar_one()
                    title = f"{entry['name']}: yleisohjelma (puoluerekisteri)"
                    await _store_document(
                        session,
                        source_type=SourceType.PDF,
                        url=url,
                        title=title,
                        text=text,
                        content_type=ContentType.PUOLUEOHJELMA,
                        party_id=party.id,
                        metadata={
                            "kind": "puolueohjelma",
                            "program_source": "puoluerekisteri.fi",
                            "registry_id": reg["registry_id"],
                            "pages": content.get("pages"),
                        },
                        replace=refresh,
                    )
                    await session.commit()
                    stats["programs_stored"] += 1
                    click.echo(f"  [ok] {abbr}: {title} ({len(text):,} merkkiä)")
            except Exception as e:
                stats["failed"] += 1
                click.echo(f"  [fail] {abbr}: {type(e).__name__}: {str(e)[:120]}")
    finally:
        await engine.dispose()

    click.echo(
        f"\nValmis: {stats['parties_added']} puoluetta lisätty, "
        f"{stats['programs_stored']} yleisohjelmaa tallennettu, "
        f"{stats['programs_missing']} ilman liitettä, {stats['failed']} epäonnistui."
    )
    return stats


# --- FSD Pohtiva -------------------------------------------------------------------


async def ingest_pohtiva(
    parties: list[str] | None = None,
    since: int = DEFAULT_POHTIVA_SINCE,
    until: int | None = None,
    types: list[str] | None = None,
    languages: list[str] | None = None,
    max_per_party: int | None = None,
    refresh: bool = False,
    delay: float = 1.0,
    dry_run: bool = False,
    parties_yaml: str = PARTIES_YAML,
) -> dict:
    """Hae puolueiden ohjelmat FSD Pohtivasta.

    Oletuksena vain tietokannassa olevat puolueet, vuodesta ``since`` alkaen,
    kieli fi (käännökset kaksinkertaistaisivat puolueen painon haussa). Pohtivan
    kopio ohitetaan, jos sama teksti on jo tallennettu puolueen omilta sivuilta
    (lähes-duplikaattitarkistus); tyypittömälle (MUU) kopiolle annetaan tällöin
    Pohtivan tyyppi ja vuosi. ``refresh`` korvaa vain aiemmin Pohtivasta haetut.
    """
    from vaalikone.cli.ingest import _get_session, _store_document

    languages = [lang.lower() for lang in (languages or ["fi"])]
    types = [t.lower() for t in types] if types else None
    wanted = {p.upper() for p in parties} if parties else None

    yaml_by_abbr = {p["abbreviation"]: p for p in load_parties_yaml(parties_yaml)}
    stats = {
        "listed": 0, "stored": 0, "skipped": 0, "duplicates": 0, "retyped": 0, "failed": 0,
    }

    engine, async_session = await _get_session()
    client = pohtiva_mod.PohtivaClient(delay=delay)
    try:
        async with async_session() as session:
            db_parties = (await session.execute(select(Party))).scalars().all()

        for party in sorted(db_parties, key=lambda p: p.abbreviation):
            abbr = party.abbreviation
            if wanted and abbr not in wanted:
                continue
            entry = yaml_by_abbr.get(abbr, {"abbreviation": abbr})
            code = pohtiva_code_for(entry)
            if not code:
                continue
            try:
                rows = await client.program_list(code)
            except Exception as e:
                click.echo(f"  [fail] {abbr} ({code}): ohjelmalista: {type(e).__name__}: {e}")
                stats["failed"] += 1
                continue

            rows = [
                r for r in rows
                if r["year"] and r["year"] >= since
                and (until is None or r["year"] <= until)
                and r["language"] in languages
                and (types is None or r["type"] in types)
            ]
            rows.sort(key=lambda r: r["year"], reverse=True)
            if max_per_party:
                rows = rows[:max_per_party]
            stats["listed"] += len(rows)
            click.echo(f"\n== {abbr} (Pohtiva {code}): {len(rows)} ohjelmaa")
            if dry_run:
                for r in rows:
                    ct, election = pohtiva_mod.classify(r["title"], r["type"])
                    click.echo(
                        f"  {r['year']} {r['language']} {ct.value:18} {r['title'][:80]}"
                    )
                continue

            # Puolueen olemassa olevat tekstit duplikaattitarkistukseen
            async with async_session() as session:
                docs = (await session.execute(
                    select(
                        Document.id, Document.title, Document.content_type,
                        Document.content_text, Source.url,
                    )
                    .join(Source, Source.id == Document.source_id)
                    .where(Document.party_id == party.id, Document.content_text.isnot(None))
                )).all()
            known_urls = {u for *_, u in docs}
            corpus = [
                (doc_id, t, ctype, shingles(c))
                for doc_id, t, ctype, c, u in docs if "fsd.tuni.fi/pohtiva" not in (u or "")
            ]

            for r in rows:
                if r["url"] in known_urls and not refresh:
                    stats["skipped"] += 1
                    continue
                try:
                    page = await client.program(r["url"])
                    if not page or len(page["text"]) < MIN_POHTIVA_CHARS:
                        click.echo(f"  [tyhjä] {r['year']} {r['title'][:70]}")
                        stats["skipped"] += 1
                        continue
                    ct, election = pohtiva_mod.classify(r["title"], r["type"])
                    cand = shingles(page["text"])
                    dup_idx = next(
                        (i for i, d in enumerate(corpus) if is_near_duplicate(cand, d[3])), None
                    )
                    if dup_idx is not None:
                        dup_id, dup_title, dup_type, dup_sh = corpus[dup_idx]
                        click.echo(f"  [dup] {r['year']} {r['title'][:60]} ≈ {dup_title[:50]}")
                        stats["duplicates"] += 1
                        if dup_type == ContentType.MUU:
                            # Sama teksti on jo kannassa tyypittömänä: anna sille Pohtivan tyyppi
                            async with async_session() as session:
                                doc = await session.get(Document, dup_id)
                                doc.content_type = ct
                                doc.published_at = doc.published_at or datetime(r["year"], 1, 1)
                                doc.metadata_ = {
                                    **(doc.metadata_ or {}), "kind": ct.value,
                                    "year": r["year"], "election": election,
                                    "pohtiva_id": r["pohtiva_id"],
                                }
                                await session.commit()
                            # Rivit käydään uusin ensin: ensimmäinen osuma voittaa
                            corpus[dup_idx] = (dup_id, dup_title, ct, dup_sh)
                            stats["retyped"] += 1
                        continue
                    kind = ct.value
                    async with async_session() as session:
                        await _store_document(
                            session,
                            source_type=SourceType.WEBSITE,
                            url=r["url"],
                            title=f"{r['title']} ({abbr} {r['year']})",
                            text=page["text"],
                            content_type=ct,
                            party_id=party.id,
                            published_at=datetime(r["year"], 1, 1),
                            language=r["language"],
                            metadata={
                                "kind": kind,
                                "program_source": "FSD Pohtiva",
                                "pohtiva_id": r["pohtiva_id"],
                                "pohtiva_code": code,
                                "pohtiva_type": r["type"],
                                "election": election,
                                "year": r["year"],
                                "attribution": pohtiva_mod.ATTRIBUTION,
                            },
                            replace=refresh,
                        )
                        await session.commit()
                    stats["stored"] += 1
                    click.echo(
                        f"  [ok] {r['year']} {r['language']} {kind}: {r['title'][:70]} "
                        f"({len(page['text']):,} merkkiä)"
                    )
                except Exception as e:
                    stats["failed"] += 1
                    click.echo(f"  [fail] {r['title'][:60]}: {type(e).__name__}: {str(e)[:100]}")
    finally:
        await client.aclose()
        await engine.dispose()

    click.echo(
        f"\nValmis: {stats['stored']} tallennettu, {stats['duplicates']} duplikaattia "
        f"({stats['retyped']} tyypitetty), "
        f"{stats['skipped']} ohitettu, {stats['failed']} epäonnistui "
        f"({stats['listed']} listattu)."
    )
    return stats
