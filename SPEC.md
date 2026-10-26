# Chart spec and recipe

Two contracts keep the pieces apart.

1. The **spec** is what `charts.js` draws. The data side builds it. The chart side never looks at the
   raw file.
2. The **recipe** is what the chat edits. It says how to turn the uploaded table into a spec. The AI
   only ever changes the recipe, through a validated change. It never sees `charts.js` or writes HTML. For what no
   field can do it may add a drawing patch, a short d3 function that runs in a sandboxed frame. See "Drawing patches".

```
uploaded file  --/api/viz/parse-->  table (rows + columns)
table + recipe --app.js pipeline-->  spec
spec           --QV.render-------->  SVG in the Franri house
```

## charts.js

```js
QV.render(svgElement, spec, opts)   // opts: {width, still, noResize, noControls, fitH, patches}. Draws in the house spec.style names
QV.ready                            // promise, resolves when Carlito 400 and 700 are loaded. AI World never waits on it
QV.exportMarkup(svgElement)         // redraws at 760 px with patches, returns {markup, W, H, transparent}, Carlito embedded for CEPS only
QV.pngFromMarkup(m, filename)       // turns that markup into a 4x PNG and downloads it
QV.exportPNG(svgElement, filename)  // both steps at once, for pages without the frame
QV.exportHTML(spec, svgElement, extra)  // one self-contained HTML page as a string. extra: {ctlInit, geoUsed, patches}
QV.outline(svgElement, maxChars)    // compact text outline of the drawn SVG, for the chat model
QV.embeddedFonts(), QV.FRAME_CSP    // Carlito as base64 CSS, and the policy used by the frame and the HTML export
QV.countryId(name), QV.isEU(name), QV.regionCountry(names), QV.loadRegionIndex()
QV.flagKeys(spec)                   // flag keys of every country and EU name in the rows and control versions
QV.colors                           // the named colours of the style drawn last. The chat may also use any hex code
```

`app.js` no longer calls `QV.render` itself. It calls `QVFrame.mount(iframe)` from `web/frame-host.js` and talks to
the chart through that. The page still loads `charts.js` for the data helpers, the font CSS and the PNG step.

## The chart frame

The chart lives in `<iframe id="chart" sandbox="allow-scripts">`, without `allow-same-origin`. The frame has an
opaque origin, so code in it can never read the session cookie, call `/api` or touch the page.
Uploaded files can carry text written to trick the model, and the model now writes code, so this is the real guard.

`frame-host.js` fetches d3, d3-sankey, topojson, `ceps-theme.js`, `aiw-theme.js`, `franri-theme.js`, `charts.js`, `frame-runtime.js` and the Carlito CSS once,
and puts them inline in the frame's `srcdoc`. The frame carries this policy as a meta tag:

```
default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; font-src data:;
img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'
```

The page itself is served with `frame-src 'none'`, so the frame cannot navigate itself to another site to leak data.
Before any patch runs, `frame-runtime.js` also removes `fetch`, `XMLHttpRequest`, `WebSocket`, `EventSource`,
WebRTC, workers, storage, `window.open` and `sendBeacon` from the frame.

The page and the frame talk only with `postMessage`. The page checks that each message comes from the frame window.

| Page to frame | Frame to page |
|---|---|
| `render` with spec, `fitH`, `still` and patches | `ready` once Carlito has loaded |
| `clear` | `rendered` with the patch errors, the spec fields the draw used, the rows that fit and the time taken |
| `png` | `png` with the SVG markup, width and height |
| `state` | `state` with the control positions and the map outline used |
| `outline` | `outline` with the text outline |
| `sig` with a spec and its patches | `sig` with a hash of that chart drawn off screen, or null |
| `geo` with the map outlines asked for | `need` for a map outline file, `size` with the height |

The page only answers `need` for `vendor/countries-50m.json` and `geo/regions/<ISO3 or index>.json`, and clamps every
height and size it gets back. The frame sets its own height from what it draws. Fit-to-screen sizing, the controls,
tooltips, the view transition between steps and the 390 px layout all work as before through the frame.
A view transition waits up to 700 ms for the frame to finish drawing.

If a render gets no answer within 6 seconds, the page throws the frame away and builds a new one.

The PNG is drawn by the frame and turned into an image by the page. The page puts the frame's markup only into an
image, so no script in it can run. The HTML export is built by the page from the spec, the patches and the frame's
`state`. It carries the same policy as a meta tag, so a patch cannot reach the network from the file either.
An export opened from disk has no sandbox, which is fine because the user made it.

There are three themes. `web/ceps-theme.js` started as `houses/ceps/theme.js` from the dataviz skill.
`web/aiw-theme.js` holds the AI World house. `web/franri-theme.js` holds the Franri house.
All three come from CEPS QuickViz through the sync. They fill `window.QV_THEMES` and have the same keys.
`window.CEPS` stays as a second name for the CEPS theme.
`charts.js` picks the theme from `spec.style` at every draw. A missing style means CEPS.
So this app sets `style: "franri"` on every spec. The page loads only `franri-theme.js`.
The chart frame loads all three, the same way CEPS does.
It reads every colour and font from the theme. It has no colour or font of its own.

## Spec shape

```json
{
  "kind": "bar",
  "title": "AI use by enterprises, 2024",
  "xLabel": "", "yLabel": "Share of enterprises (%)", "unit": "%",
  "decimals": null, "orientation": "auto", "valueLabels": "auto", "stack": "percent",
  "highlight": ["Belgium"], "colors": {"Germany": "navy"},
  "legendTitle": "", "note": "", "source": "Eurostat", "sourceUrl": "",
  "rows": [{"cat": "Belgium", "v": 24.7}, {"cat": "EU27", "v": 13.5}]
}
```

`xLabel` always names the category or time axis and `yLabel` the value axis, whatever the orientation.
A horizontal bar or stacked bar puts `xLabel` on the left and `yLabel` at the bottom. Scatter is the one
exception: `xLabel` names v on x and `yLabel` names v2 on y.

The chart frame is at most 760 px wide. On screen the chart renders at the width of its frame, never under
320 px, so text keeps the 13 px floor on phones. The base height is 520 px, or 480 px when the chart is under
560 px wide. Some kinds grow taller to fit many rows, and `height` overrides the base.
Heatmap cells are always square. The grid takes the largest cell that fits both ways and sits centred.
Without fit mode or a set height, a cell is at most 72 px, unless its number needs more room.
Row labels may use the width the square cells leave free, up to 220 px, as long as each cell still fits its number.
In fit-to-screen mode, on screens at least 901 px wide and 700 px tall, `app.js` measures the height left for the
frame and passes it as `fitH`. The chart then takes that height minus any controls, between 320 px and 0.8 times its
width. Smaller screens get no `fitH`.

A chart never scrolls inside its frame. Each draw has a space: `fitH` in fit mode, a set `height`, or else 900 px.
Kinds that grow for many rows, a horizontal bar, stacked bar, heatmap and dot range, grow only up to that space.
Their rows get thinner down to 18 px. `fitRows` in `charts.js` works out how many rows fit at 18 px and sends it
back in `rendered` as `fit: {n, cap}`, where `n` is the rows it was given. When even 14 px rows would not fit, it
draws the first ones that do and notes "Showing the first k of n, to fit the screen." In fit mode the SVG is never
taller than `fitH`. A set `height` above it is scaled down to fit, never scrolled.

`fitTop` in `app.js` reads `fit` after every draw. When the rows do not fit and the user has set no top N, it sets
an automatic one, `{n, other: false, by: "latest", column, auto: true}`, keyed to the `cat` column. N is `cap`
minus the totals drawn, because totals never count toward N. So the usual Top N rules hold: totals stay as
reference rows and rates get no Other. The note reads "Showing the top 15 of 29 countries, to fit the screen."
On a bar chart with an automatic top N and no set orientation, the bars stay horizontal. On a larger screen N
goes up again, but only by two or more, so N cannot flip between two values. When every row fits, the automatic
top N is removed. Any `top_n` op from the chat replaces it, and n 0 is kept as `{n: 0}`, which means show all.
More rows than fit then get rows down to 14 px. `recipeForAI` sends an automatic top N with `fit: "screen"`.
The frame keeps `scrollbar-gutter: stable`, the fixed SVG height in fit mode and the 3 px redraw threshold.
A PNG export is always redrawn off screen at 760 px wide, so every PNG has the desktop size whatever the screen.
The HTML export draws at the window width, between 320 and 760 px.

## Layout fields

All are optional. A missing or null field means automatic, which is the house default.

