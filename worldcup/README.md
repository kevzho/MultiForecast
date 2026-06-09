# World Cup 2026 Predictor

The World Cup predictor forecasts the 48-team 2026 tournament: group advancement, group winner probability, knockout progression, finalist probability, and win-cup probability. It is built as a standalone `worldcup/` package so tournament logic can evolve separately from the Premier League engine.

## Current Capabilities

- Elo-anchored scoreline Monte Carlo model.
- FIFA group ranking and tiebreakers.
- Third-place ranking for the 12 group-third teams.
- Verified Round of 32 bracket structure and third-place assignment constraints.
- Live-results support through `data/wc/wc2026_results.csv`.

## Modeling Ladder

The current baseline is `EloModel`, an Elo-anchored Poisson scoreline approximation that exactly matches Elo-derived W/D/L probabilities. The next modeling layer is Poisson + Skellam, followed by Dixon-Coles calibration and machine-learning features when enough validated international data is available.

## Data Files

World Cup data lives under `data/wc/`:

- `wc2026_groups.csv`: 12 groups, 48 teams, FIFA rank seeds, confederations.
- `wc2026_fixtures.csv`: group fixtures plus knockout placeholders.
- `wc2026_results.csv`: live result stub.
- `intl_elo_ratings.csv`: international Elo seed ratings.
- `SOURCES.md`: rank, venue, Elo, and fixture verification notes.

## Key Modules

- `data.py`: loaders and validation.
- `model.py`: `ScorelineDist`, Elo helpers, and `EloModel`.
- `tiebreakers.py`: FIFA group and third-place ranking rules.
- `bracket.py`: Round of 32 map and knockout advancement helpers.
- `simulate.py`: full tournament Monte Carlo.
- `ui.py`: Streamlit tab renderer.

## Sources

- Official 2026 draw: <https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026>
- International results: <https://github.com/martj42/international_results>
- FU-Berlin WM2026 ratings: <https://www.wiwiss.fu-berlin.de/wm2026/Rankings/index.html>
- FIFA men's ranking: <https://inside.fifa.com/fifa-world-ranking/men>

## Methods & Limitations

International tournaments are noisy. Each team plays only three group matches before knockout volatility takes over, and small rating differences can swing advancement paths. Treat probabilities as calibrated ranges, not certainties. The model is designed to update cleanly as live results, better ratings, and stronger scoreline models are added.
