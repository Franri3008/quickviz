import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MANIFEST = WEB / "renderer-manifest.json"
DEFAULT_SOURCE = ROOT.parent / "ceps-quickviz" / "web"
FILES = ["charts.js", "aiw-theme.js", "ceps-theme.js", "franri-theme.js", "aiw-logo.svg", "capabilities.json"]
DIRS = ["vendor", "geo", "flags", "export", "fonts"]
SKIP = {"__pycache__", ".DS_Store"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def listed(base: Path) -> list[str]:
    out = [f for f in FILES if (base / f).is_file()]
    for d in DIRS:
        for p in sorted((base / d).rglob("*")):
            if p.is_file() and not SKIP & set(p.relative_to(base).parts):
                out.append(p.relative_to(base).as_posix())
    return sorted(out)


def commit(source: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return r.stdout.strip() or None


def check() -> list[str]:
    if not MANIFEST.exists():
        return ["web/renderer-manifest.json is missing, run scripts/sync_renderer.py"]
    files = json.loads(MANIFEST.read_text())["files"]
    bad = []
    for rel, digest in sorted(files.items()):
        p = WEB / rel
        if not p.is_file():
            bad.append(f"{rel} is missing")
        elif sha(p) != digest:
            bad.append(f"{rel} differs from the synced copy")
    for rel in listed(WEB):
        if rel not in files:
            bad.append(f"{rel} is not in the manifest")
    return bad


def sync(source: Path):
    missing = [f for f in FILES if not (source / f).is_file()] + [d for d in DIRS if not (source / d).is_dir()]
    if missing:
        sys.exit(f"Not found in {source}: {', '.join(missing)}")
    for d in DIRS:
        shutil.rmtree(WEB / d, ignore_errors=True)
    files = {}
    for rel in listed(source):
        dest = WEB / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, dest)
        files[rel] = sha(dest)
    MANIFEST.write_text(json.dumps({"source": "ceps-quickviz/web", "commit": commit(source), "files": files}, indent=1) + "\n")
    print(f"Synced {len(files)} files from {source}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        bad = check()
        print("\n".join(bad) or "Renderer matches the manifest")
        sys.exit(1 if bad else 0)
    sync(args.source.resolve())


if __name__ == "__main__":
    main()
