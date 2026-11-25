# Vaalikone

Suomen poliittisen datan tietokanta ja AI-kyselypalvelu. Kerää puolueiden vaaliohjelmat, varjobudjetit, kansanedustajien tiedot ja äänestyshistorian yhteen paikkaan. Dataa voi kysellä tekoälyllä CLI:n, REST API:n, web-chatin tai MCP-serverin kautta.

Rakennettu kevään 2027 eduskuntavaaleja varten.

## Ominaisuudet

- **16 puoluetta** — kaikki eduskuntapuolueet + pienpuolueet
- **380+ dokumenttia** — vaaliohjelmat, varjobudjetit, politiikkaohjelmat (web + PDF)
- **Täysistuntopuheenvuorot** — haettavissa uudesta `api.eduskunta.fi` -hausta (`vaalikone ingest speeches`)
- **Kirjalliset kysymykset (KK)** — 41 900+ kysymystä (`vaalikone ingest questions`)
- **2 677 kansanedustajaa** — eduskunnan avoin data vuodesta 1907
- **183 710+ äänestystä äänestysotsikoilla** — `vaalikone ingest vote-subjects`
- **2 424 ehdokasta eduskuntavaaleista 2023** — äänimäärät, valintatieto, vaalipiiri (Tilastokeskus)
- **Hybrid-haku** — PostgreSQL full-text + ILIKE + pg_trgm + semanttinen vektorihaku
- **AI-chat** — kysele politiikasta luonnollisella kielellä (OpenAI / lokaali Ollama), SSE-streaming
- **Web UI** — chat tummalla/vaalealla teemalla, historia, puoluevärit, streaming
- **Taustatyöt** — Celery + Redis (`--queue`), worker konttina docker composessa
- **API-avainauth** — `VAALIKONE_API_KEY` + `X-API-Key` -header, malli-allowlist, SSRF-suoja
- **Offline-tuki** — toimii ilman nettiä lokaalien mallien kanssa

## Järjestelmävaatimukset

- **Python** 3.12+
- **Docker** ja Docker Compose
- **Levytila**: ~2 GB (tietokanta + mallit)
- **RAM**: vähintään 8 GB, suositus 16+ GB
- **GPU/Apple Silicon**: valinnainen, nopeuttaa lokaaleja malleja

### Valinnaiset

- **OpenAI API -avain**: parempi suomenkielinen laatu (embedding + LLM)
- **Ollama**: lokaalit mallit offline-käyttöön (ilmainen)

## Asennus

### 1. Kloonaa ja konfiguroi

```bash
git clone https://github.com/trotor/vaalikone.git
cd vaalikone
cp .env.example .env
```

Muokkaa `.env`-tiedostoa:

```env
# Pakollinen
DATABASE_URL=postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone
REDIS_URL=redis://localhost:6382/0

# Valinnainen — parempi laatu
OPENAI_API_KEY=sk-proj-...

# Valinnainen — lokaalit mallit
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_MODEL=gpt-5.4-nano
DEFAULT_EMBED_MODEL=ollama/bge-m3
```

### 2. Käynnistä tietokanta

```bash
docker compose up -d postgres redis
```

Tarkista että palvelut ovat käynnissä:

```bash
docker compose ps
# postgres ja redis pitäisi olla "healthy"
```

### 3. Asenna Python-riippuvuudet

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 4. Aja tietokantamigraatiot

```bash
alembic upgrade head
```

### 5. Lataa valmis tietokanta (valinnainen)

Jos haluat aloittaa valmiilla datalla (380+ dokumenttia, 183 000+ äänestystä):

```bash
# Pura dump
gunzip -k data/vaalikone-dump.sql.gz

# Lataa tietokantaan
docker exec -i $(docker ps -qf "name=postgres") psql -U vaalikone < data/vaalikone-dump.sql
```

### 6. Tai syötä data alusta

