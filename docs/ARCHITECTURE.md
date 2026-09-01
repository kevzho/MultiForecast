# Architecture

## Data flow

```text
football-data results ─┐
                      ├─ canonical domestic matches ─ models ─ validation
ESPN full schedules ──┘                                  │
                                                        ▼
World Cup inputs ─ World Cup models ─────────────── simulations
                                                        │
                                                        ▼
                                          versioned forecast artifacts
                                                │               │
                                                ▼               ▼
                                           Next.js/Vercel   Streamlit analytics
```

The domestic and World Cup simulators share modeling concepts but retain separate competition rules. Domestic leagues rank a season table; the World Cup ranks groups, third-place qualifiers, and a knockout bracket.

## Boundaries

- `domestic/` owns Big Five data, match models, league rules, forecasts, and match previews.
- `worldcup/` owns international inputs, FIFA tiebreakers, bracket construction, and tournament simulation.
- `export_forecasts.py` is the publication boundary. It converts both products into the TypeScript contract in `web/lib/contracts.ts`.
- `web/` never fits models during a request. Vercel serves deterministic, cacheable artifacts produced by the Python pipeline.
- `app.py` can run models interactively and is the deeper analytics surface.

## Reliability

Current schedules are validated for team count, fixture count, duplicate home/away pairings, dates, and scores. Remote failures use the last canonical file. A failed artifact build fails the scheduled workflow; a transient source failure does not discard valid data.

Artifact and cache identity includes the schema version, competition, season, model, data timestamp, simulation count, and seed where applicable.
