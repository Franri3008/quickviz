# QuickViz

A free web app at https://quickviz.franri.dev.
You upload a data file or a picture of a chart. You get the chart that fits it best.
Or you describe a chart in words and get a sample with mockup data.
Then you chat with an AI to change it. You download it as PNG or HTML.
Anyone can use it without signing in.
Signing in with Google gives more credits a day.

Version 3.0.0 is built on a copy of CEPS QuickViz 2.1.0.
The CEPS invitations, passwords and tiers are cut out.
Google sign-in and daily credits replace them.
The charts use the Franri house, named QuickViz on the page, with no logo.
The admin can also give a signed-in person the AI World and CEPS houses. See "Chart styles".
The page and the charts use Carlito, at the CEPS sizes.

Version 3.1.0 adds an MCP server at `/mcp`. Claude Code and Claude Desktop can make and change charts with it.
Each person makes a personal API key in the account menu. See "Use QuickViz from Claude".

## Run it locally

Needs Python 3.12.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8011 --reload
```

Open http://localhost:8011.

The server needs an OpenRouter key. It looks in three places, in this order.

1. The `OPENROUTER_API_KEY` environment variable.
2. `OPENROUTER_API_KEY=` in `.env` in this folder.
3. `OPENROUTER_API_KEY=` in `~/Documents/github/observatory-site/.env`.

Without a key the page still loads. Every AI step then answers 503.

Locally the app keeps its data in `quickviz.db`, a SQLite file in this folder.
Git ignores it. Delete it to start from zero.
Sign-in stays hidden until the Google settings are set. Everything else works without them.

## The page

The page has four steps.

1. Upload. Drop a file or a chart picture. You see the columns and the first rows.
   Or type what you want to see. A sample chart with made-up numbers shows as you type.
2. Preview. The app picks a chart and draws it. You type nothing.
3. Adjust. You chat to change the chart. Undo takes back any change.
4. Export. Download the chart as PNG or as one HTML file.

The reader takes CSV, TSV, XLSX, old XLS, JSON and Eurostat files, up to 5 MB.
It keeps totals like EU27 out of sums.
When it is not sure how to read a file, it asks Claude Haiku 5.5 once.

A chart picture goes to Claude Haiku 5.5 three times.
Each value is the middle of the three answers.
Values the answers disagree on are marked unsure, and you can edit them.
A table picture keeps one column per number header, so Revenue, Profit and Employees stay three columns.
The value is called Rank only when the numbers can be ranks.

Above the chart, steps 2 and 3 show two rows of blocks. The first holds the chart types.
The second holds every column of the data, in the data's own order.
The columns the chart draws are selected, like the active chart type.
Clicking a number column makes it the value of a one-value chart such as bar.
On a chart drawn from several value columns it adds or removes that column, from 2 up to 8, or exactly 2 on a dot range.
Clicking a text column makes it the labels. On line and stacked area it makes it the lines.
A column that cannot go in the chart is greyed out with a dashed border. Its tip says why.
Each click redraws on the page with no AI call, and the title and axis titles follow the new column.
The chat can still swap columns, and the row follows.
Each row stays one line at any width. Blocks that do not fit go into a grey "+N" block with a menu.
"+N" is selected when it hides a selected item.

## Mockup data

Under the upload box is a text box.
Its caption reads "...or describe what you want to see with mockup data".
Typing draws a sample chart. Next loads it into step 2 like a file.

A mockup chart is marked once.
A "Mockup data" badge sits above the chart on the page.
The chart's source line reads "Mockup data, not real numbers".
The PNG and the HTML file carry that source line. Their file names start with `mockup-`.
The chat cannot change that source line.

The box "Use real numbers from the web" turns on when the text asks for public numbers.
It then draws numbers found by a web search. Those charts carry their source links instead.

The three routes are `/api/pick`, `/api/fill` and `/api/web-data`.
They use credits like every other AI call.
They also have a limit per IP per minute.

A reload keeps your work for 7 days.
It is saved in your browser only, under a random id.
Nothing about it is sent to the server.

## Models

| Step | Model |
|---|---|
| Chart type and column roles | TypeSafe Jev 1.13 |
| Title, axis names, file reading help | Claude Haiku 5.5, then Gemini 3.8 Flash if Haiku fails |
| Chat | Claude Haiku 5.5 only |
| Chart pictures | Claude Haiku 5.5, 3 calls |
| Mockup chart type, chartable, web data score | TypeSafe Jev 1.13 |
| Mockup labels | Gemini 3.8 Flash, then Gemini 2.5 Flash Lite |
| Web data | Gemini 3.8 Flash with web search |

Each can be changed with an env var.
They are `JEV_MODEL`, `LABEL_MODELS`, `CHAT_MODEL`, `REDRAW_MODEL`, `FILL_MODELS` and `WEB_MODEL`.

## Credits

All AI calls use one OpenRouter key. So each visitor gets a number of credits a day.

One credit is USD 0.001 of real model cost.
The cost comes from OpenRouter. When OpenRouter gives none, the app counts `FALLBACK_COST_USD`.
A typical call costs from under 1 credit to about 9.

| Who | Credits a day |
|---|---|
| A visitor who is not signed in | 100, counted per IP |
| A signed-in person | 1000 |
| A person the admin gave a number | That number |

The whole site also stops at USD 3 a day across everyone.
All of these are settings.
The day resets at midnight UTC.

The header shows "N credits left today". It updates after each call.
Typing a mockup, web data, file reading help, names, chat and chart pictures all use credits.
A chart picture makes 3 calls. It only starts when 3 calls' worth of credits is left.
That is 3 times `CALL_CREDITS`, so 15 credits by default.

At zero the server answers 429.
The page then shows a banner saying today's credits are used up.
A visitor who is not signed in also gets a "Sign in for more" button.
When the site cap is hit, the banner says the site is busy today instead.
The chart, the chart type tabs, undo and the downloads keep working.

The old limit on the number of calls is gone. Credits are the only limit per person.
The per-minute limits on the mockup routes stay.

Credits and spend live in the database. So Render sleeping or a redeploy does not reset them.

**The real hard cap is still the limit on the OpenRouter key.**
Set it as in step 4 of "Set up production" below.

The IP comes from the first entry of `X-Forwarded-For`.
A visitor can fake that header.
The site cap and the key limit still hold when they do.

## Accounts

Sign-in is Google only. There are no passwords and the app sends no email.
The button shows only when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set.

The flow is the standard OAuth 2.0 authorization code flow with PKCE and a state check.
It asks for `openid email profile`. Google sends the browser back to `/auth/google/callback`.
The first sign-in makes the account.

The session cookie is HttpOnly and SameSite Lax. It is Secure when `PUBLIC_URL` starts with https.
A session lasts 30 days. The database keeps only a hash of the cookie.
Every write to `/api` must come from the site's own origin.

The menu under the email in the header has "Sign out".
Signing in keeps the chart in progress. The page saves it in the browser before it leaves for Google.
A description typed but not yet loaded with Next is not kept.

## Admin

The person whose Google email equals `ADMIN_EMAIL` is the admin.
They see "Admin" in the header menu. It opens `/admin`. Everyone else gets 404 there.

The page lists every account with the credits used today and in the last 7 days.
It sets one person's daily credits. An empty box goes back to the default.
It blocks or unblocks a person. Blocking signs them out at once and stops them signing in.
A blocked person can still use the site like any visitor who is not signed in.
The admin cannot block themselves.

The "Chart styles" column has one box per house: QuickViz, AI World and CEPS.
A change saves at once. At least one box stays on. The admin's own row is fixed with all three.

## Chart styles

There are three styles: `franri` (shown as QuickViz), `aiw` (AI World) and `ceps` (CEPS).
Every account has `franri` until the admin changes it. The admin always has all three.
Visitors who are not signed in only get `franri`.

A person with more than one style sees a "Style" menu above the chart.
The pick redraws the chart and the sample chart, and is saved to the account.
The page loads a theme file only when that style is first picked.

The server checks the style on every request that takes one.
`allowed_styles(user)` and `check_style(user, style)` in `app/auth.py` do it.
A style the account does not have gets 403 before any model call, so no credits go.
The style is stored in `users.styles` as a comma list. `users.chart_style` holds the last pick.
Both columns are added at start-up to an older database, Postgres or SQLite.

## Health check

`GET /api/health` needs no sign-in. Omni Dashboard can read it.
It answers 200 when healthy and 503 when not.
It checks the key with OpenRouter at most once every 5 minutes.
It fails when the key is refused, when OpenRouter cannot be reached, or when the key has under 0.5 USD left.
Its metrics include today's spend from the database and the money left on the key.

`GET /api/version` gives the version.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | empty | The one key for all AI calls |
| `MAX_BODY_BYTES` | 6291456 | Largest request body to `/api` |
| `MAX_UPLOAD_BYTES` | 5242880 | Largest file or picture |
| `DATABASE_URL` | `sqlite:///quickviz.db` in this folder | The database. A `postgres://` URL works too |
| `PUBLIC_URL` | `http://localhost:8011` | The site's own address. Used for the Google redirect and the origin check |
| `PRODUCTION` | false | When true, only `PUBLIC_URL` is a valid origin. When false, localhost is too |
| `SESSION_HOURS` | 720 | How long a sign-in lasts |
| `GOOGLE_CLIENT_ID` | empty | Google OAuth client id. Empty hides sign-in |
| `GOOGLE_CLIENT_SECRET` | empty | Google OAuth client secret. Empty hides sign-in |
| `ADMIN_EMAIL` | empty | The Google email of the admin |
| `CREDITS_ANON_DAY` | 100 | Credits a day for one IP that is not signed in |
| `CREDITS_USER_DAY` | 1000 | Credits a day for a signed-in person, unless the admin set a number |
| `USD_PER_CREDIT` | 0.001 | What one credit is worth |
| `CALL_CREDITS` | 5 | Credits held for each call while it runs |
| `GLOBAL_DAY_USD` | 3 | Money in USD the whole site may spend in a day |
| `FALLBACK_COST_USD` | 0.01 | Cost counted when OpenRouter gives none, or the call fails |
| `RATE_PICK` | 60 | Mockup chart picks one IP may ask for in a minute |
| `RATE_FILL` | 60 | Mockup label calls one IP may ask for in a minute |
| `RATE_WEB` | 12 | Web data searches one IP may ask for in a minute |
| `RATE_RENDER` | 20 | Server renders one person may ask for in a minute |
| `RENDER_MAX_SCALE` | 2 | Largest PNG scale for a server render. 4 passes 512 MB |
| `RENDER_TIMEOUT_S` | 25 | Longest one server render may take |
| `RENDER_IDLE_S` | 300 | Seconds with no render before Chromium shuts |
| `RENDER_RECYCLE` | 40 | Renders before Chromium restarts. 0 never restarts it |
| `RENDER_SINGLE_PROCESS` | 1 | Run Chromium as one process. 0 lets it split |
| `CHROME_PATH` | empty | Chromium to use. Empty looks in the Playwright folder, then on the `PATH` |

