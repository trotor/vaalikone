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

# Europarlamenttivaalit 2024: ehdokkaiden äänimäärät, vertausluku ja valintatieto
EUROVAALIT_EHDOKKAAT_TABLE = "euvaa/14gy.px"

# Presidentinvaali 2024: ehdokkaiden äänimäärät koko maassa (SSS), kierros 1 ja 2
PRESIDENTINVAALI_EHDOKKAAT_TABLE = "pvaa/14d5.px"

# Kuntavaalit 2025: ehdokkaiden äänimäärä ja valintatieto per vaalipiiri
KUNTAVAALIT_VAALIPIIRI_TABLES = {
    "Helsinki": "kvaa/14uk.px",
    "Uusimaa": "kvaa/14ux.px",
    "Varsinais-Suomi": "kvaa/14uy.px",
    "Satakunta": "kvaa/14uz.px",
    "Häme": "kvaa/14v1.px",
    "Pirkanmaa": "kvaa/14v2.px",
    "Kaakkois-Suomi": "kvaa/14v3.px",
    "Savo-Karjala": "kvaa/14v4.px",
    "Vaasa": "kvaa/14v5.px",
    "Keski-Suomi": "kvaa/14v6.px",
    "Oulu": "kvaa/14v7.px",
    "Lappi": "kvaa/14v8.px",
}


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

    async def fetch_municipal_candidates(
        self, table: str, constituency: str, year: str = "2025"
    ) -> list[dict]:
        """Kuntavaalien ehdokkaat yhdestä vaalipiiritaulusta.

        Rakenne: Vuosi, Ehdokas ("Sukunimi Etunimi / PUOLUE / Kunta"),
        Tiedot (äänimäärä yht, ennakkoäänet, osuus, valintatieto 1=valittu...).
        """
        meta = await self._get_json(table)
        ehdokas = next(v for v in meta["variables"] if "ehdokas" in v["code"].lower())
        tiedot = next(v for v in meta["variables"] if v["code"] == "contentscode")
        time_var = next(v for v in meta["variables"] if v["code"].startswith("timeperiod"))

        query = {
            "query": [
                {"code": time_var["code"], "selection": {"filter": "item", "values": [year]}},
                {"code": ehdokas["code"],
                 "selection": {"filter": "item", "values": ehdokas["values"]}},
                {"code": "contentscode",
                 "selection": {"filter": "item", "values": tiedot["values"]}},
            ]
        }
        data = await self._post_query(table, query)

        dims = data["dimension"]
        sizes = data["size"]
        values = data["value"]
        codes = list(dims.keys())
        idx = {c: i for i, c in enumerate(codes)}

        def _position(code: str, value_code: str) -> int:
            index = dims[code]["category"]["index"]
            if isinstance(index, dict):
                return index[value_code]
            return index.index(value_code)

        def value_at(coords: list[int]) -> float | None:
            flat = 0
            for c, s in zip(coords, sizes):
                flat = flat * s + c
            v = values[flat]
            return None if v is None else float(v)

        tiedot_labels = dims["contentscode"]["category"]["label"]

        def _tieto_pos(keywords):
            for code_val, lab in tiedot_labels.items():
                if any(k in lab.lower() for k in keywords):
                    return _position("contentscode", code_val)
            raise ValueError(f"Tieto not found: {keywords}")

        aanet_i = _tieto_pos(["änimäärä yhteensä", "aanimaara yhteensa"])
        osuus_i = _tieto_pos(["osuus"])
        valinta_i = _tieto_pos(["valintatieto"])

        ehdokas_labels = dims[ehdokas["code"]]["category"]["label"]
        ehdokas_index = dims[ehdokas["code"]]["category"]["index"]
        n_ehdokas = sizes[idx[ehdokas["code"]]]

        candidates = []
        for e in range(n_ehdokas):
            if isinstance(ehdokas_index, dict):
                value_code = next(k for k, v in ehdokas_index.items() if v == e)
            else:
                value_code = ehdokas_index[e]
            raw = ehdokas_labels[value_code]
            parts = [p.strip() for p in raw.split("/")]
            name = parts[0] if parts else raw
            party = parts[1] if len(parts) > 1 else None
            kunta = parts[2] if len(parts) > 2 else None
            name_parts = name.split(" ", 1)
            last_name = name_parts[0] if name_parts else name
            first_name = name_parts[1] if len(name_parts) > 1 else ""
            votes = value_at([0, e, aanet_i])
            share = value_at([0, e, osuus_i])
            valinta = value_at([0, e, valinta_i])
            candidates.append({
                "candidate_number": value_code,
                "first_name": first_name,
                "last_name": last_name,
                "party_abbr": party,
                "constituency": f"{constituency} / {kunta}" if kunta else constituency,
                "elected": valinta == 1.0,
                "votes": int(votes) if votes is not None else None,
                "vote_share": share,
                "comparison_number": None,
            })
        return candidates

    async def fetch_election_results(
        self,
        table: str,
        year: str,
        area: str | None = None,
        kierros: list[str] | None = None,
        constituency: str | None = None,
    ) -> list[dict]:
        """Yleinen PxWeb-haku vaalitauluille, joissa dimensiot ovat
        Vuosi, [Alue], Ehdokas, [Kierros], Tiedot(contentscode).

        Toimii mm. euvaa/14gy.px (eurovaalit) ja pvaa/14d5.px (presidentinvaali).
        """
        meta = await self._get_json(table)
        ehdokas = next(v for v in meta["variables"] if "ehdokas" in v["code"].lower())
        tiedot = next(v for v in meta["variables"] if v["code"] == "contentscode")
        time_var = next(v for v in meta["variables"] if v["code"].startswith("timeperiod"))

        query: list[dict] = [
            {"code": time_var["code"], "selection": {"filter": "item", "values": [year]}},
            {"code": ehdokas["code"],
             "selection": {"filter": "item", "values": ehdokas["values"]}},
            {"code": "contentscode",
             "selection": {"filter": "item", "values": tiedot["values"]}},
        ]
        for v in meta["variables"]:
            if v["code"] in (time_var["code"], ehdokas["code"], "contentscode"):
                continue
            if "alue" in v["code"].lower() and area is not None:
                query.append({"code": v["code"],
                              "selection": {"filter": "item", "values": [area]}})
            elif "kierros" in v["text"].lower() and kierros is not None:
                query.append({"code": v["code"],
                              "selection": {"filter": "item", "values": kierros}})
            else:
                query.append({"code": v["code"],
                              "selection": {"filter": "item", "values": v["values"][:1]}})
        data = await self._post_query(table, {"query": query})

        dims = data["dimension"]
        sizes = data["size"]
        values = data["value"]
        codes = list(dims.keys())
        idx = {c: i for i, c in enumerate(codes)}

        def _position(code: str, value_code: str) -> int:
            index = dims[code]["category"]["index"]
            if isinstance(index, dict):
                return index[value_code]
            return index.index(value_code)

        def value_at(coords: list[int]) -> float | None:
            flat = 0
            for c, s in zip(coords, sizes):
                flat = flat * s + c
            v = values[flat]
            return None if v is None else float(v)

        tiedot_labels = dims["contentscode"]["category"]["label"]

        def _tieto_pos(keywords, exclude=()):
            for code_val, lab in tiedot_labels.items():
                low = lab.lower()
                if any(k in low for k in keywords) and not any(x in low for x in exclude):
                    return _position("contentscode", code_val)
            return None

        aanet_i = _tieto_pos(["änet (lkm", "aanet (lkm"], exclude=["ennakko", "vaalipäiv"])
        osuus_i = _tieto_pos(["osuus äänistä", "osuus aanista"], exclude=["ennakko", "vaalipäiv"])
        vluku_i = _tieto_pos(["vertausluku"])
        valinta_i = _tieto_pos(["valintatieto"])

        ehdokas_index = dims[ehdokas["code"]]["category"]["index"]
        ehdokas_labels = dims[ehdokas["code"]]["category"]["label"]
        n_ehdokas = sizes[idx[ehdokas["code"]]]

        kierros_code = next((c for c in codes if "kierros" in dims[c].get("label", "").lower()
                             or "kierros" in c.lower()), None)
        kierros_labels = None
        if kierros_code:
            kierros_labels = dims[kierros_code]["category"]["label"]
            kierros_index = dims[kierros_code]["category"]["index"]
            kierros_values = (list(kierros_labels.keys()) if isinstance(kierros_index, dict)
                              else kierros_index)
            n_kierros = sizes[idx[kierros_code]]
        else:
            kierros_values = [None]
            n_kierros = 1

        def _coord(dim_code, pos):
            return pos if dim_code in idx else 0

        # valintatieto puuttuu presidentinvaalista: päätellään kierroksen voittaja
        raw_rows = []
        for k in range(n_kierros):
            kierros_value = kierros_values[k] if kierros_labels else None
            kierros_lab = (kierros_labels.get(kierros_value, kierros_value)
                           if kierros_labels else None)
            for e in range(n_ehdokas):
                if isinstance(ehdokas_index, dict):
                    value_code = next(kk for kk, vv in ehdokas_index.items() if vv == e)
                else:
                    value_code = ehdokas_index[e]
                raw = ehdokas_labels[value_code]
                if "äänestysliput" in raw.lower() or "hylätyt" in raw.lower():
                    continue
                if "/" in raw:
                    parts = [p.strip() for p in raw.split("/")]
                    name, party = parts[0], (parts[1] if len(parts) > 1 else None)
                    np = (name.split(" ", 1) + [""])[:2]
                    first_name, last_name = np[1], np[0]
                else:
                    # presidentinvaali: "Etunimi Sukunimi"
                    name, party = raw, None
                    np = name.split(" ", 1)
                    first_name, last_name = (np + [""])[:2]
                coords = [0] * len(codes)
                coords[idx[ehdokas["code"]]] = e
                if kierros_code:
                    coords[idx[kierros_code]] = k
                coords[idx["contentscode"]] = aanet_i
                votes = value_at(coords)
                coords[idx["contentscode"]] = osuus_i if osuus_i is not None else 0
                share = value_at(coords) if osuus_i is not None else None
                coords[idx["contentscode"]] = vluku_i if vluku_i is not None else 0
                vluku = value_at(coords) if vluku_i is not None else None
                coords[idx["contentscode"]] = valinta_i if valinta_i is not None else 0
                valinta = value_at(coords) if valinta_i is not None else None
                raw_rows.append({
                    "candidate_number": value_code,
                    "kierros": kierros_lab,
                    "kierros_value": kierros_value,
                    "first_name": first_name,
                    "last_name": last_name,
                    "party_abbr": party,
                    "constituency": constituency,
                    "elected": (valinta == 1.0) if valinta_i is not None else None,
                    "votes": int(votes) if votes is not None else None,
                    "vote_share": share,
                    "comparison_number": vluku,
                })

        # presidentinvaali: toisen kierroksen eniten ääniä saanut = valittu
        if valinta_i is None:
            k2 = [r for r in raw_rows
                  if r["kierros"] and r["kierros"].lower().startswith(("toinen", "2"))]
            if k2:
                winner = max(k2, key=lambda r: r["votes"] or 0)
                for r in raw_rows:
                    if r in k2:
                        r["elected"] = r is winner
            for r in raw_rows:
                if r.get("kierros_value"):
                    r["candidate_number"] = f"{r['candidate_number']}-{r['kierros_value']}"
        for r in raw_rows:
            r.pop("kierros_value", None)
        return raw_rows
