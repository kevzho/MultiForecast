# MultiForecast

MultiForecast is a dual-mode football forecaster: a Premier League season simulator and a World Cup 2026 tournament predictor in one Streamlit app. Both products share a Monte Carlo and statistical-modeling foundation, while keeping league-table logic and group-plus-knockout tournament logic cleanly separated.

![Premier League dashboard](img/pl.png)

## Architecture

```text
app.py                         # Streamlit entry point with two tabs
premier_league/
  dashboard.py                 # Premier League tab
  refresh.py                   # Daily PL refresh workflow entry
  run.py                       # PL simulation runner
  engine/                      # Premier League engine modules
  viz/                         # PL analysis notebooks
worldcup/
  ui.py                        # World Cup tab
  data.py, model.py            # WC loaders and match models
  tiebreakers.py, bracket.py   # FIFA ranking and knockout logic
  simulate.py                  # WC tournament Monte Carlo
data/
  *.csv, *.json                # Premier League data
  wc/                          # World Cup data layer
cache/                         # App and simulation caches
.github/workflows/
  daily-refresh.yml            # Automated PL refresh
```

## Shared Concepts

Both products use rating-based match probabilities, scoreline or result sampling, Monte Carlo aggregation, cache-aware outputs, and a daily GitHub Action refresh pattern. They diverge where football formats diverge: the Premier League product simulates a 20-team league table, while the World Cup product simulates groups, FIFA tiebreakers, third-place qualification, and a knockout bracket.

## Run Locally

```bash
streamlit run app.py
```

Premier League refresh and pipeline:

```bash
python -m premier_league.refresh
python -m premier_league.run
```

World Cup simulator smoke run:

```bash
python -m worldcup.simulate
```

## Automated Daily Refresh

The GitHub Action `Daily Refresh (PL + World Cup)` runs `python refresh_all.py`
every day at 10:00 UTC and commits updated tracked `data/` outputs. Premier
League and World Cup live fetch steps are non-fatal, so a flaky upstream source
prints a warning and the job continues with the last-good data where possible.

## Product Docs

- [Premier League predictor](premier_league/README.md)
- [World Cup 2026 predictor](worldcup/README.md)

## Modeling Roadmap

The modeling path is Elo first, then Poisson/Skellam scoreline models, then Dixon-Coles calibration, and finally richer ML features once stable data and validation loops are in place.

## Changelog

- `v2.0`: World Cup 2026 predictor and monorepo restructure.
- `v1.x`: Premier League Monte Carlo dashboard.