`IP_DAY_CALLS` and `IP_DAY_USD` are gone. Remove them from Render.

## The shared renderer

`web/charts.js` draws the charts. It is shared with CEPS QuickViz.
Never edit it here by hand.

`scripts/sync_renderer.py` copies it from `../ceps-quickviz/web/`.
It also copies the three theme files, the logo file, `capabilities.json` and the folders `vendor`, `geo`, `flags`, `export` and `fonts`.
The Franri theme lives in CEPS QuickViz as `web/franri-theme.js`, so it syncs like the others.
CEPS ships it but shows no menu entry for it.
It writes the sha256 of every copied file to `web/renderer-manifest.json`, with the CEPS commit it came from.

```sh
.venv/bin/python scripts/sync_renderer.py
.venv/bin/python scripts/sync_renderer.py --check
```

A test fails when a synced file no longer matches its hash, or when a file in those folders is not in the manifest.
Anything personal goes in its own file.

`ceps-theme.js` and `aiw-theme.js` are synced. The page loads them only when a person picks that style.
The chart frame always has all three.

`web/charts-mock.js` is personal. It makes the mockup charts and is not synced.

## Web data

`app/web_data.py` asks a model to search the web and return only cited numbers.
`app/mock.py` serves it at `/api/web-data`.
Answers are kept for one hour, so the same question costs once.
`tests/test_web_data.py` covers it and the mockup routes.