| Field | Values | Kinds |
|---|---|---|
| `legend` | auto, on, off | every kind with a legend, also the heatmap colour bar, the map colour key and the donut list |
| `legendPos` | auto, top, bottom, right, left | the same. Auto is bottom, or right for the donut |
| `legendDir` | auto, horizontal, vertical | the same. Auto is horizontal at top and bottom, vertical at the sides |
| `legendSort` | auto, az, za, value, reverse | categorical legends and the donut list. value is largest first |
| `tickAngle` | 0 to 90 | the bottom axis labels. 0 keeps them flat. Auto tilts long labels 35 degrees |
| `grid` | auto, off, value, both | value draws lines across the value axis only. both adds lines along the other axis |
| `valueMin`, `valueMax` | numbers | the value axis. In a scatter, the y axis. Marks past the ends are clamped |
| `valueLog` | true, false | log value axis. Ignored with a note when a value is 0 or below. Not for stacked kinds |
| `xMin`, `xMax`, `xLog` | numbers, true, false | the scatter x axis, and the histogram range |
| `ticks` | 2 to 12 | about how many value axis ticks |
| `fontSize` | small, normal, large | ticks and labels. small is 13 and 15, normal 15 and 16, large 16 and 18. Titles stay 18 |
| `barGap` | 0 to 0.8 | gap between bars as a share of the slot. bar, stacked_bar, histogram, heatmap cells |
| `lineWidth` | 1 to 6 | line and bump. Faded lines get 0.6 of it |
| `markers` | auto, on, off | dots on line and bump points |
| `curve` | smooth, straight, step | line and stacked_area |
| `titleAlign` | left, center, right | the chart title |
| `refLine`, `refLabel` | number, text | a dashed reference line on the value axis. bar, line, stacked_area, stacked_bar absolute, scatter, dot_range |
| `trendline` | true, false | a dashed least squares line in a scatter, in log space on log axes |
| `pointSize` | small, normal, large | scatter dots |
| `donutHole` | 0 to 0.8 | 0 makes a pie. The centre total shows from 0.45 |
| `height` | 320 to 900 | chart height in px |
| `fontSize` as a number | 9 to 24 | ticks and labels in px. Labels are one px bigger, axis titles three |
| `titleSize` | 12 to 32 | the chart title in px. The default is 18 |
| `fontStyle` | `{part: face}` | bold and italic text per part. See below |
| `dimSize` | small, normal, 9 to 24 | the size of the names that are not highlighted. Only with a highlight. See below |
| `textHalo` | auto, on, off | a white halo behind value, axis and node labels so they read over marks and gridlines |
| `textColor` | black, green, navy, red, grey, teal, slate | every chart text |
| `background` | white, transparent, light grey, pale green, pale blue, pale yellow | the chart background. transparent is for slides, and the PNG keeps it |
| `border` | on, off | a thin grey frame round the whole chart |
| `padding` | 0 to 48 | space round the chart edges in px. The default is 16 |
| `labelMax` | 4 to 60 | cuts category, series and legend names after this many characters, with an ellipsis and the full name on hover |
| `thousands` | auto, comma, space, none | the thousands separator |
| `decimalMark` | point, comma | the decimal separator |
| `numberStyle` | auto, short, full | short writes 12.5k and 3.2M, full writes every digit |
| `axisTitles` | on, off | hides both axis titles without deleting their text |
| `opacity` | 0.15 to 1 | bars, areas, dots, cells and lines |
| `lineStyle` | solid, dashed, dotted | every line of a line or ranking chart |
| `dashed` | list of series names | draws those series dashed |
| `markerShape` | circle, square, diamond, triangle | dots on lines, scatter points and dot range dots |
| `flags` | auto, on, off | country flags before country names. See "Country flags" |
| `shade` | list of up to 3 `{from, to, label, opacity}` | a paper-coloured wash over a range of the time or category axis, so the marks in it read lighter. line, stacked_area, bar, stacked_bar. See "Shaded ranges" |
| `controls` | list of up to 4 | interactive controls, see below |

`valueLabels` "on" also prints every line point when there are three series or fewer, segment values at the
right edge of a stacked area, counts on histogram bars and both values on a dot range. "off" also hides the
treemap and donut values. When the legend is off on a donut, slice names go on the slices.
On a donut "on" also prints each slice's share inside the slice, with or without a legend. A slice too thin for
its label gets none, because the legend line already gives its share. Without a legend, "on" puts the name and
the share on the slice when the ring has room for two lines. On a treemap "on" prints the value alone on a tile
too small for its name.
On a sankey "on" adds each node's total after its name. Auto and off leave it out.
A treemap shows a legend of its tiles only when `legend` is "on". It then follows `legendPos`, `legendDir`,
`legendSort` and `legendTitle` like any other legend.
Maps print no values. They show each value on hover, and the chat says so when asked for map labels.
On a dot range the value axis moves right when a low value's label would touch the item names.

`fontStyle` maps text parts to "bold", "italic", "bold italic" or "normal". The parts are these.

| Part | Text |
|---|---|
| `title` | the chart title |
| `axisTitle` | both axis titles, xLabel and yLabel |
| `tickLabels` | axis tick labels, category names along an axis, heatmap row and column names, ranking end labels, flow chart node names |
| `valueLabels` | numbers printed on marks, stacked bar totals, treemap tile names, names inside donut slices, scatter point names |
| `legend` | legend items and title, the heatmap colour bar, the map colour key, the donut list |
| `note` | the note |
| `source` | the source line |

A missing part keeps the house look, in CEPS and AI World alike. The house draws the title, the axis titles, the
legend title and a few small value labels bold, and the rest normal. "italic" means italic and not bold, so a bold
part made italic is "bold italic". "normal" means neither. Highlighted names and EU names stay bold whatever the face.
The donut centre total, reference line labels and shade labels keep their own look.
`charts.js` reads `fontStyle` once per draw. `fw`, `fi` and `fm` give the weight, the style and the measuring font of a
part. Every place that measures a part's text uses `fm`, so bold text wraps, clips and makes room as it should. A face
that is not set adds no `font-style` attribute, so the SVG of a chart without `fontStyle` stays the same.
The PNG and HTML exports draw through the same code, so they keep the faces.
In the chat, `set: {fontStyle: {source: "italic"}}` changes only the source. `applyChange` merges it into the
parts already set. null for a part puts that part back, and `fontStyle` null resets every part.
The server reads face words and part names loosely. "Bold-Italic" becomes "bold italic", "regular" becomes
"normal", and `xLabel` or `yLabel` become `axisTitle`. An unknown part such as `subtitle` is an error the model
gets back once.

`dimSize` sets the size of the names that are not highlighted. Highlighted names and EU names keep their size.
"small" is 3 px below the size the name would have, and never below 9. A number is the size in px, 9 to 24, read
like `fontSize`. "normal" gives the names their usual size. null resets.
It works on bar and stacked bar category names, heatmap row names, dot range names, ranking end labels and scatter
point names. On a bar and a dot range the numbers next to a dimmed name get the same size.
Stacked bar totals, segment numbers and heatmap cell numbers keep their size. A line chart draws no names at the
line ends, so it has no `dimSize`.
It only acts when `highlight` names at least one of the names in that set. A stacked bar with a highlighted
series has no highlighted category, so its category names keep their size. Then `charts.js` does not read
`dimSize`, so `used` leaves it out and the chat says it did not change.
`dimOf` in `charts.js` gives the size of each name. Every place that measures these names uses it. That covers
`labelWidth` for the left margin, `clip`, wrapping, the flag room and the bar direction test. So smaller names make
the margin narrower, and a bar chart can turn vertical at a narrower width.
In the chat, "Make the other names smaller" is `{dimSize: "small"}`. With no highlight set the chat changes nothing
and says the names need a highlight first.

The heatmap colour bar and the map colour key share one key. Horizontal it is a bar or a row of cells with
labels under it. Vertical it is a bar with the low value at the bottom and the high value on top, or a column
of swatches with the highest class on top. The plot shrinks to make room on whichever side it goes.
Under 560 px of chart width, a legend or key placed left or right goes to the bottom instead. When the class
labels of a map key would crowd, the key labels the edges between cells, such as `5%` and `10%`. If even those
crowd, the key becomes a column.

## Which fields each kind draws

Not every field does something on every kind. A treemap has no axes, a histogram has one series and so no
legend, and a ranking chart prints ranks, so it has no thousands separator. The one list of what each kind
really draws is `web/capabilities.json`.

| Key | Holds |
|---|---|
| `always` | `kind` and `controls`. Never checked |
| `common` | fields every kind draws: title, titleAlign, titleSize, note, source, height, fontSize, textColor, background, border, padding, labelMax, opacity, fontStyle |
| `kinds` | per kind, the other fields it draws |
| `names`, `labels` | plain words for the kind and each field, used in the chat replies |

Short version of `kinds`. Axis means xLabel, yLabel, axisTitles, tickAngle and grid. Numbers means unit, decimals,
thousands, decimalMark and numberStyle. Legend means legend, legendPos, legendDir, legendSort and legendTitle.

| kind | Draws |
|---|---|
| bar | axis, numbers, legend, orientation, valueLabels, highlight, dimSize, colors, value range and log, ticks, barGap, refLine, textHalo, flags, shade. The legend only appears with a highlight |
| line | axis, numbers, legend, valueLabels, highlight, colors, value range and log, ticks, lineWidth, markers, curve, refLine, textHalo, lineStyle, dashed, markerShape, flags, shade |
| stacked_area | axis, numbers, legend, valueLabels, highlight, colors, value range, ticks, curve, refLine, textHalo, flags, shade |
| stacked_bar | axis, numbers, legend, orientation, stack, valueLabels, highlight, dimSize, colors, value range, ticks, barGap, refLine, textHalo, flags, shade. Range and refLine only when absolute |
| scatter | axis, numbers, legend, valueLabels, highlight, dimSize, colors, value and x range and log, ticks, refLine, trendline, pointSize, markerShape, textHalo, flags |
| histogram | axis, numbers, valueLabels, colors, value range, x range, ticks, barGap, textHalo |
| heatmap | xLabel, axisTitles, tickAngle, numbers, legend without legendSort, valueLabels, highlight, dimSize, barGap, textHalo, flags |
| treemap | numbers, legend, valueLabels, highlight, colors, textHalo |
| donut | yLabel, numbers, legend, legendPos, legendSort, valueLabels, highlight, colors, donutHole, textHalo |
| sankey | numbers, valueLabels, highlight, colors, textHalo |
| bump | axis, highlight, dimSize, colors, lineWidth, markers, lineStyle, dashed, markerShape, textHalo, flags |
| dot_range | axis, numbers, legend, valueLabels, highlight, dimSize, colors, value range and log, ticks, refLine, markerShape, textHalo, flags |
| map | numbers, legend without legendSort, highlight, textHalo |

Three things keep the chat truthful.

1. The server. `app/capabilities.py` loads the JSON. `validate_change(..., kind, caps=True)` removes every
   field the kind does not draw, after the map label rule. The kind is the one in the change, else the current one.
   `null` always passes, because it only resets. When a field is removed, `/api/viz/chat` asks the model once more.
   It names the removed fields and asks for a patch, or for a plain reply that the chart cannot show it. If the
   second reply still uses such a field, it is removed and the reply starts with "A histogram cannot show legend,
   so that part did not change.", or is only that when nothing else is left.
2. The prompt. The model gets `fields_this_chart_draws`, the row for the current kind, and is told never to set
   or claim anything outside it.
