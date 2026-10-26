import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "flags"
PACKAGE = "flag-icons@7.6.0"
SVGO = "svgo@3.3.5"
BOX = "0 0 640 480"
NOTICE = "flag-icons 7.6.0 | MIT License | Copyright (c) 2013 Panayiotis Lipiridis | github.com/lipis/flag-icons"


def country_codes() -> dict:
    src = (WEB / "charts.js").read_text()
    alias = json.loads(re.search(r"const GEO_ALIAS = (\{.*?\});\n", src).group(1))
    return {key: names for key, names in alias.items()}


def pick(names: list, have: set) -> str:
    two = [n for n in names if len(n) == 2 and n in have]
    if len(two) != 1:
        raise SystemExit(f"no single flag for {names[0]}: {two}")
    return two[0]


def body(key: str, svg: str) -> str:
    m = re.fullmatch(r"\s*<svg([^>]*)>(.*)</svg>\s*", svg, re.S)
    if not m:
        raise SystemExit(f"{key}: not one svg element")
    attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
    if attrs.get("viewBox") != BOX:
        raise SystemExit(f"{key}: viewBox is {attrs.get('viewBox')}")
    keep = {k: v for k, v in attrs.items() if k not in ("xmlns", "xmlns:xlink", "viewBox", "width", "height", "id")}
    inner = m.group(2).replace("xlink:href=", "href=")
    ids = re.findall(r'\sid="([^"]+)"', inner)
    for i in sorted(set(ids), key=len, reverse=True):
        new = f"qvf{key}-{i}"
        inner = re.sub(rf'(\sid=")({re.escape(i)})(")', rf"\g<1>{new}\g<3>", inner)
        inner = re.sub(rf'(url\(#)({re.escape(i)})(\))', rf"\g<1>{new}\g<3>", inner)
        inner = re.sub(rf'(href="#)({re.escape(i)})(")', rf"\g<1>{new}\g<3>", inner)
    base = {"fill": "#000", "stroke": "none", "stroke-width": "1", "fill-rule": "nonzero", **keep}
    head = " ".join(f'{k}="{v}"' for k, v in base.items())
    return f"<g {head}>{inner}</g>"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["npm", "pack", PACKAGE, "--silent", "--pack-destination", str(tmp)], check=True, capture_output=True)
        tgz = next(tmp.glob("flag-icons-*.tgz"))
        with tarfile.open(tgz) as t:
            t.extractall(tmp / "pkg", filter="data")
        pkg = tmp / "pkg" / "package"
        src = pkg / "flags" / "4x3"
        have = {p.stem for p in src.glob("*.svg")}
        want = {key: pick(names, have) for key, names in country_codes().items()}
        want["eu"] = "eu"
        sel, opt = tmp / "sel", tmp / "opt"
        sel.mkdir()
        for key, code in want.items():
            (sel / f"{key}.svg").write_text((src / f"{code}.svg").read_text())
        subprocess.run(["npx", "--yes", SVGO, "-q", "-p", "1", "--multipass", "-f", str(sel), "-o", str(opt)], check=True, capture_output=True)
        flags = {key: body(key, (opt / f"{key}.svg").read_text()) for key in sorted(want)}
        OUT.mkdir(exist_ok=True)
        (OUT / "flags.json").write_text(json.dumps({"_notice": NOTICE, **flags}, separators=(",", ":"), ensure_ascii=False) + "\n")
        (OUT / "LICENSE").write_text((pkg / "LICENSE").read_text())
    size = (OUT / "flags.json").stat().st_size
    print(f"{len(flags)} flags, {size / 1024:.0f} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