## Tests

```sh
.venv/bin/python -m pytest -q
```

The tests use a fake OpenRouter. They spend nothing. Some need Node, and a few need Chrome.
`tests/test_render.py` and `tests/test_mcp.py` draw real charts when they find the Chromium headless shell. Without it those tests are skipped.

## Server render

`POST /api/render` draws a chart on the server. It returns the PNG and the self-contained HTML file.
Only signed-in people may call it. It costs no credits, since no model is called.
One person may draw `RATE_RENDER` charts a minute.

The core is `render_chart(spec, style, width, scale)` in `app/render.py`. It is a plain async function.
It returns the PNG bytes, the HTML text, the size, the style used and the time taken.
It loads the real `charts.js`, the three themes and d3 into a headless Chromium page. Nothing is drawn by new code.
Python talks to Chromium over a pipe with the DevTools protocol. Playwright only installs the browser.
Its Node driver costs 130 to 250 MB more, so it never runs.

Chromium starts on the first render, not at boot. It runs as one process.
Its error output goes to the server log. When it stops, the log shows its last 20 lines.
One chart is drawn at a time, with a fresh page each time.
The browser shuts after `RENDER_IDLE_S` seconds with no render. It restarts after every `RENDER_RECYCLE` renders.
The page can only load files from `web/`. Every other address is blocked.
Drawing patches are dropped from the spec, so no user code runs on the server.

