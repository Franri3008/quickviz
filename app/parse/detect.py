import math
import re

from app.parse.execute import clean_id, level_key, summarize
from app.parse.recipe import DEFAULT_MISSING, Block, IdColumn, Label, Recipe, ValueColumn, Wide
from app.parse.values import (FLAG_TOKEN, PLAIN, MAX_COLS, SOURCE_LINE, TIME_NAME, ParseError, comma_votes, is_period, nonempty,
                              read_value, strip_foot, to_number)

MISS = {m.lower() for m in DEFAULT_MISSING} | {""}
KIND_MISS = MISS - {"x", "c", "na", "none", "null", "nan"}
TIME_DIM = re.compile(r"^(time|time_period|time period|year|years|period|jahr|jahre|année|annee|période|periode|jaar|date)$|\\", re.I)
LABEL_SUFFIX = re.compile(r"\s*\((labels|codes|label|code)\)\s*$", re.I)
UNIT_KEY = re.compile(r"^(unit|units|unit of measure|unité|unite|einheit|maßeinheit|measure|unidad|unità)\b", re.I)
SEX_WORDS = {"men", "women", "male", "female", "males", "females", "total", "both sexes", "m", "f", "t", "man", "woman",
             "hommes", "femmes", "ensemble", "männer", "frauen", "insgesamt", "mannen", "vrouwen", "totaal", "sex: total",
             "sex: male", "sex: female"}
LEGEND = re.compile(r"^(special value|available flags:?|flags?:?|special values:?|zeichenerklärung.*|_+|-+|\s*)$", re.I)
AGG_RE = re.compile(
    r"^(eu|eu-?\d{2}(_\d{4})?|ea|ea-?\d{2}(_\d{4})?|efta|euro ?area\b.*|european union\b.*|eurozone.*|oecd\b.*|world|g7|g20|"
    r"total|.*\btotal\b.*|.*\b(insgesamt|gesamt|ensemble|totaal|totale|zusammen)\b.*|all|all\b.*|grand total|both sexes|_t|"
    r"[a-u]-[a-u](_.*)?|.*\bincome\b.*|.*& (pacific|caribbean|central asia|north africa).*|.*\bmembers\b.*|.*small states|"
    r"arab world|.*\(excluding .*|.*\bida\b.*|.*\bibrd\b.*|sub-saharan africa.*|north america|south asia.*|latin america.*|"
    r"middle east.*|central europe and the baltics|africa (eastern|western) and .*|europe & central asia.*|east asia.*|"
    r"fragile and conflict.*|heavily indebted.*|least developed.*|.*demographic dividend|not classified)$", re.I)


TOTAL_WORD = re.compile(r"\b(total|insgesamt|gesamt|ensemble|totaal|totale)\b", re.I)


def _cell(grid, i, j):
    row = grid[i]
    if j >= len(row):
        return ""
    v = row[j]
    return "" if v is None else v


def kind(c):
    if c == "" or c is None:
        return "E"
    if isinstance(c, bool):
        return "T"
    if isinstance(c, (int, float)):
        if isinstance(c, float) and not math.isfinite(c):
            return "E"
        return "P" if is_period(c) else "N"
    s = c.strip()
    low = s.lower()
    if not s:
        return "E"
    if PLAIN.match(s):
        if "." not in s and len(s) == 4 and 1800 <= int(s) <= 2100:
            return "P"
        return "N"
    if low in KIND_MISS:
        return "M"
    if FLAG_TOKEN.match(s) and (s.strip("()").islower() or len(s.strip("()")) == 1):
        return "F"
    if is_period(s):
        return "P"
    v, fl = read_value(s, False, MISS)
    if v is None:
        v, fl = read_value(s, True, MISS)
    if v is not None:
        return "N"
    if fl:
        return "M"
    return "T"


