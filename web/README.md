# Football Forecast web

Next.js frontend for the Big Five domestic league and World Cup prediction products. The application reads versioned JSON from `public/data`; it does not calculate forecasts in the browser.

## Run locally

```bash
npm install
npm run dev
```

Validation commands:

```bash
npm run lint
npm run typecheck
npm run build
```

## Deploy to Vercel

Create a Vercel project from the repository and set **Root Directory** to `web`. The included `vercel.json` selects the Next.js framework and build command.

Set `NEXT_PUBLIC_STREAMLIT_URL` when the header should link to the live Streamlit analytics application. If it is unset or is not an HTTP(S) URL, the link is omitted.

## Data artifacts

`public/data/manifest.json` is the only index the interface loads directly. Schema `1.0.0` has this shape:

```text
manifest
├── schemaVersion
├── artifactVersion
├── generatedAt
├── leagues[]
│   ├── id, name, shortName, country, code
│   ├── season, expectedTeams
│   └── status, dataUrl, generatedAt, note
└── worldCup
    ├── id, name, shortName, code
    ├── edition, expectedTeams
    └── status, dataUrl, generatedAt, note
```

Competition entries use one of five statuses: `ready`, `stale`, `building`, `unavailable`, or `sample`. A missing `dataUrl` produces a deliberate empty state.

Exact TypeScript contracts live in `lib/contracts.ts`:

- `LeagueForecastArtifact` covers standings, season probabilities, fixtures and match breakdowns.
- `TournamentForecastArtifact` covers groups, team progression, fixtures and knockout rounds.
- `ForecastFixture` and `MatchForecast` are shared across domestic and tournament views.

`python ../export_forecasts.py` replaces the development samples with complete league and tournament artifacts and updates the manifest. Published artifacts set `isDemo` to `false`; development samples remain explicitly labeled.

## Project map

```text
app/
├── page.tsx                         overview
├── leagues/[slug]/                  table forecast
│   ├── fixtures/                    fixture list
│   └── matches/[matchId]/           match breakdown
├── world-cup/                       tournament overview
│   ├── groups/                      groups and fixtures
│   ├── bracket/                     knockout progression
│   └── matches/[matchId]/           match breakdown
└── methodology/                     methods and freshness guide
components/
├── forecast-components.tsx          shared fixture and match views
├── league-view.tsx                  domestic views
├── world-cup-view.tsx               tournament views
├── overview-client.tsx              product overview
├── site-header.tsx                  navigation and footer
└── ui.tsx                           shared presentation components
lib/
├── contracts.ts                     artifact schema
├── data.ts                          browser artifact loader
└── format.ts                        display formatting
public/data/                          versioned forecast artifacts
```

## Publishing rules

- Probabilities are decimals from `0` to `1`.
- Timestamps are ISO 8601 strings or `null` when unknown.
- Unknown numerical values are `null`, never placeholder estimates.
- Outcome probabilities for a match should sum to `1` within floating-point tolerance.
- IDs must remain stable between a fixture list and its match-detail URL.
- `coverage` must reflect partial exports so the interface can disclose gaps.
- The artifact’s `model` and `methodology` fields describe what actually ran; the UI does not infer them.
