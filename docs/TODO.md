# TODO

## Seuraavat vaiheet

### Tietoturva (ennen julkista käyttöä)
- [ ] API-autentikaatio (API-avain tai Keycloak)
- [ ] Malli-allowlist chat-endpointtiin
- [ ] URL-validointi SSRF-suojaksi (connectors)
- [ ] ILIKE wildcard -eskalointi (escape `%` ja `_`)
- [ ] Docker-porttien sitominen 127.0.0.1:hin
- [ ] Dockerfile: non-root user
- [ ] Salasanojen siirto ympäristömuuttujiin

### Eurooppalaiset AI-mallit (kokeiltava)
- [ ] **Mistral** — `mistral-small`, `mistral-medium` LiteLLM:n kautta
  - Tarkista suomenkielinen laatu chat-vastauksissa
  - Vertaa hinta/laatu GPT-4.1-miniin
- [ ] **Mistral Embed** — embedding-malli, vertaa bge-m3:een
- [ ] **Grok** (xAI) — `grok-2`, `grok-2-mini`
  - LiteLLM tukee: `xai/grok-2`
  - Vaatii XAI_API_KEY
- [ ] **Cohere** — `command-r`, `command-r-plus`
  - Hyvä monikielinen tuki
  - Embed v3 -malli suomeksi
- [ ] **Mistral lokaalit** — `mistral-nemo:12b` Ollamassa
  - `ollama pull mistral-nemo`
  - Vertaa deepseek-r1:14b:hen

### MCP Server
- [ ] FastMCP-toteutus
- [ ] Tools: query, ingest_url, list_parties, search_votes, get_representative
- [ ] Resources: parties://list, sources://stats
- [ ] Testaa Claude Code + Claude Desktop -integraatio

### Lisädata
- [ ] Eduskuntavaalit 2023 — ehdokas- ja tulosdata vaalit.fi:stä
- [ ] Kuntavaalit 2025 — ehdokasdata
- [ ] Vaalikoneiden vastausdata (YLE, HS) jos saatavilla
- [ ] Kansanedustajien some-tilit (X/Twitter)
- [ ] Eduskunnan puheenvuorot (SaliDBPuheenvuoro-taulu)

### Tekninen kehitys
- [ ] Celery-työntekijä indeksointiin (tausta-ajot)
- [ ] Keycloak-autentikaatio (dev → prod)
- [ ] Rate limiting API:lle
- [ ] Dependency lockfile (uv.lock tai requirements.lock)
- [ ] CI/CD (GitHub Actions: testit, lint, Docker build)
- [ ] Tietokantadumpin automaattinen päivitys (cron)

### Web UI
- [ ] Vastauksen streaming (SSE/WebSocket)
- [ ] Keskusteluhistoria (local storage)
- [ ] Mobiili-responsiivisuus
- [ ] Tumma/vaalea teema
- [ ] Puolueiden värikoodit vastauksissa
