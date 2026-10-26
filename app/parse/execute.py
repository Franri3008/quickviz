import datetime as dt
import re

from app.parse.recipe import Recipe
from app.parse.values import (ID_FOOT, MAX_ROWS, PERIOD_HEAD, SOURCE_LINE, TIME_NAME, ParseError, col_type, is_period,
                              month_year, read_value, strip_foot, to_number)

GENERIC = re.compile(r"^Column \d+$")
SOURCE_KEY = re.compile(r"^\s*(source|sources|source of data|data source|quelle|bron|fuente|fonte)\s*:?\s*$", re.I)
AREA_NAME = re.compile(r"geo|country|countries|area|location|member state|nation|pays|land|staat|economy|reporter", re.I)


def _get(row, j):
    if j is None or j >= len(row):
        return ""
    v = row[j]
    return "" if v is None else v


def clean_id(v):
    if isinstance(v, str):
        v = re.sub(r"\s+", " ", ID_FOOT.sub("", v)).strip()
    return v


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def level_key(grid, row_i, col, floor):
    if row_i >= len(grid):
        return ""
    row = grid[row_i]
    for j in range(col, floor - 1, -1):
        v = _text(_get(row, j))
        if v:
            return strip_foot(v)
    return ""


def _keys(grid, b):
    if not b.wide:
        return []
    levels = b.wide.levels
    if not levels:
        return [(strip_foot(v.name.strip()),) for v in b.value_columns]
    rows = b.header_rows[-len(levels):]
    floor = min(v.index for v in b.value_columns)
    out = []
    for v in b.value_columns:
        key = tuple(level_key(grid, r, v.index, floor) for r in rows)
        if len(rows) < len(levels):
            parts = v.name.split(" ", len(levels) - 1)
            key = tuple(parts + [""] * (len(levels) - len(parts)))
        out.append(key)
    return out


def _note_like(row, ncols):
    cells = [c for c in row if c != "" and c is not None]
    if len(cells) != 1 or ncols < 3:
        return False
    c = cells[0]
    return isinstance(c, str) and to_number(c, False) is None


def _serial_dates(name, vals):
    if not TIME_NAME.search(name):
        return None
    nums = [v for v in vals if v != "" and v is not None]
    if not nums or not all(isinstance(v, int) and 20000 <= v <= 60000 for v in nums):
        return None
    base = dt.date(1899, 12, 30)
    return [(base + dt.timedelta(days=v)).isoformat() if isinstance(v, int) else "" for v in vals]


def _months(vals):
    filled = [v for v in vals if v != "" and v is not None]
    if not filled:
        return None
    conv = [month_year(v) if isinstance(v, str) else None for v in filled]
    if sum(1 for c in conv if c) < 0.9 * len(filled):
        return None
    return [(month_year(v) or _text(v)) if v != "" and v is not None else "" for v in vals]


def _short(name):
    s = re.split(r"\s+(in|by|of|per|selon|nach|par)\s+", name.strip(), maxsplit=1, flags=re.I)[0]
    return s.lower()


def _noun(name, k):
    if AREA_NAME.search(name):
        return f"{k} areas"
    if re.search(r"r[eé]gion|province|nuts|d[eé]partement|bundesland|county|state", name, re.I):
        return f"{k} regions"
    if re.search(r"sector|nace|industr|wirtschaftszweig|branche", name, re.I):
        return f"{k} sectors"
    return f"{k} {name} values"


def summarize(grid, recipe):
    blocks = recipe.blocks
    parts = []
    labels = list(dict.fromkeys(b.label.column for b in blocks if b.label))
    if len(blocks) > 1:
        if len(labels) == 1:
            parts.append(f"{len(blocks)} tables by {_short(labels[0])}")
        else:
            parts.append(f"{len(blocks)} tables stacked")
    cands = [c for c in (blocks[0].id_columns if blocks else []) if not TIME_NAME.search(c.name)]
    cands.sort(key=lambda c: 0 if AREA_NAME.search(c.name) else 1)
    for first in cands:
        seen = set()
        for b in blocks:
            col = next((c.index for c in b.id_columns if c.name == first.name), None)
            if col is None:
                continue
            for i in range(b.data_start, min(b.data_end, len(grid) - 1) + 1):
                v = clean_id(_get(grid[i], col))
                if v != "" and i not in b.header_rows:
                    seen.add(_text(v))
        if len(seen) > 1:
            parts.append(_noun(first.name, len(seen)))
            break
    wide = next((b for b in blocks if b.wide), None)
    if wide:
        keys = list(zip(*_keys(grid, wide))) if wide.value_columns else []
        names = wide.wide.levels or [wide.wide.name]
        for name, ks in zip(names, keys):
            ks = set(k for k in ks if k)
            if all(re.fullmatch(r"\d{4}", k) for k in ks):
                parts.append(f"{len(ks)} years")
            elif all(is_period(k) for k in ks):
                parts.append(f"{len(ks)} periods")
            else:
                parts.append(f"{len(ks)} {name.lower()} values")
    else:
        nv = max((len(b.value_columns) for b in blocks), default=0)
        if nv:
            parts.append(f"{nv} number column" + ("s" if nv > 1 else ""))
    if any(v.flag_index is not None for b in blocks for v in b.value_columns):
        parts.append("flags kept")
    if recipe.aggregates:
        parts.append(f"{len(recipe.aggregates)} total" + ("s" if len(recipe.aggregates) > 1 else "") + " marked")
    s = ", ".join(parts) or "1 table"
    return s[0].upper() + s[1:]


