# Premier League Predictor

The Premier League predictor forecasts the live 2025/26 season with Elo ratings and Monte Carlo simulation. It produces title probability, top-four probability, relegation probability, expected final points, and final-position distributions for every club.

## How It Works

The engine starts from the current league table and remaining fixtures, converts team Elo ratings into match outcome probabilities, samples the rest of the season many times, and aggregates the final tables.

Key modules:

- `engine/elo.py`: Elo expected-score math, match updates, and rating persistence.
- `engine/simulation.py`: Monte Carlo season simulation.
- `engine/pipeline.py`: cache-aware orchestration around the simulation.
- `engine/table.py`: current table construction from played matches.
- `engine/remaining_fixtures.py`: remaining fixture scraping and manual overrides.
- `engine/load_data.py` and `engine/fetch_data.py`: local CSV loading and football-data.co.uk refresh.
- `dashboard.py`: Streamlit rendering for the Premier League tab.
- `refresh.py`: daily refresh entry point used by GitHub Actions.
- `run.py`: command-line simulation runner.

## Data Flow

Primary data lives in the repo-level `data/` directory:

- `data/E0_2526.csv`: match results and fixtures from football-data.co.uk.
- `data/summary_table2526.csv`: current table snapshot.
- `data/power_rankings_2526.csv`: current Elo power rankings.
- `data/remaining_fixtures2526.csv`: remaining PL fixtures.
- `data/simulation_results_2526.csv`: latest aggregated forecast output.

Cache files remain in repo-level `cache/` so the app and daily refresh keep their previous behavior.

## Daily Refresh

The GitHub Action `.github/workflows/daily-refresh.yml` runs:

```bash
python -m premier_league.refresh
```

That refreshes source data, rebuilds Elo ratings, updates fixtures and the summary table, clears stale simulation cache, and reruns the PL simulation.

## Run Locally

```bash
streamlit run app.py
python -m premier_league.refresh
python -m premier_league.run
```

## Methodology

Match probabilities are based on generalized Elo with a home-advantage adjustment and an empirical draw rate from current season results. The Monte Carlo layer samples each remaining match and ranks every simulated final table.

## Limitations

The model is intentionally compact. It does not yet include injuries, transfers, betting markets, lineup strength, tactical matchups, or match-level goal models. Early-season forecasts can be volatile because the played-match sample is small.
