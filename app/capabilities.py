import json
from pathlib import Path

CAPS = json.loads((Path(__file__).resolve().parents[1] / "web" / "capabilities.json").read_text())


def honoured(kind: str | None) -> set[str]:
    if kind not in CAPS["kinds"]:
        return set()
    return set(CAPS["always"]) | set(CAPS["common"]) | set(CAPS["kinds"][kind])


def unsupported(edits: dict, kind: str | None) -> list[str]:
    if kind not in CAPS["kinds"]:
        return []
    ok = honoured(kind)
    return [k for k, v in edits.items() if v is not None and k not in ok]


def kind_name(kind: str | None) -> str:
    return CAPS["names"].get(kind or "", "chart")


def say_missing(fields: list[str], kind: str | None) -> str:
    labels = list(dict.fromkeys(CAPS["labels"].get(f, f) for f in fields))
    if not labels:
        return ""
    what = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " or " + labels[-1]
    art = "an" if kind_name(kind)[0] in "aeiou" else "a"
    return f"{art.capitalize()} {kind_name(kind)} cannot show {what}, so that part did not change."
