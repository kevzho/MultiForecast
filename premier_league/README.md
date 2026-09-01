# Legacy Premier League Engine

This package preserves the original 2025/26 Premier League predictor for reference and backward compatibility. It is no longer the production entry point.

The 2026/27 implementation lives in [`domestic/`](../domestic/README.md). That package covers the Premier League, Serie A, Ligue 1, La Liga, and Bundesliga with shared data, validation, model-selection, simulation, and match-breakdown components.

Use the current commands from the repository root:

```bash
streamlit run app.py
python refresh_all.py
python export_forecasts.py
```

The Vercel application reads the generated artifacts in `web/public/data/`. See the root [`README.md`](../README.md) for the repository map and deployment instructions.
