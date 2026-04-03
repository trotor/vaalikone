# Vaalikone

Suomen poliittisen datan tietokanta ja AI-kyselypalvelu. Keraa puolueiden vaaliohjelmat, varjobudjetit, kansanedustajien tiedot ja aanestyshistorian yhteen paikkaan. Dataa voi kysella tekoalylla CLI:n, REST API:n, web-chatin tai MCP-serverin kautta.

Rakennettu kevaan 2027 eduskuntavaaleja varten.

## Ominaisuudet

- **16 puoluetta** — kaikki eduskuntapuolueet + pienpuolueet
- **103 dokumenttia** — vaaliohjelmat, varjobudjetit, politiikkaohjelmat (web + PDF)
- **2 677 kansanedustajaa** — eduskunnan avoin data vuodesta 1907
- **183 710 aanestysta** — kansanedustajien aanestyshistoria
- **Hybrid-haku** — PostgreSQL full-text + semanttinen vektorihaku (pgvector)
- **AI-chat** — kysele politiikasta luonnollisella kielella (OpenAI / lokaali Ollama)
- **Web UI** — selainpohjainen chat-kayttoliittyma
- **Offline-tuki** — toimii ilman nettia lokaalien mallien kanssa

## Teknologiapino

| Kerros | Teknologia |
|--------|-----------|
| Kieli | Python 3.12+ |
| API | FastAPI + Uvicorn |
| CLI | Click |
| ORM | SQLAlchemy 2.0 (async) |
| Migraatiot | Alembic |
| Tietokanta | PostgreSQL 16 + pgvector |
| LLM | LiteLLM (OpenAI, Ollama) |
| Embedding | OpenAI text-embedding-3-small / Ollama (bge-m3, mxbai-embed-large, nomic-embed-text) |
| Scraping | trafilatura (web), PyMuPDF (PDF) |
| Infra | Docker Compose |

## Pikakaynistys

```bash
# 1. Kloonaa ja asenna
git clone <repo-url>
cd vaalikone
cp .env.example .env
# Muokkaa .env: lisaa OPENAI_API_KEY (valinnainen)

# 2. Kaynnista tietokanta
docker compose up -d postgres redis

# 3. Asenna Python-riippuvuudet
pip install -e ".[dev]"

# 4. Aja migraatiot
alembic upgrade head

# 5. Syota alkudata
vaalikone seed parties
vaalikone ingest representatives
vaalikone ingest votes --max-pages 50

# 6. Kaynnista web UI
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003
# Avaa http://localhost:8003
```

## CLI-komennot

```bash
# Datan syotto
vaalikone seed parties                          # Syota puolueet
vaalikone ingest representatives                # Hae kansanedustajat eduskunnasta
vaalikone ingest votes --max-pages 100          # Hae aanestyksia
vaalikone ingest url <URL> --party SDP          # Indeksoi web-sivu
vaalikone ingest pdf <URL> --party PS           # Indeksoi PDF
vaalikone ingest embed --model text-embedding-3-small  # Generoi embeddings

# Haku ja kysely
vaalikone search "metsakeskus"                  # Tekstihaku
vaalikone search "verotus" --party KOK          # Puoluekohtainen haku
vaalikone chat "Vertaa puolueiden ilmastopolitiikkaa"   # AI-chat

# Tilastot
vaalikone stats                                 # Tietokannan tilastot
vaalikone documents                             # Dokumentit puolueittain
vaalikone documents --party VIHR                # Yhden puolueen dokumentit
vaalikone sources list                          # Lahteet
vaalikone sources stats                         # Lahdetilastot
```

## REST API

```
GET  /health                    Terveystarkistus
GET  /api/v1/stats              Tietokannan tilastot
GET  /api/v1/parties            Puolueet
GET  /api/v1/parties/{abbr}     Puolueen tiedot + tilastot
GET  /api/v1/representatives    Kansanedustajat (?party=SDP)
GET  /api/v1/documents          Dokumentit (?party=VIHR)
GET  /api/v1/sources            Datalähteet
GET  /api/v1/sources/stats      Lahdetilastot
GET  /api/v1/search?q=...       Tekstihaku (?party=KOK&limit=10)
POST /api/v1/chat               AI-chat (JSON body)
GET  /api/v1/connectivity       Palveluiden tila (OpenAI, Ollama, internet)
```

## Docker Compose -portit

| Palvelu | Portti |
|---------|--------|
| FastAPI | 8003 |
| PostgreSQL | 5435 |
| Redis | 6382 |
| Keycloak | 8083 (profiili: auth) |

## Embedding-mallit

Tuetut embedding-mallit (valitaan `--model` -flagilla tai .env:ssa):

| Malli | Dimensio | Kieli | Sijainti |
|-------|----------|-------|----------|
| text-embedding-3-small | 1536 | Monikielinen | OpenAI API |
| text-embedding-3-large | 3072 | Monikielinen | OpenAI API |
| bge-m3 | 1024 | Monikielinen (erinomainen suomi) | Ollama (lokaali) |
| mxbai-embed-large | 1024 | Monikielinen | Ollama (lokaali) |
| nomic-embed-text | 768 | Englanti (kohtalainen suomi) | Ollama (lokaali) |

## LLM-mallit

| Malli | Koko | Sijainti | Huom |
|-------|------|----------|------|
| gpt-4o-mini | - | OpenAI API | Nopea, halpa, hyva suomi |
| gpt-4o | - | OpenAI API | Paras laatu |
| deepseek-r1:14b | 9 GB | Ollama (lokaali) | Reasoning-malli, toimii offline |
| llama3.2:3b | 2 GB | Ollama (lokaali) | Kevyt, nopea |

## Puolueet tietokannassa

### Eduskuntapuolueet
SDP, KOK, PS, KESK, VIHR, VAS, RKP, KD, LIIK

### Pienpuolueet
PIR, EOP, FP, VKK, SKP, LIB, SML

## Projektirakenne

```
vaalikone/
├── docker-compose.yml
├── pyproject.toml
├── alembic/                    # Tietokantamigraatiot
├── src/vaalikone/
│   ├── api/                    # FastAPI + web UI
│   │   ├── routes/             # API-endpointit
│   │   └── static/             # Web chat UI
│   ├── cli/                    # Click CLI -komennot
│   ├── core/                   # Config, database, auth
│   ├── models/                 # SQLAlchemy-mallit
│   ├── ingest/                 # Indeksointiputki
│   │   └── connectors/         # Eduskunta, web, PDF
│   └── query/                  # Haku + AI-vastaus
├── config/
│   └── parties.yaml            # Puoluekonfiguraatio
└── tests/                      # 32 testia
```

## Kehitys

```bash
# Testit
python -m pytest tests/ -v

# Linting
ruff check src/ tests/

# Uusi migraatio
alembic revision --autogenerate -m "kuvaus"
alembic upgrade head
```

## Lisenssi

MIT
