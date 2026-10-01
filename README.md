# QuickViz

Type what data you have. A sample chart appears before you finish typing.

TypeSafe's Jev (`typesafe/jev-1.13` on OpenRouter) picks the chart type from the presets in
`presets.json`. It fires 200 ms after you stop typing. A second small model then fills in
realistic titles and labels.

## Run

```
python3 server.py
```

Open http://127.0.0.1:8799. Python standard library only.

The server needs `OPENROUTER_API_KEY`. It reads the environment first, then `.env` in this folder.

## Files

| File | What |
|---|---|
| `server.py` | Serves the page and proxies `/api/pick` (Jev) and `/api/fill` (labels) |
| `presets.json` | The chart types Jev chooses from, with the description Jev sees |
| `app.js` | Input, debounce, calls, state |
| `charts.js` | The renderers |
| `SPEC.md` | The chart spec that joins the two |
| `render.yaml` | Render config, unused until we deploy |

## Version

The version lives in `VERSION`. The server writes it into `index.html`, shows it in the page corner and at `/api/version`, and adds it to the script and style URLs so a new release is never served from a stale browser cache. Bump it on every release.