```bash
# Puolueet (16 kpl)
vaalikone seed parties

# Kansanedustajat eduskunnan avoimesta datasta
vaalikone ingest representatives

# Äänestyksiä (50 sivua ~ 5 000 ääntä, nopea) — otsikot tulevat mukaan
vaalikone ingest votes --max-pages 50
vaalikone ingest vote-subjects --max-pages 50   # Täyttää äänestysten otsikot jälkikäteen

# Täysistuntopuheenvuorot ja kirjalliset kysymykset (uusi api.eduskunta.fi)
vaalikone ingest speeches ilmastonmuutos --max-results 100
vaalikone ingest questions --max-results 100 --valtiopaiva "2023 vp"

# Ehdokkaat eduskuntavaaleista 2023 (Tilastokeskus PxWeb)
vaalikone ingest candidates --year 2023

# Kaikkien puolueiden vaaliohjelmat, puolueohjelmat ja varjobudjetit
# (osoitteet konfiguroitu: config/sources.yaml)
vaalikone ingest programs                          # kaikki
vaalikone ingest programs --party SDP              # vain yksi puolue
vaalikone ingest programs --kind varjobudjetti     # vain varjobudjetit

# Kaikki komennot voi myös jonottaa taustalle (--queue, vaatii workerin):
vaalikone ingest url "https://..." --party SDP --queue

# Puolueohjelmia verkosta
vaalikone ingest url "https://www.kokoomus.fi/periaateohjelma/" --party KOK
vaalikone ingest crawl "https://www.vihreat.fi/ohjelmat/" --party VIHR --depth 2

# PDF-dokumentteja
vaalikone ingest pdf "https://www.perussuomalaiset.fi/wp-content/uploads/2018/10/periaateohjelma.pdf" --party PS

# Embeddings (semanttinen haku)
vaalikone ingest embed --model ollama/bge-m3
```

### 7. Käynnistä palvelin

```bash
uvicorn vaalikone.api.app:app --host 0.0.0.0 --port 8003
```

Avaa selaimessa: **http://localhost:8003**

## Ollama-mallien asennus (valinnainen)

Ollama mahdollistaa lokaalit mallit ilman nettiyhteyttä ja API-kuluja.

```bash
# Asenna Ollama: https://ollama.com/download

# LLM-mallit (vastausten generointi)
ollama pull deepseek-r1:14b    # 9 GB — reasoning, vaatii 16+ GB RAM
ollama pull llama3.2:3b        # 2 GB — kevyt ja nopea

# Embedding-mallit (vektorihaku)
ollama pull bge-m3             # 1.2 GB — paras suomenkielinen (suositus)
ollama pull mxbai-embed-large  # 669 MB — vaihtoehto
```

### Mallisuositukset koneen mukaan

| RAM | LLM | Embedding |
|-----|-----|-----------|
| 8 GB | llama3.2:3b | nomic-embed-text |
| 16 GB | deepseek-r1:14b | bge-m3 |
| 24+ GB | deepseek-r1:14b | bge-m3 |

## Käyttö

### Web UI

Käynnistä palvelin ja avaa http://localhost:8003. Chat-käyttöliittymä tunnistaa automaattisesti käytettävissä olevat mallit (OpenAI/Ollama) ja toimii myös offline.

### CLI

```bash
# Datan syöttö
vaalikone seed parties                          # Syötä puolueet
vaalikone ingest representatives                # Hae kansanedustajat
vaalikone ingest votes --max-pages 100          # Hae äänestyksiä (otsikoilla)
vaalikone ingest vote-subjects                  # Äänestysotsikot jälkikäteen
vaalikone ingest speeches ilmastonmuutos        # Täysistuntopuheenvuorot
vaalikone ingest questions --max-results 100   # Kirjalliset kysymykset
vaalikone ingest candidates --year 2023         # Ehdokkaat 2023
vaalikone ingest programs                       # Vaaliohjelmat + varjobudjetit (config/sources.yaml)
vaalikone ingest url <URL> --party SDP          # Indeksoi web-sivu
vaalikone ingest pdf <URL> --party PS           # Indeksoi PDF
vaalikone ingest crawl <URL> --party VIHR --depth 2  # Rekursiivinen crawlaus
vaalikone ingest embed --model ollama/bge-m3    # Generoi embeddings

# Haku ja kysely
vaalikone search "metsäkeskus"                  # Tekstihaku
vaalikone search "verotus" --party KOK          # Puoluekohtainen haku
vaalikone chat "Vertaa puolueiden ilmastopolitiikkaa"  # AI-chat

# Tilastot ja hallinta
vaalikone stats                                 # Tietokannan tilastot
vaalikone documents                             # Dokumentit puolueittain
vaalikone documents --party VIHR                # Yhden puolueen dokumentit
vaalikone sources list                          # Lähteet
vaalikone compare-embeddings                    # Vertaile embedding-malleja
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
GET  /api/v1/search?q=...       Tekstihaku (?party=KOK&limit=10)
POST /api/v1/chat               AI-chat (JSON body)
POST /api/v1/chat/stream        AI-chat SSE-streamina (chunk/done -eventit)
POST /api/v1/suggest            Jatkokysymysehdotukset
GET  /api/v1/suggestions        Etusivun kysymysehdotukset
GET  /api/v1/connectivity       Palveluiden tila (OpenAI, Ollama)
GET  /api/v1/elections          Vaalit
GET  /api/v1/elections/{id}/candidates  Ehdokkaat (?party=SDP&elected_only=true&q=...)
GET  /api/v1/elections/{id}/stats       Puoluekohtaiset tilastot vaaleista
GET  /api/v1/representatives/{id}/votes  Kansanedustajan äänestyshistoria otsikoilla
```

