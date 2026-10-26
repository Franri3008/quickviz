import datetime as dt
import math
import re

MAX_ROWS = 100_000
MAX_COLS = 80
MAX_CELL = 200

MISSING = {"", ":", "..", "...", "-", "–", "—", "n/a", "na", "nan", "null", "none", "#n/a", "#value!", "#div/0!", "x"}
TIME_NAME = re.compile(
    r"^(year|yr|date|month|time|quarter|qtr|week|day|period|season|fy|timestamp|datetime|hour|jaar|annee|année|jahr|año|anno"
    r"|mois|monat|maand|mes|mese|datum|zeit|zeitraum|période|periode|trimestre|quartal|jaar|ano)s?$"
    r"|(_|\b)(year|date|month|quarter|week|day|period|season|time)$", re.I)
MONTHS = {}
for _i, _names in enumerate([
        "january jan janvier janv januar jän jaenner januari enero ene gennaio genn janeiro styczeń",
        "february feb février fevrier févr fevr februar febr februari febrero febbraio fevereiro",
        "march mar mars märz maerz mrz maart marzo março",
        "april apr avril avr abril aprile",
        "may mai mei mayo maggio maio",
        "june jun juin juni junio giugno junho",
        "july jul juillet juil juli julio luglio julho",
        "august aug août aout augustus agosto ago",
        "september sep sept septembre septiembre settembre setembro",
        "october oct octobre oktober okt octubre ottobre outubro",
        "november nov novembre noviembre novembro",
        "december dec décembre decembre déc dezember dez diciembre dicembre dezembro"]):
    for _n in _names.split():
        MONTHS[_n] = _i + 1
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
MONTH_YEAR = re.compile(rf"^({_MONTH_ALT})\.?[\s\-/]*('?\d{{2}}|\d{{4}})$|^(\d{{4}})[\s\-/]+({_MONTH_ALT})\.?$", re.I)
DATE_RE = re.compile(
    r"^(\d{4}([-/.]\d{1,2}([-/.]\d{1,2})?)?|\d{4}[- ]?[qQ][1-4]|[qQ][1-4][- ]?\d{4}|\d{4}[- ]?[wWmM]\d{1,2}|\d{4}[sS][12]"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?([- ]\d{2,4})?)"
    r"([ T]\d{1,2}:\d{2}(:\d{2})?)?$", re.I)
PERIOD_HEAD = re.compile(r"^(1[89]\d{2}|20\d{2}|2100)([- ]?([qQ][1-4]|[mM]\d{1,2}|[sS][12]|-\d{2}))?$")
FLAG = re.compile(r"^(.*?\d)\s*[bcdefnpsuz]{1,3}$")
FLAG_SPLIT = re.compile(r"^(.*?\d)\s*\(?([a-zA-Z]{1,3})\)?$")
FLAG_TOKEN = re.compile(r"^\(?[a-zA-Z]{1,3}\)?$")
FOOT = re.compile(r"\s*[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]+$")
ID_FOOT = re.compile(r"\s*(?:[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]+|\(\d\)|\(\*+\))$")
NUM_DOT = re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
NUM_COMMA = re.compile(r"^[-+]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")
NUM_SPACE = re.compile("^[-+]?\\d{1,3}([ \u00a0\u202f\u2009]\\d{3})+([.,]\\d+)?$")
SCI = re.compile(r"^[-+]?\d+(\.\d+)?[eE][-+]?\d+$")
SOURCE_LINE = re.compile(r"^\s*(source|sources|data source|quelle|bron|fuente|fonte)\s*[:\-]\s*(.+)$", re.I)
SPACES = " \u00a0\u202f\u2009"


class ParseError(ValueError):
    pass


def cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, float):
        if not math.isfinite(v):
            return ""
        if v.is_integer() and abs(v) < 1e15:
            return int(v)
        return v
    if isinstance(v, int):
        return v
    return str(v).strip()[:MAX_CELL]


def is_blank(c):
    return c is None or c == ""


def nonempty(row):
    return sum(1 for c in row if c != "" and c is not None)


def strip_foot(t):
    return FOOT.sub("", t).strip() if t else t


PLAIN = re.compile(r"^-?\d{1,15}(\.\d+)?$")