3. The frame. During a draw `charts.js` wraps the spec in a proxy that notes every field the renderer reads.
   Shared helpers only read a field when they will use it. The legend helper returns before reading `legend` when
   there are no items, and the axis helper skips `valueLog` for linear only axes. A few fields are noted by hand:
   the number fields when a number is formatted, `ticks` when a tick count is used, `titleSize` when a title is
   drawn, `textHalo` when some text got the halo. `rendered` carries this list as `used`, or `null` when nothing
   was drawn, such as a map still loading. After a chat change `app.js` compares the `set` fields with `used`.
   A field that was set to a real value and not read did not take effect, and the bubble then reads "The legend
   did not show on this bar chart, so that part did not change." in place of the model's claim.
4. The no-change check. A field can be read and still change nothing, such as `legend` "on" when the legend
   already shows. After a chat change is drawn, `applyReply` in `app.js` calls `chart.sig` for the recipe before
   and the recipe after. The frame draws each spec off screen twice, once at the on-screen width and fit height,
   and once at 760 px. It hashes the SVG markup of both, with the random gradient and clip ids taken out. When the
   spec has controls, the controls and rows go into the hash too, since a hidden step can change. A blank draw
   returns no signature, and then nothing is checked. When both signatures match, the change is taken back and
   dropped from undo. The model's claim is not shown. A change of fields or steps is sent back once as `no_effect`,
   with what was set, its old value and whether the renderer read it. The model is asked for a patch, or to say
   plainly the chart did not change. If the second reply is not a visible change, or its patch fails, the bubble
   reads "The chart did not change, so nothing was applied." A first reply that was a patch and changed nothing gets
   that line at once, with no second call. Only `sendChat` runs this check. Resize, tab clicks, controls and the
   slider never call `chart.sig`.

`tests/test_capabilities.py` keeps the table and `charts.js` together. It reads each renderer and every helper
it calls, and fails when a kind stops reading a field the table claims, or reads one the table does not list.

Switching kind drops `valueMin`, `valueMax`, `valueLog`, `xMin`, `xMax`, `xLog`, `refLine` and `refLabel`,
because the axes change meaning. The other layout fields stay.

`rows` is a tidy table. Each row uses only the fields its kind needs. Rows are drawn in the order given,
so sorting happens in the pipeline.

| Field | Meaning |
|---|---|
| `cat` | A category name |
| `series` | A sub-group name |
| `t` | A time step such as "2021" or "2021-Q3", sorted as given |
| `v` | The main number |
| `v2` | A second number, only for scatter |

| kind | Uses | Notes |
|---|---|---|
| bar | cat, v | vertical when every name fits flat under its bar, else horizontal. See "Bar direction". `orientation` overrides |
| line | t, series, v | series optional |
| stacked_area | t, series, v | |
| stacked_bar | cat, series, v | `stack` "percent" (default) or "absolute". Horizontal unless `orientation` is "vertical" |
| scatter | v, v2, series, cat | v on x, v2 on y. cat names points, up to 24 are labelled |
| histogram | v | one row per observation |
| heatmap | cat, series, v | cat on rows, series on columns |
| treemap | cat, v | |
| donut | cat, v | up to 6 slices, the rest goes to Other |
| sankey | cat, series, v | cat is the source, series the target |
| bump | t, cat, v | v is the rank, 1 is top |
| dot_range | cat, series, v | exactly two series are the two dots. More than two draws nothing |
| map | cat, v | countries, or the regions of one country. `geo` may force an ISO3 code |

A dot range takes its two dots from a series column with exactly two values, or from two number columns.
Two number columns qualify when their names share a 4 letter start or end and their ranges overlap, such as
`ai_use_pct_all_firms` and `ai_use_pct_large_firms`. They are then fed as the two series, labelled with Gemini's
column labels or the part of the names that differs. A time column only works once it is filtered to two periods.
When nothing fits, dot range is not offered. A stacked bar or heatmap never uses a group that puts each item in
only one group, and a sankey never uses a column that maps one to one onto the source. The wide fallback of these
kinds stacks number columns that pass the same name and range test. A stacked bar or stacked area also stacks
columns that fail it, when every one has a bare name with no unit word, such as LNG, Oil, Coal and Nuclear. Words
like pct, per, share, eur or million, and columns named like a total, keep a column out.

Maps match countries by name, ISO2, ISO3 and the Eurostat codes `EL` and `UK`. Regions match by name, ISO 3166-2
code such as `DE-BY`, and NUTS 1 or NUTS 2 code such as `DE2` or `DE21`. The NUTS shapes are GISCO NUTS 2024
for the EU, EFTA and candidate countries, and NUTS 2021 for the United Kingdom. Changed 2021 codes match when the
region kept its name. NUTS 3 does not match.

### Bar direction

A bar chart with `orientation` "auto" or unset runs vertical only when the bars fit. It is horizontal when there are
more than 30 bars. It is also horizontal when the widest category name does not fit flat in its bar slot. That test
works out the real slot the vertical chart would get. It takes the plot width at the width being drawn, less the value
axis and a side legend, and the same band padding as the vertical draw. A name fits when it is at least 6 px narrower
than the slot, which is the same rule the bottom axis uses to tilt its labels. Names are measured at the tick font
size, bold when they are highlighted, EU names, or bold through `fontStyle`. A name made smaller by `dimSize` is
measured at its smaller size. So a vertical bar chart never tilts its
names unless `tickAngle` asks for it. A `tickAngle` above 0 keeps the chart vertical, because the user asked for tilted
names. Bars named by years, dates, quarters or halves, such as 2023, 2023-05 or 2023 Q1, always stay vertical, so
time reads left to right. Their names tilt when they do not fit. An explicit "vertical" or "horizontal" always wins.
A stacked bar stays horizontal unless set to "vertical".
No other kind has an orientation.

The test only gets easier as the chart gets wider, so each set of bars has one width where it turns vertical. A resize
can cross it once and never flips back and forth. A taller horizontal chart can add a page scrollbar, and the
narrower page keeps it horizontal. The frame reports the direction it drew as `orient`, as before.

Look fields: `highlight` turns the named items green and the rest grey. On a bar chart each highlighted name on the axis
takes the colour of its own bar. EU aggregates (EU27, EU,
euro area) are always navy, following the house. `colors` maps an item to a colour. That is one of the named
colours in `QV.colors` (green, navy, red, grey, light grey, yellow, light green, teal, slate, rose), or any hex code
such as `#ff8800` or `#f80`. Users may pick any colour they like.
The server lowercases each colour and turns 3 digit hex into 6 digits. Anything else is refused, such as "orange",
`rgb(...)` or text with `;` or `url(`. The renderer checks again with `paint` and ignores what is not a colour.
Text on a coloured fill turns dark or white by the fill's lightness, through `textOn`.

The categorical palette is ten colours in this order. Green, navy, red, grey, yellow `#f2c64b`, teal, slate, rose,
light grey `#a3a3a1`, light green. It is `CAT` in `charts.js` and `cat` in `ceps-theme.js`. When EU27 is drawn,
navy is skipped, because navy stays for the EU.

In AI World, `cat` in `aiw-theme.js` is blue, red, emerald, amber, violet, cyan, orange, pink, slate and lime.
Amber is moved after emerald, so red and amber are never neighbours in a series. When EU27 is drawn, blue is
skipped, because blue stays for the EU. A highlight is red. The CEPS colour names still work in AI World.
Each one maps to the nearest AI World colour, so navy is the AI World blue and green is emerald.

## Shaded ranges

`shade` tints a run of the time or category axis, for example projection years. The chat sends
`{"shade": {"from": 2026, "label": "Projection"}}`, and the server always stores a list of at most 3 ranges.
`from` and `to` are a year, a number or an item name. The server turns "2026" into 2026 and matches a name the
same loose way as `highlight`. A missing `from` starts at the start of the axis. A missing `to` runs to the end.
`label` is at most 30 characters. `opacity` is 0.1 to 0.9 and says how strong the wash is, 0.55 by default.
null or [] removes it.

`charts.js` draws each range as a `rect.qv-shade-band` in `g.qv-shade` inside `g.qv-plot`, filled with the
paper colour of the chart. It sits over the marks and under the value labels. It spans the whole plot height, or
the whole plot width on horizontal bars, and never leaves the plot box, so the axis ticks, tick labels, axis
titles and legend stay as they are. On a time axis the band starts at the point of `from`. On bars it starts at
the edge of the bar slot. The label is drawn small at the top of the band, in the muted text colour, and is
left out when the band is too narrow. A name matches first. A number matches the first and last period whose
leading number is in range, so 2026 also matches "2026-Q1". A range that matches nothing draws nothing.
`shade` is not dropped when the kind changes, and the kinds that do not draw it ignore it.

The prompt says to use `shade`, never a patch, to shade or dim a range of the axis. It also says that a patch
which changes the opacity, fill or tint of marks selects marks only and never `g.axis`, `.qv-axis-title` or the
legend, because the axes live inside `g.qv-plot`. When the user asks to adjust an effect already on the chart, the
model changes it and keeps it, and it removes a shade or patch only when asked.

## Interactive controls

`recipe.controls` lists up to 4 controls that readers of the chart and of the HTML download can use.
The PNG shows the current state without the controls.

| type | Fields | What it does |
|---|---|---|
| `legend` | none | clicking a legend item hides or shows its series. Keyboard works too |
| `checkbox` | label, field auto, series or cat | one tick box per drawn item, plus "Show all". The last item cannot be unticked |
| `slider` | column, label, play | steps through the values of a time or number column, one at a time. play adds a play button, 1.1 s a step |
| `switch` | column with exactly 2 values, or 2 options | a two-way toggle. CEPS draws a switch. AI World draws the same button group as a select with buttons |
| `select` | column with 2 to 24 names, or 2 to 12 options, style dropdown or buttons | pick one value |

Each option of a switch or select holds `set` and `ops` like a chat reply, never `kind` or `controls`.
All controls sit in one centred row at the bottom of the chart, in both styles. The row is below the legend and the
footnote, directly above the source and logo row. It wraps and stays centred on a phone. Older recipes may still carry
`position`. It is ignored. A slider on the time axis reveals the steps up to the one picked.