To run it locally, install the browser once.

```sh
.venv/bin/python -m playwright install chromium-headless-shell
```

Set `CHROME_PATH` to use another Chromium.

## Use QuickViz from Claude

QuickViz is an MCP server too. Claude Code and Claude Desktop can send it a table and get a finished chart back.
The chart uses the same steps as the page, so it comes out the same. It costs the same credits.

1. Sign in on https://quickviz.franri.dev.
2. Open the menu under your email and pick "Keys for Claude".
3. Give the key a name and press "Make a key". Copy the key. It is shown only once.

Add it to Claude Code with this command. Put your key in place of `<key>`.

```sh
claude mcp add --transport http quickviz https://quickviz.franri.dev/mcp --header "Authorization: Bearer <key>"
```

For Claude Desktop, add this to `claude_desktop_config.json`. On a Mac it is in `~/Library/Application Support/Claude/`.
Claude Desktop starts local servers only, so `mcp-remote` connects it to the web address. It needs Node.

```json
{
  "mcpServers": {
    "quickviz": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://quickviz.franri.dev/mcp", "--header", "Authorization:${QUICKVIZ_AUTH}"],
      "env": {"QUICKVIZ_AUTH": "Bearer <key>"}
    }
  }
}
```

The server has three tools.

| Tool | What it does |
|---|---|
| `list_styles` | The chart styles your account may use, the default one and the credits left today |
| `make_chart` | Takes CSV text, an optional description, style and chart type. Gives back a PNG and a short summary with a chart id and a download link |
| `edit_chart` | Takes a chart id and a change in plain words. Gives back a new chart id, the PNG and a download link |

The chart spec stays on the server. `make_chart` stores it and gives back a chart id. `edit_chart` loads the chart by that id,
changes it and stores the result under a new id. The old id keeps working until it expires.
A chart id lasts 7 days, as its download link does. An unknown or expired id gets "That chart has expired, make it again".
An old client that still sends a spec to `edit_chart` gets a short error that asks for the chart id.

