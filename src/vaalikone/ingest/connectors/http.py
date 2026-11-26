"""Yhteiset HTTP-asetukset puolueiden sivuja hakeville konnektoreille."""

# Osa puolueiden sivuista (esim. avoinpuolue.fi) palauttaa 403 httpx:n oletus-UA:lle.
HARVESTER_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; vaalikone-harvester/1.0)"}
