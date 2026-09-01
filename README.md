# MultiForecast

MultiForecast predicts the 2026 World Cup and the 2026/27 seasons in the Premier League, Serie A, Ligue 1, La Liga, and Bundesliga. It ships as two applications backed by one Python forecasting system:

- `web/`: the complete public Next.js product, ready for Vercel.
- `app.py`: the Streamlit analytics application for live model runs and deeper exploration.

Both surfaces use the same versioned JSON forecast contract.

## Product coverage

- World Cup group advancement, knockout progression, title probabilities, and projected bracket.
- Domestic title, UEFA qualification, relegation, expected points, and full position distributions.
- Elo, Elo-Poisson, attack/defense Poisson, Skellam, Dixon-Coles, and Bradley-Terry/Davidson models.
- Walk-forward model comparison with log loss, Brier score, RPS, and calibration.
- Match previews with W/D/L probabilities, expected goals, likely scorelines, O/U 2.5, BTTS, clean sheets, engine comparison, and season-impact scenarios.
- Daily last-known-good data refreshes and static artifact publication.

## Repository map

```text
app.py                    Streamlit entry point
export_forecasts.py       Builds all Vercel forecast artifacts
refresh_all.py            Daily data and artifact refresh
domestic/                 Shared Big Five engine, UI, and pipeline
worldcup/                 World Cup models, simulation, UI, and export
premier_league/           Legacy compatibility package
web/                      Next.js/Vercel application
data/domestic/processed/  Canonical domestic match data
data/wc/                  World Cup inputs and fitted strengths
tests/                    Python unit and integration tests
docs/                     Architecture, data, modeling, and deployment guides
```

See [domestic/README.md](domestic/README.md) for the domestic package map and [web/README.md](web/README.md) for frontend routes.

## Run locally

Python 3.11 is the deployed runtime.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Generate the shared artifacts and run the Vercel app:

```bash
python export_forecasts.py
cd web
npm install
npm run dev
```

The frontend is available at `http://localhost:3000`; Streamlit defaults to `http://localhost:8501`.

## Refresh and verify

```bash
python -m domestic.refresh
python refresh_all.py
python -m pytest -q

cd web
npm run lint
npm run typecheck
npm run build
```

`refresh_all.py` updates current schedules and results, refreshes the World Cup inputs, reruns model selection and simulations, and writes `web/public/data/manifest.json` plus one artifact per competition.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data and models](docs/DATA_AND_MODELS.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Domestic engine](domestic/README.md)
- [World Cup engine](worldcup/README.md)
- [Vercel frontend](web/README.md)

Forecasts are probabilistic estimates, not betting advice.
