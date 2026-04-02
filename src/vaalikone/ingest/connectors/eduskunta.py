import httpx


BASE_URL = "https://avoindata.eduskunta.fi"


class EduskuntaClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

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

    async def fetch_representatives(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_reps = []
        page = 0
        while True:
            result = await self.fetch_table_page("MemberOfParliament", page=page, per_page=per_page)
            rows = self.parse_rows(result)
            all_reps.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_reps

    async def fetch_votes(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_votes = []
        page = 0
        while True:
            result = await self.fetch_table_page(
                "SaliDBAanestysEdustaja", page=page, per_page=per_page
            )
            rows = self.parse_rows(result)
            all_votes.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_votes

    async def fetch_vote_summaries(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_summaries = []
        page = 0
        while True:
            result = await self.fetch_table_page(
                "SaliDBAanestys", page=page, per_page=per_page
            )
            rows = self.parse_rows(result)
            all_summaries.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_summaries
