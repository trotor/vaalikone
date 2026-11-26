# Vaalikone

Suomen poliittisen datan tietokanta ja AI-kyselypalvelu. Kerää puolueiden vaaliohjelmat, varjobudjetit, hallitusohjelmat, kansanedustajien tiedot, äänestyshistorian ja vaalien ehdokkaat yhteen paikkaan. Dataa voi kysellä tekoälyllä CLI:n, REST API:n, web-chatin tai MCP-serverin kautta.

Rakennettu kevään 2027 eduskuntavaaleja varten.

## Ominaisuudet

- **22 puoluetta** — kaikki 20 Oikeusministeriön puoluerekisterissä olevaa puoluetta + rekisteristä poistetut PIR ja FP (`config/parties.yaml`)
- **2 046 dokumenttia** — 76 eduskuntavaaliohjelmaa, 22 eurovaaliohjelmaa, 50 kunta- ja aluevaaliohjelmaa, 139 puolue-/periaate-/erityisohjelmaa, 12 varjobudjettia, 1 421 ryhmäpuheenvuoroa, hallitusohjelmat 2015–2023; kaikki embedattu (bge-m3)
- **Ryhmäpuheenvuorot 2019→** — eduskuntaryhmien viralliset kannat täysistunnoissa (välikysymykset, budjetit, lakiesitykset), puolue puheenvuoron hetken ryhmästä (`vaalikone ingest group-speeches`)
- **Eduskuntavaalit 2027 -aineistot** — vaihtoehtobudjetit 2027 (SDP, VIHR, VAS, LIIK), SDP:n poliittinen ohjelma 2026, Vihreiden puolueohjelma 2027–2031, Vasemmistoliiton tavoiteohjelma 2025–2028, RKP:n puolueohjelma 2025, LIB/SML/VAPL-vaaliohjelmat 2027, KD:n ja Kokoomuksen 2026 erityisohjelmat
- **Puoluerekisterin yleisohjelmat** — puolueiden rekisteriin toimittamat viralliset yleisohjelmat (PDF) suoraan puoluerekisteri.fi:stä (`vaalikone ingest party-register`)
- **FSD Pohtiva -ohjelma-arkisto** — vaali-, euro-, kunta- ja aluevaali-, periaate- ja erityisohjelmat tekstinä vuodesta 2019 (oletus) kaikille puolueille, duplikaattitarkistus puolueiden omia PDF:iä ja sivuja vastaan (`vaalikone ingest pohtiva`)
- **Täysistuntopuheenvuorot** — haettavissa uudesta `api.eduskunta.fi` -hausta (`vaalikone ingest speeches`)
- **Kirjalliset kysymykset (KK)** — 41 900+ kysymystä (`vaalikone ingest questions`)
- **2 677 kansanedustajaa** — eduskunnan avoin data vuodesta 1907
- **6 521 täysistuntoäänestystä 2019→** eduskuntaryhmien jakaumineen (ryhmä äänestyshetkellä) ja **570 700 edustajakohtaista ääntä** vaalikaudelta 2023→ (`vaalikone ingest votes`, api.eduskunta.fi)
- **2 424 ehdokasta eduskuntavaaleista 2023** — äänimäärät, valintatieto, vaalipiiri (Tilastokeskus)
- **29 950 ehdokasta kuntavaaleista 2025** — kaikki 12 vaalipiiriä, äänimäärät ja valintatieto (`vaalikone ingest candidates --election kuntavaalit --year 2025`)
- **232 ehdokasta europarlamenttivaaleista 2024** — äänimäärät, vertausluku, valintatieto (15 valittua)
- **Presidentinvaali 2024** — 9 ehdokasta × 2 kierrosta, koko maan äänet (valittu: Stubb)
- **3 249 vaalirahoitusriviä** — eduskuntavaalit 2023, eurovaalit 2024, presidentinvaali 2024, kuntavaalit 2025: tukija, summa, ehdokas, puolue (vaalirahoitusvalvonta.fi; lopullinen ilmoitus korvaa ennakkoilmoituksen)
- **Hallitusohjelmat 2015, 2019 (Rinne), 2019 (Marin), 2023 (Orpo)** — PDF:t valtioneuvostosta (ei puoluesidonnaisia)
- **Hybrid-haku** — SQLite full-text/LIKE + semanttinen vektorihaku (sqlite-vec); PostgreSQL+pgvector valinnainen
- **AI-chat** — kysele politiikasta luonnollisella kielellä (mikä tahansa LiteLLM-provider / lokaali Ollama), SSE-streaming
- **Web UI** — chat tummalla/vaalealla teemalla, historia, puoluevärit, streaming
- **MCP-serveri** — 11 työkalua Claude Codelle / Vibe: haku, vertailu, chat, äänestykset, ehdokkaat, tilastot
- **Tietokanta** — SQLite + sqlite-vec oletuksena (`./vaalikone.db`, ei Dockeria); PostgreSQL+pgvector valinnainen (`--profile pg`)
- **Taustatyöt** — Celery + Redis (`--queue`, profiili `queue`)
- **API-avainauth** — `VAALIKONE_API_KEY` + `X-API-Key` -header, malli-allowlist, SSRF-suoja
- **Read-only -tila** — toimii ilman API-avainta pelkällä haulla (`__text_only__`)
- **Offline-tuki** — toimii ilman nettiä lokaalien mallien kanssa