class Rows:
    def __init__(self, grid):
        self.grid = grid
        self.n = len(grid)
        self.w = min(MAX_COLS, max((len(r) for r in grid), default=0))
        self.cache = {}

    def kinds(self, i):
        k = self.cache.get(i)
        if k is None:
            row = self.grid[i]
            k = [kind(row[j]) if j < len(row) else "E" for j in range(self.w)]
            self.cache[i] = k
        return k

    def blank(self, i):
        return all(k == "E" for k in self.kinds(i))

    def count(self, i, kinds):
        return sum(1 for k in self.kinds(i) if k in kinds)

    def filled(self, i):
        return [j for j, k in enumerate(self.kinds(i)) if k != "E"]

    def data_like(self, i):
        return self.count(i, "NM") >= 1

    def header_like(self, i):
        return self.count(i, "NM") == 0 and self.count(i, "TPF") >= 1

    def text(self, i):
        return tuple(str(_cell(self.grid, i, j)).strip() for j in range(self.w))


def _num_cols(R, start, end):
    cols = set()
    for i in range(start, min(end, start + 30, R.n - 1) + 1):
        if R.blank(i):
            break
        for j, k in enumerate(R.kinds(i)):
            if k in "NM":
                cols.add(j)
    return cols


def _find_header(R, start, stop):
    nc = _num_cols(R, start, start + 30)
    up, r = [], start - 1
    while r > stop and len(up) < 6 and not R.blank(r) and R.header_like(r):
        up.append(r)
        r -= 1
    while len(up) >= 2 and len(R.filled(up[0])) >= 2 and not any(j in nc for j in R.filled(up[0])) \
            and sum(1 for j in R.filled(up[1]) if j in nc) >= 2:
        up = up[1:]
    acc = []
    for k, r in enumerate(up):
        cells = R.filled(r)
        in_nc = sum(1 for j in cells if j in nc)
        if k == 0:
            acc.append(r)
            continue
        if in_nc >= 2 or (0 not in cells and in_nc >= 1):
            acc.append(r)
        else:
            break
    group = None
    if len(acc) >= 2 and len(R.filled(acc[0])) == 1:
        j = R.filled(acc[0])[0]
        corner = str(_cell(R.grid, acc[1], j)).strip()
        if j not in nc and corner and not TIME_DIM.search(corner):
            group = acc[0]
            acc = acc[1:]
    if len(acc) == 1 and len(R.filled(acc[0])) == 1 and len(_num_cols(R, start, start + 5)) >= 2:
        return [], group
    return list(reversed(acc)), group


def _extend(R, start, headers):
    htext = {R.text(h) for h in headers}
    numeric, textual = set(), set()
    for j, k in enumerate(R.kinds(start)):
        if k in "NMP":
            numeric.add(j)
        elif k in "TF":
            textual.add(j)
    end = start
    i = start + 1
    while i < R.n:
        if R.blank(i):
            break
        ks = R.kinds(i)
        if R.text(i) in htext:
            break
        cells = [j for j, k in enumerate(ks) if k != "E"]
        if len(cells) == 1 and ks[cells[0]] == "T" and R.w >= 3:
            break
        bad = sum(1 for j, k in enumerate(ks) if k == "T" and j in numeric and j not in textual)
        has_num = any(k in "NM" for k in ks)
        if has_num:
            if bad > (1 if len(cells) >= 4 else 0):
                break
        else:
            if bad:
                break
            if len(cells) < 2:
                nxt = i + 1
                if not (cells and cells[0] in textual and R.w <= 2 and nxt < R.n and not R.blank(nxt) and R.data_like(nxt)):
                    break
        for j, k in enumerate(ks):
            if k in "NMP":
                numeric.add(j)
            elif k == "T" and j not in numeric:
                textual.add(j)
        end = i
        i += 1
    return end


def _runs(R):
    runs, i = [], 0
    while i < R.n:
        if R.blank(i) or not R.data_like(i):
            i += 1
            continue
        stop = runs[-1]["end"] if runs else -1
        headers, group = _find_header(R, i, stop)
        end = _extend(R, i, headers)
        start = i
        if headers and group is None and headers[-1] < i - 1:
            start = headers[-1] + 1
        runs.append({"start": start, "end": end, "headers": headers, "group": group})
        i = end + 1
    return runs


def _profile(R, rows, j):
    c = {"N": 0, "P": 0, "M": 0, "F": 0, "T": 0, "E": 0}
    for i in rows:
        c[R.kinds(i)[j]] += 1
    return c


