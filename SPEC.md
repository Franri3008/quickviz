# Chart spec

The one contract between the data side (`app.js`, `server.py`) and the chart side (`charts.js`).
The data side builds a spec. The chart side draws it. Neither looks inside the other.

```js
QV.render(svgElement, spec)   // draws the spec, fades from the previous chart
QV.mock(kind, labels, seed)   // returns a spec with made-up data, used before a file is loaded
QV.exportPNG(svgElement, filename)
```

## Shape

```json
{
  "kind": "bar",
  "title": "GDP by country",
  "xLabel": "Country",
  "yLabel": "GDP",
  "unit": "$",
  "mock": false,
  "rows": [{"cat": "France", "v": 3.1}, {"cat": "Spain", "v": 1.6}]
}
```

`kind` is one of the ids in `presets.json`. `rows` is a tidy table. Each row uses only the fields
its kind needs. `mock` is true when the numbers are invented, and the chart then says so.

| Field | Meaning |
|---|---|
| `cat` | A category name, a string |
| `series` | A sub-group name, a string |
| `t` | A time step, a string such as "2021" or "2021-03", sorted as given |
| `v` | The main number |
| `v2` | A second number, only for scatter |

## Fields per kind

| kind | Uses | Notes |
|---|---|---|
| bar | cat, v | |
| line | t, series, v | series optional, one line per series |
| stacked_area | t, series, v | |
| stacked_bar | cat, series, v | drawn as shares of 100 |
| scatter | v, v2, series | v on x, v2 on y, series optional colour |
| histogram | v | one row per observation, binned by the chart |
| heatmap | cat, series, v | cat on rows, series on columns |
| treemap | cat, v | |
| donut | cat, v | 2 to 5 rows work best |
| sankey | cat, series, v | cat is the source, series the target |
| bump | t, cat, v | v is the rank, 1 is top |
| dot_range | cat, series, v | exactly two series, the two dots per row |

`xLabel` and `yLabel` are the axis titles. Either can be empty.
