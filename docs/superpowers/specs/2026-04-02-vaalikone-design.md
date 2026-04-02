# Vaalikone — Suomen poliittisen datan tietokanta ja AI-kyselypalvelu

## Tarkoitus

Universaali data-backend joka kerää suomalaisten puolueiden mielipiteet, vaaliohjelmat, kansanedustajien tiedot ja päätöshistorian yhteen tietokantaan. Dataa voi kysellä tekoälyllä CLI:n, REST API:n tai MCP-serverin kautta. Tarkoitus olla valmiina kevään 2027 eduskuntavaaleihin.

## Arkkitehtuuri

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐
│  CLI Client │  │  MCP Server  │  │  Web UI      │
│  (click)    │  │  (FastMCP)   │  │  (myöhemmin) │
└──────┬──────┘  └──────┬───────┘  └──────┬───────┘
       │                │                  │
       └────────────────┼──────────────────┘
                        │
                 ┌──────▼───────┐
                 │  FastAPI     │
                 │  REST API    │
                 │  + Keycloak  │
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
   ┌──────▼──────┐ ┌───▼────┐ ┌─────▼──────┐
   │ PostgreSQL  │ │ pgvector│ │ Task Queue │
   │ (metadata,  │ │ (embed- │ │ (Celery +  │
   │  lähteet,   │ │  dings) │ │  Redis)    │
   │  puolueet)  │ │         │ │            │
   └─────────────┘ └────────┘ └─────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │  Ingest     │
                              │  Workers    │
                              │  + AI Filter│
                              └─────────────┘
```

### Komponentit

- **FastAPI** — REST API kaikille operaatioille (kysely, indeksointi, hallinta)
- **MCP Server** — FastMCP-kirjastolla, kiinnittyy Claude Codeen tai muuhun MCP-clientiin
- **CLI** — Click-pohjainen komentorivityökalu
- **PostgreSQL + pgvector** — yksi tietokanta sekä strukturoidulle datalle että vektoreille
- **Celery + Redis** — asynkroninen indeksointi taustalla
- **LiteLLM** — mallien abstraktio (OpenAI, Ollama, muu)
- **Keycloak** — autentikaatio, aluksi dev-moodissa pois päältä

## Tietomalli

Migraatiot hoidetaan Alembicilla. Tietomalli voi muuttua projektin edetessä.

### parties (puolueet)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| name | TEXT NOT NULL | Virallinen nimi |
| abbreviation | TEXT NOT NULL UNIQUE | Lyhenne (SDP, KOK...) |
| founded | INTEGER | Perustamisvuosi |
| ideology | TEXT | Aatesuunta |
| website | TEXT | Verkkosivut |
| logo_url | TEXT | Logon URL |

### representatives (kansanedustajat)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| party_id | UUID FK → parties | |
| first_name | TEXT NOT NULL | |
| last_name | TEXT NOT NULL | |
| constituency | TEXT | Vaalipiiri |
| elected_year | INTEGER | Valittu vuonna |
| birth_year | INTEGER | Syntymävuosi |
| email | TEXT | |
| website | TEXT | Henkilökohtainen sivusto |
| photo_url | TEXT | |
| social_media | JSONB | Some-tilit |

### sources (lähteet)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| source_type | ENUM(website, pdf, social_media, api, manual) | |
| url | TEXT | Lähteen osoite |
| title | TEXT | Kuvaus |
| fetched_at | TIMESTAMPTZ | Milloin haettu |
| status | ENUM(pending, indexed, failed) | |
| party_id | UUID FK → parties (nullable) | |
| representative_id | UUID FK → representatives (nullable) | |
| metadata | JSONB | Scraping-asetukset, päivitysväli yms. |

### documents (indeksoidut sisällöt)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| source_id | UUID FK → sources | |
| party_id | UUID FK → parties (nullable) | |
| representative_id | UUID FK → representatives (nullable) | |
| title | TEXT | |
| content_text | TEXT | Raaka teksti |
| content_type | ENUM(vaaliohjelma, blogikirjoitus, some_postaus, puheenvuoro, äänestys, kirjallinen_kysymys, aloite, muu) | |
| published_at | TIMESTAMPTZ | Julkaisupäivä |
| language | TEXT DEFAULT 'fi' | |
| ai_summary | TEXT | AI-generoitu yhteenveto |
| ai_topics | JSONB | AI-tunnistetut aihepiirit |
| ai_sentiment | TEXT | Sentimentti |
| metadata | JSONB | |

### embeddings (vektoriembeddings)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| document_id | UUID FK → documents | |
| chunk_index | INTEGER | Chunkin järjestysnumero |
| chunk_text | TEXT | Chunkin teksti |
| embedding | VECTOR | pgvector-vektori |
| model_name | TEXT | Mikä malli tuotti embeddingin |

### votes (äänestykset)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| representative_id | UUID FK → representatives | |
| session | TEXT | Istuntokausi |
| subject | TEXT | Äänestyksen aihe |
| vote | ENUM(jaa, ei, tyhjä, poissa) | |
| voted_at | TIMESTAMPTZ | |
| document_url | TEXT | Linkki asiakirjaan |

### query_log (kyselyloki)

| Kenttä | Tyyppi | Kuvaus |
|--------|--------|--------|
| id | UUID PK | |
| user_id | TEXT | |
| query_text | TEXT | |
| response_text | TEXT | |
| model_used | TEXT | |
| tokens_used | INTEGER | |
| created_at | TIMESTAMPTZ | |

## Indeksointiputki

### Vaiheet

1. **Tunnistus + scraping** — lähdetyyppi tunnistetaan, sisältö haetaan (trafilatura web, PyMuPDF PDF, API-clientit)
2. **AI-filtteri** — LLM prosessoi raakatekstin: tunnistaa puolueen/edustajan, luokittelee sisältötyypin, tekee yhteenvedon, poimii aihepiirit, arvioi sentimentin
3. **Chunking + embedding** — pilkotaan ~500 token paloiksi, vektoroidaan
4. **Tallennus** — documents + embeddings + source-päivitys

### Syöttötavat

```bash
# Yksittäinen URL
vaalikone ingest https://www.sdp.fi/vaaliohjelma-2027

