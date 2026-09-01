# Domestic forecasting package

The domestic package handles the Premier League, Serie A, Ligue 1, La Liga, and Bundesliga through configuration rather than league-specific copies.

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | League sizes, source codes, standings rules, qualification assumptions, and storage paths |
| `data.py` | Canonical schema, aliases, football-data ingestion, validation, history, and rollover detection |
| `sources.py` | Full 2026/27 ESPN fixture schedules merged with football-data results |
| `models.py` | Scoreline distributions and all domestic match models |
| `validation.py` | Walk-forward evaluation, calibration, selection, and ensemble weights |
| `standings.py` | Score-aware tables and configurable tiebreakers |
| `simulation.py` | Seeded scoreline Monte Carlo and conditional match scenarios |
| `breakdowns.py` | Match probabilities, goal markets, form, comparison, and season impact |
| `pipeline.py` | Training, rollover, model selection, simulation, and preview orchestration |
| `artifacts.py` | Generic versioned JSON envelopes |
| `refresh.py` | Big Five current-season refresh command |
| `ui.py` | Streamlit domestic-league interface |

## Common entry points

```python
from domestic import build_forecast, get_league, load_matches

config = get_league("bundesliga")
matches = load_matches(config)
run = build_forecast(config, n_simulations=2_000)
```

```bash
python -m domestic.refresh
python export_forecasts.py --league bundesliga
```

Generated fixtures are confined to tests. Production refreshes use a verified remote schedule or the last valid canonical file.
