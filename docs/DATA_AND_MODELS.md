# Data and models

## Domestic data

Canonical columns are:

```text
league, season, date, home_team, away_team,
home_goals, away_goals, status, source_updated_at
```

Full current schedules come from ESPN and completed results are overlaid from football-data.co.uk. Five historical seasons per league are stored in `data/domestic/processed/` for fitting and walk-forward evaluation. Raw responses and last-known-good mirrors are local caches and are not committed.

Club aliases normalize source-specific names before fitting. Returning Elo ratings regress toward the league mean between seasons; promoted clubs receive conservative seeds below the returning-club floor and update normally once results arrive.

## Match models

- **Elo**: the 2025/26 result model and home advantage baseline.
- **Elo-Poisson**: preserves Elo W/D/L mass while producing scorelines.
- **Poisson/Skellam**: recency-weighted attack and defense strengths with fast result probabilities.
- **Dixon-Coles**: adjusts correlated low-scoring results.
- **Bradley-Terry/Davidson**: directly models wins, draws, and losses, then shapes a score grid.
- **Ensemble**: optional performance-weighted combination of fitted score grids.

The production model is selected separately for each league. Walk-forward tests fit only matches completed before each prediction and report log loss, Brier score, Ranked Probability Score, and calibration error. The Elo baseline remains selected unless another engine improves the chosen out-of-sample metric.

## Season simulation

Every unplayed fixture samples a scoreline. The table therefore tracks points, wins, goals for, goals against, goal difference, away goals, and form. Each league applies its configured ranking and relegation/playoff rules.

UEFA qualification slots are explicit assumptions because domestic cup winners and European performance places can change the final allocation. The applications display that caveat next to the forecast.

## Match breakdowns

Each scheduled match includes W/D/L, expected goals, top scorelines, O/U 2.5, BTTS, clean-sheet probabilities, model comparison, recent form, and calibration status. Season-impact views condition the score grid on a home win, draw, or away win and rerun the remaining season.
