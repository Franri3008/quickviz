import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "export"
ESBUILD = "esbuild@0.28.2"
WORLD_Q = 20000
WORLD_TOL = 0.01

JS = [
    ("charts.js", "charts.min.js"),
    ("ceps-theme.js", "ceps-theme.min.js"),
    ("aiw-theme.js", "aiw-theme.min.js"),
    ("vendor/d3.min.js", "d3.min.js"),
    ("vendor/d3-sankey.min.js", "d3-sankey.min.js"),
    ("vendor/topojson-client.min.js", "topojson-client.min.js"),
]
WORLD = ("vendor/countries-50m.json", "countries-50m.min.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def banner(src: str) -> str:
    first = src.split("\n", 1)[0]
    return first + "\n" if first.startswith("// https://") and "Copyright" in first else ""


def minify(src_path: Path, out_path: Path):
    r = subprocess.run(["npx", "--yes", ESBUILD, str(src_path), "--minify", "--legal-comments=none", "--charset=utf8", "--log-level=warning"],
                       capture_output=True, text=True, check=True)
    out_path.write_text(banner(src_path.read_text()) + r.stdout.strip() + "\n")


def simplify(pts: list, tol: float) -> list:
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        span = dx * dx + dy * dy or 1e-12
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / span))
            d = (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2
            if d > best:
                best, bi = d, i
        if bi > 0 and best > tol * tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def requantize(topo: dict, q: int, tol: float = 0.0) -> dict:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    x0, y0, x1, y1 = topo["bbox"]
    nsx, nsy = (x1 - x0) / (q - 1), (y1 - y0) / (q - 1)
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        deg = []
        for dx, dy in arc:
            x += dx
            y += dy
            deg.append((x * sx + tx, y * sy + ty))
        pts = []
        for lon, lat in simplify(deg, tol):
            p = (round((lon - x0) / nsx), round((lat - y0) / nsy))
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) == 1:
            pts.append(pts[0])
        px = py = 0
        enc = []
        for a, b in pts:
            enc.append([a - px, b - py])
            px, py = a, b
        arcs.append(enc)
    return {"type": "Topology", "bbox": topo["bbox"], "transform": {"scale": [nsx, nsy], "translate": [x0, y0]},
            "objects": {"countries": topo["objects"]["countries"]}, "arcs": arcs}


def build_world(src_path: Path, out_path: Path):
    topo = requantize(json.loads(src_path.read_text()), WORLD_Q, WORLD_TOL)
    out_path.write_text(json.dumps(topo, separators=(",", ":")))


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {}
    for src, out in JS:
        minify(WEB / src, OUT / out)
        manifest[out] = {"source": src, "source_sha256": sha(WEB / src), "sha256": sha(OUT / out)}
    build_world(WEB / WORLD[0], OUT / WORLD[1])
    manifest[WORLD[1]] = {"source": WORLD[0], "source_sha256": sha(WEB / WORLD[0]), "sha256": sha(OUT / WORLD[1])}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for out, m in manifest.items():
        print(f"{out}: {(WEB / m['source']).stat().st_size} -> {(OUT / out).stat().st_size} bytes")


if __name__ == "__main__":
    sys.exit(main())
