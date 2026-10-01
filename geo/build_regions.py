"""Builds geo/regions/<ISO3>.json (one TopoJSON per country) and geo/regions/index.json (region name to country).
Source: Natural Earth 10m admin-1 states and provinces. Needs npx (mapshaper). Run from the repo root:
    python3 geo/build_regions.py
"""
import json, os, re, subprocess, tempfile, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor

SRC = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson"
OUT = os.path.join(os.path.dirname(__file__), "regions")
# Natural Earth names some coarse regions in one language only. Add the other common spelling.
GROUP_EXTRA = {
    "Apulia": ["puglia"], "Sicily": ["sicilia"], "Toscana": ["tuscany"], "Lombardia": ["lombardy"], "Piemonte": ["piedmont"],
    "Sardegna": ["sardinia"], "Valle d'Aosta": ["aosta valley"], "Trentino-Alto Adige": ["sudtirol", "south tyrol"],
    "Cataluña": ["catalonia", "catalunya"], "Andalucía": ["andalusia"], "País Vasco": ["basque country", "euskadi"],
    "Valenciana": ["comunidad valenciana", "valencia", "comunitat valenciana", "valencian"], "Islas Baleares": ["balearic islands", "illes balears"],
    "Foral de Navarra": ["navarra", "navarre"], "Madrid": ["comunidad de madrid"], "Castilla y León": ["castile and leon"],
    "Castilla-La Mancha": ["castile la mancha"], "Canary Is.": ["canarias", "canary islands"], "Murcia": ["region de murcia"],
    "Bretagne": ["brittany"], "Normandie": ["normandy"], "Corse": ["corsica"],
}
PREFIX = re.compile(r"^(region de la|region del|region de|region|provincia de|province of|state of|estado de|community of|comunidad de|comunitat) |( community)$")


def norm(s):  # must match normRegion in charts.js
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^the ", "", re.sub(r"[^a-z0-9]+", " ", s).strip())
    return PREFIX.sub("", s).strip()


def main():
    data = json.load(urllib.request.urlopen(SRC))
    by = {}
    for f in data["features"]:
        p, a3 = f["properties"], f["properties"]["adm0_a3"]
        if not a3 or a3 == "-99" or not f.get("geometry"):
            continue
        names = {p.get(k) for k in ["name", "name_en", "woe_name", "gn_name", "postal", "iso_3166_2"]}
        names |= set((p.get("name_alt") or "").split("|"))
        code = (p.get("iso_3166_2") or "").split("-")[-1]
        aliases = {norm(n) for n in names if n and len(str(n)) > 1} | ({norm(code)} if len(code) > 1 else set())
        # short forms people write: "Magallanes" for "Magallanes y Antartica Chilena", "Aisen" for "Aisen del General..."
        aliases |= {re.split(r" (y|and|del|de la|et) ", x)[0] for x in aliases if " " in x} - {""}
        aliases = {x for x in aliases if len(x) > 1}
        f["properties"] = {"name": p["name"], "aliases": sorted(a for a in aliases if a), "group": p.get("region") or ""}
        by.setdefault(a3, []).append(f)
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp()

    def build(a3):
        src = os.path.join(tmp, a3 + ".geojson")
        json.dump({"type": "FeatureCollection", "features": by[a3]}, open(src, "w"))
        out = os.path.join(OUT, a3 + ".json")
        # Two layers when the country has a coarser level (French regions over departements, Spanish communities
        # over provinces): "units" is admin-1, "groups" is the same shapes dissolved by Natural Earth's region field.
        groups = len({f["properties"]["group"] for f in by[a3]} - {""}) > 1
        cmd = ["npx", "-y", "mapshaper@0.6", "-i", src, "name=units", "-simplify", "4%", "keep-shapes"]
        if groups:
            cmd += ["-dissolve", "group", "+", "name=groups"]
        cmd += ["-o", out, "format=topojson", "quantization=10000", "target=*"]
        subprocess.run(cmd, check=True, capture_output=True)
        topo = json.load(open(out))
        for g in topo["objects"].get("units", {}).get("geometries", []):
            g["properties"].pop("group", None)
        for g in topo["objects"].get("groups", {}).get("geometries", []):
            name = g["properties"].get("group", "")
            al = {norm(name), norm(name.replace(" Is.", " Islands"))}
            al |= {re.split(r" (y|and|del|de la|et) ", x)[0] for x in al if " " in x}
            al |= {norm(x) for x in GROUP_EXTRA.get(name, [])}
            g["properties"] = {"name": name, "aliases": sorted(x for x in al if len(x) > 1)}
            group_names.setdefault(a3, set()).update(g["properties"]["aliases"])
        json.dump(topo, open(out, "w"), separators=(",", ":"))

    group_names = {}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(build, by))
    index = {}
    for a3, al in group_names.items():
        for a in al:
            index.setdefault(a, set()).add(a3)
    for a3, fs in by.items():
        for f in fs:
            for a in f["properties"]["aliases"]:
                index.setdefault(a, set()).add(a3)
    index = {a: (sorted(s)[0] if len(s) == 1 else sorted(s)) for a, s in index.items()}
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), separators=(",", ":"), sort_keys=True)
    print(len(by), "countries,", len(index), "names")


if __name__ == "__main__":
    main()
