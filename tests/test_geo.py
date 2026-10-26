import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
REGIONS = WEB / "geo" / "regions"


def aliases():
    src = (WEB / "charts.js").read_text()
    return json.loads(re.search(r"const GEO_ALIAS = (\{.*?\});\n", src).group(1))


@pytest.mark.parametrize("code,iso", [("el", "300"), ("uk", "826"), ("gr", "300"), ("gb", "826")])
def test_eurostat_country_codes(code, iso):
    assert code in aliases()[iso]


def test_index_has_nuts_codes():
    idx = json.loads((REGIONS / "index.json").read_text())
    assert idx["de2"] == "DEU"
    assert idx["dea"] == "DEU"
    assert idx["el30"] == "GRC"
    assert idx["ukc"] == "GBR"
    assert idx["fr1"] == "FRA"
    assert idx["nl31"] == "NLD"


@pytest.mark.parametrize("a3,layer,count", [("DEU", "nuts1", 16), ("DEU", "nuts2", 38), ("FRA", "nuts1", 14), ("GBR", "nuts1", 12), ("ITA", "nuts2", 21)])
def test_nuts_layers(a3, layer, count):
    topo = json.loads((REGIONS / f"{a3}.json").read_text())
    geoms = topo["objects"][layer]["geometries"]
    assert len(geoms) == count
    assert all(g["properties"]["nuts"].lower() in g["properties"]["aliases"] for g in geoms)
    assert list(topo["objects"])[0] == "units"


def test_german_sample_codes_all_match():
    topo = json.loads((REGIONS / "DEU.json").read_text())
    have = {a for g in topo["objects"]["nuts1"]["geometries"] for a in g["properties"]["aliases"]}
    rows = (Path(__file__).resolve().parents[1] / "samples" / "MOCK_ai_vacancy_share_german_regions_wide.csv").read_text().splitlines()
    codes = [r.split(",")[2].lower() for r in rows if re.match(r"^[^,]+,DE-", r)]
    assert len(codes) == 16 and set(codes) <= have