## Käyttöönotto 5 minuutissa (valmis data mukana)

Vaatimukset: Python 3.12+ ja git (Git LFS). Dockeria ei tarvita.

```bash
# 1. Kloonaa (LFS tuo valmiin tietokannan ~121 MB)
git clone https://github.com/trotor/vaalikone.git
cd vaalikone
git lfs pull

# 2. Pura valmis tietokanta (2 046 dokumenttia, 22 puoluetta, 6 521 äänestystä + 570 700 edustajan ääntä, 32 000+ ehdokasta, 3 249 vaalirahoitusriviä)
gunzip -k data/vaalikone.db.gz        # → ./vaalikone.db

# 3. Asenna riippuvuudet
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 4. Käynnistä palvelin
.venv/bin/uvicorn vaalikone.api.app:app --port 8003
# → Web UI: http://localhost:8003
```

**Valmis tietokanta riittää sellaisenaan** — mitään lisädataa ei tarvitse syöttää. Alla oleva `vaalikone ingest ...` -osio on vain niille, jotka haluavat hakea itse lisää lähteitä tai rakentaa oman kannan alusta asti.

Ilman LLM API-avainta järjestelmä toimii **read-only -tilassa**: haku, puoluevertailu (`/api/v1/compare`), äänestys- ja ehdokashaku toimivat heti, chat palauttaa lähdeotteet ilman LLM:ää (`__text_only__`).

```bash
# CLI ilman palvelinta:
.venv/bin/vaalikone search "metsäkeskus"
.venv/bin/vaalikone search "verotus" --party KOK
.venv/bin/vaalikone stats

# LLM-chat päälle: lisää .env:ään oma avain, esim.
#   LLM_API_KEY=oma-avain
#   LLM_API_KEY_ENV=MISTRAL_API_KEY
#   DEFAULT_LLM_MODEL=mistral/mistral-small-latest
# tai lokaali Ollama: DEFAULT_LLM_MODEL=ollama/llama3.2:3b (ollama pull ensin)
```

**MCP-serveri Claude Codelle / Vibelle** (valmiin tietokannan kanssa):

```bash
# Vibe:
vibe mcp add vaalikone --transport stdio \
  --command "$(pwd)/.venv/bin/python" --arg=-m --arg=vaalikone.mcp.server

# Claude Code: lisää projektin juureen .mcp.json
# {"mcpServers": {"vaalikone": {"command": ".venv/bin/python", "args": ["-m", "vaalikone.mcp.server"]}}}
```

