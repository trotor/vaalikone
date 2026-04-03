# Vaalikone

Suomen poliittisen datan tietokanta ja AI-kyselypalvelu. Keraa puolueiden vaaliohjelmat, varjobudjetit, kansanedustajien tiedot ja aanestyshistorian yhteen paikkaan. Dataa voi kysella tekoalylla CLI:n, REST API:n, web-chatin tai MCP-serverin kautta.

Rakennettu kevaan 2027 eduskuntavaaleja varten.

## Ominaisuudet

- **16 puoluetta** — kaikki eduskuntapuolueet + pienpuolueet
- **103+ dokumenttia** — vaaliohjelmat, varjobudjetit, politiikkaohjelmat (web + PDF)
- **2 677 kansanedustajaa** — eduskunnan avoin data vuodesta 1907
- **183 710+ aanestysta** — kansanedustajien aanestyshistoria
- **Hybrid-haku** — PostgreSQL full-text + semanttinen vektorihaku (pgvector)
- **AI-chat** — kysele politiikasta luonnollisella kielella (OpenAI / lokaali Ollama)
- **Web UI** — selainpohjainen chat-kayttoliittyma
- **Offline-tuki** — toimii ilman nettia lokaalien mallien kanssa

## Jarjestelmavaatimukset

- **Python** 3.12+
- **Docker** ja Docker Compose
- **Levytila**: ~2 GB (tietokanta + mallit)
- **RAM**: vahintaan 8 GB, suositus 16+ GB
- **GPU/Apple Silicon**: valinnainen, nopeuttaa lokaaleja malleja

### Valinnaiset

- **OpenAI API -avain**: parempi suomenkielinen laatu (embedding + LLM)
- **Ollama**: lokaalit mallit offline-kayttoon (ilmainen)

## Asennus

### 1. Kloonaa ja konfiguroi

```bash
git clone <repo-url>
cd vaalikone
cp .env.example .env
```

Muokkaa `.env`-tiedostoa:

```env
# Pakollinen
DATABASE_URL=postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone
REDIS_URL=redis://localhost:6382/0

# Valinnainen - parempi laatu
OPENAI_API_KEY=sk-proj-...

# Valinnainen - lokaalit mallit
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_MODEL=gpt-4o-mini          # tai ollama/deepseek-r1:14b
DEFAULT_EMBED_MODEL=text-embedding-3-small  # tai ollama/bge-m3
```

### 2. Kaynnista tietokanta

```bash
docker compose up -d postgres redis
```

Tarkista etta palvelut ovat kay:

```bash
docker compose ps
# postgres ja redis pitaisi olla "healthy"
```

### 3. Asenna Python-riippuvuudet

```bash
# Suositus: kaytta virtuaaliymparistoa
python -m venv .venv
source .venv/bin/activate

# Asenna
pip install -e ".[dev]"
```

### 4. Aja tietokantamigraatiot

```bash
alembic upgrade head
```

### 5. Syota alkudata

```bash
# Puolueet (16 kpl)
vaalikone seed parties

# Kansanedustajat eduskunnan avoimesta datasta
vaalikone ingest representatives

# Aanestyksia (50 sivua = ~5000 aanestysta, nopea)
vaalikone ingest votes --max-pages 50

# Lisaa aanestyksia (2000 sivua = ~200 000, kestaa muutaman minuutin)
vaalikone ingest votes --max-pages 2000
```

### 6. Indeksoi puolueohjelmia

```bash
# Esimerkkeja
vaalikone ingest url "https://www.kokoomus.fi/periaateohjelma/" --party KOK
vaalikone ingest url "https://www.vihreat.fi/ohjelmat/periaateohjelma-2020-2028/" --party VIHR
vaalikone ingest pdf "https://www.perussuomalaiset.fi/wp-content/uploads/2018/10/periaateohjelma.pdf" --party PS

# Katso dokumentit puolueittain
vaalikone documents
```

### 7. Generoi embeddings (vektorihaku)

```bash
# OpenAI:lla (vaatii API-avaimen, paras suomenkielinen laatu)
vaalikone ingest embed --model text-embedding-3-small

# TAI lokaalilla mallilla (ilmainen, vaatii Ollaman)
vaalikone ingest embed --model ollama/bge-m3
```

### 8. Kaynnista palvelin

```bash
# Kehitystila
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003

# Tai taustalle
nohup uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003 > /tmp/vaalikone.log 2>&1 &
```

Avaa selaimessa: **http://localhost:8003**