`app.js` compiles the controls in `compileControls`. Each combination of steps becomes one variant: the rows and any
fields that differ from the main spec. At most 60 variants and 60,000 rows are allowed, else the change is refused.
`charts.js` draws the controls as HTML and swaps in the picked variant. The SVG keeps an empty band of the row's
height above the source row, and the row is placed over it with absolute positioning, so the chart and its controls
read as one picture. The PNG draws with `noControls`, so it has no band and no controls, the same as before. The HTML export starts
from the state on screen through `ctlInit`.

## Drawing patches

Some requests no spec field can express, such as one label moved by hand, leader lines or an arrow with a note.
For those the chat model returns a patch next to its `set` and `ops`:

```json
{"reply": "Moved Belgium's label to the left of its dot.",
 "patch": {"code": "const dot = svg.selectAll(\".qv-plot circle\").filter(d => d && d.cat === \"Belgium\"); ...", "note": "Belgium label left"}}
```

`code` is the body of a function `(svg, d3, data, size)`. `svg` is the d3 selection of the drawn chart, `data` the
drawn rows and `size` is `{width, height}`. It edits the drawn SVG after `charts.js` has drawn it.

- The recipe keeps `patches` as a list of `{code, note}`. They run in order after every draw: a resize, a control
  change, a spec edit, a map outline arriving, the PNG redraw and the HTML export.
- Each patch runs in try/catch. Every `for`, `while` and `do` loop gets a guard that throws after 1 second, and a
  patch that takes longer than 1 second also counts as failed. A failing patch is skipped and the chart is drawn
  again without it, so it looks as it did.
- When the newest patch fails, `app.js` takes the change back and asks the model once more, sending the code and the
  error as `patch_error`. If that fails too, the chat says the change did not work.
- "Undo this" removes the patch like any other change. Switching the chart type drops every patch, and the chat adds
  one grey line that says so. The server refuses a patch that comes with a kind change.
- The model never sees `charts.js`. It gets `svg_outline`, built in the frame by `QV.outline`: tags, classes, bound
  data, the element's own attributes and the box in SVG pixels, for marks, labels, axes and legend. It also shows
  `fill-opacity`, `stroke-opacity` and an inline style opacity or fill. Groups of the same
  element are cut to a sample. A cut group of small `g` elements, such as axis ticks, also lists the items that are
  faded, so the model can see a patch that dimmed tick labels. The whole outline is cut at 6,000 characters. `recipeForAI` sends the notes of the
  patches already applied as `patches`.
- The server checks the code before the browser sees it. It must be at most 4,096 characters. It may not use `fetch`,
  `XMLHttpRequest`, `WebSocket`, `EventSource`, WebRTC, `sendBeacon`, `import`, `eval`, `Function(`, `constructor`,
  `document.cookie`, `parent`, `top`, `frames`, `opener`, `window`, `globalThis`, `location`, `navigator`,
  `postMessage`, storage, `window.open`, timers, transitions, `document.write` or the d3 file loaders.
  `parent`, `top` and the names after `constructor` are checked outside strings and comments, and `.top` as a property is fine.
  A hit is sent back to the model as an error, like any bad reply. This list is a cheap first layer. The frame is the guard.

## Country flags

A small flag sits before each country name. It shows on the category axis of a bar chart, stacked bar and dot range,
on heatmap rows, on the end labels of a ranking chart and in legends, so also on line, stacked area and scatter legends.
Maps, treemaps, donuts and sankeys get no flags.

`spec.flags` is auto, on or off. Auto shows flags when at least 80% of the names are countries or EU aggregates,
by `QV.countryId` and `QV.isEU`. Other is not counted. On shows them for every name that is a country. No AI call is made.
A name that is not a country gets no flag and keeps its place. EU27, EU and the euro area get the EU flag.
`flags` is only read when at least one name has a flag, so asking for flags on a chart of size classes says it did not take effect.

The flags come from `flag-icons` 7.6.0, the 4x3 set, MIT licence. `web/flags/flags.json` holds one entry per country
QuickViz can name, keyed by the ISO numeric id that `countryId` returns, plus `eu` and a one-line `_notice`.
The licence is `web/flags/LICENSE`. `scripts/build_flags.py` makes both. It needs Node, runs svgo at precision 1 and
prefixes every id inside a flag. Precision 0 would halve the file but drops the EU stars and breaks 40 other flags.
The file is 1.58 MB, 480 KB gzipped.

A flag is a `<use class="qv-flag">` of a `<symbol>` in the chart's own `<defs>`. So the PNG needs no image load and
the canvas is never tainted. The flag is 4:3, 0.75 of the font size tall, with no rounded corners. A hairline border
in the axis line colour keeps white flags visible. The label column gets the flag width plus a gap. The text is cut
to the room left. Flags before right-aligned labels are placed after `labelMax` cuts the text, so the gap stays the same.
On a vertical bar chart the flag sits under the bar and the name moves down below it. The flags shrink to fit narrow
bars and are left out under 8 px.

The page loads `flags.json` once with the frame. `frame-host.js` sends each render and signature request only the
flags its spec names. The frame reports the flags it drew in `state` as `flagsUsed`. The HTML export inlines just
those, plus the notice. With controls it adds the flags of every control version.

## How the CEPS house is applied

Read from `~/.agents/skills/dataviz/houses/ceps/` (house.md, types.md, theme.css, theme.js).

- Carlito 400 and 700 only. Sizes 13 (floor, notes), 15 (ticks, legend, source), 16 (value and
  category labels), 18 (axis titles, the chart title). Fonts are vendored in `web/fonts/`.
  Carlito has no italic file, so an italic part from `fontStyle` is drawn slanted by the browser.
- Ink `#1a1a1a`, ticks grey `#6b6b69`, dashed `2 3` grid `#e3e3e1`, axis lines `#d4d4d2`. White paper.
- Square marks, square 14 px swatches, no shadows, no rounded corners, no uppercase, no middots.
- Single series is CEPS green. Many series take `CEPS.cat` by name. EU aggregates navy. Other grey.
- Highlight follows the per-country bar rule. Highlighted green, EU27 navy, the rest grey. The
  legend then reads "Belgium / EU27 / Other countries".
- Print legend below the plot, centred, unless `legendPos` moves it. Then the footnote row (13 px grey), then `Source: <name>`
  as the last row, bottom left. The source row only shows once a source is set. A `Source:` line found
  in an uploaded Excel or CSV is used as the starting value.
- Heatmaps use the white to green ramp of `types.md`. Diverging data uses crimson to white to green.
  Maps use the six-class `CEPS.seq` scale with a class legend below the map, labels like `750+`.

## How the AI World house is applied

Read from `~/.agents/skills/dataviz/houses/aiw/` (house.md, types.md, theme.css).

- The system font stack. No web font, so nothing waits on Carlito and no export embeds it.
- The font sizes are the CEPS sizes, so both styles lay out the same. Only the font family changes.
  `fontStyle` works the same way as in CEPS. Treemap tile labels stay 400 unless `fontStyle` sets `valueLabels`.
- Ink `#0f172a`, ticks `#4b5563`, dashed `2 3` grid `#dbdbdb`, axis lines `#cccccc`. White paper.
- Single series is blue `#2756d3`. EU aggregates are blue too. A highlight is red `#e53229`, the rest grey.
- Heatmaps run white to violet to deep purple. Diverging data runs deep red to white to deep green.
- Maps use the seven-class blue scale of `types.md`, on a light blue sea `#e0f2fe`. Countries outside the data are `#e5e7eb`.
- A dot range takes blue then red for two groups, and grey then blue for two periods.
- The controls take the blue accent and 6 px corners. Two-way and three-way choices look the same, as on aiworld.eu.
  A `switch` is drawn as a button group, set by `ctl.twoWay` in `aiw-theme.js`. There is no knob.
  Buttons sit in one group on `#f8fafc` with a thin border. A blue pill slides to the picked button, whose label
  turns white. Labels are 600 in muted grey. The play button is the pale control colour with a grey icon.
- Treemap tiles are all the AI World blue, since QuickViz treemaps have no groups. Colours set in the chat still win,
  and Other stays muted. Tile labels copy the d3plus defaults of the real AIW treemaps. Each tile shows its name top
  left and its share of the total centred at the bottom, like "4.23%". Both are 400 in d3plus's font stack, Roboto
  then Helvetica Neue, with 5 px padding. Each is sized on its own to fill its box, from 40 px down to 8 px. A name
  that does not fit at 8 px ends in "...". Text is #f7f7f7, or #555555 on a light tile by the YIQ 128 rule.
  With `valueLabels` "on" the raw value is an extra line under the name. With "off" the share is left out.
  A "%" unit shows the value itself in place of the share. The raw value is always in the hover title.
  CEPS treemaps are drawn as before.
- The AI World logo sits in the chart SVG, so it lands in the PNG and the HTML file. It links to aiworld.eu.
  `spec.logo` is `{show, pos}`. A missing logo means shown at the bottom right. The other corners are
  bottom-left, top-right and top-left. Its height is 3.68 percent of the chart width, between 20.7 and 29.9 px.
  At the bottom it shares the source row, and the source text is clipped to leave it room.
  At the top it sits beside the title, and the title wraps to leave it room. CEPS charts never draw a logo.
- The logo paths are copied into `aiw-theme.js` from `web/aiw-logo.svg`, the file from aiworld.eu.
  Inline paths need no image load, so the frame policy and the PNG canvas both accept them.

## How the Franri house is applied

This is the only style in QuickViz 3. CEPS QuickViz ships the file but shows no menu entry for it.

