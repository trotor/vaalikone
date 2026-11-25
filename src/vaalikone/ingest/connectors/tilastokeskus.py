"""Tilastokeskus PxWeb API connector — election candidate and result data.

Source: https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin/evaa/ (CC BY 4.0).
Table 13t3.px: "Ehdokkaiden saamat äänimäärät sekä vertausluku eduskuntavaaleissa"
variables: Vuosi, Ehdokas ("Sukunimi Etunimi / PUOLUE / Vaalipiiri"),
Valintatieto (Valittu/Varalla/Ei valittu), Tiedot (äänet, osuus, vertausluku).
"""

import httpx

PXWEB_BASE = "https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin"

# Eduskuntavaalit: ehdokkaiden äänimäärät ja vertausluku (2023)
EDUSKUNTAVAALIT_EHDOKKAAT_TABLE = "evaa/13t3.px"


class TilastokeskusClient:
    def __init__(self, base_url: str = PXWEB_BASE):
        self.base_url = base_url

    async def _get_json(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(f"{self.base_url}/{path}")
            resp.raise_for_status()
            return resp.json()

    async def _post_query(self, path: str, query: dict) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/{path}",
                json={**query, "response": {"format": "json-stat2"}},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_candidates(self, table: str = EDUSKUNTAVAALIT_EHDOKKAAT_TABLE) -> list[dict]:
        """Fetch all candidates with votes for an election table.

        Returns list of dicts: {candidate_number, name, party, constituency,
        elected, votes, vote_share, comparison_number}.
        """
        meta = await self._get_json(table)
        {v["code"]: v for v in meta["variables"]}
        ehdokas = next(v for v in meta["variables"] if "ehdokas" in v["code"].lower())

        query = {
            "query": [
                {
                    "code": v["code"],
                    "selection": {"filter": "item", "values": v["values"]},
                }
                for v in meta["variables"]
            ]
        }
        data = await self._post_query(table, query)

        dims = data["dimension"]
        sizes = data["size"]
        values = data["value"]

        # json-stat2: value index = sum over dimensions in order, last dim fastest
        list(dims.keys()).index(ehdokas["code"])
        # locate dimension indexes
        codes = list(dims.keys())
        idx = {c: i for i, c in enumerate(codes)}

        def _position(code: str, value_code: str) -> int:
            index = dims[code]["category"]["index"]
            if isinstance(index, dict):
                return index[value_code]
            return index.index(value_code)

        def label(code: str, value_index: int) -> str:
            labels = dims[code]["category"]["label"]
            if isinstance(labels, dict):
                index = dims[code]["category"]["index"]
                value_code = index[value_index] if isinstance(index, list) else next(
                    k for k, v in index.items() if v == value_index
                )
                return labels[value_code]
            return labels[value_index]

        def value_at(coords: list[int]) -> float | None:
            flat = 0
            for c, s in zip(coords, sizes):
                flat = flat * s + c
            v = values[flat]
            return None if v is None else float(v)

        # dimension order in this table: Vuosi, Ehdokas, Valintatieto, Tiedot
        n_ehdokas = sizes[idx[ehdokas["code"]]]
        valintatieto_code = next(c for c in codes if "valintatieto" in c or "vaalitiedot" in c)
        tiedot_code = next(c for c in codes if c == "contentscode")
        sizes[idx[valintatieto_code]]
        sizes[idx[tiedot_code]]
        codes[0]

        vt_labels = dims[valintatieto_code]["category"]["label"]
        elected_label = None
        for code_val, lab in vt_labels.items():
            if "valittu" in lab.lower() and "ei" not in lab.lower():
                elected_label = _position(valintatieto_code, code_val)
        tiedot_labels = dims[tiedot_code]["category"]["label"]
        def _tieto_pos(keywords):
            for code, lab in tiedot_labels.items():
                if any(k in lab.lower() for k in keywords):
                    return _position(tiedot_code, code)
            raise ValueError(f"Tieto not found: {keywords}")

        aanet_i = _tieto_pos(["änet", "aanet"])
        osuus_i = _tieto_pos(["osuus"])
        vluku_i = _tieto_pos(["vertausluku"])

        candidates = []
        for e in range(n_ehdokas):
            raw = label(ehdokas["code"], e)
            parts = [p.strip() for p in raw.split("/")]
            name = parts[0] if parts else raw
            party = parts[1] if len(parts) > 1 else None
            constituency = parts[2] if len(parts) > 2 else None
            # name "Sukunimi Etunimi"
            name_parts = name.split(" ", 1)
            last_name = name_parts[0] if name_parts else name
            first_name = name_parts[1] if len(name_parts) > 1 else ""
            elected = (
                elected_label is not None
                and value_at([0, e, elected_label, aanet_i]) is not None
            )
            votes = value_at([0, e, 0, aanet_i])
            share = value_at([0, e, 0, osuus_i])
            vluku = value_at([0, e, 0, vluku_i])
            idx_map = dims[ehdokas["code"]]["category"]["index"]
            if isinstance(idx_map, list):
                candidate_number = idx_map[e]
            else:
                candidate_number = next(k for k, v in idx_map.items() if v == e)
            candidates.append({
                "candidate_number": candidate_number,
                "first_name": first_name,
                "last_name": last_name,
                "party_abbr": party,
                "constituency": constituency,
                "elected": elected,
                "votes": int(votes) if votes is not None else None,
                "vote_share": share,
                "comparison_number": vluku,
            })
        return candidates
