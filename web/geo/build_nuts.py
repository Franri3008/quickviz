import json, os, subprocess, tempfile, urllib.request

from build_regions import norm

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regions")
URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_10M_{year}_4326_LEVL_{level}.geojson"
ISO3_FIX = {"XK": "KOS"}


def fetch(year, level):
    return json.load(urllib.request.urlopen(URL.format(year=year, level=level)))["features"]


def iso3(p):
    return ISO3_FIX.get(p["CNTR_CODE"], p.get("ISO3_CODE") or "")


def names(p):
    out = set()
    for n in (p.get("NAME_LATN"), p.get("NUTS_NAME")):
        for part in str(n or "").split("/"):
            if len(norm(part)) > 1:
                out.add(norm(part))
    return out


def layers():
    by = {}
    for level in (1, 2):
        now = fetch(2024, level)
        old = fetch(2021, level)
        ids = {f["properties"]["NUTS_ID"] for f in now}
        feats = now + [f for f in old if f["properties"]["CNTR_CODE"] == "UK"]
        by_name = {}
        for f in feats:
            by_name.setdefault((iso3(f["properties"]), norm(f["properties"]["NAME_LATN"])), f)
        extra = {}
        for f in old:
            p = f["properties"]
            if p["NUTS_ID"] in ids or p["CNTR_CODE"] == "UK":
                continue
            twin = by_name.get((iso3(p), norm(p["NAME_LATN"])))
            if twin:
                extra.setdefault(twin["properties"]["NUTS_ID"], set()).add(norm(p["NUTS_ID"]))
        for f in feats:
            p = f["properties"]
            a3 = iso3(p)
            if not a3:
                continue
            al = {norm(p["NUTS_ID"])} | extra.get(p["NUTS_ID"], set())
            f["properties"] = {"nuts": p["NUTS_ID"], "name": p["NAME_LATN"], "aliases": al, "names": names(p)}
            by.setdefault(a3, {}).setdefault(level, []).append(f)
    for a3, levels in by.items():
        for fs in levels.values():
            whole = len(fs) == 1
            for f in fs:
                p = f["properties"]
                p["aliases"] = sorted(p["aliases"] | (set() if whole else p["names"]))
                del p["names"]
    return by


def add(a3, levels, tmp, index):
    path = os.path.join(OUT, a3 + ".json")
    if not os.path.exists(path):
        return False
    base = json.load(open(path))
    keep = {k: v for k, v in base["objects"].items() if not k.startswith("nuts")}
    base["objects"] = keep
    clean = os.path.join(tmp, a3 + "-base.json")
    json.dump(base, open(clean, "w"))
    inputs = []
    for level, fs in sorted(levels.items()):
        raw = os.path.join(tmp, f"{a3}-n{level}.geojson")
        json.dump({"type": "FeatureCollection", "features": [{**f, "properties": {"nuts": f["properties"]["nuts"]}} for f in fs]}, open(raw, "w"))
        simple = os.path.join(tmp, f"nuts{level}.json")
        subprocess.run(["npx", "-y", "mapshaper@0.6", "-i", raw, "-simplify", "8%", "keep-shapes", "-o", simple, "format=geojson"], check=True, capture_output=True)
        inputs.append(simple)
    merged = os.path.join(tmp, a3 + ".json")
    subprocess.run(["npx", "-y", "mapshaper@0.6", "-i", clean, *inputs, "combine-files", "-o", merged, "format=topojson", "quantization=10000", "target=*"],
                   check=True, capture_output=True)
    topo = json.load(open(merged))
    for k, obj in keep.items():
        new = topo["objects"][k]["geometries"]
        assert len(new) == len(obj["geometries"]), (a3, k)
        for g, o in zip(new, obj["geometries"]):
            g["properties"] = o.get("properties", {})
    for level, fs in levels.items():
        props = {f["properties"]["nuts"]: f["properties"] for f in fs}
        for g in topo["objects"][f"nuts{level}"]["geometries"]:
            g["properties"] = props[g["properties"]["nuts"]]
            for a in g["properties"]["aliases"]:
                index.setdefault(a, set()).add(a3)
    order = list(keep) + [f"nuts{level}" for level in sorted(levels)]
    topo["objects"] = {k: topo["objects"][k] for k in order}
    json.dump(topo, open(path, "w"), separators=(",", ":"))
    return True


def main():
    by = layers()
    ipath = os.path.join(OUT, "index.json")
    old = json.load(open(ipath))
    index = {a: set([v] if isinstance(v, str) else v) for a, v in old.items()}
    tmp = tempfile.mkdtemp()
    done = [a3 for a3 in sorted(by) if add(a3, by[a3], tmp, index)]
    index = {a: (sorted(s)[0] if len(s) == 1 else sorted(s)) for a, s in index.items()}
    json.dump(index, open(ipath, "w"), separators=(",", ":"), sort_keys=True)
    print(len(done), "countries with NUTS layers:", " ".join(done))
    print("no region file:", " ".join(sorted(set(by) - set(done))) or "none")


if __name__ == "__main__":
    main()