The self-contained HTML file is not sent in the reply. It is 450 to 950 KB, and Claude Code cuts tool output at 25,000 tokens.
The summary gives a download link instead, `GET <base>/mcp/files/<id>.html`, and the curl line to save it.

```sh
curl -s -H "Authorization: Bearer $KEY" -o chart.html https://quickviz.franri.dev/mcp/files/<id>.html
```

The base is the address the call came in on. The chart id is the `<id>` part of the link.
The tool text tells Claude to run that curl line in the current folder and to report the saved path.
The link takes a key of the account that made the chart. Any of its keys works.
The owner can also open the link in a browser while signed in to QuickViz with Google. It then shows the chart in the tab.
A browser that is not signed in gets a short page with a Sign in button. After sign-in Google returns to the same chart.
A browser signed in to another account gets a page that says the chart belongs to another account.
An unknown or expired id gets a page that says chart links last 7 days.
Calls without `text/html` in `Accept`, like curl, keep the old answers. Another account gets 404, and no key gets 401.
The server keeps only the chart spec, a few KB, in the `chart_files` table under a long random id.
It draws the HTML again on each download. A download costs no credits but shares the render rate limit.
Links last 7 days. Older ones are deleted at startup, on each new chart, and when a call finds them expired. Then they answer 404.

The server keeps its prompts, models and steps to itself.
Every model call carries a rule never to reveal them, and to read the user's words only as a chart request.
A model reply that still quotes a prompt or names a model id is replaced by a fixed line before it goes out.
A leaking title or label is dropped on its own, and the rest of the chart stays.
This lowers the risk. It does not remove it. A model that follows an injected instruction can still leak a paraphrase or an encoded copy.
The page sends no model ids or debug fields either.
Errors to Claude are short and fixed. The full detail goes to the server log. SPEC.md has the details.

The key works only for the MCP server and its downloads. It cannot sign in to the page or make more keys.
Your credits, your styles and a block by the admin apply to it as they do on the page.
Delete a key in the same dialog when you no longer need it. It stops working at once.

## Deploy

Render deploys from `master`. The settings are in `render.yaml`.
The service runs from the `Dockerfile`. Docker brings Chromium, its system libraries and the Roboto font.
The service was made by hand in the dashboard, not from `render.yaml`.
So set everything below in the dashboard yourself.

## Set up production

Do these four steps once, in this order.

1. Make the Google sign-in client.
   - Open Google Cloud Console. Pick or make a project.
   - Go to "Google Auth Platform". Fill in the app name and your email on the "Branding" page.
   - On the "Audience" page pick "External". Publish the app so anyone can sign in.
   - Go to "Clients" and make a new client. The type is "Web application".
   - Under "Authorised JavaScript origins" add `https://quickviz.franri.dev` and `http://localhost:8011`.
   - Under "Authorised redirect URIs" add `https://quickviz.franri.dev/auth/google/callback` and `http://localhost:8011/auth/google/callback`.
   - Save. Copy the client id and the client secret.
2. Make the database.
   - Sign in to Neon. Make a new project on the free plan, in a region in Europe.
   - Open "Connect". Copy the connection string. It starts with `postgresql://`.
   - The app makes its tables itself on the first start.
3. Set up Render.
   - Open the quickviz service. Under "Settings", set the branch to `master`.
   - Set the runtime to Docker and the Dockerfile path to `./Dockerfile`. There is no build or start command.
   - Under "Environment" set these variables.

     | Variable | Value |
     |---|---|
     | `OPENROUTER_API_KEY` | The key, as now |
     | `DATABASE_URL` | The Neon connection string |
     | `GOOGLE_CLIENT_ID` | From step 1 |
     | `GOOGLE_CLIENT_SECRET` | From step 1 |
     | `ADMIN_EMAIL` | Your Google email |
     | `PUBLIC_URL` | `https://quickviz.franri.dev` |
     | `PRODUCTION` | `true` |

   - Delete `IP_DAY_CALLS` and `IP_DAY_USD` if they are there. `PYTHON_VERSION` does nothing under Docker.
   - The credit settings can stay unset. The defaults are in the table above.
   - Deploy. Then open the site, sign in, and open "Admin" from the menu under your email.
