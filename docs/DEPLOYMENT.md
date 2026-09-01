# Deployment

## Vercel

Create a Vercel project from this repository and set **Root Directory** to `web`. The framework is Next.js and the production build command is `npm run build`.

Set this optional environment variable to link the public site to the analytics app:

```text
NEXT_PUBLIC_STREAMLIT_URL=https://your-app.streamlit.app
```

Forecast JSON is generated before deployment and committed under `web/public/data/`. No Python runtime or private data-source token is required by Vercel.

## Streamlit

Deploy the same repository with:

```text
Entry point: app.py
Python: 3.11
Dependencies: requirements.txt
```

The root `.streamlit/config.toml` contains the shared theme and headless server settings. Do not commit `.streamlit/secrets.toml`.

## Automated refresh

`.github/workflows/daily-refresh.yml` runs the source refresh and artifact exporter each day. It commits canonical processed data and public forecast artifacts after verification. Configure branch protection so pull-request CI must pass Python tests, frontend lint, TypeScript checking, and the Next.js production build.

For a manual local publication:

```bash
python refresh_all.py
cd web
npm run build
```

If a live source is unavailable, the refresh keeps the last valid schedule. If artifact generation fails, the workflow exits non-zero and does not publish a partial manifest.
