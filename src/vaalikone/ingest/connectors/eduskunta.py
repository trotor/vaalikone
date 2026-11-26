import httpx

from vaalikone.core.config import get_settings

# Vanha avoimen datan taulurajapinta (siirtyy uuteen palveluun 2027 alusta)
BASE_URL = "https://avoindata.eduskunta.fi"
# Uusi hakurajapinta (täysistuntopuheet, valtiopäiväasiat ym.)
SEARCH_URL = "https://api.eduskunta.fi"


def _base_url() -> str:
    return getattr(get_settings(), "EDUSKUNTA_API_URL", BASE_URL) or BASE_URL


def _search_url() -> str:
    return getattr(get_settings(), "EDUSKUNTA_SEARCH_URL", SEARCH_URL) or SEARCH_URL


class EduskuntaClient:
    def __init__(self, base_url: str | None = None, search_url: str | None = None):
        self.base_url = base_url or _base_url()
        self.search_url = search_url or _search_url()

    async def fetch_table_page(
        self, table: str, page: int = 0, per_page: int = 100
    ) -> dict:
        url = f"{self.base_url}/api/v1/tables/{table}/rows"
        params = {"page": page, "perPage": per_page}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def fetch_table_batch(
        self, table: str, pk_name: str, pk_start: int = 0, per_page: int = 100
    ) -> dict:
        url = f"{self.base_url}/api/v1/tables/{table}/batch"
        params = {"pkName": pk_name, "pkStartValue": pk_start, "perPage": per_page}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    def parse_rows(self, response: dict) -> list[dict]:
        columns = response["columnNames"]
        return [dict(zip(columns, row)) for row in response["rowData"]]

    async def _fetch_all_pages(
        self, table: str, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_rows = []
        page = 0
        while True:
            result = await self.fetch_table_page(table, page=page, per_page=per_page)
            rows = self.parse_rows(result)
            all_rows.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_rows

    async def fetch_representatives(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        return await self._fetch_all_pages("MemberOfParliament", max_pages, per_page)

    async def fetch_votes(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        return await self._fetch_all_pages("SaliDBAanestysEdustaja", max_pages, per_page)

    async def fetch_vote_summaries(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        return await self._fetch_all_pages("SaliDBAanestys", max_pages, per_page)

    async def search(
        self,
        query: str | None = None,
        category: str | None = None,
        expression: dict | None = None,
        max_results: int = 100,
        start_from: int = 0,
        combined_search: bool = True,
    ) -> dict:
        """Search the new api.eduskunta.fi search endpoint.

        Categories: kansanedustaja, valtiopaivaasia, asiakirja, tapahtuma,
        puheenvuoro, aanestys, yhteystieto, sivu, tiedosto.
        """
        body: dict = {
            "maxResults": max_results,
            "startFromIndex": start_from,
            "combinedSearch": combined_search,
        }
        if query:
            body["query"] = query
        if category:
            body["category"] = category
        if expression:
            body["expression"] = expression
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.search_url}/api/v1/search", json=body)
            resp.raise_for_status()
            return resp.json()

    async def search_speeches(
        self, query: str, max_results: int = 100, start_from: int = 0
    ) -> dict:
        """Search floor speeches (puheenvuorot) by text. Returns full speech text."""
        return await self.search(
            query=query, category="puheenvuoro",
            max_results=max_results, start_from=start_from,
        )

    async def search_group_speeches(
        self, max_results: int = 500, start_from: int = 0
    ) -> dict:
        """Ryhmäpuheenvuorot (puheenvuorotyyppikoodi R): eduskuntaryhmän virallinen kanta."""
        return await self.search(
            category="puheenvuoro",
            expression={"property": "puheenvuorotyyppikoodi", "match": "R"},
            max_results=max_results, start_from=start_from, combined_search=False,
        )

    async def search_written_questions(
        self, max_results: int = 100, start_from: int = 0, valtiopaiva: str | None = None
    ) -> dict:
        """List written questions (kirjalliset kysymykset, KK)."""
        expression = {"property": "eduskuntatunnus", "match": "KK"}
        if valtiopaiva:
            expression = {
                "and": [
                    expression,
                    {"property": "valtiopaiva", "match": valtiopaiva},
                ]
            }
        return await self.search(
            category="valtiopaivaasia", expression=expression,
            max_results=max_results, start_from=start_from,
            combined_search=False,
        )

    async def fetch_document_xml(self, eduskuntatunnus: str) -> str | None:
        """Fetch the XML body of a parliamentary matter (e.g. KK 237/2023 vp)."""
        import urllib.parse
        encoded = urllib.parse.quote(eduskuntatunnus, safe="")
        url = f"{self.search_url}/api/v1/valtiopaivaasiat/{encoded}/xml"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text

    async def fetch_document_html(self, eduskuntatunnus: str) -> str | None:
        """Backwards-compatible alias for fetch_document_xml."""
        return await self.fetch_document_xml(eduskuntatunnus)