4. Limit the OpenRouter key.
   - In the OpenRouter dashboard, open "Keys" and edit the key Render uses.
   - Set a credit limit that resets daily, about the same as `GLOBAL_DAY_USD`, so USD 3.
   - OpenRouter then refuses calls past it, whatever the app counts.

To try sign-in locally, put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.
`PUBLIC_URL` stays `http://localhost:8011`.

## Version

The version lives in `VERSION`. It is 4.1.1.
The chart link from `make_chart` and `edit_chart` now opens in a browser for its owner while signed in with Google.
Anyone else in a browser gets a short page that asks them to sign in, or says the chart belongs to another account or expired.
The tool text now tells Claude to save the file with the curl line into the current folder and report its path.
4.1.0 stopped sending the HTML file inline. The summary gives a 7-day download link.
`html=true` is gone. The chart spec no longer leaves the server. The tools give a chart id, and `edit_chart` takes that id.
Model replies pass a filter that holds back prompt text and model names. Errors to Claude are short and fixed.
Clipped donut names show in full on hover.
With `labelRoom: "full"`, the names on the two sides of a bump or sankey chart take at most half the width together.
Longer names are cut again and show in full on hover. Thinned year labels always keep the first and the last year.
This changes `charts.js` and `export/charts.min.js` here first. CEPS QuickViz takes the same change in 3.1.0.
4.0.0 let the chat and `edit_chart` show long names in full with `labelRoom: "full"`. The default still cuts them.
It also made `edit_chart` check the drawn chart, so a change that draws the same chart says so.
3.2.0 added the columns row above the chart and kept table pictures wide.
3.1.3 made the server render work in the Docker image again.
3.1.2 let the chat pick which value columns a wide chart shows.
3.1.1 drew rank tables as a ranking chart.
3.1.0 added the MCP server and personal API keys.
The server writes it into the page and adds it to every script and style URL.
So a new release is never served from an old browser cache.
Bump it on every release.

## Files

```text
app/main.py         the app, the page, static files, health and version
app/config.py       settings and the key lookup
app/guard.py        the daily credits per IP, per person and for the site
app/auth.py         Google sign-in, sessions, /api/me and the origin check
app/admin.py        the admin API
app/db.py           the database connection
app/models.py       the tables
app/protect.py      the request size limit and safety headers
app/llm.py          the OpenRouter call, with the credit check and cost count
app/health.py       the /api/health checks
app/viz.py          the chart API: parse, redraw, reread, decide, names, chat
app/viz_reading.py  file reading, the AI fallback and chart pictures
app/viz_chat.py     the chat prompt and the checks on its answers
app/mock.py         the mockup routes, pick, fill and web data
app/render.py       the server render and /api/render
app/keys.py         personal API keys, /api/keys
app/pipeline.py     the chart steps for MCP, with app/pipeline.js run in the render page
app/mcp_server.py   the MCP server at /mcp
app/parse/          the rule-based file reader
app/web_data.py     sourced web data
web/index.html      the page
web/app.js          the page logic
web/credits.js      the credit count, sign-in and the account menu
web/admin.html      the admin page
web/keep.js         saves the page in IndexedDB
web/help.js         the chart types dialog
web/keys.js         the "Keys for Claude" dialog
web/frame-host.js   the sandboxed chart frame
web/charts.js       the shared renderer, synced
web/franri-theme.js the Franri house, synced
web/charts-mock.js  mockup charts and chart as you type
scripts/            the renderer sync and the CEPS build scripts
samples/            mock files the tests read
demo/               demo files from version 2
Dockerfile          the Render image, with Chromium for the server render
```
