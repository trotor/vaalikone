# TODO

## Tehty (2026-11-25)

### Tietoturva
- [x] API-autentikaatio (`VAALIKONE_API_KEY` + `X-API-Key`-header, `/health` ja `/` avoinna)
- [x] Malli-allowlist chat-endpointtiin (`CHAT_ALLOWED_MODELS`)
- [x] URL-validointi SSRF-suojaksi (`ingest/url_validation.py`, käytössä web/pdf/crawler)
- [x] ILIKE wildcard -eskalointi (`escape_ilike`, escape `\`, `%`, `_`)
- [x] Docker-porttien sitominen 127.0.0.1:hin
- [x] Dockerfile: non-root user
- [x] Salasanojen siirto ympäristömuuttujiin (docker-compose `${VAR:-default}`)

### Uusi data
- [x] Kaikkien 16 puolueen vaaliohjelmat/puolueohjelmat + varjobudjetit 2026 (`config/sources.yaml`, `vaalikone ingest programs`)
- [x] Äänestysotsikot (`ingest vote-subjects`, `votes.subject_title`)
- [x] Täysistuntopuheenvuorot (`ingest speeches`, uusi `api.eduskunta.fi`)
- [x] Kirjalliset kysymykset KK (`ingest questions`, 41 900+ kpl)
- [x] Ehdokasdata eduskuntavaalit 2023 (Tilastokeskus PxWeb `evaa/13t3.px`, 2 424 ehdokasta)
- [x] API: `/elections`, `/elections/{id}/candidates`, `/elections/{id}/stats`, `/representatives/{id}/votes`
- [x] MCP-työkalut: `search_votes`, `list_candidates`

### Tekninen kehitys
- [x] Celery-työntekijä (`workers/tasks.py`) + `--queue` CLI-komennoissa, worker docker composessa
- [x] Tietokanta: indeksit, unique-constraints (dedup), pg_trgm, `representatives.person_id`
- [x] Haku: N+1-korjattu (snippetit SQL:ssä), ILIKE-escape
- [x] CI/CD (GitHub Actions: ruff, pytest + postgres-palvelu, docker build)
- [x] Dependency lockfile (`uv.lock`)
- [x] Alembic: `DATABASE_URL`-env override

### Web UI
- [x] Vastauksen streaming (SSE, `/api/v1/chat/stream`)
- [x] Keskusteluhistoria (localStorage + sivupaneeli)
- [x] Mobiili-responsiivisuus (media query)
- [x] Tumma/vaalea teema (localStorage)
- [x] Puolueiden värikoodit lähdetageissa
- [x] API-avain -kenttä (X-API-Key, localStorage)

## Seuraavat vaiheet

### Eurooppalaiset AI-mallit (kokeiltava)
- [ ] **Mistral** — `mistral-small`, `mistral-medium` LiteLLM:n kautta
- [ ] **Mistral Embed** — embedding-malli, vertaa bge-m3:een
- [ ] **Grok** (xAI) — `xai/grok-2` (vaatii XAI_API_KEY)
- [ ] **Cohere** — `command-r`, Embed v3 suomeksi
- [ ] **Mistral lokaalit** — `mistral-nemo:12b` Ollamassa

### Lisädata
- [x] Puoluerekisteri-harvesteri: 20 rekisteröityä puoluetta + yleisohjelmat (`ingest party-register`) (2026-11-26)
- [x] FSD Pohtiva -harvesteri: puolueohjelmat 2019→, EU-vaaliohjelmat, duplikaattitarkistus (`ingest pohtiva`) (2026-11-26)
- [ ] Eduskuntavaaliohjelmat 2027 — puolueet julkaisevat talvella 2026–27; lisää `config/sources.yaml`:iin ja aja `ingest pohtiva --since 2026` kun FSD on arkistoinut
- [ ] Puolueiden säännöt rekisteristä (`publicapi/attachment/{id}/2/rules.pdf`) — tarvitaanko?
- [ ] Puoluetuki ja puolueiden tukiilmoitukset (vaalirahoitusvalvonta.fi)
- [ ] Kuntavaalit 2025 — ehdokasdata (stat.fi kvaa / oikeusministeriö)
- [ ] Eduskuntavaalit 2027 — ehdokas- ja tulosdata kun julkaistaan
- [ ] Vaalikoneiden vastausdata (YLE, HS) jos saatavilla
- [ ] Kansanedustajien some-tilit (X/Twitter)
- [ ] Vaalirahailsmoitukset (vaalirahoitus.fi)
- [ ] Hallitusohjelma 2023 + budjetit (valtioneuvosto.fi, VM)
- [ ] Eduskunnan vanha avoindata siirtyy 2027 uuteen palveluun — päivitä `EDUSKUNTA_API_URL`

### Tekninen kehitys
- [ ] Keycloak-autentikaatio tuotantoon (dev-profiili jo composessa)
- [ ] Rate limiting API:lle (esim. slowapi)
- [ ] Tietokantadumpin automaattinen päivitys (cron)
- [ ] Lisää testejä: ingest-polkujen integraatiotestit mockatulla API:lla