- Carlito 400 and 700, with the CEPS sizes. `webFont` is true, so `QV.ready` waits for it and the exports embed it.
- Ink `#1c1917`. Ticks and notes are ash `#7a766f`, 4.52 to 1 on white.
- Bars that are not highlighted are ash too. Lines and other marks that are not highlighted are pebble `#8a857e`.
- One series is petrol `#13759a`. A highlight is tangerine `#c4540c`. The EU is indigo `#6348f2`.
- Many series take ten colours. They are petrol, tangerine, green, indigo, rose, sky, berry, gold, magenta and forest.
- Maps use a seven-step ramp from pale yellow green to deep petrol `#0d3f63`.
- Heatmaps run white to `#5fa3bd` to `#0d3f63`, the same petrol family as the map ramp.
- Diverging data runs burnt orange to white to deep petrol.
- There is no logo. `logo` is null in the theme, so `spec.logo` draws nothing.
- Treemaps have no AIW tile labels. They get the CEPS tile labels in the Franri colours.

The palette checks are in `~/Desktop/Workbench/quickviz-v3-parts/tools/`.
`palette_check.py` prints the contrast and colour-blind numbers. `palette_report.json` holds the last run.

## Light chart on a dark page

The CEPS house has no dark variant, and QuickViz does not add one. The chart is always drawn in the
light house, on screen and in every export. In dark mode only the page around it goes dark. The chart
frame stays white, with the 8 px radius, a faint light border and a soft shadow.

`render` still reads its colours from CSS variables named `--qv-*` on the SVG, falling back to the
CEPS values. `style.css` no longer sets any of them, so the fallbacks always apply. `exportPNG` redraws
the chart off screen and `exportHTML` carries no variables, so both are in the light house as well.
A theme switch does not redraw the chart.

## Recipe

Kept in `app.js` as `state.recipe`. The pipeline is fixed: filter, rename, aggregate by role, percent
share, top n, sort.

```json
{
  "kind": "line",
  "roles": {"t": "quarter", "series": "country", "v": "youth_unemployment_pct"},
  "agg": "auto",
  "filters": [{"column": "country", "keep": ["Spain", "EU27"]}, {"column": "quarter", "min": 2020}],
  "rename": {"country": {"EU27": "EU average"}},
  "percent": null,
  "top": {"n": 10, "other": false, "by": "latest"},
  "sort": {"by": "value", "order": "desc"},
  "title": null, "xLabel": null, "yLabel": null, "unit": null,
  "highlight": [], "colors": {}, "source": "Eurostat"
}
```

Right after filtering, the pipeline handles aggregate rows. A row is one when any of its text cells is in the
table's `aggregates`, or passes `QV.isEU`. Such a row is kept only when one of those cells sits in a column the kind
draws as its own item, such as `cat` of a bar or `series` of a line. Otherwise it would be added to the countries,
so it is dropped. Stacked bar, stacked area, treemap, donut and sankey drop aggregate rows in every case, because
they add up their parts. A filter that keeps an aggregate by name brings it back. If dropping would leave no
rows, nothing is dropped. Flag columns, named `flag` or ending in `_flag`, are never offered as a chart role.

`null` text fields mean automatic, taken from Gemini's labels or the column names. `""` means removed.
A `min` or `max` filter on a time column compares the leading year, so `2020` keeps `2020-Q1` onwards.

### No blending

A chart never combines rows unless the user asked for it. With `agg` "auto" every drawn value is one value from
the source rows. Only an explicit `aggregate` op, from the user or the chat, may sum, average or count. `top_n` with
Other and `percent_share` are the other asked-for maths. When the roles leave a value of `(count)`, rows are counted.

`withAutoFilters` in `app.js` keeps this true. It runs in `fitsKind` and at the end of every `applyChange`.
It looks at each text column that no role uses, skipping flag columns. When that column has more than one value
inside one drawn item, such as size class under a bar per country, it adds a filter that keeps one value and marks it
`auto: true`. Time columns and columns of years go first and keep the latest. Other columns keep, in this order:
a value the parser marked as an aggregate or that passes `QV.isEU`, a total by name such as Total, All or Both sexes,
a total by range, such as "10 persons employed or more" next to "From 10 to 249" and "250 or more", or else the first
value in file order. A pick made before survives a kind switch while its column stays free. A column with a value
for nearly every row and over 24 values is an identifier and is never filtered. A filter the user or chat sets on a
column replaces its auto filter.

Two cases only filter time. Histograms, scatters with no `cat`, and `(count)` charts count or plot observations,
so they keep every row. With an explicit `aggregate` op, category columns are left free so the op has rows to combine.

If items still hold more than one value after this, `aggregate` draws nothing. `fitsKind` then does not offer the
kind, and `applyChange` refuses the change with a line that asks the user how to combine the rows.

Totals found by name or range join the aggregate list in `aggInfo`. So a stacked bar, treemap, donut or sankey leaves
them out like EU27, and the preview tags them as totals.

When at least one category column is auto filtered, `withAutoControls` adds a `select` dropdown per auto filtered
column with 2 to 24 values, category columns first, marked `auto: true`. It stays within 4 controls and 60 versions.
It drops auto dropdowns whose column a role now uses. Once a change sets `controls`, the recipe gets
`noAutoControls` and no new auto dropdowns are added. `recipeForAI` sends controls without the `auto` mark.

`buildSpec` writes "Showing: 10 persons employed or more, 2025." at the start of `autoNote` when a category column
outside the roles is filtered to one value. It lists those values, then the year. Each control version gets its
own `autoNote`. It is not drawn. `recipeForAI` sends it to the chat as `what_is_shown`.

An auto filter can pick one value from a column that has no dropdown, because it has over 24 values or the controls
are full. Then nothing on the chart would say what is drawn. `hiddenPicks` in `app.js` writes one line for it, such as
"Showing EU27. 32 areas in the file." It shows in `#shown-line`, a grey line just above the chart frame.
The values are called areas when most are countries, EU aggregates or regions, else "values of <column>".
The line sits on the page, not in the SVG. So `spec.note` stays the user's own text, and the PNG and HTML carry
only what the user chose. A user who wants it in the export asks the chat for a note, which uses `what_is_shown`.

The title must match the rows drawn. `trueYears` in `buildSpec` checks every year in the title that is a year of the
data. A range that is not the drawn span becomes the drawn span, written "2025" or "2021 to 2025". A lone year
becomes the drawn span when it differs. "since 2019" becomes the first drawn year. Years that are not in the data,
like a 2030 target, are left alone. This runs for every control version, the names title and a chat title.

### Top N

`topN` in `app.js` runs after the filters, the auto filters and `percent_share`. So it ranks within the picked
size class and year, never across blended values.

Aggregate rows never count toward N. They are found the same way as above, by the parser's list, `QV.isEU`, a total
by name and a total by range. A renamed aggregate still counts as one. When the kind kept them, they stay on the chart
as reference bars in navy. So a top 20 on the stress bar chart draws 20 countries plus EU27 and the euro area.
Aggregates are never added into Other either.

On kinds with a time axis, line and stacked area, `by` picks how items are ranked. `latest` is the default and ranks
by the last drawn period. `mean` ranks by the average over the drawn periods, `total` by the sum of their sizes, and a
period such as `2023` by that period. An item with no value in that period ranks after the others. A period that is
not drawn falls back to `latest`. Other kinds ignore `by`. They rank by the size of the item, summed over its series.
A slider step builds its own chart, so each step ranks by its own period. Bump keeps its rank logic. It keeps the
items with the best rank they ever reached.

`other` adds up the rest into one Other item, per series and period. That is only right for counts and amounts.
`isRate` decides when the values are rates. It is true after `percent_share`, with an explicit mean or median, or
when the value column's name, its unit from the parser, the recipe unit or Gemini's unit reads as a percentage,
rate, ratio, share, average, index, score or per head. A count, or an explicit sum or count, is never a rate.
For rates Other is left out. This was chosen over an unweighted "Other (average)", because a plain mean of country
rates is not the rate of the rest and readers would take it for one. The EU27 bar already gives the reference.
`recipeForAI` sends `values_are: "rates"`, so the model says why. When a `top_n` change lands on rate data and the
reply still claims an Other, `applyReply` drops those sentences and adds the reason.

`buildSpec` puts one line after the "Showing" note, such as "Top 20 of 29 countries, by 2025 value. Totals are shown
for reference and not counted." It says how many were kept, out of how many, how they were ranked, and what happened
to the rest. Items are called countries or regions when most of them are, else items. The line is left out when
nothing was cut. `charts.js` writes its own "Top 40 shown" line only when it capped the bars itself.
The words say "total" only for amounts. Stacked bar, heatmap, dot range and sankey rank by the item's sum over its
series. For amounts that reads "by 2025 total". For rates it reads "by the sum of their 2025 values", and "by sum of values from
2021 to 2025" replaces "by total from 2021 to 2025" on a time axis.

`buildSpec` sets `spec.rate` when `isRate` is true. `charts.js` caps a bar chart at 40 bars. For counts and amounts
the rest is summed into one Other bar. With `spec.rate` the rest is left out and no Other bar is drawn, for the same
reason as Top N above.

A treemap adds its values up, so a treemap of rates is never offered. `summedRates` in `app.js` is true for a
treemap spec with `spec.rate`, unless the unit is % and the values add up to 100 within 0.6, the test the donut uses
for a whole. Shares made with `percent_share` "total" pass. `fitsKind` then returns null, so the kind is not in the
chart type tabs, the "Make it" chip or Jev's fallback order. A chat change or tab click to a treemap of rates is
refused with "A treemap adds the values up, and these are rates, so the tiles would mean nothing. Nothing was changed."
The system prompt tells the model the same.

`top.column` names the column the top N was set on. A `top_n` op takes the drawn column with the most values among
the kind's item roles, `cat` or `series` for stacked bar, heatmap, dot range and sankey, else the kind's key role.
`topField` then applies it to whichever role that column holds now. So a swap of `cat` and `series` keeps the same
countries. When the column is on no role, the top N rests until it comes back. Older recipes get the key column on
their next change.

A role is checked against what the chart will really draw. `roomOf` counts each column's values after its own
filters and after a top N on it, so 32 countries with a top 10 fit as heatmap columns, which allow 24. A roles op
that names a column the kind cannot take is refused with a plain reason, such as "GEO has 32 values, too many for
the columns of a heatmap chart. The most is 24. Ask for a top 20 first. Nothing was changed." Role guesses never
pick a flag column. When a chat change is refused, the bubble shows only that reason, never the model's reply.

