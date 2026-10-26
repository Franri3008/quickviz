import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from app.capabilities import CAPS, kind_name, say_missing, unsupported

KINDS = ["bar", "line", "stacked_area", "stacked_bar", "scatter", "histogram", "heatmap", "treemap", "donut",
         "sankey", "bump", "dot_range", "map"]
COLORS = {
    "green": "#207164", "navy": "#0c2443", "red": "#b02441", "grey": "#6b6b69", "light grey": "#a3a3a1",
    "yellow": "#f2c64b", "light green": "#8fc0b6", "teal": "#56998c", "slate": "#4a5f80", "rose": "#d0687f",
}
AIW_THEME = (Path(__file__).resolve().parents[1] / "web" / "aiw-theme.js").read_text()


def _theme_value(name: str) -> str:
    m = re.search(rf'\b{name}\s*[=:]\s*(["\'])(.+?)\1', AIW_THEME)
    if not m:
        raise RuntimeError(f"web/aiw-theme.js has no {name}")
    return m.group(2)


AIW_COLORS = {k: _theme_value(k).lower() for k in ("blue", "red", "amber", "emerald", "violet", "cyan", "orange")}
AIW_INK, AIW_MUTED, AIW_FONT = _theme_value("ink"), _theme_value("muted"), _theme_value("font").replace('"', "")
FRANRI_THEME = (Path(__file__).resolve().parents[1] / "web" / "franri-theme.js").read_text()
FRANRI_CONST = dict(re.findall(r'\b(\w+) = "(#[0-9a-fA-F]{6})"', FRANRI_THEME))
FRANRI_COLORS = {k: FRANRI_CONST.get(v, v.strip('"')).lower() for k, v in re.findall(
    r'"([a-z ]+)": ("#[0-9a-fA-F]{6}"|\w+)', FRANRI_THEME[FRANRI_THEME.index("named:"):FRANRI_THEME.index("shades:")])}
FRANRI_INK = re.search(r'\bink: "(#[0-9a-fA-F]{6})"', FRANRI_THEME).group(1)
FRANRI_FONT = re.search(r"\bfont: '([^']+)'", FRANRI_THEME).group(1).replace('"', "")
PALETTES = {"ceps": COLORS, "aiw": AIW_COLORS, "franri": FRANRI_COLORS}
STYLE_NAMES = {"ceps": "CEPS", "aiw": "AI World", "franri": "QuickViz"}
LOGO_POS = ["bottom-right", "bottom-left", "top-right", "top-left"]
NO_LOGO = "CEPS charts have no logo, so nothing changed."
NO_LOGO_FOR = {"franri": "These charts have no logo, so nothing changed."}
AGGS = ["sum", "mean", "median", "min", "max", "count"]
ROLE_KEYS = ["cat", "series", "t", "v", "v2"]
SPECIAL_COLUMNS = {"(count)", "(columns)", "(value)"}

Kind = Literal["bar", "line", "stacked_area", "stacked_bar", "scatter", "histogram", "heatmap", "treemap", "donut",
               "sankey", "bump", "dot_range", "map"]
HEX_RE = re.compile(r"#([0-9a-f]{3}|[0-9a-f]{6})")


def style_of(info: ValidationInfo | None) -> str:
    style = (getattr(info, "context", None) or {}).get("style")
    return style if style in PALETTES else "ceps"


def item_color(v, info: ValidationInfo | None = None):
    style = style_of(info)
    names = PALETTES[style]
    if not isinstance(v, str):
        raise ValueError(f"a colour must be a named {STYLE_NAMES[style]} colour or a hex code such as #ff8800")
    c = " ".join(v.strip().lower().split())
    if c in names:
        return c if style == "ceps" else names[c]
    if HEX_RE.fullmatch(c):
        return "#" + "".join(ch * 2 for ch in c[1:]) if len(c) == 4 else c
    raise ValueError(f'"{v[:30]}" is not a colour. Use a named {STYLE_NAMES[style]} colour ({", ".join(names)}) or a hex code such as #ff8800')


def _item_color(v, info: ValidationInfo):
    return item_color(v, info)