**Vain itsepuuhaajille:** oma data alusta asti (tyhjä kanta, hae lähteistä): ks. [Asennus](#asennus) alla — `alembic upgrade head` luo skeeman, `vaalikone ingest ...` täyttää datan. Ei pakollista valmiilla dumpilla.

## Missä data säilyy?

**Kaikki data on paikallisessa SQLite-tiedostossa** `./vaalikone.db` — ei pilvessä, ei jaetussa kannassa, ei Dockeria:

- Tietokanta: `sqlite+aiosqlite:///./vaalikone.db` (projektin juuressa, git-ignoroitu)
- Vektorihaku: `sqlite-vec`-laajennus (ladataan automaattisesti yhteydessä)
- Taulut: `parties`, `representatives`, `votings` (täysistuntoäänestykset + eduskuntaryhmien jakaumat), `votes` (edustajakohtaiset äänet, `subject` = `votings.voting_id`), `documents`, `embeddings` (float32-BLOB), `sources`, `elections`, `candidates`, `campaign_finances` (vaalirahoitus), `query_log`
- Valinnainen PostgreSQL+pgvector: `docker compose --profile pg up -d postgres` + `DATABASE_URL=postgresql+...` (ks. `.env.example`); datan siirto: `scripts/migrate_pg_to_sqlite.py`
- Valmis data jaettavaksi: `data/vaalikone.db.gz` (Git LFS, ~121 MB)
- GitHub-repo ei ole julkinen — dataa ei ole pushattu mihinkään

**Mitä lähtee ulos koneelta?**
- Datan haku lähteistä (eduskunta.fi, stat.fi, puolueiden sivut) — vain HTTP GET
- **Vain LLM-chat** lähettää kysymyksen + lähdeotteet valitulle LLM-palvelulle (esim. OpenAI/Mistral API tai lokaali Ollama). Ilman API-avainta järjestelmä toimii read-only -tilassa eikä lähetä mitään ulos.
- Embeddingit voi generoida täysin lokaalisti Ollamalla (`ollama/bge-m3`) — silloin mikään teksti ei lähde koneelta.

## Järjestelmävaatimukset

- **Python** 3.12+ — **ei Dockeria tarvita oletuksena** (data on SQLite-tiedostossa)
- **Docker** valinnainen: PostgreSQL/pgvector (`--profile pg`) tai Celery-jono (`--profile queue`)
- **Levytila**: ~2 GB (tietokanta + mallit)
- **RAM**: vähintään 4 GB, suositus 8+ GB
- **GPU/Apple Silicon**: valinnainen, nopeuttaa lokaaleja malleja

### Valinnaiset

- **LLM: mikä tahansa LiteLLM-provideri** (Mistral, OpenAI, Groq, oma gateway...) — ks. alla
- **Ollama**: lokaalit mallit offline-käyttöön (ilmainen)

### LLM-providerin valinta (ei kovakoodattu OpenAI)

`.env`:

```env
# Esimerkki Mistral:
LLM_API_KEY=oma-mistral-avain
LLM_API_KEY_ENV=MISTRAL_API_KEY
DEFAULT_LLM_MODEL=mistral/mistral-small-latest
CHAT_ALLOWED_MODELS=mistral/mistral-small-latest,mistral/mistral-medium-latest,__text_only__

# Tai oma gateway / proxy:
# LLM_API_BASE=https://oma-gateway.example.com/v1
```

Tuetut provider-etuliitteet reititetään automaattisesti (mistral/, gpt-…, groq/, anthropic/, deepseek/, gemini/, ollama/…). Vanha `OPENAI_API_KEY` toimii yhä fallbackina. Ilman LLM:ää koko järjestelmä toimii pelkällä haulla (`__text_only__`, `/api/v1/compare`).

### Read-only -tila (ilman API-avainta)

Ilman API-avainta järjestelmä toimii automaattisesti **read-only -tilassa** (tai pakota: `READ_ONLY_MODE=true`):
- chat vain `__text_only__` -mallilla (pelkkä haku lähteineen, LLM-mallit → 403)
- suggestiot oletuksista ilman LLM-kutsuja
- ei kirjoituksia tietokantaan (query_log ohitetaan), MCP:n `ingest_url` estetty
- `/api/v1/stats` ja `/api/v1/connectivity` raportoivat `read_only: true`
- haku, `/api/v1/compare`, äänestys- ja ehdokashaut toimivat normaalisti

Lokaalilla Ollama-mallilla (`ollama/...`) LLM toimii myös ilman API-avainta — read-only ei mene päälle.


## Asennus

### 1. Kloonaa ja konfiguroi

```bash
git clone https://github.com/trotor/vaalikone.git
cd vaalikone
cp .env.example .env
```

Muokkaa `.env`-tiedostoa:

```env
# Oletus: paikallinen SQLite (ei asennusta)
DATABASE_URL=sqlite+aiosqlite:///./vaalikone.db
# PostgreSQL vaihtoehtona: docker compose --profile pg up -d postgres
# DATABASE_URL=postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone
REDIS_URL=redis://localhost:6382/0  # vain --queue-taustatyöt

# Valinnainen — parempi laatu
OPENAI_API_KEY=sk-proj-...

# Valinnainen — lokaalit mallit
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_MODEL=gpt-5.4-nano
DEFAULT_EMBED_MODEL=ollama/bge-m3
```

### 2. Asenna Python-riippuvuudet

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Aja tietokantamigraatiot (luo SQLite-tiedoston skeeman)

```bash
alembic upgrade head
# tämä luo ./vaalikone.db:n ja kaikki taulut
```

### 4. Lataa valmis tietokanta (valinnainen)

Jos haluat aloittaa valmiilla datalla (2 046 dokumenttia, 22 puoluetta, 6 521 äänestystä + 570 700 edustajan ääntä, 32 000+ ehdokasta, 3 249 vaalirahoitusriviä):

```bash
git lfs pull
gunzip -k data/vaalikone.db.gz    # → ./vaalikone.db
```

### 5. Tai syötä data alusta

```bash
# Puolueet (22 kpl, config/parties.yaml)
vaalikone seed parties

# Puoluerekisteri: lisää puuttuvat rekisteröidyt puolueet ja hae niiden yleisohjelmat (PDF)
vaalikone ingest party-register

# Kansanedustajat eduskunnan avoimesta datasta
vaalikone ingest representatives

# Täysistuntojen äänestykset (api.eduskunta.fi): äänestykset + ryhmäjakaumat 2019→,
# edustajakohtaiset äänet 2023→ (~200 riviä/äänestys). Idempotentti, ajettavissa uudelleen.
vaalikone ingest votes
vaalikone ingest votes --since 2026 --member-votes-since 2026   # vain tuoreet

# Täysistuntopuheenvuorot ja kirjalliset kysymykset (uusi api.eduskunta.fi)
vaalikone ingest speeches ilmastonmuutos --max-results 100
vaalikone ingest group-speeches                    # ryhmäpuheenvuorot 2019→ (eduskuntaryhmien kannat)
vaalikone ingest questions --max-results 100 --valtiopaiva "2023 vp"

# Ehdokkaat eduskuntavaaleista 2023 (Tilastokeskus PxWeb)
vaalikone ingest candidates --year 2023

# Ehdokkaat kuntavaaleista 2025 — kaikki 12 vaalipiiriä kerralla
vaalikone ingest candidates --election kuntavaalit --year 2025

# Ehdokkaat europarlamenttivaaleista 2024 ja presidentinvaalista 2024
vaalikone ingest candidates --election europarlamenttivaalit --year 2024
vaalikone ingest candidates --election presidentinvaali --year 2024

# Vaalirahoitusrivit (vaalirahoitusvalvonta.fi CSV; tiedostot haetaan listaussivulta,
# uudempi versio ja lopullinen ilmoitus korvaavat vanhemman / ennakkoilmoituksen)
vaalikone ingest campaign-finance --election eduskuntavaalit --year 2023
vaalikone ingest campaign-finance --election europarlamenttivaalit --year 2024
vaalikone ingest campaign-finance --election presidentinvaali --year 2024
vaalikone ingest campaign-finance --election kuntavaalit --year 2025

# Kaikkien puolueiden vaaliohjelmat, puolueohjelmat ja varjobudjetit
# (osoitteet konfiguroitu: config/sources.yaml)
vaalikone ingest programs                          # kaikki
vaalikone ingest programs --party SDP              # vain yksi puolue
vaalikone ingest programs --kind varjobudjetti     # vain varjobudjetit
vaalikone ingest programs --party KD --refresh     # korvaa aiemmin haetut (esim. ohuet sivut)

# FSD Pohtiva: puolueohjelmat 2019→ (vaali-, EU-, kunta- ja alue-, periaate- ja erityisohjelmat).
# Aja VASTA party-registerin ja programsin JÄLKEEN: Pohtiva ohittaa ohjelmat, jotka on jo
# haettu puolueen omilta sivuilta tai rekisteristä (duplikaattitarkistus toimii vain tähän suuntaan).
vaalikone ingest pohtiva --dry-run                 # näytä mitä haettaisiin
vaalikone ingest pohtiva                           # kaikki kannan puolueet, suomeksi, 2019→
vaalikone ingest pohtiva --party VAS --since 2023  # yksi puolue, uudemmat
vaalikone ingest pohtiva --party RKP --lang sv     # ruotsinkieliset ohjelmat
vaalikone ingest pohtiva --type yleisohjelma --since 1990   # periaateohjelmien historia

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

### 6. Käynnistä palvelin

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
vaalikone ingest votes                          # Äänestykset 2019→ + edustajien äänet 2023→
vaalikone ingest speeches ilmastonmuutos        # Täysistuntopuheenvuorot
vaalikone ingest group-speeches                 # Ryhmäpuheenvuorot 2019→
vaalikone ingest questions --max-results 100   # Kirjalliset kysymykset
vaalikone ingest candidates --year 2023         # Ehdokkaat eduskuntavaalit 2023
vaalikone ingest candidates --election kuntavaalit --year 2025  # Kuntavaalit 2025
vaalikone ingest candidates --election europarlamenttivaalit --year 2024
vaalikone ingest campaign-finance --election kuntavaalit --year 2025  # Vaalirahoitus
vaalikone ingest programs                       # Vaaliohjelmat + varjobudjetit + hallitusohjelmat (config/sources.yaml)
vaalikone ingest programs --kind kuntavaaliohjelma  # Kuntavaaliohjelmat 2025
vaalikone ingest party-register                 # Puoluerekisteri: puolueet + yleisohjelmat
vaalikone ingest pohtiva                        # FSD Pohtiva: puolueohjelmat 2019→ (programsin jälkeen)
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
GET  /api/v1/compare?q=...      Puoluevertailu ILMAN LLM:ää (lähdeotteet per puolue)
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

### MCP-serveri (Claude Code / Vibe)

Projekti sisältää MCP-serverin, joka kytkeytyy suoraan tähän tietokantaan:

```bash
# Vibe:
vibe mcp add vaalikone --transport stdio \
  --command .venv/bin/python --arg=-m --arg=vaalikone.mcp.server

# Claude Code (.mcp.json projektin juureen):
{
  "mcpServers": {
    "vaalikone": {
      "command": ".venv/bin/python",
      "args": ["-m", "vaalikone.mcp.server"]
    }
  }
}
```

Työkalut: `query` (LLM-chat), `search`, `compare`, `list_parties`, `get_party`, `list_documents`, `party_votes` (eduskuntaryhmien äänet asiasta), `search_votes` (edustajien äänet), `list_candidates`, `stats`, `ingest_url` (estetty read-only -tilassa).

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
  -d '{"question": "Mitä puolueet sanovat metsäkeskuksesta?", "model": "gpt-6-luna"}'
```

## Docker Compose

### Portit

| Palvelu | Portti | Huom |
|---------|--------|------|
| FastAPI | 8003 | Web UI + API (profiili `api`) |
| PostgreSQL | 5435 | valinnainen, profiili `pg` (+ pgvector) |
| Redis | 6382 | valinnainen, profiili `queue` (Celery) |
| Keycloak | 8083 | profiili `auth` |

Oletus: ei kontteja — SQLite-tiedosto `vaalikone.db` projektin juuressa.

Portit on siirretty +3 oletuksesta päällekkäisyyksien välttämiseksi.

### Komennot

```bash
docker compose --profile pg up -d postgres    # Valinnainen: PostgreSQL/pgvector
docker compose --profile queue up -d redis worker  # Valinnainen: Celery-taustatyöt
docker compose --profile api up -d            # Valinnainen: API konttina
# Oletuksena ei tarvita mitään: data on ./vaalikone.db (SQLite + sqlite-vec)
docker compose down                          # Sammuta
docker compose down -v                       # Poista pgdata (SQLite-tiedosto ei katoa)
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

Puoluelista seuraa Oikeusministeriön puoluerekisteriä (https://puoluerekisteri.fi, 20 puoluetta 11/2026).
`config/parties.yaml` yhdistää rekisterin (`registry_id`) ja Pohtivan (`pohtiva`) puoluekoodit vaalikoneen lyhenteisiin.

### Eduskuntapuolueet
SDP, KOK, PS, KESK, VIHR, VAS, RKP, KD, LIIK

### Muut rekisteröidyt puolueet
SKP, VKK, LIB, EOP, SML, AP (Avoin Puolue), KRI (Kristallipuolue), VAPL (Vapauden liitto),
TP (Totuuspuolue), HAMP (Hamppupuolue), SGP (Suomen Graniittipuolue)

### Rekisteristä poistetut (data säilytetty)
PIR (Piraattipuolue), FP (Feministinen puolue)

### Puoluedatan lähteet ja kattavuus

| Lähde | Komento | Mitä tuo |
|-------|---------|----------|
| Puolueiden omat sivut | `ingest programs` | Vaaliohjelmat, varjobudjetit, uusimmat puolueohjelmat (esim. Vihreiden puolueohjelma 2027–2031, Vapauden liiton eduskuntavaaliohjelma 2027) — `config/sources.yaml` |
| Puoluerekisteri | `ingest party-register` | Viralliset yleisohjelmat niiltä 10 puolueelta 20:stä, joilla liite on rekisterissä (AP, KRI, VKK, VAPL, TP, LIB, EOP, HAMP, SML, SGP). |
| Eduskunta (api.eduskunta.fi) | `ingest group-speeches` | 1 421 ryhmäpuheenvuoroa 2019→ — eduskuntaryhmän virallinen kanta jokaiseen isoon keskusteluun |
| Eduskunta (api.eduskunta.fi) | `ingest votes` | 6 521 täysistuntoäänestystä 2019→ ryhmäjakaumineen + 570 700 edustajan ääntä 2023→ — miten puolueet oikeasti äänestivät (MCP: `party_votes`, `search_votes`) |
| FSD Pohtiva | `ingest pohtiva` | ~190 suomenkielistä ohjelmaa 2019→: eurovaaliohjelmat 2024, kunta- ja aluevaaliohjelmat 2025, periaate- ja erityisohjelmat. Jo kannassa olevat (3-sanajonojen kattavuus ≥ 50 %) ohitetaan, ja tyypittömälle kopiolle annetaan Pohtivan tyyppi ja vuosi. |

Järjestys tuoreeseen kantaan: `seed parties` → `party-register` → `programs` → `pohtiva` → `embed`.

Uusien ohjelmien löytäminen: puolueiden WordPress-sivukartat (`/sitemap_index.xml`, `lastmod`) kertovat
mitkä ohjelmasivut ovat uusia tai päivittyneitä; lisää löydökset `config/sources.yaml`:iin ja aja `ingest programs`
(jo haetut ohitetaan ennen latausta). keskusta.fi estää harvesterin (403) 11/2026 — Keskustan ohjelmat tulevat Pohtivasta.

Ohjelmatyypit (`content_type`): `vaaliohjelma` (eduskunta), `eurovaaliohjelma`, `kuntavaaliohjelma` (kunta + alue),
`puolueohjelma` (yleis-, periaate-, tavoite- ja erityisohjelmat), `varjobudjetti`, `hallitusohjelma`.
Pohtivan dokumenteissa on lisäksi `metadata.year`, `metadata.election` ja `published_at` (ohjelman vuosi).

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

- **Eduskunnan avoin data**: https://avoindata.eduskunta.fi ja https://api.eduskunta.fi (kansanedustajat, äänestykset, puheenvuorot, kirjalliset kysymykset)
- **Tilastokeskus PxWeb**: https://pxdata.stat.fi — ehdokkaat ja äänimäärät eduskunta- ja kuntavaaleissa (`evaa/`, `kvaa/`-taulut)
- **Puolueiden verkkosivut**: vaaliohjelmat, puolueohjelmat, varjobudjetit (osoitteet: `config/sources.yaml`)
- **Oikeusministeriön puoluerekisteri**: https://puoluerekisteri.fi — rekisteröidyt puolueet ja niiden yleisohjelmat (julkinen `publicapi`, `vaalikone ingest party-register`)
- **Valtioneuvoston julkaisut**: hallitusohjelmat (julkaisut.valtioneuvosto.fi)
- **Vaalirahoitusvalvonta**: vaalirahoitusilmoitusten tutkittavat aineistot, CSV (`vaalikone ingest campaign-finance`)
- **FSD Pohtiva**: POHTIVA – Poliittisten ohjelmien tietovaranto, Yhteiskuntatieteellinen tietoarkisto (FSD), Tampereen yliopisto, https://www.fsd.tuni.fi/pohtiva/ (`vaalikone ingest pohtiva`). Pohtivaan viitataan tieteellisen käytännön mukaan; Tietoarkisto pyytää tiedon julkaisuista, joissa aineistoa on hyödynnetty. Harvesteri pitää pyyntöjen välillä 1 s tauon.
- **vaalit.fi**: vaalilainsäädäntö ja äänestysinfo

> Huom: Eduskunnan nykyinen API (avoindata.eduskunta.fi) poistuu käytöstä vuoden 2026 lopussa.

## Lisenssi

MIT