def _source(grid, recipe):
    spans = [(b.data_start, b.data_end) for b in recipe.blocks]
    for n in recipe.notes:
        m = SOURCE_LINE.match(n)
        if m:
            return m.group(2).strip().rstrip(".")[:120]
    idx = list(range(min(60, len(grid)))) + list(range(max(60, len(grid) - 40), len(grid)))
    for i in idx:
        if any(a <= i <= z for a, z in spans):
            continue
        row = grid[i]
        for j, c in enumerate(row):
            if not isinstance(c, str) or not c:
                continue
            m = SOURCE_LINE.match(c)
            if m:
                return m.group(2).strip().rstrip(".")[:120]
            if j == 0 and SOURCE_KEY.match(c):
                nxt = next((x for x in row[1:] if isinstance(x, str) and x.strip()), "")
                if nxt:
                    return nxt.strip().rstrip(".")[:120]
    return ""


def execute(grid, recipe):
    if isinstance(recipe, dict):
        recipe = Recipe.model_validate(recipe)
    if not grid:
        raise ParseError("The file has no data")
    missing = {m.strip().lower() for m in recipe.missing_markers} | {""}
    comma = recipe.decimal == ","
    order, kinds, recs = [], {}, []
    bad = total = 0
    melted = set()
    truncated = False

    def add(name, kind):
        if name not in kinds:
            order.append(name)
            kinds[name] = kind

    n = len(grid)
    for b in recipe.blocks:
        multi = len(b.value_columns) > 1 and not b.wide
        if b.label:
            add(b.label.column, "label")
        if b.wide:
            for c in b.id_columns:
                add(c.name, "id")
        else:
            items = sorted([(c.index, 0, c) for c in b.id_columns] + [(v.index, 1, v) for v in b.value_columns], key=lambda x: (x[0], x[1]))
            for _, k, o in items:
                if k == 0:
                    add(o.name, "id")
                else:
                    add(o.name, "value")
                    if o.flag_index is not None:
                        add(o.name + "_flag" if multi else "flag", "flag")
        keys = _keys(grid, b)
        levels = (b.wide.levels or [b.wide.name]) if b.wide else []
        if b.wide:
            for lv in levels:
                add(lv, "key")
            add("Value", "value")
            if any(v.flag_index is not None for v in b.value_columns):
                add("flag", "flag")
        skip = set(b.header_rows)
        id_names = [c.name for c in b.id_columns]
        used = [c.index for c in b.id_columns] + [v.index for v in b.value_columns]
        ncols = len(used)
        for i in range(b.data_start, min(b.data_end, n - 1) + 1):
            if i in skip:
                continue
            row = grid[i]
            if all(_get(row, j) == "" for j in used):
                continue
            if _note_like(row, ncols) and _get(row, b.id_columns[0].index if b.id_columns else 0) == "":
                continue
            ids = [clean_id(_get(row, c.index)) for c in b.id_columns]
            filled = [(x, nm) for x, nm in zip(ids, id_names) if x != ""]
            if filled and all(_text(x) == nm for x, nm in filled) and len(filled) >= max(1, len(ids) // 2 + (len(ids) == 1)):
                if all(read_value(_get(row, v.index), comma, missing)[0] is None for v in b.value_columns):
                    continue
            base = {}
            if b.label:
                base[b.label.column] = b.label.value
            for nm, x in zip(id_names, ids):
                base[nm] = x
            vals = []
            for v in b.value_columns:
                raw = _get(row, v.index)
                x, inflag = read_value(raw, comma, missing)
                total += 1
                if x is None and not inflag and _text(raw).lower() not in missing and not (isinstance(raw, str) and raw.strip() == ""):
                    bad += 1
                if v.flag_index is not None and v.flag_index != v.index:
                    fl = _text(_get(row, v.flag_index))
                    fl = "" if fl.lower() in (":",) else fl
                else:
                    fl = inflag
                vals.append((v, x, fl))
            if b.wide:
                for (v, x, fl), key in zip(vals, keys):
                    if x is None:
                        continue
                    rec = dict(base)
                    for lv, k in zip(levels, key):
                        rec[lv] = k
                    rec["Value"] = x
                    if v.flag_index is not None:
                        rec["flag"] = fl
                    melted.add(key)
                    recs.append(rec)
            else:
                rec = base
                for v, x, fl in vals:
                    rec[v.name] = x
                    if v.flag_index is not None:
                        rec[v.name + "_flag" if multi else "flag"] = fl
                recs.append(rec)
            if len(recs) > MAX_ROWS:
                truncated = True
                break
        if truncated:
            break
    recs = recs[:MAX_ROWS]
    cols, types, conv = [], [], {}
    for name in order:
        vals = [r.get(name) for r in recs]
        kind = kinds[name]
        if kind == "value":
            if all(v is None for v in vals) and name != "Value":
                continue
            cols.append(name)
            types.append("number")
            conv[name] = vals
            continue
        texts = [("" if v is None else v) for v in vals]
        if all(t == "" for t in texts):
            continue
        if kind == "flag":
            cols.append(name)
            types.append("category")
            conv[name] = [_text(t) for t in texts]
            continue
        if kind == "key":
            ks = [_text(t) for t in texts]
            mm = _months(ks)
            if mm:
                ks = mm
            filled = [k for k in ks if k]
            t = "time" if filled and all(is_period(k) or PERIOD_HEAD.match(k) for k in filled) else "category"
            cols.append(name)
            types.append(t)
            conv[name] = ks
            continue
        ser = _serial_dates(name, texts)
        if ser:
            cols.append(name)
            types.append("time")
            conv[name] = ser
            continue
        mm = _months(texts)
        if mm:
            cols.append(name)
            types.append("time")
            conv[name] = mm
            continue
        raw_vals = [t for t in texts if t != ""]
        nums = [to_number(t, comma) for t in raw_vals]
        t = col_type(name, raw_vals, nums)
        cols.append(name)
        types.append(t)
        if t == "number":
            conv[name] = [to_number(x, comma) if x != "" else None for x in texts]
        else:
            conv[name] = [_text(x) if not isinstance(x, str) else x for x in texts]
    if not cols or not recs:
        raise ParseError("Found a header but no rows of data")
    rows = [[conv[c][i] for c in cols] for i in range(len(recs))]
    units = {b.unit for b in recipe.blocks}
    unit = units.pop() if len(units) == 1 else None
    cols_out = []
    for j, name in enumerate(cols):
        vals = [r[j] for r in rows if r[j] is not None and r[j] != ""]
        info = {"name": name, "type": types[j], "distinct": len(set(map(str, vals))),
                "samples": list(dict.fromkeys(str(v) for v in vals))[:3]}
        if types[j] == "number" and vals:
            info["min"] = min(vals)
            info["max"] = max(vals)
        if kinds[name] == "value" and unit:
            info["unit"] = unit
        cols_out.append(info)
    present = set()
    for j, name in enumerate(cols):
        if kinds[name] in ("id", "label", "key") and types[j] != "number":
            present.update(conv[name])
    aggregates = [a for a in recipe.aggregates if a in present]
    notes = [x for x in recipe.notes if not SOURCE_LINE.match(x)][:5]
    if types and all(t != "number" for t in types):
        notes = (notes + ["No column of numbers found, charts will count rows"])[:5]
    issues, conf = [], 1.0
    if total and bad:
        issues.append(f"{bad} value cell" + ("s" if bad > 1 else "") + " could not be read as numbers")
        conf -= min(0.4, 2 * bad / total)
    generic = [c for c in cols if GENERIC.match(c)]
    if generic:
        issues.append(", ".join(generic[:3]) + (" has" if len(generic) == 1 else " have") + " no header name")
        conf -= min(0.3, 0.1 * len(generic))
    for b in recipe.blocks:
        if b.data_end >= n:
            issues.append("A block ends past the last row")
            conf -= 0.1
            break
    reading = {"summary": summarize(grid, recipe), "confidence": round(max(0.0, min(1.0, conf)), 2),
               "recipe": recipe.model_dump(), "alternatives": [], "issues": issues}
    return {"columns": cols_out, "rows": rows, "n_rows": len(rows), "truncated": truncated, "melted": len(melted),
            "source_hint": _source(grid, recipe), "notes": notes, "aggregates": aggregates, "sheet": recipe.sheet,
            "reading": reading}
