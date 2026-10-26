# QuickViz

A free web app at https://quickviz.franri.dev.
You upload a data file or a picture of a chart. You get the chart that fits it best.
Or you describe a chart in words and get a sample with mockup data.
Then you chat with an AI to change it. You download it as PNG or HTML.
Anyone can use it without signing in.
Signing in with Google gives more credits a day.

Version 3.0.0 is built on a copy of CEPS QuickViz 2.1.0.
The CEPS invitations, passwords, tiers and styles are cut out.
Google sign-in and daily credits replace them.
The charts use the Franri house, with no logo. It is the only style.
The page and the charts use Carlito, at the CEPS sizes.

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

`ceps-theme.js` and `aiw-theme.js` are synced but not loaded by the page.
The chart frame and the renderer tests still use them.

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

## Deploy

Render deploys from `master`. The settings are in `render.yaml`.
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
   - Set the build command to `pip install -r requirements.txt`.
   - Set the start command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
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
     | `PYTHON_VERSION` | `3.12.7` |

   - Delete `IP_DAY_CALLS` and `IP_DAY_USD` if they are there.
   - The credit settings can stay unset. The defaults are in the table above.
   - Deploy. Then open the site, sign in, and open "Admin" from the menu under your email.
4. Limit the OpenRouter key.
   - In the OpenRouter dashboard, open "Keys" and edit the key Render uses.
   - Set a credit limit that resets daily, about the same as `GLOBAL_DAY_USD`, so USD 3.
   - OpenRouter then refuses calls past it, whatever the app counts.

To try sign-in locally, put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.
`PUBLIC_URL` stays `http://localhost:8011`.

## Version

The version lives in `VERSION`.
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
app/parse/          the rule-based file reader
app/web_data.py     sourced web data
web/index.html      the page
web/app.js          the page logic
web/credits.js      the credit count, sign-in and the account menu
web/admin.html      the admin page
web/keep.js         saves the page in IndexedDB
web/help.js         the chart types dialog
web/frame-host.js   the sandboxed chart frame
web/charts.js       the shared renderer, synced
web/franri-theme.js the Franri house, synced
web/charts-mock.js  mockup charts and chart as you type
scripts/            the renderer sync and the CEPS build scripts
samples/            mock files the tests read
demo/               demo files from version 2
```