`tests/test_top_n.py` checks each of these on the stress, venture capital, vacancy and patent rank files.
`tests/test_role_swap.py` checks the swaps and `tests/test_fit_screen.py` the automatic top N.

`tests/test_no_blending.py` builds the chart of every kind that fits each file in `samples/` and
`tests/parse_corpus/`. It checks each drawn value is the one source value of its item after filters, that counts
are row counts, and that scatter items are drawn once. It also checks the mean and percent maths on the stress file.

## Chat change

`POST /api/viz/chat` sends the recipe without rows, or an empty recipe with `kind` null when nothing is drawn yet, the columns (every value when a column has 60
or fewer, else samples plus any value named in the message), 5 sample rows, the first 12 drawn rows,
the drawn item names, the last 8 chat turns and the SVG outline. A retry after a failed patch adds `patch_error`. A retry after a change that drew nothing new adds `no_effect`.
The server always uses the "franri" style and the answer says so in `style`. It drops any `logo` the model sets. The model replies with:

```json
{"reply": "Kept Spain, Italy and EU27 and highlighted Spain.",
 "set": {"highlight": ["Spain"]},
 "ops": [{"op": "filter", "column": "country", "keep": ["Spain", "Italy", "EU27"]}]}
```

### The safe list

| op | Fields | Effect |
|---|---|---|
| `filter` | column, keep or drop or min/max | keep or drop values, or a numeric or year range. Filters on the same column merge |
| `clear_filters` | column optional | remove filters |
| `top_n` | n, other, by | keep the n largest items, optionally the rest as Other. n 0 removes it. by is latest, total, mean or one period. See "Top N" |
| `sort` | by value/label/none, order asc/desc | order of bars, rows or series |
| `aggregate` | how sum/mean/median/min/max/count | how rows sharing a label combine. The only way to combine rows, see "No blending" |
| `percent_share` | within total/group/none | values become % of the whole, or of each group or time step |
| `rename` | column, map | relabel items |
| `roles` | cat, series, t, v, v2 | pick which column plays which role. null clears an optional role |

`set` may hold kind, title, xLabel, yLabel, legendTitle, note, source, unit, decimals (0 to 3),
orientation, valueLabels, stack, highlight, colors, and every layout field above. null in `set` puts a layout
field back to automatic. `fontStyle` merges part by part, see "Layout fields". `dimSize` only acts with a highlight, see "Layout fields". min must be below max, and a log axis needs a min above 0.

The system prompt follows the style. `system_prompt(style)` in `app/viz_chat.py` fills in the colour names, the patch
colours, the patch font and the logo line. For CEPS the colour names are green, navy, red, grey, light grey, yellow,
light green, teal, slate and rose. They stay names in the reply. For AI World they are blue, red, amber, emerald,
violet, cyan and orange. The server turns them into their hex codes, so the chart draws the same in either style.
The AI World names, hex codes, ink, grey and font are read from `web/aiw-theme.js` when the server starts, so they never drift.
For Franri they are the names in `named` in `web/franri-theme.js`, such as petrol, tangerine, indigo and grey.
They are read from that file when the server starts, and turn into hex codes the same way.
Any hex code works in every style. A bad colour gets an error that names the chosen style, such as "Use a named QuickViz colour".

`logo` is a field in `set`, `{"show": true or false, "pos": "bottom-right", "bottom-left", "top-right" or "top-left"}`.
It works only for AI World. The server fills in what the model left out. `show` defaults to true, and `pos` keeps the
current corner or else bottom-right. It also takes `false`, `"off"` or a corner such as `"top left"`. For CEPS the
server drops `logo` and the reply is "CEPS charts have no logo, so nothing changed." The same reply replaces a reply
that changed nothing when the message asked about a logo. `logo` is in the `always` list of `web/capabilities.json`,
so no chart kind drops it. A control option cannot set it.

The system prompt lists every field with the kinds it works for and a few worked examples, such as the colour
bar moved to the right. It has a section on writing patches with d3 v7, with four examples: move one label, add
leader lines, add an arrow with text, and restyle one mark. Fields come first. A patch is for what no field can do.
The model refuses only things outside a flat 2D chart, such as 3D or animation beyond the slider, and edits to the
data values themselves. When it refuses, the reply must say what can be done instead. It must never say that something is handled by the template. `recipeForAI` sends the layout fields
that are set under `layout`, so the model sees the current state. On a bar or stacked bar it sends `orientation` as the way the bars
run now. For a bar that is the direction the frame last drew, which `rendered` carries as `orient`.

The server validates the reply with pydantic (`app/viz_chat.py`, extra keys forbidden), then checks
every column name and every value against the real data, fixing case and punctuation ("eu 27" to
"EU27"). A bad reply is sent back once with the error. A second bad reply returns 422 and nothing
changes. A keep list of names matches the same loose way, so "belgium" keeps "Belgium". The prompt tells the model
that a group such as "only EU27 countries" is a keep list of the member countries found in the column, never the
EU27 aggregate row. `top_n` `by` takes latest, total or mean, with last, sum, average and avg read as those. Any
other `by` must be a period of a time column, matched the same way, or the reply is sent back. `app.js` then applies the change to a copy of the recipe. If the result draws nothing, it is
not applied. Every applied change, chat or tab click, pushes the old recipe on an undo stack. Typing
"undo" undoes locally without calling the model.

The chart type tabs switch the chart in step 2 and step 3. Both call `localChange` with the same change,
`{set: {kind}, autoTime: true}`. In step 2 the switch adds no chat line. Its undo entry has no chat message, so an
undo of it later adds a grey "Undone" line. Jev's pick stays first in the tabs and keeps a small green dot.

The suggestion chips above the chat input are built from the current chart. A kind switch is only offered when
`fitsKind` can feed it from the data. Sort, top 10, percentages, highlight, a time range and a shorter
title only appear when they would change something.

## Endpoints in app/viz.py

None needs a sign-in. Every model call goes through `app.llm.openrouter`. It checks credits in
`app/guard.py` first and raises 429 when they are used up. It then records the real cost of the call.
The cost counts for the signed-in person, or for the IP when nobody is signed in. It also counts for the site total.
See "Credits" in the README.

| Route | Body | Model |
|---|---|---|
| `POST /api/viz/parse?name=&sheet=` | the raw file bytes | none, or `LABEL_MODELS` once per file and sheet when the detector's confidence is below 0.7. See "When the detector is not sure" |
| `POST /api/viz/reread` | file_id, sheet, and a recipe or a header_row | none |
| `POST /api/viz/redraw?name=` | the raw PNG or JPG bytes | `REDRAW_MODEL`, default Claude Haiku 5.5, 3 calls at once. They count as 3 calls against the budget before any is sent. See "Chart pictures" |
| `POST /api/viz/decide` | text, columns, file, sheet | Jev 1.13, one decisions call for the kind and every column role. The file and sheet name go in as a hint |
| `POST /api/viz/names` | text, columns, kind, roles, file, filters, years, data_years | `LABEL_MODELS`, default Claude Haiku 5.5 then Gemini 3.8 Flash |
| `POST /api/viz/chat` | message, recipe, columns, sample, history, chart_rows, chart_names, outline, patch_error, no_effect | `CHAT_MODEL`, Claude Haiku 5.5, with no fallback. The style is always `franri` and the chart has no logo |

`/names` gets the one-value filters outside the roles as `filters`, each `{column, value, reader, options}`. `reader`
is true when a dropdown lets the reader switch it, and `options` lists its values. `years` are the years drawn and
`data_years` every year in the data. The prompt says to name only the drawn years and never a pick the reader can
switch. When the title still names a switchable value word for word, the server asks once more. It then runs the
same year check as `trueYears` on the title. The page asks `/names` again for a new title after a change that alters
which category values are picked, unless the recipe has its own title.

The page sends `text` as an empty string to `/decide` and `/names`. Both still accept a description, so the
field stays in the API. `/decide` then asks Jev about the columns alone. The page makes these two calls once per
file and sheet, when step 2 is first opened. The chat never got the step 2 text. It works from the recipe,
the columns and the sample rows.

Settings come from the environment or `.env`: `CHAT_MODEL`, `LABEL_MODELS`,
`JEV_MODEL`, `REDRAW_MODEL`, `MAX_UPLOAD_BYTES`.

## Mockup data

Step 1 has a text box under the upload box.
Its caption reads "...or describe what you want to see with mockup data".
It has no warning line. The upload box keeps its own.

Typing draws a sample chart under the box, 200 ms after the user stops.
Under 4 characters, or when Jev says the text is not chartable, the line reads "There's no graph to show".
The arrows beside the chart type step through the kinds Jev offered.
The left and right keys do the same when the text box is not focused.

The box "Use real numbers from the web" stays off until Jev scores the text 0.7 or more for web data.
With it ticked, the sample uses numbers found by a web search, with their source links.

`web/charts-mock.js` makes the sample. It is personal to this app and is not synced.
It loads after `charts.js` and adds `QV.mock`, `QV.mockTyping`, `QV.mockTable` and `QV.withMockPatch`.

Next turns the sample into a table, like a parsed file, and opens step 2.
The table has no `file_id`, so Other readings and the header pick stay hidden.
It carries `described` with the kind, the title, the unit and the column of each role.
So step 2 calls neither `/api/viz/decide` nor `/api/viz/names`. It opens on the same chart.

Made-up numbers get `mock: true`. The chart is marked once.
Its source line reads "Mockup data, not real numbers". It has no extra note line and no tag in the chart.
`buildSpec` in `app.js` always sets that source for mockup data. So the chat cannot edit it away.
The PNG and the HTML file carry the same source line.
A "Mockup data" badge shows next to the file name and above the chart. It is part of the page, not the chart.
PNG and HTML file names start with `mockup-`.
`QV.withMockPatch` now only strips any old mockup patch. It adds nothing.

Web data gets `mock: false` and its own source line.
The source line names the sources and links to the first one.
Step 1 lists every source as a link.

### Mockup endpoints in app/mock.py