## Ollama-mallien asennus (valinnainen)

Ollama mahdollistaa lokaalit mallit ilman nettiyhteytta ja API-kuluja.

```bash
# Asenna Ollama: https://ollama.com/download

# LLM-mallit (vastausten generointi)
ollama pull deepseek-r1:14b    # 9 GB - paras reasoning, vaatii 16+ GB RAM
ollama pull llama3.2:3b        # 2 GB - kevyt ja nopea

# Embedding-mallit (vektorihaku)
ollama pull bge-m3             # 1.2 GB - paras monikielinen
ollama pull mxbai-embed-large  # 669 MB - hyva vaihtoehto
ollama pull nomic-embed-text   # 274 MB - kevyin

# zembed-1 (kokeellinen, 2560d, paras laatu)
# Lataa GGUF: https://huggingface.co/Abhiray/zembed-1-Q4_K_M-GGUF
# ollama create zembed-1 -f models/Modelfile.zembed-1
```

### Mallisuositukset koneen mukaan

| RAM | LLM | Embedding |
|-----|-----|-----------|
| 8 GB | llama3.2:3b | nomic-embed-text |
| 16 GB | deepseek-r1:14b | bge-m3 |
| 24+ GB | deepseek-r1:14b | zembed-1 / bge-m3 |

## Kaytto

### Web UI

Kaynnista palvelin ja avaa http://localhost:8003. Chat-kayttoliittyma tunnistaa automaattisesti kaytettavissa olevat mallit (OpenAI/Ollama) ja toimii myos offline.

### CLI

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

### REST API

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

#### Chat API esimerkki

```bash
curl -X POST http://localhost:8003/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Mita puolueet sanovat metsakeskuksesta?", "model": "gpt-4o-mini"}'
```

## Docker Compose

### Portit

| Palvelu | Portti | Huom |
|---------|--------|------|
| FastAPI | 8003 | Web UI + API |
| PostgreSQL | 5435 | +pgvector |
| Redis | 6382 | Celery broker |
| Keycloak | 8083 | Profiili: auth |

Portit on siirretty +3 oletuksesta, jotta ne eivat mene paallekkain muiden palveluiden kanssa.

### Komennot

```bash
# Peruspalvelut
docker compose up -d postgres redis

# Kaikki (ml. API Docker-konttina)
docker compose up -d

# Keycloak-autentikaatio (kehitysvaiheessa)
docker compose --profile auth up -d

# Sammuta
docker compose down

# Poista data ja aloita alusta
docker compose down -v
```

## Embedding-mallit

| Malli | Dimensio | Kieli | Sijainti | Koko |
|-------|----------|-------|----------|------|
| text-embedding-3-small | 1536 | Monikielinen | OpenAI API | - |
| text-embedding-3-large | 3072 | Monikielinen | OpenAI API | - |
| zembed-1 (Q4_K_M) | 2560 | Monikielinen | Lokaali (GGUF) | 2.5 GB |
| bge-m3 | 1024 | Monikielinen (erinomainen suomi) | Ollama | 1.2 GB |
| mxbai-embed-large | 1024 | Monikielinen | Ollama | 669 MB |
| nomic-embed-text | 768 | Englanti (kohtalainen suomi) | Ollama | 274 MB |

## LLM-mallit

| Malli | Koko | Sijainti | Huom |
|-------|------|----------|------|
| o4-mini | - | OpenAI API | Nopea, edullinen |
| gpt-4.1-mini | - | OpenAI API | Hyva yleismalli |
| gpt-4.1 | - | OpenAI API | Paras laatu |
| o3-mini | - | OpenAI API | Reasoning |
| deepseek-r1:14b | 9 GB | Ollama (lokaali) | Reasoning, offline |
| llama3.2:3b | 2 GB | Ollama (lokaali) | Kevyt, nopea |

## Puolueet

### Eduskuntapuolueet
SDP, KOK, PS, KESK, VIHR, VAS, RKP, KD, LIIK

### Pienpuolueet
PIR, EOP, FP, VKK, SKP, LIB, SML

## Projektirakenne