### Tietoturva

Kun `VAALIKONE_API_KEY` on asetettu, kaikki `/api/v1/*`-päätteet vaativat
`X-API-Key`-headerin. Chat-mallit rajataan `CHAT_ALLOWED_MODELS`-allowlistillä
(pilkulla erotettu, `__text_only__` sallittu aina). URL-connectoreissa on
SSRF-suoja (yksityiset IPt, localhost ja muut kuin http/https -skeemat estetään).
Docker Compose -portit on sidottu 127.0.0.1:een ja kontit ajavat non-root-käyttäjänä.

#### Chat API -esimerkki

```bash
curl -X POST http://localhost:8003/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Mitä puolueet sanovat metsäkeskuksesta?", "model": "gpt-5.4-nano"}'
```

## Docker Compose

### Portit

| Palvelu | Portti | Huom |
|---------|--------|------|
| FastAPI | 8003 | Web UI + API |
| PostgreSQL | 5435 | + pgvector |
| Redis | 6382 | Celery broker |
| Keycloak | 8083 | Profiili: auth |

Portit on siirretty +3 oletuksesta päällekkäisyyksien välttämiseksi.

### Komennot

```bash
docker compose up -d postgres redis      # Peruspalvelut
docker compose up -d                     # Kaikki (ml. API konttina)
docker compose --profile auth up -d      # + Keycloak
docker compose down                      # Sammuta
docker compose down -v                   # Poista data
```

## Embedding-mallien vertailu

Benchmark suomenkielisellä politiikkadatalla (15 kyselyä):

| Malli | Keskiarvo | Voitot | Puoluekattavuus | Koko |
|-------|-----------|--------|-----------------|------|
| **bge-m3 (lokaali)** | **0.578** | **12/15** | **11/16** | 1.2 GB |
| OpenAI text-embedding-3-small | 0.513 | 2/15 | 7/16 | — |
| zembed-1 (lokaali) | 0.486 | 0/15 | 11/16 | 2.5 GB |
| mxbai-embed-large (lokaali) | 0.637* | 10/15* | 8/16* | 669 MB |

\* mxbai-embed-large sai parhaat pisteet mutta vain 5 % dokumenteista embeddautui onnistuneesti (epävakaa).

**Suositus: bge-m3** — paras vakaus (100 %) + hyvä laatu suomeksi.

## LLM-mallien vertailu

| Malli | Aika | Laatu | Hinta/kysely |
|-------|------|-------|-------------|
| **gpt-5.4-nano** | **2.2 s** | **Erinomainen** | ~$0.001 |
| gpt-4.1-mini | 3.1 s | Hyvä | ~$0.003 |
| gpt-4.1 | 5.7 s | Erinomainen | ~$0.01 |
| gpt-4.1-nano | 1.6 s | OK | ~$0.0005 |
| deepseek-r1:14b (lokaali) | >60 s | Kohtalainen suomi | Ilmainen |

## Puolueet

### Eduskuntapuolueet
SDP, KOK, PS, KESK, VIHR, VAS, RKP, KD, LIIK

### Pienpuolueet
PIR, EOP, FP, VKK, SKP, LIB, SML

## Kehitys

```bash
python -m pytest tests/ -v                # Testit
ruff check src/ tests/                    # Linting
alembic revision --autogenerate -m "..."  # Uusi migraatio
alembic upgrade head                      # Aja migraatiot
```

## Vianmääritys

### Portti varattu

```bash
lsof -ti:8003 | xargs kill -9
```

### Tietokantayhteys ei toimi

```bash
docker compose ps
docker compose logs postgres
```

### Embedding-dimensiovirhe

```bash
docker exec $(docker ps -qf "name=postgres") psql -U vaalikone \
  -c "DELETE FROM embeddings; ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector;"
vaalikone ingest embed --model ollama/bge-m3 --force
```

## Datalähteet

- **Eduskunnan avoin data**: https://avoindata.eduskunta.fi
- **Puolueiden verkkosivut**: vaaliohjelmat, varjobudjetit, politiikkaohjelmat
- **Hallitusohjelma 2023**: julkaisut.valtioneuvosto.fi
- **vaalit.fi**: vaalilainsäädäntö ja äänestysinfo

> Huom: Eduskunnan nykyinen API (avoindata.eduskunta.fi) poistuu käytöstä vuoden 2026 lopussa.

## Lisenssi

MIT