# Tiedosto
vaalikone ingest --file vaaliohjelma.pdf --party SDP

# Eduskunnan bulk-data
vaalikone ingest --source eduskunta --type votes
vaalikone ingest --source eduskunta --type representatives

# Sivuston crawlaus
vaalikone ingest --crawl https://www.sdp.fi --party SDP --depth 2

# MCP:n kautta
"Indeksoi tämä dokumentti: https://..."
```

### Lähteiden hallinta

```bash
vaalikone sources list                 # Kaikki lähteet
vaalikone sources list --party SDP     # Puoluekohtaiset
vaalikone sources stats                # Tilastot
```

### Valmiit connectorit (built-in)

- `eduskunta` — avoindata.eduskunta.fi (edustajat, äänestykset, asiakirjat)
- `vaalit` — vaalit.fi (ehdokkaat, tulokset)
- `puolueet` — kaikkien puolueiden verkkosivujen scraping (konfiguraatiosta)

## Kyselyputki

### Vaiheet

1. **Kyselyn prosessointi** — LLM muokkaa haettavaan muotoon, tunnistaa aihe/puolueet/aikarajaus
2. **Hybrid-haku** — pgvector semanttinen haku + PostgreSQL full-text search suomeksi, yhdistetty Reciprocal Rank Fusion -rankingilla
3. **Kontekstin kokoaminen** — Top-K chunkit + metadata (puolue, edustaja, lähde)
4. **LLM-vastaus** — vastaus lähdeviitteineen

### Käyttötavat

```bash
# CLI chat
vaalikone chat "Vertaa puolueiden ilmastopolitiikkaa"

# Yksittäinen kysely
vaalikone query "Ketkä äänestivät sote-uudistuksen puolesta?"

# REST API
POST /api/v1/query {"question": "...", "model": "gpt-4o"}