```
vaalikone/
├── docker-compose.yml          # Tietokanta + palvelut
├── Dockerfile                  # API-kontin rakennus
├── pyproject.toml              # Python-riippuvuudet
├── alembic.ini                 # Migraatiokonfiguraatio
├── alembic/                    # Tietokantamigraatiot
│   └── versions/
├── src/vaalikone/
│   ├── api/                    # FastAPI + web UI
│   │   ├── app.py              # FastAPI-sovellus
│   │   ├── deps.py             # Riippuvuusinjektiot
│   │   ├── routes/             # API-endpointit
│   │   │   ├── parties.py
│   │   │   ├── representatives.py
│   │   │   ├── documents.py
│   │   │   ├── sources.py
│   │   │   ├── stats.py
│   │   │   └── query.py        # Haku + chat
│   │   └── static/
│   │       └── index.html      # Web chat UI
│   ├── cli/                    # Click CLI
│   │   ├── main.py             # CLI-ryhma
│   │   ├── seed.py             # Puolueiden syotto
│   │   ├── ingest.py           # Datan indeksointi
│   │   ├── sources.py          # Lahteiden hallinta
│   │   ├── search.py           # Tekstihaku
│   │   ├── chat.py             # AI-chat
│   │   ├── stats.py            # Tilastot
│   │   └── documents.py        # Dokumenttilista
│   ├── core/
│   │   ├── config.py           # Asetukset (.env)
│   │   └── database.py         # SQLAlchemy async
│   ├── models/                 # Tietokantamallit
│   │   ├── base.py
│   │   ├── party.py
│   │   ├── representative.py
│   │   ├── source.py
│   │   ├── document.py
│   │   ├── embedding.py
│   │   ├── vote.py
│   │   └── query_log.py
│   ├── ingest/                 # Indeksointiputki
│   │   ├── pipeline.py         # Chunking + embedding
│   │   ├── chunker.py          # Tekstin pilkonta
│   │   ├── embedder.py         # Vektorointi (OpenAI/Ollama)
│   │   └── connectors/
│   │       ├── eduskunta.py    # Eduskunnan avoin data
│   │       ├── web.py          # Web-scraping (trafilatura)
│   │       └── pdf.py          # PDF-indeksointi (PyMuPDF)
│   └── query/                  # Kyselyputki
│       ├── pipeline.py         # Haku -> LLM -> vastaus
│       ├── hybrid_search.py    # Teksti + semanttinen haku
│       └── response.py         # LLM-vastauksen generointi
├── config/
│   └── parties.yaml            # Puoluekonfiguraatio
├── models/
│   └── Modelfile.zembed-1      # Ollama GGUF -malli
└── tests/                      # 32+ testia
    ├── conftest.py
    ├── test_api.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_models.py
    ├── test_chunker.py
    ├── test_eduskunta.py
    ├── test_web_connector.py
    ├── test_pdf_connector.py
    ├── test_search.py
    ├── test_e2e.py
    └── ...
```

## Kehitys

```bash
# Testit
python -m pytest tests/ -v

# Linting
ruff check src/ tests/

# Uusi tietokantamigraatio
alembic revision --autogenerate -m "kuvaus"
alembic upgrade head

# Tietokannan tyhjennys ja uudelleenluonti
docker compose down -v
docker compose up -d postgres redis
alembic upgrade head
vaalikone seed parties
```

## Vianmaaritys

### Portti varattu

```bash
lsof -ti:8003 | xargs kill -9
```

### Tietokantayhteys ei toimi

```bash
docker compose ps          # Tarkista etta postgres on "healthy"
docker compose logs postgres  # Katso logit
```

### Embedding-virhe "expected N dimensions"

Eri embedding-malleilla on eri dimensiot. Tyhjenna vanhat ja generoi uudelleen:

```bash
# PostgreSQL:ssa
docker exec $(docker ps -qf "name=postgres") psql -U vaalikone -c "DELETE FROM embeddings;"
docker exec $(docker ps -qf "name=postgres") psql -U vaalikone -c "ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector;"

# Generoi uudelleen
vaalikone ingest embed --model <uusi-malli> --force
```

### Ollama ei vastaa

```bash
ollama serve    # Kaynnista Ollama
ollama list     # Tarkista mallit
```

## Datalähteet

- **Eduskunnan avoin data**: https://avoindata.eduskunta.fi (kansanedustajat, aanestykset, asiakirjat)
- **Puolueiden verkkosivut**: vaaliohjelmat, varjobudjetit, politiikkaohjelmat
- **vaalit.fi**: ehdokasdata (tuleva integraatio)

> Huom: Eduskunnan nykyinen API (avoindata.eduskunta.fi) poistuu kaytosta vuoden 2026 lopussa. Uusi API tulee osoitteeseen eduskunta.fi/avoin-data.

## Lisenssi

MIT