All three take JSON and need `text` of at least 4 characters. Text past 2,000 characters is cut.
Each one runs through `app.llm.openrouter`, so it uses credits like every other call.
Its cost counts for the visitor and for the site total.
Each one also has a limit per IP per minute. Past it the answer is 429 with reason `rate` and `retry_after`.
The page shows that message in the status line and opens no banner.

| Route | Body | Model | Limit a minute |
|---|---|---|---|
| `POST /api/pick` | text | Jev 1.13, one decisions call for the kind, chartable and web data | `RATE_PICK`, 60 |
| `POST /api/fill` | text, kind | `FILL_MODELS`, Gemini 3.8 Flash then Gemini 2.5 Flash Lite | `RATE_FILL`, 60 |
| `POST /api/web-data` | text, kind | `WEB_MODEL`, the first fill model, with web search forced | `RATE_WEB`, 12 |

Short text gets 400. A kind the route cannot fill gets 422.
A web search with no cited numbers gets 422 too. A model reply that cannot be read gets 502.
Web data answers are kept for one hour, 128 at most, keyed by the text, the kind and the model.
A kept answer costs nothing and says `cached: true`.
`app/web_data.py` builds the web search request and checks its answer.

The parser reads CSV, TSV, pipe and semicolon files, decimal commas, cp1252 text, XLSX (openpyxl, merged
cells filled from their top-left cell), Eurostat bulk TSV, JSON records and JSON-stat. Old `.xls` needs
`xlrd`. How it reads a sheet is in "File reading" below.


## File reading

The parser in `app/parse/` works in two steps. Detection looks at the raw cell grid and writes a reading
recipe. One executor turns any recipe into the table. Claude Haiku can write the same recipe when the
detector is not sure, so the recipe is the contract between the two. `app/viz_parse.py` stays as a thin
wrapper, so `from app.viz_parse import parse_file, ParseError` keeps working.

```
read_grid(raw, name, sheet) -> (grid, sheets)    grid is a list of rows. grid.sheet is the sheet read, or None
detect(grid) -> (recipe, confidence, alternatives)    alternatives is a list of {summary, recipe}
execute(grid, recipe) -> table                   the dict parse_file returns, without name, sheet and sheets
parse_file(raw, name, sheet) -> table            read_grid, detect, execute, then name, sheet, sheets
```

All four live in `app.parse`. The models are in `app/parse/recipe.py`. They forbid unknown keys.
`detect_full(grid)` returns the same three plus the detector's issues. `summarize(grid, recipe)` gives the
one-line summary for any recipe without running it.

```
Recipe {
  sheet: str | None                 the sheet the indices point into. None for text files
  blocks: [Block]                   at least one. Their rows are stacked in order
  missing_markers: [str]            value cells equal to one of these become empty. Case does not matter
  decimal: "." | ","
  thousands: "" | "," | "." | " "   " " also covers the no-break spaces
  aggregates: [str]                 id values that are sums or averages of others, like EU27 or Total
  notes: [str]                      footnotes and remarks worth showing, not data
}
Block {
  header_rows: [int]                one or more stacked header rows. Can be empty when names are given
  data_start: int                   first data row
  data_end: int                     last data row, inclusive
  label: {column: str, value: str} | None    adds a constant column to every row of the block
  id_columns: [{index: int, name: str}]       copied as they are, typed by their content
  value_columns: [{index: int, name: str, flag_index: int | None}]
  wide: {name: str, levels: [str] | None} | None
  unit: str | None
}
```

Rows and columns are 0-based into the grid of the chosen sheet. Blank rows between `data_start` and
`data_end` are skipped. So is a row whose id cells repeat the header names.
A headerless run of rows close under a block, with the same columns, joins it as a second block. The detector
leaves it out when its values are all empty or 0 and every id in it already appeared above, because those rows
would only give the same item a second, empty value.

Names come from the recipe. The executor does not read them from `header_rows`, with one exception for
`wide.levels`.

`flag_index` points to the column holding the flag of that value. When it equals the value's own `index`,
the flag sits inside the cell, like `12.3 p`. Flags land in a column named `flag`. With more than one value
column and no `wide`, each gets `<value name>_flag` right after it.

`wide` melts the value columns into rows. Each value column's `name` becomes the key, in a column called
`wide.name`, and the number goes in `Value`. When `wide.levels` is set, the header has one row per level, as in a
country by year by sex crosstab. Then each level gets its own column. The levels match the last
`len(levels)` rows of `header_rows`, in order. Rows above them can hold a constant measure or unit. The key
for a level is the cell of its row at the value column, or the nearest non-empty cell to its left that is
not left of the first value column. Melted rows whose value is empty are dropped.

With `wide`, the column order is the label, the id columns, the wide columns, `Value`, then `flag`. Without
`wide`, the label comes first and the id and value columns keep their order in the file, each value followed
by its flag. When blocks differ in columns, the union is taken in order of first use and missing cells are
empty. Columns that end up with no value at all are left out, except `Value`.

Id columns named like a date that hold Excel serial numbers become ISO dates. Id columns of month names with
a year, in English, French, German, Dutch, Spanish, Italian or Portuguese, become `YYYY-MM`.

When every block has the same `unit`, each number column from a value column carries it as `unit` in its
column dict.

Value cells are numbers. A missing marker, a blank, or text that does not read as a number becomes empty
(`null`), never 0. Footnote marks like `12.3¹` or `12.3*`, in-cell flags, `%`, currency signs and
`(12)` for negatives are read as the number. Id cells lose trailing footnote marks like `Belgium¹`.

The table gets these keys on top of the old ones (`columns`, `rows`, `n_rows`, `truncated`, `melted`,
`source_hint`, `notes`):

```
aggregates: [str]     id values in the rows that are aggregates. Charts should not add them to the others
reading: {
  summary: str        one plain sentence, like "3 tables by size class, 32 areas, 4 years, flags kept"
  confidence: float   0 to 1. Below 0.7 the AI fallback should run
  recipe: dict        the recipe used, as plain JSON
  alternatives: [{summary, recipe}]   up to 3 other readings worth offering
  issues: [str]       short plain lines on what looked wrong
}
```

Aggregates are a list of values, never a mark on rows, so the row arrays keep their shape. A value counts
when any id cell of a row equals it.

### When the detector is not sure

`app/viz_reading.py` runs the route. It calls `read_grid`, `detect` and `execute`. When the detector's confidence
is 0.7 or more, that table goes back as it is and no model is called.

Below 0.7 the route asks `LABEL_MODELS` for a recipe, Claude Haiku 5.5 first and Gemini 3.8 Flash as fallback.
The call goes through `app.llm.openrouter`, so its cost lands on the person who uploaded the file.
The model gets the system prompt, the Recipe JSON schema, the sheet names, the detector's recipe, its confidence
and issues, and a compact view of the grid. The view has the first 60 rows and the last 15. Rows next to a blank
row in the middle are shown too, at most 40, so the edges of stacked tables are never hidden. Each line is
`r<row>| <col>:<text>`, empty cells left out, text cut at 40 characters.

The model returns a recipe only, never code. It is checked in four steps before it is used.

1. `Recipe.model_validate`, which forbids unknown keys.
2. Free text is cleaned. Aggregates and notes are kept only when they appear in the grid. Names lose control
   characters and are cut short.
3. `validate` checks it against the real grid. Every row and column index must be in range. Header rows must sit
   above the data and must not hold numbers, years aside. Each value column must read as numbers in at least 80%
   of its non-empty cells, missing markers aside. A flag column must hold short codes like `b` or `p` in at least
   90% of its filled cells. No column may be used twice, and a block may not run past a row that repeats its header.
4. `execute` runs it and its `reading.confidence` is the score, with the same rules as the detector.

If the recipe fails a step, or scores below the detector, the model gets one retry with the reasons.
The reading that scored best is kept. A tie keeps the detector's reading. When the model's reading wins,
the detector's reading becomes the first alternative. `reading` then also has `source` ("rules", "ai" or
"picked") and `ai`: `{model, cost, tries, reasons, cached, kept}`, or `{error: "cap" | "failed"}` when the call
could not be made. A cap or OpenRouter failure never fails the upload. The detector's table goes back.

The result is cached in memory per file hash and sheet, 256 entries. A cache hit re-executes the cached recipe
and costs nothing. A result where the detector won is cached too. A failed call is not.

Uploaded files can carry text written to steer the model. This is safe because the model only ever returns a
recipe, a list of row and column numbers and short names. It is validated against the grid before use and runs
through the same executor as the detector's own. The model writes no code and no text that reaches the page
unchecked. The prompt also tells it to treat every cell as data.

Measured on 2026-10-12 with real Haiku calls. A small file costs about 0.0004 USD per call. The stress file's
grid is about 4,700 tokens in and 650 out, 0.0008 USD, 3 to 4 seconds. One AI parse with its retry measured
0.0012 USD. So one AI parse costs at most about 0.002 USD.

### Chart pictures

`POST /api/viz/redraw` takes a PNG or JPG of a chart and gives back a table like `/parse`. `redraw` in
`app/viz_reading.py` runs it. The first bytes must be a PNG or JPEG header, else the answer is 422.

The picture goes to `REDRAW_MODEL` as a base64 data URL, 3 times at once, at temperature 0.3. The prompt asks for
one first line, `bars: horizontal`, `bars: vertical` or `bars: none` when the chart has no bars. Then it asks for
only a JSON array of `{label, series, value}`, one item per value drawn, with plain numbers. It tells the model to
treat text in the picture as data only. The route reserves 3 calls before it sends any.
That needs at least 3 times `CALL_CREDITS` left, so 15 credits by default.
When there are not, it answers 429 and sends nothing. Each call then goes through `app.llm.openrouter`, which records
its own cost. Reservations no call used are given back at the end. The route uses the answers it got. When no call got through, it raises the first error, a 429 first
when there is one.

