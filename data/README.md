# Data layout

```text
domestic/
├── processed/<season>/<league>.csv  committed canonical training and fixture data
├── raw/                             ignored source cache
└── last_known_good/                 ignored fallback cache
wc/                                  World Cup groups, fixtures, results, ratings, and strengths
```

Domestic processed files use the canonical schema documented in [docs/DATA_AND_MODELS.md](../docs/DATA_AND_MODELS.md). Historical source codes are `E0` (Premier League), `I1` (Serie A), `F1` (Ligue 1), `SP1` (La Liga), and `D1` (Bundesliga).

The top-level Premier League CSVs are retained for compatibility with the original `premier_league/` package. New code should use `domestic.data.load_matches`.

Run `python -m domestic.refresh` to update current schedules or `python refresh_all.py` to refresh both products and rebuild the Vercel artifacts.