def _clean_name(s):
    s = re.sub(r"\s+", " ", strip_foot(str(s).strip()))
    return LABEL_SUFFIX.sub("", s).strip()


def _header_parts(R, headers, j, value_cols, first_val):
    parts = []
    for r in headers:
        v = _cell(R.grid, r, j)
        if (v == "" or v is None) and j in value_cols and r != headers[-1]:
            v = level_key(R.grid, r, j, first_val)
        parts.append(_clean_name(v) if v not in ("", None) else "")
    return parts


def _dedupe(parts):
    out = []
    for p in parts:
        if p and (not out or out[-1] != p):
            out.append(p)
    return out


def _period_name(keys):
    keys = [k for k in keys if k]
    if keys and all(re.fullmatch(r"\d{4}", k) for k in keys):
        return "Year"
    return "Period"


def _level_name(keys):
    low = {k.lower() for k in keys if k}
    if low and low <= SEX_WORDS:
        return "Sex"
    return "Category"


def _columns(R, run, info):
    headers = run["headers"]
    rows = [i for i in range(run["start"], run["end"] + 1)]
    sample = rows if len(rows) <= 3000 else rows[:2000] + rows[-500:]
    prof = {j: _profile(R, sample, j) for j in range(R.w)}
    numeric, ids, flags, dropped, mixed = [], [], {}, [], []
    for j in range(R.w):
        p = prof[j]
        filled = p["N"] + p["P"] + p["T"] + p["F"]
        if filled == 0:
            continue
        nums = p["N"] + p["P"]
        if nums and nums >= 0.8 * (nums + p["T"]):
            numeric.append(j)
            if p["T"]:
                mixed.append(j)
        else:
            ids.append(j)
            if nums and nums >= 0.2 * (nums + p["T"]):
                mixed.append(j)
    first_val = min(numeric) if numeric else 0
    names = {}
    const_rows = []
    vcols = set(numeric)
    if headers and len(numeric) >= 2:
        for r in headers[:-1] if len(headers) > 1 else []:
            vals = [str(level_key(R.grid, r, j, first_val)).strip() for j in numeric]
            if len(set(vals)) == 1 and vals[0] and not is_period(vals[0]):
                const_rows.append(r)
    use_headers = [r for r in headers if r not in const_rows]
    for j in range(R.w):
        parts = _header_parts(R, use_headers, j, vcols, first_val) if use_headers else []
        if j not in vcols and len(use_headers) > 1:
            kept = []
            for r, p in zip(use_headers, parts):
                periods = sum(1 for jj in numeric if is_period(level_key(R.grid, r, jj, first_val)))
                if p and TIME_DIM.search(p) and periods >= 1 and any(q for q in parts if q and q != p):
                    continue
                kept.append(p)
            parts = kept
        names[j] = " ".join(_dedupe(parts))
    for j in range(R.w):
        p = prof[j]
        if j in numeric or p["N"] + p["P"] + p["T"] + p["F"] == 0:
            continue
        if not names[j] and p["F"] >= 1 and p["T"] == 0 and j - 1 in numeric:
            flags[j - 1] = j
            ids.remove(j)
    value_cols, id_cols = [], []
    for j in numeric:
        p = prof[j]
        name = names[j]
        if not name and j == 0 and p["T"] == 0:
            vals = [to_number(_cell(R.grid, i, j), False) for i in rows[:200]]
            if all(isinstance(v, int) for v in vals) and vals and vals == list(range(vals[0], vals[0] + len(vals))):
                dropped.append(j)
                continue
        if is_period(name):
            value_cols.append(j)
            continue
        if p["N"] == 0:
            vals = [str(_cell(R.grid, i, j)) for i in sample if _cell(R.grid, i, j) != ""]
            if TIME_NAME.search(name or "") or len(set(vals)) < len(vals) * 0.9 + 2:
                id_cols.append(j)
                continue
        if TIME_NAME.search(name or "") and p["N"] + p["P"] > 0:
            id_cols.append(j)
            continue
        value_cols.append(j)
    id_cols = sorted(set(id_cols) | set(ids))
    for j in id_cols:
        if not names[j]:
            names[j] = f"Column {j + 1}"
    for j in value_cols:
        if not names[j]:
            names[j] = f"Column {j + 1}"
    inflag = set()
    for j in value_cols:
        if j in flags:
            continue
        hits = 0
        for i in sample[:3000]:
            c = _cell(R.grid, i, j)
            if isinstance(c, str) and c:
                v, fl = read_value(c, info["comma"], MISS)
                if fl:
                    hits += 1
                    break
        if hits:
            inflag.add(j)
    units = []
    for r in const_rows:
        u = str(level_key(R.grid, r, numeric[0], first_val)).strip()
        if u:
            units.append(u)
    return {"names": names, "ids": id_cols, "values": value_cols, "flags": flags, "inflag": inflag, "mixed": mixed,
            "const_rows": const_rows, "use_headers": use_headers, "units": units, "dropped": dropped}