def _plain_number(t, comma_decimal):
    if PLAIN.match(t):
        if "." not in t:
            return int(t)
        if comma_decimal and re.fullmatch(r"-?\d{1,3}\.\d{3}", t):
            return int(t.replace(".", ""))
        return float(t)
    t = re.sub(r"^[€$£¥]\s*|\s*[€$£¥%]$|\s*(eur|usd|gbp)$", "", t, flags=re.I).strip()
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    t = t.replace("−", "-")
    dec = False
    if SCI.match(t):
        v, dec = float(t), True
    elif NUM_SPACE.match(t):
        v, dec = float(re.sub(f"[{SPACES}]", "", t).replace(",", ".")), bool(re.search(r"[.,]\d+$", t))
    elif comma_decimal and NUM_COMMA.match(t):
        v, dec = float(t.replace(".", "").replace(",", ".")), "," in t
    elif NUM_DOT.match(t):
        v, dec = float(t.replace(",", "")), "." in t
    elif NUM_COMMA.match(t):
        v, dec = float(t.replace(".", "").replace(",", ".")), "," in t
    else:
        return None
    if not math.isfinite(v):
        return None
    return int(v) if v.is_integer() and abs(v) < 1e15 and not dec else v


def to_number(s, comma_decimal):
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return s if (not isinstance(s, float) or math.isfinite(s)) else None
    t = str(s).strip()
    if t.lower() in MISSING:
        return None
    m = FLAG.match(t)
    if m:
        t = m.group(1)
    t = strip_foot(t)
    return _plain_number(t, comma_decimal)


def read_value(s, comma_decimal, missing):
    if isinstance(s, bool):
        return None, ""
    if isinstance(s, (int, float)):
        return (s if (not isinstance(s, float) or math.isfinite(s)) else None), ""
    if s is None:
        return None, ""
    t = str(s).strip()
    if t.lower() in missing or t == "":
        return None, ""
    flag = ""
    v = _plain_number(strip_foot(t), comma_decimal)
    if v is not None:
        return v, ""
    m = FLAG_SPLIT.match(t)
    if m:
        v = _plain_number(strip_foot(m.group(1).strip()), comma_decimal)
        if v is not None:
            return v, m.group(2)
    parts = t.split()
    if len(parts) == 2 and parts[0].lower() in missing and FLAG_TOKEN.match(parts[1]):
        return None, parts[1].strip("()")
    return None, flag


def month_year(s):
    if not isinstance(s, str):
        return None
    m = MONTH_YEAR.match(s.strip())
    if not m:
        return None
    if m.group(1):
        mon, yr = MONTHS[m.group(1).lower()], m.group(2).lstrip("'")
    else:
        mon, yr = MONTHS[m.group(4).lower()], m.group(3)
    if len(yr) == 2:
        yr = ("20" if int(yr) < 70 else "19") + yr
    return f"{yr}-{mon:02d}"


def is_period(c):
    if isinstance(c, bool):
        return False
    if isinstance(c, int):
        return 1800 <= c <= 2100
    if isinstance(c, float):
        return c.is_integer() and 1800 <= c <= 2100
    if not isinstance(c, str):
        return False
    t = strip_foot(c.strip())
    return bool(PERIOD_HEAD.match(t)) or bool(re.fullmatch(r"(1[89]|20)\d{2}[- ]?(Q[1-4]|S[12]|H[12])", t, re.I)) \
        or bool(month_year(t))


def comma_votes(values):
    comma = dot = 0
    for v in values:
        if not isinstance(v, str):
            continue
        t = strip_foot(v.strip())
        m = FLAG_SPLIT.match(t)
        if m:
            t = m.group(1).strip()
        if re.fullmatch(r"[-+]?\d+,\d{1,2}", t) or re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+,\d+", t) or re.fullmatch(r"[-+]?\d+,\d{4,}", t) \
                or re.fullmatch(r"[-+]?\d{1,3}(\.\d{3}){2,}", t):
            comma += 1
        elif re.fullmatch(r"[-+]?\d+\.\d{1,2}", t) or re.fullmatch(r"[-+]?\d+\.\d{4,}", t) or re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", t):
            dot += 1
    return comma, dot


def col_type(name, raw_vals, nums):
    vals = [v for v in raw_vals if not (isinstance(v, str) and v.strip().lower() in MISSING)]
    if not vals:
        return "category"
    n_num = sum(1 for x in nums if x is not None)
    strs = [str(v) for v in vals]
    n_date = sum(1 for s in strs if DATE_RE.match(s))
    ints = n_num == len(vals) and all(isinstance(x, int) for x in nums if x is not None)
    year_like = ints and all(1800 <= x <= 2100 for x in nums if x is not None)
    distinct = len(set(strs))
    if TIME_NAME.search(name) and (n_date >= 0.9 * len(vals) or year_like or ints or not n_num):
        return "time"
    if year_like and 1 < distinct < len(vals) * 0.9 + 2:
        return "time"
    if n_num >= 0.9 * len(vals):
        return "number"
    if n_date >= 0.9 * len(vals):
        return "time"
    return "category"