# MCP
"Kysy vaalikoneelta: mitä hallituspuolueet..."
```

## MCP Server

### Tools

| Tool | Kuvaus |
|------|--------|
| query | Kysely tietokannasta luonnollisella kielellä |
| ingest_url | Indeksoi URL |
| ingest_text | Indeksoi teksti suoraan |
| list_sources | Listaa lähteet (filtteröinti puolue/tyyppi) |
| list_parties | Listaa puolueet |
| get_representative | Hae edustajan tiedot |
| search_votes | Hae äänestykset aiheesta |
| ingest_status | Tarkista indeksoinnin tila |

### Resources

| Resource | Kuvaus |
|----------|--------|
| parties://list | Puoluelista |
| representatives://list | Edustajat |
| sources://stats | Indeksointitilastot |

## Puolueet

### Eduskuntapuolueet

| Puolue | Lyhenne | Verkkosivut |
|--------|---------|-------------|
| Suomen Sosiaalidemokraattinen Puolue | SDP | sdp.fi |
| Kansallinen Kokoomus | KOK | kokoomus.fi |
| Perussuomalaiset | PS | perussuomalaiset.fi |
| Suomen Keskusta | KESK | keskusta.fi |
| Vihreä liitto | VIHR | vihreat.fi |
| Vasemmistoliitto | VAS | vasemmisto.fi |
| Svenska folkpartiet i Finland | RKP | sfp.fi |
| Kristillisdemokraatit | KD | kd.fi |
| Liike Nyt | LIIK | liikenyt.fi |

### Pienpuolueet

| Puolue | Lyhenne |
|--------|---------|
| Piraattipuolue | PIR |
| Eläinoikeuspuolue | EOP |
| Feministinen puolue | FP |
| Valta kuuluu kansalle | VKK |
| Suomen Kommunistinen Puolue | SKP |
| Liberaalipuolue | LIB |
| Sinimusta Liike | SML |

## Teknologiapino

| Kerros | Teknologia |
|--------|-----------|
| Kieli | Python 3.12+ |
| API | FastAPI + Uvicorn |
| MCP | FastMCP |
| CLI | Click |
| ORM | SQLAlchemy 2.0 |
| Migraatiot | Alembic |
| Tietokanta | PostgreSQL 16 + pgvector |
| Tehtäväjono | Celery + Redis |
| Scraping | trafilatura (web), PyMuPDF (PDF), httpx |
| LLM-abstraktio | LiteLLM (OpenAI, Ollama) |
| Embedding | sentence-transformers (lokaali) tai OpenAI |
| Autentikaatio | Keycloak (Docker) |
| Infrastruktuuri | Docker Compose |
| Testit | pytest + pytest-asyncio |
| Linting | ruff |

## Docker Compose -portit

| Palvelu | Portti |
|---------|--------|
| FastAPI (api) | 8003 |
| PostgreSQL | 5435 |
| Redis | 6382 |
| Keycloak | 8083 |
| Ollama | 11434 (olemassa oleva host-asennus) |

Ollama on jo asennettuna hostissa — ei omaa Docker-konttia, käytetään `host.docker.internal:11434`.

Keycloak on oletuksena pois päältä (`KEYCLOAK_ENABLED=false`).

## Projektirakenne

```
vaalikone/
├── docker-compose.yml
├── pyproject.toml
├── alembic/                    # tietokantamigraatiot
│   └── versions/
├── src/
│   └── vaalikone/
│       ├── api/                # FastAPI routes
│       │   ├── routes/
│       │   │   ├── query.py
│       │   │   ├── ingest.py
│       │   │   ├── parties.py
│       │   │   ├── representatives.py
│       │   │   └── sources.py
│       │   └── deps.py         # riippuvuudet (DB, auth)
│       ├── mcp/                # MCP server
│       │   └── server.py
│       ├── cli/                # Click CLI
│       │   ├── main.py
│       │   ├── chat.py
│       │   ├── ingest.py
│       │   └── sources.py
│       ├── core/               # jaettu ydinlogiikka
│       │   ├── config.py       # asetukset (.env)
│       │   ├── auth.py         # Keycloak-integraatio
│       │   ├── llm.py          # LiteLLM-abstraktio
│       │   └── database.py     # SQLAlchemy engine + session
│       ├── models/             # SQLAlchemy mallit
│       │   ├── party.py
│       │   ├── representative.py
│       │   ├── source.py
│       │   ├── document.py
│       │   ├── embedding.py
│       │   ├── vote.py
│       │   └── query_log.py
│       ├── ingest/             # indeksointiputki
│       │   ├── pipeline.py     # pääputki
│       │   ├── ai_filter.py    # AI-rikastus
│       │   ├── chunker.py      # tekstin pilkonta
│       │   └── connectors/     # datalähteiden connectorit
│       │       ├── eduskunta.py
│       │       ├── web.py
│       │       ├── pdf.py
│       │       └── social.py
│       ├── query/              # kyselyputki
│       │   ├── pipeline.py     # pääputki
│       │   ├── hybrid_search.py
│       │   └── response.py     # vastauksen generointi
│       └── workers/            # Celery taskit
│           └── tasks.py
├── config/
│   ├── parties.yaml            # puolueiden konfiguraatio
│   └── sources.yaml            # lähteiden konfiguraatio
├── tests/
└── docs/
```

## Alkuindeksointi

Järjestelmän käynnistyksen jälkeen ladataan:

1. Kaikki puolueet `config/parties.yaml` -tiedostosta
2. Eduskunnan avoin data: kansanedustajat + äänestyshistoria
3. Puolueiden verkkosivuilta vaaliohjelmat
4. vaalit.fi: ehdokasdata