def _wide(R, run, cols):
    vals = cols["values"]
    names = cols["names"]
    hdr = cols["use_headers"]
    per = [j for j in vals if is_period(names[j])]
    if not hdr or len(vals) < 2:
        return None, [], per
    if len(hdr) >= 2:
        rows = hdr[-2:]
        first_val = min(vals)
        k0 = [str(level_key(R.grid, rows[0], j, first_val)).strip() for j in vals]
        k1 = [str(level_key(R.grid, rows[1], j, first_val)).strip() for j in vals]
        k0 = [strip_foot(k) for k in k0]
        k1 = [strip_foot(k) for k in k1]
        if all(k0) and all(k1) and len(set(k0)) > 1 and len(set(k1)) > 1 and len(set(zip(k0, k1))) == len(vals):
            if all(is_period(k) for k in k0):
                return Wide(name=_period_name(k0), levels=[_period_name(k0), _level_name(k1)]), vals, per
            if all(is_period(k) for k in k1):
                return Wide(name=_period_name(k1), levels=[_level_name(k0), _period_name(k1)]), vals, per
    dim = any(TIME_DIM.search(str(_cell(R.grid, r, j)).strip()) for r in hdr for j in cols["ids"][:1])
    if len(per) >= 3 or (len(per) >= 2 and (dim or len(per) == len(vals))):
        return Wide(name=_period_name([names[j] for j in per])), per, per
    return None, [], per


def _label_line(R, top, floor):
    r = top - 1
    while r > floor and R.blank(r):
        r -= 1
    if r <= floor:
        return None
    cells = R.filled(r)
    if not cells or len(cells) > 2 or cells[0] > 1:
        return None
    a = str(_cell(R.grid, r, cells[0])).strip()
    if len(cells) == 2:
        b = str(_cell(R.grid, r, cells[1])).strip()
        if not a or not b:
            return None
        return r, a.rstrip(":").strip(), b
    if ":" in a:
        k, v = a.split(":", 1)
        if k.strip() and v.strip() and len(k) <= 60:
            return r, k.strip(), v.strip()
    return r, "", a