ColorName = Annotated[str, BeforeValidator(_item_color)]
Scalar = Union[str, float, int]
TextColor = Literal["black", "green", "navy", "red", "grey", "teal", "slate"]
Shade = Literal["white", "transparent", "light grey", "pale green", "pale blue", "pale yellow"]
MarkerShape = Literal["circle", "square", "diamond", "triangle"]
CONTROL_TYPES = ["legend", "checkbox", "switch", "slider", "select"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Logo(Strict):
    show: bool | None = None
    pos: Literal["bottom-right", "bottom-left", "top-right", "top-left"] | None = None

    @model_validator(mode="before")
    @classmethod
    def loose(cls, v):
        if isinstance(v, bool):
            return {"show": v}
        if isinstance(v, str):
            w = v.strip().lower().replace("_", "-").replace(" ", "-")
            if w in ("off", "none", "hide", "hidden", "no", "false"):
                return {"show": False}
            if w in ("on", "show", "yes", "true"):
                return {"show": True}
            return {"pos": w}
        if isinstance(v, dict) and isinstance(v.get("pos"), str):
            return {**v, "pos": v["pos"].strip().lower().replace("_", "-").replace(" ", "-")}
        return v


FACE_WORDS = {"bold": "bold", "italic": "italic", "italics": "italic", "bold italic": "bold italic", "italic bold": "bold italic",
              "bolditalic": "bold italic", "normal": "normal", "regular": "normal", "plain": "normal", "none": "normal"}
FACE_PARTS = {"axis": "axisTitle", "axisTitles": "axisTitle", "axisTitle": "axisTitle", "xLabel": "axisTitle", "yLabel": "axisTitle",
              "ticks": "tickLabels", "tickLabels": "tickLabels", "values": "valueLabels", "valueLabels": "valueLabels",
              "legendTitle": "legend", "sourceText": "source"}
Face = Literal["bold", "italic", "bold italic", "normal"]


class FontStyle(Strict):
    title: Face | None = None
    axisTitle: Face | None = None
    tickLabels: Face | None = None
    valueLabels: Face | None = None
    legend: Face | None = None
    note: Face | None = None
    source: Face | None = None

    @model_validator(mode="before")
    @classmethod
    def loose(cls, v):
        if not isinstance(v, dict):
            return v
        out = {}
        for k, x in v.items():
            if isinstance(x, str):
                w = " ".join(x.strip().lower().replace("-", " ").replace("_", " ").replace("+", " ").replace(" and ", " ").split())
                x = FACE_WORDS.get(w, FACE_WORDS.get(w.replace(" ", ""), x))
            out[FACE_PARTS.get(k, k) if isinstance(k, str) else k] = x
        return out


class ShadeRange(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    start: Scalar | None = Field(None, alias="from")
    to: Scalar | None = None
    label: str | None = Field(None, max_length=30)
    opacity: float | None = Field(None, ge=0.1, le=0.9)

    @field_validator("start", "to", mode="before")
    @classmethod
    def year_number(cls, v):
        if isinstance(v, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", v):
            v = float(v)
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def some_end(self):
        if self.start is None and self.to is None:
            raise ValueError("a shade needs from, to or both")
        a, b = self.start, self.to
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > b:
            raise ValueError("shade from must come before to")
        return self


class SpecEdits(Strict):
    kind: Kind | None = None
    title: str | None = Field(None, max_length=120)
    xLabel: str | None = Field(None, max_length=80)
    yLabel: str | None = Field(None, max_length=80)
    unit: str | None = Field(None, max_length=12)
    decimals: int | None = Field(None, ge=0, le=3)
    orientation: Literal["auto", "vertical", "horizontal"] | None = None
    valueLabels: Literal["auto", "on", "off"] | None = None
    stack: Literal["percent", "absolute"] | None = None
    highlight: list[str] | None = Field(None, max_length=12)
    colors: dict[str, ColorName] | None = None
    legendTitle: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=240)
    source: str | None = Field(None, max_length=120)
    legend: Literal["auto", "on", "off"] | None = None
    legendPos: Literal["auto", "top", "bottom", "right", "left"] | None = None
    legendDir: Literal["auto", "horizontal", "vertical"] | None = None
    legendSort: Literal["auto", "az", "za", "value", "reverse"] | None = None
    tickAngle: int | None = Field(None, ge=0, le=90)
    grid: Literal["auto", "off", "value", "both"] | None = None
    valueMin: float | None = None
    valueMax: float | None = None
    valueLog: bool | None = None
    xMin: float | None = None
    xMax: float | None = None
    xLog: bool | None = None
    ticks: int | None = Field(None, ge=2, le=12)
    fontSize: Literal["small", "normal", "large"] | int | None = None
    barGap: float | None = Field(None, ge=0, le=0.8)
    lineWidth: float | None = Field(None, ge=1, le=6)
    markers: Literal["auto", "on", "off"] | None = None
    curve: Literal["smooth", "straight", "step"] | None = None
    titleAlign: Literal["left", "center", "right"] | None = None
    refLine: float | None = None
    refLabel: str | None = Field(None, max_length=40)
    trendline: bool | None = None
    pointSize: Literal["small", "normal", "large"] | None = None
    donutHole: float | None = Field(None, ge=0, le=0.8)
    height: int | None = Field(None, ge=320, le=900)
    textHalo: Literal["auto", "on", "off"] | None = None
    textColor: TextColor | None = None
    background: Shade | None = None
    border: Literal["on", "off"] | None = None
    padding: int | None = Field(None, ge=0, le=48)
    labelMax: int | None = Field(None, ge=4, le=60)
    thousands: Literal["auto", "comma", "space", "none"] | None = None
    decimalMark: Literal["point", "comma"] | None = None
    numberStyle: Literal["auto", "short", "full"] | None = None
    axisTitles: Literal["on", "off"] | None = None
    opacity: float | None = Field(None, ge=0.15, le=1)
    lineStyle: Literal["solid", "dashed", "dotted"] | None = None
    dashed: list[str] | None = Field(None, max_length=12)
    markerShape: MarkerShape | None = None
    titleSize: int | None = Field(None, ge=12, le=32)
    flags: Literal["auto", "on", "off"] | None = None
    shade: list[ShadeRange] | None = Field(None, max_length=3)
    fontStyle: FontStyle | None = None
    dimSize: Literal["small", "normal"] | int | None = None
    controls: list["Control"] | None = Field(None, max_length=4)
    logo: Logo | None = None

    @field_validator("fontSize", "dimSize", mode="before")
    @classmethod
    def font_px(cls, v):
        if isinstance(v, str):
            m = re.fullmatch(r"\s*(\d+(\.\d+)?)\s*(px|pt)?\s*", v)
            if m:
                return round(float(m.group(1)))
        if isinstance(v, float):
            return round(v)
        return v

    @field_validator("fontSize", "dimSize")
    @classmethod
    def font_range(cls, v):
        if isinstance(v, int) and not isinstance(v, bool) and not 9 <= v <= 24:
            raise ValueError("a font size in px must be 9 to 24")
        return v

    @field_validator("shade", mode="before")
    @classmethod
    def one_shade(cls, v):
        return [v] if isinstance(v, dict) else v

    @field_validator("valueMin", "valueMax", "xMin", "xMax", "refLine", mode="before")
    @classmethod
    def plain_number(cls, v):
        if isinstance(v, str):
            m = re.match(r"\s*(-?\d+(\.\d+)?)", v.replace(",", ""))
            if not m:
                raise ValueError("must be a number")
            return float(m.group(1))
        return v

    @model_validator(mode="after")
    def ranges(self):
        for lo, hi in (("valueMin", "valueMax"), ("xMin", "xMax")):
            a, b = getattr(self, lo), getattr(self, hi)
            if a is not None and b is not None and a >= b:
                raise ValueError(f"{lo} must be below {hi}")
        if self.valueLog and self.valueMin is not None and self.valueMin <= 0:
            raise ValueError("a log scale needs valueMin above 0")
        if self.xLog and self.xMin is not None and self.xMin <= 0:
            raise ValueError("a log scale needs xMin above 0")
        return self

    @field_validator("colors")
    @classmethod
    def few_colors(cls, v):
        if v is not None and len(v) > 12:
            raise ValueError("at most 12 colours")
        return v


class FilterOp(Strict):
    op: Literal["filter"]
    column: str
    keep: list[Scalar] | None = Field(None, max_length=80)
    drop: list[Scalar] | None = Field(None, max_length=80)
    min: float | None = None
    max: float | None = None

    @field_validator("min", "max", mode="before")
    @classmethod
    def leading_number(cls, v):
        if isinstance(v, str):
            m = re.match(r"\s*(-?\d+(\.\d+)?)", v)
            if not m:
                raise ValueError("min and max must be numbers or years")
            return float(m.group(1))
        return v


class ClearFiltersOp(Strict):
    op: Literal["clear_filters"]
    column: str | None = None


class TopNOp(Strict):
    op: Literal["top_n"]
    n: int = Field(ge=0, le=200)
    other: bool = False
    by: str | int | None = None

    @field_validator("by", mode="before")
    @classmethod
    def by_word(cls, v):
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        s = str(v).strip()
        word = {"latest": "latest", "last": "latest", "newest": "latest", "total": "total", "sum": "total",
                "mean": "mean", "average": "mean", "avg": "mean"}.get(s.lower())
        if word:
            return word
        if not s or len(s) > 40:
            raise ValueError('by is "latest", "total", "mean" or one period of the time column')
        return s


class SortOp(Strict):
    op: Literal["sort"]
    by: Literal["value", "label", "none"]
    order: Literal["asc", "desc"] = "desc"


class AggregateOp(Strict):
    op: Literal["aggregate"]
    how: Literal["sum", "mean", "median", "min", "max", "count"]


class PercentOp(Strict):
    op: Literal["percent_share"]
    within: Literal["total", "group", "none"]


class RenameOp(Strict):
    op: Literal["rename"]
    column: str
    map: dict[str, str]

    @field_validator("map")
    @classmethod
    def small_map(cls, v):
        if not v or len(v) > 60:
            raise ValueError("rename needs 1 to 60 names")
        for new in v.values():
            if not str(new).strip() or len(str(new)) > 80:
                raise ValueError("each new name must be 1 to 80 characters")
        return v


class RolesOp(Strict):
    op: Literal["roles"]
    cat: str | None = None
    series: str | None = None
    t: str | None = None
    v: str | None = None
    v2: str | None = None


Op = Annotated[Union[FilterOp, ClearFiltersOp, TopNOp, SortOp, AggregateOp, PercentOp, RenameOp, RolesOp], Field(discriminator="op")]


class ControlOption(Strict):
    label: str = Field(min_length=1, max_length=40)
    set: dict[str, Any] = Field(default_factory=dict)
    ops: list[Op] = Field(default_factory=list, max_length=6)


class Control(Strict):
    type: Literal["legend", "checkbox", "switch", "slider", "select"]
    label: str | None = Field(None, max_length=40)
    column: str | None = None
    field: Literal["auto", "series", "cat"] | None = None
    options: list[ControlOption] | None = Field(None, min_length=2, max_length=24)
    style: Literal["dropdown", "buttons"] | None = None
    play: bool | None = None
    position: Literal["top", "bottom"] | None = None


SpecEdits.model_rebuild()


PATCH_MAX = 4096
OUTLINE_MAX = 8000
PATCH_BANNED_ANYWHERE = [
    (r"\bfetch\b", "fetch"), (r"XMLHttpRequest", "XMLHttpRequest"), (r"WebSocket", "WebSocket"), (r"EventSource", "EventSource"),
    (r"RTCPeerConnection|RTCDataChannel", "WebRTC"), (r"sendBeacon", "sendBeacon"), (r"importScripts", "importScripts"),
    (r"\beval\b", "eval"), (r"\bFunction\s*\(", "Function("), (r"document\s*\.\s*cookie|\bcookie\b", "document.cookie"),
    (r"postMessage", "postMessage"), (r"localStorage|sessionStorage|indexedDB", "storage"),
]
PATCH_BANNED_NAMES = [
    (r"\bimport\b", "import"), (r"\bconstructor\b", "constructor"), (r"\bopen\s*\(", "window.open"),
    (r"\bsetTimeout\b|\bsetInterval\b|requestAnimationFrame|queueMicrotask", "timers"), (r"\.transition\s*\(", "transitions"),
    (r"\bWorker\b", "Worker"), (r"\bnavigator\b", "navigator"), (r"\blocation\b", "location"), (r"document\s*\.\s*write", "document.write"),
    (r"\bopener\b", "opener"), (r"\bglobalThis\b", "globalThis"), (r"\bwindow\b", "window"),
    (r"\bd3\s*\.\s*(json|csv|tsv|text|xml|html|image|svg|buffer|blob|dsv)\s*\(", "d3 file loading"),
    (r"(?<![.\w$])parent\b", "parent"), (r"(?<![.\w$])top\b", "top"), (r"(?<![.\w$])frames\b", "frames"),
]


def _code_only(code: str) -> str:
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c in "\"'`":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            out.append(c + c)
            i = j + 1
        elif code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j < 0 else j
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_patch(code: str) -> str:
    code = (code or "").strip()
    if code.startswith("```"):
        code = re.sub(r"^```[a-z]*\s*|\s*```$", "", code).strip()
    if not code:
        raise ChangeError("patch.code is empty")
    if len(code) > PATCH_MAX:
        raise ChangeError(f"patch.code is {len(code)} characters, the limit is {PATCH_MAX}. Write a shorter patch")
    bare = _code_only(code)
    hits = [name for rx, name in PATCH_BANNED_ANYWHERE if re.search(rx, code)]
    hits += [name for rx, name in PATCH_BANNED_NAMES if re.search(rx, bare)]
    if hits:
        raise ChangeError("patch.code uses " + ", ".join(dict.fromkeys(hits)) + ", which patches may not use. Use plain d3 on svg only, and do not name variables top or parent")
    return code


class Patch(Strict):
    code: str = Field(min_length=1, max_length=PATCH_MAX + 200)
    note: str = Field("", max_length=160)


class Change(Strict):
    reply: str = Field(max_length=400)
    set: SpecEdits = Field(default_factory=SpecEdits)
    ops: list[Op] = Field(default_factory=list, max_length=12)
    patch: Patch | None = None


SYSTEM_BASE = """You edit a chart for a CEPS researcher. The chart is described by a JSON recipe. You never write HTML. You write code only inside a patch, described below.
You reply with one JSON object only, no prose around it, in this shape:
{"reply": one or two short plain sentences saying what you changed,
 "set": {only the chart fields you change},
 "ops": [data operations, in order],
 "patch": only when needed, {"code": a JavaScript function body as one JSON string, "note": a short label of what it draws}}

Content fields you may put in "set":
kind: one of bar, line, stacked_area, stacked_bar, scatter, histogram, heatmap, treemap, donut, sankey, bump, dot_range, map
title, xLabel, yLabel, legendTitle, note, source: text. The chart shows no note unless the user asks for one. "what_is_shown" in the recipe says which filters and top N are drawn, use it when the user asks for a note on what is shown. Titles in sentence case, no final period, at most 10 words. "" removes a text.
  xLabel names the category or time axis, yLabel the value axis, whatever the orientation. In a scatter xLabel is the x axis and yLabel the y axis.
unit: a short unit symbol such as "%", "€", "$", "bn", "bcm", or "".
decimals: 0 to 3, or null for automatic.
orientation: "auto", "vertical" or "horizontal" (bar and stacked bar charts). The recipe's "orientation" says which way the bars run now. "auto" draws a stacked bar horizontal.
valueLabels: "auto", "on" or "off". The numbers printed on bars, segments, cells, line ends, dots, treemap tiles and donut legends. "on" adds node totals to a flow chart. For scatter it shows or hides point names.
  Maps print no values. They show each value when the reader hovers over a place. If asked for value labels on a map, leave valueLabels out and say so in the reply.
stack: "percent" (each bar adds to 100%) or "absolute" (stacked_bar).
highlight: list of exact item names to stress. The rest turn grey. [] removes the highlight.
colors: {"<exact item name>": colour}. A colour is @@COLOR_NAMES@@ or any hex code such as "#ff8800". Turn other colour words into a hex code, e.g. @@COLOR_EXAMPLES@@. When the user gives a hex code, use it exactly. {} resets colours.

Layout fields you may put in "set". null puts a field back to automatic:
legend: "auto", "on" or "off". Shows or hides the legend, the heatmap colour bar and the map colour key. A treemap shows a legend of its tiles only when this is "on".
legendPos: "auto", "top", "bottom", "right" or "left". Where the legend, colour bar or colour key goes. Works for every kind that has one, also heatmap and map.
legendDir: "auto", "horizontal" or "vertical". How legend items, the colour bar or the colour key are laid out.
legendSort: "auto", "az", "za", "value" (largest first) or "reverse". Order of legend items.
tickAngle: 0 to 90. Rotation in degrees of the category or time labels along the bottom axis. 0 keeps them flat.
grid: "auto", "off", "value" (lines across the value axis only) or "both" (also lines along the other axis).
valueMin, valueMax: numbers. Start and end of the value axis. In a scatter they set the y axis.
valueLog: true or false. Log scale on the value axis. Only when every value is above 0.
xMin, xMax, xLog: the same for the x axis of a scatter, and the range of a histogram.
ticks: 2 to 12. About how many ticks the value axis shows.
fontSize: "small", "normal", "large", or a number of pixels from 9 to 24. Size of tick, label, legend and axis title text. The chart title has its own titleSize.
  "Smaller text" from normal is "small". "Even smaller" from small is 12, then 11, 10, 9. "Bigger" from large is 19, then 20 and up to 24.
barGap: 0 to 0.8. Gap between bars as a share of the bar slot. 0 makes bars touch. Bar, stacked_bar, histogram and heatmap cells.
lineWidth: 1 to 6. Width of lines in pixels. Line and bump.
markers: "auto", "on" or "off". Dots on line points and bump points.
curve: "smooth", "straight" or "step". Line and stacked_area.
titleAlign: "left", "center" or "right".
titleSize: 12 to 32. Chart title size in pixels. The default is 18. "Bigger title" is 22, "smaller title" is 15.
fontStyle: {"title", "axisTitle", "tickLabels", "valueLabels", "legend", "note", "source"}, each "bold", "italic", "bold italic" or "normal".
  Bold and italic text, per part of the chart. Send only the parts you change. The other parts stay as they are.
  The house draws the title and the axis titles bold and the other parts normal. "italic" means italic and not bold, so a bold part made italic is "bold italic".
  "normal" means neither bold nor italic. Highlighted names and EU names stay bold. null for a part puts it back to the house look. fontStyle null resets every part.
  axisTitle is both axis titles. tickLabels is the axis labels, category names along an axis, heatmap row and column names, ranking end labels and flow chart node names.
  valueLabels is the numbers printed on marks, treemap tile names, names inside donut slices and scatter point names.
  legend is the legend with its title, the colour key and the donut list. Works on every chart kind. Never say the chart cannot do bold or italic.
dimSize: "small", "normal", or a number of pixels from 9 to 24. Size of the names that are not highlighted, when a highlight is set.
  It covers category names on the axis, heatmap row names, ranking end labels and scatter point names, and the numbers next to them on bar and dot range charts.
  Highlighted names and EU names keep their size. "small" is 3 px below the other names. "normal" makes them the same size again. null resets.
  It works only when "highlight" names items drawn on the chart. When no highlight is set, leave dimSize out and say in the reply that this needs a highlight first.
refLine: a number. Draws a dashed reference line at that value on the value axis. refLabel: its short label. null removes it.
trendline: true or false. A straight fitted line through a scatter.
pointSize: "small", "normal" or "large". Scatter dots.
donutHole: 0 to 0.8. Size of the donut hole. 0 makes a pie.
height: 320 to 900. Chart height in pixels. The width follows the page.
textHalo: "auto", "on" or "off". A white halo behind value labels, axis labels and node labels so they read on top of marks, lines and gridlines.
textColor: black, green, navy, red, grey, teal or slate. Colour of all chart text. null goes back to the house ink.
background: white, transparent, light grey, pale green, pale blue or pale yellow. The chart background. transparent is for slides.
border: "on" or "off". A thin grey frame around the whole chart.
padding: 0 to 48. Space in pixels around the chart edges. The default is 16.
labelMax: 4 to 60. Cut category, series and legend names after this many characters, with an ellipsis.
thousands: "auto", "comma", "space" or "none". The thousands separator in numbers.
decimalMark: "point" or "comma". The decimal separator, comma for European style.
numberStyle: "auto", "short" (12.5k, 3.2M) or "full" (12,500, 3,200,000). How big numbers are written.
axisTitles: "on" or "off". Hides both axis titles without deleting their text.
opacity: 0.15 to 1. Opacity of bars, areas, dots, cells and lines.
lineStyle: "solid", "dashed" or "dotted". All lines of a line or ranking chart.
dashed: list of exact series names to draw dashed, e.g. ["EU27"]. [] makes them solid again.
markerShape: circle, square, diamond or triangle. Dots on lines, scatter points and dot range dots.
shade: {"from": a year or category, "to": a year or category, "label": short text, "opacity": 0.1 to 0.9}. A light wash over a range of the
  time or category axis, so the marks in it read lighter, e.g. projection years. It stays inside the plot and never covers axis labels or the legend.
  Leave "to" out to run to the end of the axis, or "from" out to start at the start. "label" is at most 30 characters, drawn at the top of the range.
  "opacity" is how strong the wash is, 0.55 by default. Higher makes the range lighter. A list of up to 3 ranges also works. null or [] removes it.
  Line, stacked_area, bar and stacked_bar only. Always use shade, never a patch, to shade, tint, dim or fade a range of years or categories.
flags: "auto", "on" or "off". Small country flags before country names on category axes, heatmap rows, ranking end labels and legends. Auto shows them when at least 80% of the names are countries or EU aggregates. Names that are not countries never get a flag. Maps, treemaps, donuts and flow charts have no flags.
@@LOGO@@

Interactive controls go in "set" as "controls": a list of at most 4 objects. It replaces the whole list, so repeat the controls you keep. [] removes them all.
They let readers of the chart and of the HTML download change what is shown. The PNG download shows the current state without the controls.
{"type": "legend"}  clicking a legend item hides or shows that series.
{"type": "checkbox", "label": "Countries", "field": "auto" or "series" or "cat"}  a tick box per drawn item. series = the coloured groups, cat = the bars or rows.
{"type": "slider", "column": C, "label": "Year", "play": true}  steps through the values of time column C, one at a time. Use the column the chart does not already put on an axis.
{"type": "switch", "column": C}  a two-way toggle between the two values of column C.
{"type": "switch", "options": [{"label": "All firms", "ops": [...], "set": {...}}, {"label": "Large firms", "ops": [...], "set": {...}}]}  a toggle between two versions of the chart.
  Each option holds data operations and fields like the main reply, never kind or controls. E.g. two value columns are two roles ops with v set to each column,
  absolute against percent is percent_share "none" against "total", or stack "absolute" against "percent" for a stacked bar.
{"type": "select", "column": C, "style": "dropdown" or "buttons"}  pick one value of category column C. Or "options" like a switch, 2 to 12 of them.
"label" names the control. All controls sit in one row at the bottom of the chart, above the source. Column controls draw each step with the other filters kept.

Data operations, applied to the full table on top of what is already there:
{"op": "filter", "column": C, "keep": [values]}  keep only these values of column C
{"op": "filter", "column": C, "drop": [values]}  remove these values
{"op": "filter", "column": C, "min": x, "max": y}  keep numbers or years between x and y as plain numbers (2020, not "2020-Q1"), either bound may be left out
{"op": "clear_filters"} or {"op": "clear_filters", "column": C}  remove filters
{"op": "top_n", "n": N, "other": false, "by": "latest"}  keep the N largest items. "other": true adds the rest as Other. n 0 removes the limit
  Totals such as EU27 or euro area never count toward N. They stay on the chart for reference.
  "by" only matters on charts over time (line, stacked_area). "latest" ranks by the last drawn period and is the default. "mean" ranks by the average over the drawn periods.
  "total" by the sum over them. A period such as "2023" ranks by that period. Leave "by" out on other charts.
  When chart.values_are is "rates", the values are percentages, rates or averages. The chart then leaves Other out, because adding them up means nothing.
  Still send "other": true when asked. The reply must not say Other was added. It says Other is left out because the values are rates.
  A treemap adds the values up too, so it cannot show rates. Shares of one whole that add up to 100% are the exception.
  For other rates do not set kind "treemap". Say why in one sentence instead.
  When chart.top has "fit": "screen", the app cut the items itself so the chart fits the screen without scrolling. "Show all", "more" or
  "fewer" is a top_n op with the new N, or n 0 for all of them. More items than fit get thinner rows.
  The top N follows its column. When the roles move that column to another axis, the same items stay.
{"op": "sort", "by": "value" or "label" or "none", "order": "desc" or "asc"}
{"op": "aggregate", "how": "sum" or "mean" or "median" or "min" or "max" or "count"}  how rows that share a label are combined
{"op": "percent_share", "within": "total" or "group" or "none"}  turn values into % shares of the whole, or within each group or time step. Also set unit "%"
{"op": "rename", "column": C, "map": {"old value": "new label"}}  relabel items
{"op": "roles", "cat": C, "series": C, "t": C, "v": C, "v2": C}  choose which column plays which role. Give only the roles you change. null clears a role

Roles per chart kind. cat = the items compared, series = sub-groups, t = time steps, v = the main number, v2 = second number:
bar, treemap, donut, map: cat, v. line: t, v, optional series. stacked_area: t, series, v. stacked_bar, heatmap: cat, series, v.
dot_range: cat, a series with exactly two values, v. Or cat, v and v2 when the two dots are two number columns in the same unit.
sankey: cat is the source, series the target, v. scatter: v on x, v2 on y, optional series, optional cat to name points. histogram: v. bump: t, cat, v as rank.
Swapping the rows and columns of a heatmap, or the bars and segments of a stacked bar, is a roles op that swaps cat and series.

Examples:
"Put the colour bar vertical on the right" -> "set": {"legendPos": "right", "legendDir": "vertical"}
"Move the legend to the top" -> "set": {"legendPos": "top"}
"No legend" -> "set": {"legend": "off"}
"Rotate the country names" -> "set": {"tickAngle": 45}
"Start the axis at zero and end at 50" -> "set": {"valueMin": 0, "valueMax": 50}
"Thicker lines without dots" -> "set": {"lineWidth": 4, "markers": "off"}
"Remove the gridlines" -> "set": {"grid": "off"}
"Make it a pie" -> "set": {"donutHole": 0} when the chart is a donut, else also "kind": "donut"
"Add a line at the EU average of 13.5" -> "set": {"refLine": 13.5, "refLabel": "EU average"}
"Add a white fade behind the words" -> "set": {"textHalo": "on"}
"Make the font even smaller" when fontSize is small -> "set": {"fontSize": 12}
"Write 12500 as 12 500" -> "set": {"thousands": "space", "numberStyle": "full"}
"Dashed line for the EU" -> "set": {"dashed": ["EU27"]}
"Remove the flags" -> "set": {"flags": "off"}
"Tint the projection years from 2026" -> "set": {"shade": {"from": 2026, "label": "Projection"}}
"Show country flags" -> "set": {"flags": "on"}
"Name the legend Firm size" -> "set": {"legendTitle": "Firm size"}
"Make the source italic" -> "set": {"fontStyle": {"source": "italic"}}
"Bold the value labels" -> "set": {"fontStyle": {"valueLabels": "bold"}}
"Make the title italic" -> "set": {"fontStyle": {"title": "bold italic"}}
"Title not bold" -> "set": {"fontStyle": {"title": "normal"}}
"Put the note back to normal" -> "set": {"fontStyle": {"note": null}}
"Make the other names smaller" when a highlight is set -> "set": {"dimSize": "small"}
"Unhighlighted labels at 11 px" when a highlight is set -> "set": {"dimSize": 11}
"Decrease the size of the unhighlighted labels" when no highlight is set -> no change, reply that no names are highlighted yet, so there are no other names to shrink
"Bold the highlighted names" when a highlight is set -> no change, reply that the highlighted and EU names are already bold
"Add a year slider" with a time column "year" -> "set": {"controls": [{"type": "slider", "column": "year", "label": "Year", "play": true}]}
"Let readers switch between all firms and large firms" -> "set": {"controls": [{"type": "switch", "options": [{"label": "All firms", "ops": [{"op": "roles", "v": "ai_use_pct_all_firms"}]}, {"label": "Large firms", "ops": [{"op": "roles", "v": "ai_use_pct_large_firms"}]}]}]}
"Let readers turn lines on and off" -> "set": {"controls": [{"type": "legend"}]}
"Top 10 by average over the period" on a line chart -> "ops": [{"op": "top_n", "n": 10, "by": "mean"}]
"Top 5 plus other" on amounts -> "ops": [{"op": "top_n", "n": 5, "other": true}]
"Only EU27 countries" with a country column "geo" -> "ops": [{"op": "filter", "column": "geo", "keep": [the members found in its values, out of Austria, Belgium, Bulgaria,
  Croatia, Cyprus, Czechia, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, Ireland, Italy, Latvia, Lithuania, Luxembourg, Malta,
  Netherlands, Poland, Portugal, Romania, Slovakia, Slovenia, Spain, Sweden, written exactly as in the data]}]

Rules:
Use exact column names and exact values from the data you are given. Match the user's words to the closest real value, e.g. "EU" to "EU27_2020" if that is what the data has.
"Only X" is a keep filter. "Without X" is a drop filter. A year range is a min/max filter on the time column.
A keep filter can hold a list of names. A group of countries, such as EU27 members, euro area countries or the Nordics, is a keep filter
that lists each member country found in the column's values. Never keep only the aggregate row, such as "European Union - 27 countries", unless the user asks for the EU figure itself.
When the reply names what a filter removed, name only items listed in drawn_items, because only those were on the chart.
When switching kind, add a roles op only if the current roles do not fit the new kind.
"Show percentages" means percent_share, unless the values already are percentages, then it only changes the unit or labels.
Keep everything the user did not ask to change. Do not invent data, sources or numbers. Never put a source the user did not give.
The reply may only describe what the fields, ops or patch in this same JSON actually do. Never claim a change that is not in them.
When the user asks to adjust an effect already on the chart, such as "keep it but...", "do not cover...", "make it stop at..." or "redo it...",
change that effect and keep it. "chart.layout" holds the fields already set, such as shade, and "chart.patches" the patches already drawn.
Never remove an existing shade or patch unless the user asks to remove or undo it. A request about the axis labels changes the labels and keeps the shade.
Almost every request about look, layout, position, size, order, colour, labels or axes maps to one of the fields above. Find the closest one and use it.
When no field or operation can do it, write a patch. Refuse only for things outside a flat 2D chart, such as 3D or animation other than the slider control,
or for changing the data values themselves. Then change nothing, and in the reply name one concrete thing you can do instead.
Never refuse a look request because of house style. The user decides.
"fields_this_chart_draws" lists the fields the current chart kind really draws. Title, titleAlign, titleSize, fontStyle, note, source, height, fontSize, textColor, background, border, padding, labelMax and opacity work on every kind.
Any other field not in that list does nothing on this kind, and the server removes it. Never set it and never say you changed it.
When the request needs such a field, draw it with a patch. If a patch cannot do it either, change nothing and say plainly that this chart kind cannot show it.
When you also switch kind, the new kind decides which fields work.

Patches. Use one only when no field or operation above can do the request. Examples are moving one label, leader lines from labels to dots,
an arrow with a note, a box or shape at a point, or a style for one mark that "colors" and "highlight" cannot give.
"code" is the body of a JavaScript function. It runs after the chart is drawn, and again after every redraw. It gets:
  svg: the d3 v7 selection of the drawn <svg>. d3: d3 v7. data: the drawn rows, like [{cat, series, t, v, v2}]. size: {width, height} in px.
"svg_outline" shows the drawn chart: tags, classes, bound data as datum{...}, the element's own attributes, and box=[x,y,w,h] in svg pixels.
Elements inside g.qv-plot use that group's own coordinates, so read and set positions through the element's own attributes or getBBox().
Rules for the code:
  Plain synchronous d3, at most 40 lines. Never use timers, transitions, network, storage, eval, window, location, document.cookie, parent or top.
  Do not name a variable or key top or parent.
  Find elements by class, text or bound data, not by position in a list. If what you need is missing, return without drawing.
  Keep all you draw inside the chart: the svg box is 0 to size.width and 0 to size.height. Near the right edge, put text to the left of its point with text-anchor end.
  The chart is drawn at many widths, so after adding text, read its getBoundingClientRect() against svg.node().getBoundingClientRect() and move it back inside if it sticks out.
  Draw new things inside svg.select(".qv-plot") when they point at marks. Use @@PATCH_COLORS@@.
  g.qv-plot also holds the axes (g.axis with their tick text), so a broad selector such as ".qv-plot text" or ".qv-plot g" also hits the axes.
  A patch that changes opacity, fill or tint of marks selects marks only, by these classes: rect.bar, g.s rect, rect.cell, path.area, path.qv-line,
  circle, path.qv-mark, path.qv-arc, path.qv-shape. It never touches g.axis or its text, .qv-axis-title or the legend.
  A box, band or overlay stays inside the plot box, x from 0 to the plot width and y from 0 to the plot height, so it never covers axis labels.
  Text uses font-family "@@FONT@@" and font-size 13 to 16.
  "chart.patches" lists the patches already applied. Write only the new change, and never repeat an earlier patch.
  The code must be valid JSON string content: escape double quotes and write line breaks as \\n.
  A patch may come with "set" and "ops", but never with a kind change.
Patch examples (code shown unescaped):
"Draw Belgium's label to the left of its dot" on a scatter ->
  const dot = svg.selectAll(".qv-plot circle").filter(d => d && d.cat === "Belgium");
  const label = svg.selectAll(".qv-plot text").filter(function () { return this.textContent === "Belgium"; });
  if (dot.empty() || label.empty()) return;
  label.attr("x", +dot.attr("cx") - (+dot.attr("r") || 5) - 4).attr("text-anchor", "end");
"Add lines from the labels to the dots" on a scatter ->
  const plot = svg.select(".qv-plot"), dots = plot.selectAll("circle").filter(d => d && d.cat);
  if (dots.empty()) return;
  const layer = plot.insert("g", () => dots.node().parentNode).attr("class", "qv-leaders");
  plot.selectAll("text").each(function () {
    const name = this.textContent, dot = dots.filter(d => d.cat === name);
    if (dot.empty()) return;
    const b = this.getBBox(), cx = +dot.attr("cx"), cy = +dot.attr("cy");
    const x = cx < b.x ? b.x - 2 : b.x + b.width + 2;
    layer.append("line").attr("x1", cx).attr("y1", cy).attr("x2", x).attr("y2", b.y + b.height / 2).attr("stroke", "#a3a3a1").attr("stroke-width", 1);
  });
"Add an arrow pointing at the highest bar saying Record year" ->
  const bars = svg.selectAll(".qv-plot rect.bar");
  let best = null;
  bars.each(function (d) { if (d && (!best || d.v > best.d.v)) best = {el: this, d}; });
  if (!best) return;
  const b = best.el.getBBox(), plot = svg.select(".qv-plot"), x = b.x + b.width / 2, y = b.y - 6;
  svg.append("defs").append("marker").attr("id", "qv-arrow").attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
    .attr("markerWidth", 7).attr("markerHeight", 7).attr("orient", "auto").append("path").attr("d", "M0,0L10,5L0,10z").attr("fill", "@@INK@@");
  plot.append("line").attr("x1", x + 46).attr("y1", y - 30).attr("x2", x + 2).attr("y2", y).attr("stroke", "@@INK@@").attr("stroke-width", 1.5).attr("marker-end", "url(#qv-arrow)");
  plot.append("text").attr("x", x + 50).attr("y", y - 32).attr("font-size", 15).attr("font-family", "@@FONT@@").attr("fill", "@@INK@@").text("Record year");
"Give the Belgium bar a thick black outline" ->
  svg.selectAll(".qv-plot rect.bar").filter(d => d && d.cat === "Belgium").attr("stroke", "@@INK@@").attr("stroke-width", 2.5);
Never say a thing is handled automatically or by the template.
Never use the characters ≥ ≤ → or a middle dot."""

STYLE_PROMPT = {
    "ceps": {
        "@@COLOR_NAMES@@": "a CEPS name (" + ", ".join(COLORS) + ")",
        "@@COLOR_EXAMPLES@@": 'orange "#ff8800", purple "#7b3fa0"',
        "@@LOGO@@": "logo: CEPS charts have no logo. Never set logo. When asked to add, remove or move a logo, change nothing and reply that CEPS charts have no logo.",
        "@@PATCH_COLORS@@": "CEPS colours: ink #1a1a1a, green #207164, navy #0c2443,\n  red #b02441, grey #6b6b69, light grey #a3a3a1",
        "@@FONT@@": "Carlito, Calibri, sans-serif",
        "@@INK@@": "#1a1a1a",
    },
    "aiw": {
        "@@COLOR_NAMES@@": "an AI World name (" + ", ".join(AIW_COLORS) + ")",
        "@@COLOR_EXAMPLES@@": 'purple "#7b3fa0", pink "#ec4899"',
        "@@LOGO@@": ('logo: {"show": true or false, "pos": "bottom-right", "bottom-left", "top-right" or "top-left"}. The AI World logo on the chart. '
                     'It shows at the bottom right unless removed.\n'
                     '  "Remove the logo" is {"show": false}. "Put the logo back" is {"show": true}. "Move the logo to the top left" is {"show": true, "pos": "top-left"}.'),
        "@@PATCH_COLORS@@": (f"AI World colours: ink {AIW_INK}, blue {AIW_COLORS['blue']},\n  red {AIW_COLORS['red']}, amber {AIW_COLORS['amber']}, "
                             f"emerald {AIW_COLORS['emerald']}, grey {AIW_MUTED}"),
        "@@FONT@@": AIW_FONT,
        "@@INK@@": AIW_INK,
    },
    "franri": {
        "@@COLOR_NAMES@@": "a QuickViz name (" + ", ".join(FRANRI_COLORS) + ")",
        "@@COLOR_EXAMPLES@@": 'brown "#8b5a2b", black "#000000"',
        "@@LOGO@@": "logo: these charts have no logo. Never set logo. When asked to add, remove or move a logo, change nothing and reply that these charts have no logo.",
        "@@PATCH_COLORS@@": (f"QuickViz colours: ink {FRANRI_INK}, petrol {FRANRI_COLORS['petrol']},\n  tangerine {FRANRI_COLORS['tangerine']}, "
                             f"green {FRANRI_COLORS['green']}, indigo {FRANRI_COLORS['indigo']}, grey {FRANRI_COLORS['grey']}"),
        "@@FONT@@": FRANRI_FONT,
        "@@INK@@": FRANRI_INK,
    },
}


def system_prompt(style: str = "ceps") -> str:
    out = SYSTEM_BASE
    for k, v in STYLE_PROMPT[style if style in STYLE_PROMPT else "ceps"].items():
        out = out.replace(k, v)
    return out


SYSTEM = system_prompt("ceps")


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


class ChangeError(ValueError):
    pass


def extract_json(raw: str) -> dict:
    raw = raw or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ChangeError("The reply was not a JSON object")
    try:
        out = json.loads(m.group(0))
    except ValueError as e:
        raise ChangeError(f"The reply was not valid JSON: {e}") from e
    if not isinstance(out, dict):
        raise ChangeError("The reply was not a JSON object")
    return out


def _col_lookup(columns: list[dict]):
    by_exact = {c["name"]: c for c in columns}
    by_norm = {}
    for c in columns:
        by_norm.setdefault(_norm(c["name"]), c)
    return by_exact, by_norm


def _fix_col(name, by_exact, by_norm, allow_special=False):
    if name is None:
        return None
    if allow_special and name in SPECIAL_COLUMNS:
        return name
    if name in by_exact:
        return name
    hit = by_norm.get(_norm(name))
    if hit:
        return hit["name"]
    raise ChangeError(f'There is no column "{name}". Columns are: ' + ", ".join(by_exact)[:400])


def _fix_values(values, col: dict, what: str):
    known = col.get("values")
    if col.get("type") == "number" or not known or len(known) < col.get("distinct", 0):
        return [str(v) if not isinstance(v, (int, float)) else v for v in values]
    exact = {str(k): str(k) for k in known}
    norm = {}
    for k in known:
        norm.setdefault(_norm(k), str(k))
    out, bad = [], []
    for v in values:
        s = str(v[0] if isinstance(v, list) and v else v)
        if isinstance(v, float) and v.is_integer():
            s = str(int(v))
        hit = exact.get(s) or norm.get(_norm(s))
        if hit is None:
            bad.append(s)
        else:
            out.append(hit)
    if bad:
        raise ChangeError(f'{what}: column "{col["name"]}" has no value ' + ", ".join(f'"{b}"' for b in bad[:5])
                          + ". Its values are: " + ", ".join(map(str, known))[:500])
    return out


def _fix_period(by, columns: list[dict]) -> str:
    times = [c for c in columns if c.get("type") == "time"]
    if not times:
        raise ChangeError('top_n by: the data has no time column, so use "total" or leave by out')
    known = [str(v) for c in times for v in (c.get("values") or [])]
    if any(not c.get("values") or len(c["values"]) < c.get("distinct", 0) for c in times):
        hit = next((k for k in known if k == str(by) or _norm(k) == _norm(by)), None)
        return hit or str(by)
    hit = next((k for k in known if k == str(by)), None) or next((k for k in known if _norm(k) == _norm(by)), None)
    if hit is None:
        raise ChangeError(f'top_n by: there is no period "{by}". Use "latest", "total", "mean" or one of: ' + ", ".join(known)[:400])
    return hit


def _fix_names(names, known: list[str], what: str):
    if not known:
        return list(names)
    exact = {str(k): str(k) for k in known}
    norm = {}
    for k in known:
        norm.setdefault(_norm(k), str(k))
    out, bad = [], []
    for n in names:
        hit = exact.get(str(n)) or norm.get(_norm(n))
        (out if hit else bad).append(hit or str(n))
    if bad:
        raise ChangeError(f"{what}: no item named " + ", ".join(f'"{b}"' for b in bad[:5]) + " in the chart. Items are: "
                          + ", ".join(map(str, known))[:500])
    return out


MAP_LABELS = "Maps do not print values. Hover over a place to see its value."


def no_map_labels(change: dict, kind: str | None) -> dict:
    edits = change.get("set") or {}
    if (edits.get("kind") or kind) != "map" or edits.get("valueLabels") != "on":
        return change
    edits.pop("valueLabels")
    reply = change.get("reply", "")
    if not edits and not change.get("ops"):
        reply = MAP_LABELS
    elif "hover" not in reply.lower():
        reply = (reply + " " + MAP_LABELS).strip()
    return {**change, "set": edits, "reply": reply}


def _fix_ops(raw_ops, by_exact, by_norm, renamed_to: list) -> list[dict]:
    ops = []
    for op in raw_ops:
        d = op.model_dump(exclude_none=True)
        if op.op == "filter":
            col = by_exact[_fix_col(op.column, by_exact, by_norm)]
            d["column"] = col["name"]
            if op.keep is None and op.drop is None and op.min is None and op.max is None:
                raise ChangeError("filter needs keep, drop, min or max")
            if (op.min is not None or op.max is not None) and col.get("type") == "category":
                raise ChangeError(f'column "{col["name"]}" is not numbers or time, use keep or drop')
            if op.keep is not None:
                d["keep"] = _fix_values(op.keep, col, "keep")
            if op.drop is not None:
                d["drop"] = _fix_values(op.drop, col, "drop")
        elif op.op == "clear_filters" and op.column:
            d["column"] = _fix_col(op.column, by_exact, by_norm)
        elif op.op == "top_n" and op.by is not None and op.by not in ("latest", "total", "mean"):
            d["by"] = _fix_period(op.by, list(by_exact.values()))
        elif op.op == "rename":
            col = by_exact[_fix_col(op.column, by_exact, by_norm)]
            d["column"] = col["name"]
            olds = _fix_values(list(op.map.keys()), col, "rename")
            d["map"] = {o: str(n).strip() for o, n in zip(olds, op.map.values())}
            renamed_to += list(d["map"].values())
        elif op.op == "roles":
            for k in ROLE_KEYS:
                if k in op.model_fields_set:
                    val = getattr(op, k)
                    d[k] = _fix_col(val, by_exact, by_norm, allow_special=True) if val else None
                    if k in ("v", "v2") and d[k] and d[k] not in SPECIAL_COLUMNS and by_exact[d[k]].get("type") != "number":
                        raise ChangeError(f'role {k} needs a column of numbers, "{d[k]}" is not')
        ops.append(d)
    return ops


def _clean_text(edits: dict) -> dict:
    for k in ("title", "xLabel", "yLabel", "legendTitle", "note", "source", "refLabel"):
        if isinstance(edits.get(k), str):
            edits[k] = re.sub(r"[≥≤→·]", "", edits[k]).strip()
    return edits


def _fix_shade(shade: list[dict], known: list[str]) -> list[dict]:
    out = []
    for band in shade:
        d = dict(band)
        for k in ("from", "to"):
            if isinstance(d.get(k), str):
                d[k] = _fix_names([d[k].strip()], known, f"shade {k}")[0]
        if isinstance(d.get("label"), str):
            d["label"] = re.sub(r"[≥≤→·]", "", d["label"]).strip()
        out.append(d)
    return out


def _fix_controls(controls: list, by_exact, by_norm, renamed_to: list, style: str = "ceps") -> list[dict]:
    out, seen = [], set()
    for i, c in enumerate(controls):
        where = f"controls.{i}"
        if c.type in ("legend", "checkbox"):
            if c.type in seen:
                raise ChangeError(f"{where}: only one {c.type} control is allowed")
            if c.column or c.options:
                raise ChangeError(f"{where}: a {c.type} control takes no column or options, it works on the drawn items")
        seen.add(c.type)
        d = c.model_dump(exclude_none=True)
        if c.type in ("switch", "slider", "select"):
            if bool(c.column) == bool(c.options):
                raise ChangeError(f"{where}: a {c.type} needs either a column or a list of options, not both")
            if c.column:
                col = by_exact[_fix_col(c.column, by_exact, by_norm)]
                d["column"] = col["name"]
                n = col.get("distinct") or len(col.get("values") or [])
                if c.type == "switch" and n != 2:
                    raise ChangeError(f'{where}: a switch on a column needs exactly 2 values, "{col["name"]}" has {n}. Use a select instead')
                if c.type == "select" and (col.get("type") == "number" or not 2 <= n <= 24):
                    raise ChangeError(f'{where}: a select needs a column of 2 to 24 names, "{col["name"]}" has {n} {col.get("type")} values')
                if c.type == "slider" and (n < 2 or (col.get("type") == "category" and n > 60)):
                    raise ChangeError(f'{where}: a slider needs a time or number column with 2 or more values, "{col["name"]}" does not fit')
            else:
                if c.type == "switch" and len(c.options) != 2:
                    raise ChangeError(f"{where}: a switch has exactly 2 options")
                if c.type == "select" and len(c.options) > 12:
                    raise ChangeError(f"{where}: a select has at most 12 options")
                opts = []
                for j, o in enumerate(c.options):
                    if "kind" in o.set or "controls" in o.set or "logo" in o.set:
                        raise ChangeError(f"{where}.options.{j}: an option cannot change the chart kind, the controls or the logo")
                    try:
                        edits = SpecEdits.model_validate(o.set, context={"style": style}).model_dump(exclude_unset=True)
                    except ValidationError as e:
                        msgs = [f'{".".join(map(str, er["loc"]))}: {er["msg"]}' for er in e.errors()[:4]]
                        raise ChangeError(f"{where}.options.{j}.set: " + "; ".join(msgs)) from e
                    if not edits and not o.ops:
                        raise ChangeError(f"{where}.options.{j}: each option needs set or ops")
                    opts.append({"label": o.label.strip(), "set": _clean_text(edits), "ops": _fix_ops(o.ops, by_exact, by_norm, renamed_to)})
                d["options"] = opts
        out.append(d)
    return out


def fix_logo(edits: dict, reply: str, style: str, current) -> tuple[dict, str]:
    if "logo" not in edits:
        return edits, reply
    asked = edits.pop("logo")
    if style != "aiw":
        return edits, reply if "no logo" in reply.lower() else NO_LOGO_FOR.get(style, NO_LOGO)
    if asked is None:
        edits["logo"] = None
        return edits, reply
    now = current if isinstance(current, dict) else {}
    pos = asked.get("pos") or (now.get("pos") if now.get("pos") in LOGO_POS else "bottom-right")
    show = asked["show"] if asked.get("show") is not None else True
    edits["logo"] = {"show": show, "pos": pos}
    return edits, reply


def validate_change(obj: dict, columns: list[dict], chart_names: list[str], kind: str | None = None, caps: bool = False,
                    style: str = "ceps", logo: dict | None = None) -> dict:
    style = style if style in PALETTES else "ceps"
    try:
        ch = Change.model_validate(obj, context={"style": style})
    except ValidationError as e:
        msgs = [f'{".".join(map(str, er["loc"]))}: {er["msg"]}' for er in e.errors()[:6]]
        raise ChangeError("Schema error. " + "; ".join(msgs)) from e
    by_exact, by_norm = _col_lookup(columns)
    renamed_to = []
    ops = _fix_ops(ch.ops, by_exact, by_norm, renamed_to)
    edits = ch.set.model_dump(exclude_unset=True)
    if ch.set.controls is not None:
        edits["controls"] = _fix_controls(ch.set.controls, by_exact, by_norm, renamed_to, style)
    known_names = list(dict.fromkeys(list(chart_names or []) + renamed_to
                                     + [str(v) for c in columns if c.get("type") != "number" for v in (c.get("values") or [])]))
    if edits.get("highlight"):
        edits["highlight"] = _fix_names(edits["highlight"], known_names, "highlight")
    if edits.get("dashed"):
        edits["dashed"] = _fix_names(edits["dashed"], known_names, "dashed")
    if edits.get("shade"):
        edits["shade"] = _fix_shade(edits["shade"], known_names)
    if edits.get("colors"):
        keys = _fix_names(list(edits["colors"].keys()), known_names, "colors")
        edits["colors"] = dict(zip(keys, edits["colors"].values()))
    edits, reply = fix_logo(edits, ch.reply.strip()[:400], style, logo)
    none = NO_LOGO_FOR.get(style, NO_LOGO)
    if reply == none and (edits or ops or ch.patch is not None):
        reply = (ch.reply.strip() + " " + none).strip()[:400]
    out = {"reply": reply, "set": _clean_text(edits), "ops": ops}
    if ch.patch is not None:
        if edits.get("kind"):
            raise ChangeError("A patch cannot come with a kind change, because switching the chart type drops every patch. Send the kind change alone")
        out["patch"] = {"code": check_patch(ch.patch.code), "note": re.sub(r"[≥≤→·]", "", ch.patch.note).strip()[:160] or ch.reply.strip()[:160]}
    if caps:
        out = drop_unsupported(no_map_labels(out, kind), kind)
    return out


def drop_unsupported(change: dict, kind: str | None) -> dict:
    edits = change.get("set") or {}
    target = edits.get("kind") or kind
    bad = unsupported(edits, target)
    if not bad:
        return change
    return {**change, "set": {k: v for k, v in edits.items() if k not in bad}, "dropped": bad}


def dropped_error(dropped: list[str], kind: str | None) -> str:
    name = kind_name(kind)
    return (f"These fields do nothing on a {name}, so they were removed: {', '.join(dropped)}. Do not use them on this chart. "
            f"Keep the rest of your change. If the request needs what they would do, draw it with a patch. "
            f"If a patch cannot do it either, leave it out and say plainly in the reply that a {name} cannot show it.")


def honest_reply(change: dict, dropped: list[str], kind: str | None) -> str:
    fix = say_missing(dropped, kind)
    if not (change.get("set") or change.get("ops") or change.get("patch")):
        return fix
    return (fix + " " + change.get("reply", "")).strip()[:400]


def _short(v, n=60):
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def build_messages(message: str, recipe: dict, columns: list[dict], sample: list, history: list[dict],
                   chart_rows: list, chart_names: list[str], outline: str = "", patch_error: dict | None = None,
                   no_effect: dict | None = None, style: str = "ceps") -> list[dict]:
    recipe = {k: v for k, v in (recipe or {}).items() if k not in ("rows",) and v not in (None, "", [], {})}
    cols = []
    for c in columns[:40]:
        e = {"name": c["name"], "type": c.get("type"), "distinct": c.get("distinct")}
        vals = c.get("values")
        if c.get("type") == "number":
            e["min"], e["max"] = c.get("min"), c.get("max")
        elif vals:
            e["values"] = [_short(v, 40) for v in vals[:60]]
        else:
            e["examples"] = [_short(v, 40) for v in (c.get("samples") or [])[:4]]
        cols.append(e)
    ctx = {
        "chart": recipe,
        "columns": cols,
        "sample_rows": [[_short(x, 30) for x in r] for r in (sample or [])[:5]],
        "drawn_items": [_short(n, 40) for n in (chart_names or [])[:40]],
        "drawn_rows_preview": (chart_rows or [])[:8],
    }
    if outline:
        ctx["svg_outline"] = outline[:OUTLINE_MAX]
    kind = recipe.get("kind")
    if kind in CAPS["kinds"]:
        ctx["fields_this_chart_draws"] = CAPS["kinds"][kind]
    msgs = [{"role": "system", "content": system_prompt(style)}]
    for h in (history or [])[-8:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        text = _short(h.get("text") or "", 300)
        if text:
            msgs.append({"role": role, "content": text})
    msgs.append({"role": "user", "content": "Current chart and data:\n" + json.dumps(ctx, ensure_ascii=False, default=str)
                 + "\n\nRequest: " + message.strip()[:600]})
    if patch_error and patch_error.get("code"):
        msgs.append({"role": "assistant", "content": json.dumps({"reply": "", "patch": {"code": str(patch_error["code"])[:PATCH_MAX]}}, ensure_ascii=False)})
        msgs.append({"role": "user", "content": "That patch failed in the browser with this error: " + str(patch_error.get("error") or "")[:300]
                     + "\nThe chart was left as it was. Reply again with one JSON object. Fix the patch, or use fields instead, or change nothing and say why."})
    elif no_effect:
        msgs.append({"role": "assistant", "content": json.dumps(no_effect.get("change") or {}, ensure_ascii=False, default=str)[:PATCH_MAX + 1500]})
        msgs.append({"role": "user", "content": "That change had no visible effect. " + str(no_effect.get("detail") or "")[:1500]
                     + "\nThe chart was left as it was. Do not send the same fields again. Reply with one JSON object."
                     + " If svg_outline shows the chart already has what the request asks, change nothing and say plainly that the chart did not change."
                     + " Otherwise draw it with a patch, working from svg_outline. Never draw a second copy of something already drawn."})
    return msgs