`picture_bars` reads the bars line from the text before the first `[`. `bars_vote` takes the answer most samples
gave. It must come from more than half of the samples that answered, and "none" never wins a direction. So two of
three saying horizontal is horizontal, and one horizontal with two silent answers is no hint.
`picture_items` reads each answer. It takes the first `[...]` in the text, keeps items with a label and a number,
and cuts names to 120 characters. At most 600 items are kept. An answer with no array counts as a sample with no values.
`merge_samples` matches items across samples by label and series. Case, spaces and punctuation do not count.
When two samples have the same number of series under other names, they are matched by order. Each cell takes the
median of its values. It is unsure when the values spread more than 5% of the median, or when fewer than all the
samples that answered had it. When no sample gave a value, the answer is 422 with "We could not read any values
from this picture. Try a sharper picture, or upload the data as a file."

The cells become a CSV with `Label` and `Value`, plus `Series` when there is more than one series. It goes through
`read_grid` and `first_reading` like an uploaded CSV, with no AI fallback. The grid is kept for the user like a parse.
`reading.source` is `picture`, there are no alternatives, and `reading.summary` is the plain line, such as
"Read from a chart picture, 4 values unsure, check them". `reading.picture` holds `{model, cost, samples, read,
unsure, flagged, bars}`. `flagged` lists `{row, column}` for each unsure cell. `reading.confidence` is 1, or 0.5 when a
cell is unsure.

The table also carries `orientation_hint`, the voted direction or null. It follows `source_hint`. `autoChart` in
`app.js` puts it in the first recipe as `orientation`, but only when that recipe is a bar or stacked bar. So the first
chart drawn from a picture of horizontal bars is horizontal too. It then counts as a set orientation, and the chat
can change it like any other.

The page sends a file to `/redraw` when its name ends in .png, .jpg or .jpeg, or its type is a PNG or JPEG.
For a picture the preview lists every row. Every number cell holds a small text input. Flagged cells are also yellow.
A typed number replaces the value, also with a decimal comma, and updates the column's min and max.
It removes the flag and the count in the line goes down. Text that is not a number puts the old value back.
The yellow triangle shows while any cell is flagged, and its tip says the values were hard to read.
The edit lives in `state.data`, so it is saved with the page and feeds the chart.

### Other readings

Every parse response carries `file_id`, the first 32 hex characters of the file's SHA-256, and `raw_head`, the
first 40 rows of the grid with at most 10 cells of 30 characters each. The server keeps the grid in memory,
keyed by the user, the file id and the sheet. It holds 12 grids for one hour.

`POST /api/viz/reread` takes `{file_id, sheet, recipe}` or `{file_id, sheet, header_row}` and returns a table like
`/parse`. No model is called. A recipe goes through the same checks as the model's. A header row builds a one
block recipe: the data runs to the first blank row, columns that are 80% numbers become values, a short code column
right of a value becomes its flag, and three or more year names melt into `Year`. The answer is 409 with
reason `gone` when the grid has left the cache or belongs to someone else. The page then sends the file to `/parse`
again and retries once.

This keeps the grid on the server instead of sending the file twice. The app runs one worker, the cache is per
user and bounded, and a file id alone gives nothing to another user.

## Saved page state

`web/keep.js` gives `window.QVKeep`, a small IndexedDB store named `qv-keep`. `app.js` uses it so a reload keeps
the work. Each record is keyed by `[browser id, part]`. The browser id is a random string kept in `localStorage`
under `quickviz-browser`. It never leaves the browser.

There are two parts. `data` holds `state.data`, the parsed table with its file name, sheet, sheets, reading and
`raw_head`. It is written only when `state.data` changes, because it can be several MB. `ui` holds `auto`,
`decide`, `names`, `namesFor`, `recipe`, `undo`, `chat`, `opts`, `spec`, `view`, `reached`, the Other readings
list, the step 2 heading and `style`. It is written 600 ms after the last change, and at once when the page is hidden.
`busy` and `drawing` are never saved. While the page is busy the write waits. A chat bubble still waiting for its
answer is left out. While Jev has not finished, the save says step 1, so a reload never lands on a half-made pick.

Both parts carry `v`, now 1, and the same `id`. `ui` also carries `at`, the time of the save. On load the page
restores only when both versions match, the ids match and `at` is under 7 days old. Anything else is ignored and
deleted, with no message. Restoring calls `showData`, `render` and `drawChat`, then goes to the saved step.
It calls neither `/api/viz/decide` nor `/api/viz/names`. Bump `KEEP_V` in `app.js` when the shape of the state
changes.

Mockup data is saved like a file. Its `mock`, `sources` and `described` stay in `data`, so the marking comes back after a reload.

Signing in leaves the page for Google and comes back to `/`. The work survives this like a reload.
The save key lives in `localStorage`. The sign-in buttons first write any save that is still waiting, then go.

Start over and loading a new file delete both parts. At start the page also deletes every user's
records whose `ui` is older than 7 days.

The original file does not survive a reload. Other readings then gets 409 `gone` from `/api/viz/reread` once the
server's grid has left its cache, and shows the server's message "The file is no longer on the server. Load it
again." The chart and the chat stay as they were. Picking another sheet shows a similar line and changes nothing.

## Exports

PNG: the frame redraws the chart off screen at 760 px with its patches, clones it with computed styles and
embeds Carlito as base64. An AI World PNG embeds no font. The page draws that markup on a 4x canvas. A 760 by 900 px chart becomes 3040 by 3600 px.
The scale drops only when the canvas would pass 16,384 px a side or 16.7 million pixels. That is the iPhone limit.
HTML: one file with d3, the theme of the chosen style only, `charts.js`,
the spec with its rows, the patches, the control state, Carlito as base64, the flags drawn and, for maps, the outlines.
An AI World file carries no Carlito and draws at once. It carries
the frame's content policy, opens offline and redraws to the window width with the same patches.

The HTML file inlines the copies in `web/export/`, never the files the page itself uses.
`scripts/build_export.py` writes them. It runs esbuild 0.28.2 through `npx`, so it needs Node. The server does not.
The copies have no comments. Only the one-line copyright notices of d3, d3-sankey and topojson-client stay, as their
licences ask. The world map copy keeps every country but drops the unused `land` layer. Its lines are simplified to
0.01 degrees and stored on a 20,000 step grid. A Benelux map, the closest zoom tried, looked the same.
Only the Carlito faces the chart's text needs go in. Plain Latin text gets 2 of the 4, and a name like "Česko" gets all 4.
`web/export/manifest.json` holds the hash of each source and copy. `tests/test_export_build.py` fails when a source
changed and the copy was not built again. After editing `charts.js` or a theme file, run
`.venv/bin/python scripts/build_export.py` and commit `web/export/`.

Measured on 2026-10-12 with a 28 country chart. The bar chart file went from 618 KB to 444 KB.
The world map file went from 1,381 KB to 958 KB.


## Accounts and credits

`app/auth.py` has Google sign-in, the session cookie and `/api/me`. `app/admin.py` has the admin API.
`app/guard.py` counts credits. `app/db.py` and `app/models.py` hold the database.

The tables are `users`, `sessions`, `oauth_states` and `spend`. They are made at startup.

| Route | What it does |
|---|---|
| `GET /api/me` | Signed in or not, the email, admin or not, whether sign-in is on, credits left today, the daily number, the reset time |
| `POST /api/logout` | Deletes the session |
| `GET /auth/google/login` | Starts sign-in. 404 when Google is not set |
| `GET /auth/google/callback` | Ends sign-in. 404 when Google is not set |
| `GET /admin` | The admin page. 404 for everyone but the admin |
| `GET /api/admin/users` | Every account with credits used today and in the last 7 days |
| `PATCH /api/admin/users/{id}` | `{"active": false}` blocks, `true` unblocks |
| `PATCH /api/admin/users/{id}/credits` | `{"credits_day": 500}` sets a daily number. `null` goes back to the default |

### Sign-in

The flow is the OAuth 2.0 authorization code flow with PKCE.
The login route makes a random state and a random verifier.
It stores the verifier in `oauth_states` under a hash of the state, for 10 minutes.
It puts the state in an HttpOnly cookie on `/auth` and sends the browser to Google with the S256 challenge.
The scopes are `openid email profile`.

The callback checks that the state in the URL matches the cookie and a stored row.
The row is deleted on first use. It then swaps the code and the verifier for tokens at Google.
It reads the ID token that came straight back from Google over TLS. It checks the issuer, the audience, the expiry,
the subject and that the email is verified.
Any failure sends the browser to `/?signin=failed`. A cancel sends it to `/?signin=cancelled`.

The user is found by Google subject, then by email. A new person gets a new account.
A blocked person goes to `/?signin=blocked` and gets no session.

The session cookie holds a random token. The database stores only its SHA-256 hash.
The cookie is HttpOnly and SameSite Lax. It is Secure when `PUBLIC_URL` starts with https.
Sessions last `SESSION_HOURS`, 720 by default.
Blocking a person deletes all their sessions at once.

Every write to `/api` must carry an `Origin` header equal to `PUBLIC_URL`.
With `PRODUCTION=false`, any localhost origin is also accepted.

### Credits

One credit is USD 0.001 of real model cost. The cost comes from OpenRouter, or from `FALLBACK_COST_USD` when none comes back.
A visitor who is not signed in is counted by IP. A signed-in person is counted by account.

Before each call the app writes a reservation of `CALL_CREDITS` to the `spend` table, under a lock.
On PostgreSQL that lock is also an advisory lock. When the call returns, the real cost replaces the reservation.
A call starts when at least part of a credit is left. Redraw needs 3 times `CALL_CREDITS`.
One call can go a little over the daily number. It never goes over by more than one call.

The site total counts every row of the day, reservations too. At `GLOBAL_DAY_USD` every call stops.

A 429 body looks like this.

```json
{"detail": {"reason": "credits", "message": "You have used up today's credits...", "left": 0, "sign_in": true, "resets_at": "2026-10-27T00:00:00Z"}}
```

`reason` is `credits` or `site`. `sign_in` is true only for a visitor who is not signed in while Google sign-in is on.
The page shows the message in the banner. With `sign_in`, the banner has a "Sign in for more" button.
`web/credits.js` keeps the header count right. It reloads `/api/me` after every write to `/api`.