def _decimal(R, runs, value_sets):
    vals = []
    for run, vs in zip(runs, value_sets):
        for i in range(run["start"], min(run["end"], run["start"] + 400) + 1):
            for j in vs:
                c = _cell(R.grid, i, j)
                if isinstance(c, str) and c:
                    vals.append(c)
    comma, dot = comma_votes(vals)
    sep = getattr(R.grid, "sep", "")
    dec = "," if comma > dot or (comma == dot and sep == ";") else "."
    th = ""
    joined = [v.strip() for v in vals[:2000]]
    if any(re.search("\\d[    ]\\d{3}", v) for v in joined):
        th = " "
    elif dec == "," and any(re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+(,\d+)?", v) for v in joined):
        th = "."
    elif dec == "." and any(re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", v) for v in joined):
        th = ","
    return dec, th


def _decimals(vals):
    d = 0
    for v in vals:
        if isinstance(v, float):
            s = repr(v)
            if "." in s and "e" not in s:
                d = max(d, len(s.split(".")[1]))
    return min(d, 6)


def _sum_aggs(matrix):
    n = len(matrix)
    if n < 3 or n > 2000 or not matrix[0]:
        return set()
    keep = []
    for c in range(len(matrix[0])):
        col = [row[c] for row in matrix if row[c] is not None]
        if col and not all(isinstance(v, int) and abs(v) <= 10 for v in col):
            keep.append(c)
    if not keep:
        return set()
    matrix = [[row[c] for c in keep] for row in matrix]
    m = len(keep)
    dec = [_decimals([row[c] for row in matrix]) for c in range(m)]

    def match(a_row, idx):
        comp = ok = 0
        for c in range(m):
            a = a_row[c]
            parts = [matrix[i][c] for i in idx]
            if a is None or any(p is None for p in parts):
                continue
            comp += 1
            tol = 0.5 * 10 ** (-dec[c]) * (len(parts) + 1) + 1e-9
            if a > 0 and abs(a - sum(parts)) <= tol:
                ok += 1
        need = 2 if m >= 2 else 1
        return comp > 0 and ok >= max(need, math.ceil(comp / 2))

    aggs = set()
    for r in range(n if m >= 2 else 0):
        for k in range(2, min(30, n - 1) + 1):
            down = list(range(r + 1, r + 1 + k))
            if down[-1] < n and not (aggs & set(down)) and match(matrix[r], down):
                aggs.add(r)
                break
            up = list(range(r - k, r))
            if up[0] >= 0 and not (aggs & set(up)) and match(matrix[r], up):
                aggs.add(r)
                break
    rest = [i for i in range(n) if i not in aggs]
    for r in range(n):
        if r in aggs:
            continue
        others = [i for i in rest if i != r]
        if len(others) >= 2 and match(matrix[r], others):
            aggs.add(r)
    return aggs


def _aggregates(R, blocks, comma):
    found = []
    failed = 0
    for b in blocks:
        rows = [i for i in range(b.data_start, b.data_end + 1) if i not in b.header_rows and not R.blank(i)]
        id_text = [c for c in b.id_columns if not TIME_NAME.search(c.name)]
        cols = {}
        for c in id_text:
            vals = [clean_id(_cell(R.grid, i, c.index)) for i in rows]
            cols[c.index] = [v if isinstance(v, str) else str(v) for v in vals]
        primary = id_text[0].index if id_text else None
        for j, vals in cols.items():
            distinct = set(v for v in vals if v)
            if len(distinct) > 5000:
                continue
            hits = {v for v in distinct if AGG_RE.match(v)}
            for v in hits:
                if v not in found:
                    found.append(v)
                if primary is not None and j != primary:
                    pv = {cols[primary][k] for k, x in enumerate(vals) if x == v}
                    if len(pv) == 1:
                        p = next(iter(pv))
                        back = {vals[k] for k, x in enumerate(cols[primary]) if x == p}
                        if back == {v} and p and p not in found:
                            found.append(p)
        if b.wide and b.wide.levels and b.value_columns:
            floor = min(v.index for v in b.value_columns)
            for r in b.header_rows[-len(b.wide.levels):]:
                for v in b.value_columns:
                    key = strip_foot(str(level_key(R.grid, r, v.index, floor)).strip())
                    if key and AGG_RE.match(key) and key not in found:
                        found.append(key)
        if b.label and AGG_RE.match(b.label.value) and b.label.value not in found:
            found.append(b.label.value)
        prim = cols.get(primary, [])
        if primary is not None and b.value_columns and len(rows) <= 2000 and len(set(prim)) == len(prim):
            matrix = [[read_value(_cell(R.grid, i, v.index), comma, MISS)[0] for v in b.value_columns] for i in rows]
            sums = _sum_aggs(matrix)
            for r in sums:
                p = cols[primary][r]
                if p and p not in found:
                    found.append(p)
            ints = all(isinstance(x, int) for row in matrix for x in row if x is not None)
            for r, p in enumerate(prim):
                if ints and TOTAL_WORD.search(p) and r not in sums and len(rows) >= 3:
                    failed += 1
    return found, failed


def _fallback(R):
    head = [i for i in range(min(R.n, 60)) if not R.blank(i)]
    if not head:
        raise ParseError("The file has no data")
    width = max(len(R.filled(i)) for i in head)
    need = max(2, math.ceil(width * 0.5)) if width >= 2 else 1
    h = next((i for i in head if len(R.filled(i)) >= need), head[0])
    last = max(i for i in range(R.n) if not R.blank(i))
    cols = [j for j in range(R.w) if any(_cell(R.grid, i, j) != "" for i in range(h + 1, min(R.n, h + 3000)))]
    if last <= h or not cols:
        raise ParseError("Found a header but no rows of data")
    names, seen = [], {}
    for j in cols:
        nm = _clean_name(_cell(R.grid, h, j)) or f"Column {j + 1}"
        if nm in seen:
            seen[nm] += 1
            nm = f"{nm} ({seen[nm]})"
        else:
            seen[nm] = 1
        names.append(nm)
    return Block(header_rows=[h], data_start=h + 1, data_end=last,
                 id_columns=[IdColumn(index=j, name=nm) for j, nm in zip(cols, names)])


def _unique(names):
    seen, out = {}, []
    for nm in names:
        if nm in seen:
            seen[nm] += 1
            out.append(f"{nm} ({seen[nm]})")
        else:
            seen[nm] = 1
            out.append(nm)
    return out


def _block(run, cols, wide, wide_cols, label=None, unit=None):
    names = cols["names"]
    if wide:
        vals = wide_cols
        ids = sorted(set(cols["ids"]) | (set(cols["values"]) - set(vals)))
    else:
        vals = cols["values"]
        ids = cols["ids"]
    allnames = _unique([names[j] for j in ids] + [names[j] for j in vals])
    idn, vn = allnames[:len(ids)], allnames[len(ids):]
    vcs = []
    for j, nm in zip(vals, vn):
        fi = cols["flags"].get(j)
        if fi is None and j in cols["inflag"]:
            fi = j
        vcs.append(ValueColumn(index=j, name=nm, flag_index=fi))
    return Block(header_rows=run["headers"], data_start=run["start"], data_end=run["end"], label=label,
                 id_columns=[IdColumn(index=j, name=nm) for j, nm in zip(ids, idn)], value_columns=vcs, wide=wide, unit=unit)


def _signature(b):
    return (tuple(c.name for c in b.id_columns), tuple(v.name for v in b.value_columns), bool(b.wide))


def _notes(R, after, used):
    notes = []
    for i in range(after + 1, R.n):
        if i in used or R.blank(i):
            continue
        cells = R.filled(i)
        if len(cells) != 1:
            continue
        t = str(_cell(R.grid, i, cells[0])).strip()
        if len(t) < 3 or LEGEND.match(t):
            continue
        notes.append(t[:300])
        if len(notes) >= 8:
            break
    return notes


def _meta(R, top):
    unit, source = None, None
    for i in range(0, max(0, top)):
        cells = R.filled(i)
        if not cells or cells[0] != 0:
            continue
        a = str(_cell(R.grid, i, 0)).strip()
        b = str(_cell(R.grid, i, cells[1])).strip() if len(cells) >= 2 else ""
        if not b and ":" in a:
            a, b = a.split(":", 1)
            a, b = a.strip(), b.strip()
        if UNIT_KEY.match(a) and b and len(b) < 120:
            unit = b
        if SOURCE_LINE.match(f"{a}: {b}") and b and not source:
            source = f"Source: {b}"
    return unit, source


def _echo(R, run, cols, used_rows):
    key = lambda i: tuple(str(_cell(R.grid, i, j)).strip() for j in cols["ids"])
    seen = {key(i) for i in used_rows if not R.blank(i)}
    rows = [i for i in range(run["start"], run["end"] + 1) if not R.blank(i)]
    empty = all(str(_cell(R.grid, i, j)).strip() in ("", "0") for i in rows for j in cols["values"])
    return bool(rows) and empty and all(key(i) in seen for i in rows)


def _build(R, info, runs, include_wide=True, only=None):
    blocks, issues, penalty = [], [], 0.0
    prev, prev_cols, prev_wide, prev_wcols = None, None, None, None
    used_rows = set()
    for k, run in enumerate(runs):
        if only is not None and k not in only:
            continue
        if not run["headers"]:
            if prev is not None and run["start"] - prev["end"] <= 4:
                nc = _num_cols(R, run["start"], run["end"])
                vset = set(prev_cols["values"])
                texty = {j for i in range(run["start"], run["end"] + 1) for j, kk in enumerate(R.kinds(i)) if kk == "T"}
                if nc & vset and nc <= vset | set(prev_cols["flags"].values()) | set(prev_cols["ids"]) and not texty & vset:
                    if _echo(R, run, prev_cols, used_rows):
                        run["ignored"] = True
                        continue
                    cont = dict(run, headers=prev["headers"])
                    used_rows.update(range(run["start"], run["end"] + 1))
                    blocks.append(_block(cont, prev_cols, prev_wide, prev_wcols))
                    run["cols"] = prev_cols
                    run["head"] = prev.get("head", prev)
                    prev = run
                    continue
            if run["end"] - run["start"] < 2 or blocks:
                run["ignored"] = True
                continue
        cols = _columns(R, run, info)
        used_rows.update(range(run["start"], run["end"] + 1))
        wide, wcols, per = _wide(R, run, cols) if include_wide else (None, [], [])
        run["cols"], run["wide"], run["per"] = cols, wide, per
        blocks.append(_block(run, cols, wide, wcols))
        prev, prev_cols, prev_wide, prev_wcols = run, cols, wide, wcols
    return blocks


def _assemble(R, runs, info, include_wide=True, only=None):
    blocks = _build(R, info, runs, include_wide, only)
    if not blocks:
        return None
    sig0 = _signature(blocks[0])
    same = [b for b in blocks if _signature(b) == sig0]
    differs = len(same) != len(blocks)
    if differs:
        blocks = same
    tops = []
    floor = -1
    chosen_runs = [r for r in runs if not r.get("ignored") and "cols" in r]
    starts = {b.data_start for b in blocks}
    labels = []
    for r in chosen_runs:
        if r["start"] not in starts:
            floor = r["end"]
            continue
        top = r["headers"][0] if r["headers"] and r["headers"][0] < r["start"] else r["start"]
        if r.get("group") is not None:
            g = r["group"]
            labels.append((g, "", str(_cell(R.grid, g, R.filled(g)[0])).strip()))
        else:
            labels.append(_label_line(R, top, floor))
        tops.append(top)
        floor = r["end"]
    orphan = any(r.get("head") is not None and r["head"].get("group") is None for r in chosen_runs if r["start"] in starts)
    if len(blocks) > 1 and all(labels) and len(labels) == len(blocks) and not orphan:
        keys = {lab[1] for lab in labels}
        key = keys.pop() if len(keys) == 1 and "" not in keys else ("Group" if any(r.get("group") is not None for r in chosen_runs) else "Table")
        taken = {c.name for c in blocks[0].id_columns}
        while key in taken:
            key = key + " (label)"
        for b, lab in zip(blocks, labels):
            text = lab[2] if lab[1] == key or key in ("Group",) else (f"{lab[1]}: {lab[2]}" if lab[1] else lab[2])
            b.label = Label(column=key, value=text)
    return blocks, differs, labels


def detect(grid):
    recipe, conf, alternatives, _ = detect_full(grid)
    return recipe, conf, alternatives


def detect_full(grid):
    R = Rows(grid)
    if not any(not R.blank(i) for i in range(min(R.n, 5000))):
        raise ParseError("The file has no data")
    sheet = getattr(grid, "sheet", None)
    runs = _runs(R)
    info = {"comma": False}
    pre = [r for r in runs if r["headers"]] or runs
    dec, th = _decimal(R, pre, [_num_cols(R, r["start"], r["end"]) for r in pre])
    info["comma"] = dec == ","
    issues = []
    conf = 1.0
    assembled = _assemble(R, runs, info) if runs else None
    alternatives = []
    if not assembled:
        block = _fallback(R)
        blocks, differs = [block], False
        conf = 0.75 if not any(c.name.startswith("Column ") for c in block.id_columns) else 0.45
        last = block.data_end
        used = set(block.header_rows)
    else:
        blocks, differs, labels = assembled
        last = max(b.data_end for b in blocks)
        used = {lab[0] for lab in labels if lab}
    first_top = min((b.header_rows[0] if b.header_rows else b.data_start) for b in blocks)
    unit, source = _meta(R, first_top)
    label_cols = {b.label.column for b in blocks if b.label}
    for b in blocks:
        if not b.unit and unit and not any(UNIT_KEY.match(c) for c in label_cols):
            b.unit = unit
    for run in runs:
        cols = run.get("cols")
        if cols and cols["units"]:
            for b in blocks:
                if b.data_start == run["start"] and not b.unit:
                    b.unit = ", ".join(cols["units"])
    notes = _notes(R, last, used)
    if source and not any(SOURCE_LINE.match(n) for n in notes):
        notes.append(source)
    recipe = Recipe(sheet=sheet, blocks=blocks, decimal=dec, thousands=th, notes=notes)
    recipe.aggregates, sum_fail = _aggregates(R, blocks, dec == ",")
    if assembled:
        if not blocks[0].header_rows:
            conf -= 0.35
            issues.append("No header row found")
        generic = [c.name for b in blocks[:1] for c in b.id_columns + b.value_columns if c.name.startswith("Column ")]
        if generic:
            conf -= min(0.3, 0.1 * len(generic))
            issues.append(", ".join(generic[:3]) + (" has" if len(generic) == 1 else " have") + " no header name")
        mixed = set()
        for run in runs:
            if run.get("cols"):
                mixed |= set(run["cols"]["mixed"])
        if mixed:
            conf -= min(0.3, 0.1 * len(mixed))
            issues.append(f"{len(mixed)} column" + ("s mix" if len(mixed) > 1 else " mixes") + " numbers and text")
        ignored = [r for r in runs if r.get("ignored")]
        big = [r for r in ignored if r["end"] - r["start"] >= 2]
        if big:
            conf -= min(0.3, 0.15 * len(big))
            issues.append(f"{len(big)} other table" + ("s were" if len(big) > 1 else " was") + " left out")
        if differs:
            conf -= 0.15
            issues.append("The file holds tables with different columns. Only the first kind is read")
        wide_run = next((r for r in runs if r.get("cols")), None)
        if wide_run is not None:
            per = wide_run.get("per") or []
            if blocks[0].wide and len(blocks[0].value_columns) <= 3 and not blocks[0].wide.levels:
                conf -= 0.1
                alt = _assemble(R, runs, info, include_wide=False)
                if alt:
                    r2 = Recipe(sheet=sheet, blocks=alt[0], decimal=dec, thousands=th, notes=notes, aggregates=recipe.aggregates)
                    alternatives.append({"summary": summarize(grid, r2), "recipe": r2})
            elif not blocks[0].wide and len(per) == 2:
                conf -= 0.05
        if differs:
            others = [k for k, r in enumerate(runs) if r.get("cols") and r["start"] not in {b.data_start for b in blocks}]
            for k in others[:2]:
                alt = _assemble(R, runs, info, only={k})
                if alt:
                    r2 = Recipe(sheet=sheet, blocks=alt[0], decimal=dec, thousands=th, notes=notes)
                    r2.aggregates = _aggregates(R, alt[0], dec == ",")[0]
                    alternatives.append({"summary": summarize(grid, r2), "recipe": r2})
        if len(blocks) > 1 and not blocks[0].label:
            conf -= 0.05
        if sum_fail:
            conf -= 0.1
            issues.append("A total row does not add up to the rows it covers")
        cols0 = next((r["cols"] for r in runs if r.get("cols")), None)
        raw_names = [cols0["names"][j] for j in cols0["ids"] + cols0["values"]] if cols0 else []
        dup = len(raw_names) - len(set(raw_names))
        if dup:
            conf -= min(0.4, 0.2 * dup)
            issues.append("Some column names repeat. The sheet may hold tables side by side")
    conf = round(max(0.0, min(1.0, conf)), 2)
    return recipe, conf, alternatives[:3], issues
