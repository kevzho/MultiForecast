# Deployment

## Vercel

Create a Vercel project from this repository and set **Root Directory** to `web`. The framework is Next.js and the production build command is `npm run build`.

Set this optional environment variable to link the public site to the analytics app:

```text
NEXT_PUBLIC_STREAMLIT_URL=https://your-app.streamlit.app
```

Forecast JSON is generated before deployment and committed under `web/public/data/`. No Python runtime or private data-source token is required by Vercel. This checkout is not linked to a Vercel project locally; connect it and confirm its Root Directory is `web`.

## Streamlit

Deploy the same repository with:

```text
Entry point: app.py
Python: 3.11
Dependencies: requirements.txt
```

The root `.streamlit/config.toml` contains the shared theme and headless server settings. Do not commit `.streamlit/secrets.toml`.

Set `FORECAST_DATA_URL` to the deployed site's `/data` URL so Streamlit reads the same published snapshot. Without it, Streamlit reads the checkout's local artifacts. The published panel caches for five minutes; interactive model runs remain available below it.

## Automated refresh

`.github/workflows/live-refresh.yml` runs every 15 minutes. It refreshes Big Five results, licensed official standings, pre-kickoff odds, and lower-cost forecast artifacts, then commits snapshots and `web/public/data`. GitHub scheduling and Vercel builds can add delay beyond 15 minutes. `.github/workflows/daily-refresh.yml` backfills up to ten real historical seasons and runs fuller validation and World Cup export daily. Both jobs share one concurrency group.

Configure these GitHub Actions secrets before enabling the live feed:

| Secret | Use |
| --- | --- |
| `FOOTBALL_DATA_ORG_TOKEN` | football-data.org v4 fixtures, live scores, official standings, stable source IDs |
| `ODDS_API_KEY` | The Odds API pre-kickoff 1X2 and 2.5 totals snapshots |

Both are optional for local development. Missing credentials leave the existing ESPN and football-data.co.uk path active; no official table or market edge is invented. The football-data.org plan must include all five competitions and permit the refresh frequency. The Odds API usage depends on markets and bookmaker region. Check provider terms before publishing bookmaker prices.

Set the optional `ODDS_REGION` workflow environment variable to change bookmaker region; it defaults to `uk`.

`data/live/{league}.json` holds the last valid licensed snapshot with source IDs and timestamps. `data/odds_snapshots.csv` stores changed bookmaker prices keyed by stable fixture ID and capture time. Forecasts never train on simulated results. The odds blend activates only after real pre-kickoff snapshots span at least two seasons and improves log loss on a recent season kept out of fitting. Until then the site shows base-model probabilities and any available market comparison.

To evaluate personal bets, keep a private CSV with `fixture_id,market,selection,decimal_odds,stake` and optional `model_probability`, then run `python evaluate_bets.py path/to/bets.csv`. It reports settled ROI and a Brier score for logged probabilities. `data/bets.csv` is ignored by Git; bets never become match-result labels.

For a manual local publication:

```bash
python refresh_all.py
cd web
npm run build
```

If a live source is unavailable, the refresh keeps the last valid schedule. If artifact generation fails, the workflow exits non-zero and does not publish a partial manifest.
