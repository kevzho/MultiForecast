# World Cup 2026 Data Sources

This data layer is intentionally self-contained for phase 1. The group assignments use the user-provided official confirmed 2026 draw from December 5, 2025.

## FIFA Rankings

`wc2026_groups.csv` stores best-effort integer FIFA rankings for all 48 teams. Each row should be verified against the FIFA/Coca-Cola Men's World Ranking at <https://inside.fifa.com/fifa-world-ranking/men> before any production use.

Ranks currently seeded for verification:

| Team | Seed Rank |
| --- | ---: |
| Mexico | 13 |
| South Korea | 22 |
| South Africa | 56 |
| Czechia | 39 |
| Canada | 30 |
| Switzerland | 20 |
| Qatar | 53 |
| Bosnia and Herzegovina | 74 |
| Brazil | 6 |
| Morocco | 8 |
| Scotland | 43 |
| Haiti | 83 |
| United States | 16 |
| Paraguay | 48 |
| Australia | 24 |
| Turkiye | 26 |
| Germany | 9 |
| Ecuador | 25 |
| Ivory Coast | 44 |
| Curacao | 82 |
| Netherlands | 7 |
| Japan | 18 |
| Sweden | 28 |
| Tunisia | 49 |
| Belgium | 10 |
| Egypt | 32 |
| Iran | 21 |
| New Zealand | 89 |
| Spain | 1 |
| Uruguay | 15 |
| Saudi Arabia | 58 |
| Cape Verde | 72 |
| France | 2 |
| Senegal | 17 |
| Norway | 33 |
| Iraq | 60 |
| Argentina | 3 |
| Austria | 23 |
| Algeria | 36 |
| Jordan | 64 |
| Portugal | 5 |
| Colombia | 12 |
| Uzbekistan | 57 |
| DR Congo | 61 |
| England | 4 |
| Croatia | 11 |
| Panama | 38 |
| Ghana | 76 |

## Fixtures

The group-stage fixture grid is generated as a deterministic round robin within each group. Dates are assigned within the requested June 11-27, 2026 window.

TODO: Verify exact FIFA match schedule, match numbering, and venues when the official fixture list is loaded. Non-host group fixtures currently use `TBD` and default to `Neutral=True`.

Host-team group matches are marked `Neutral=False` only when the seeded venue is in that host's country:

- Mexico group matches in Mexico
- Canada group matches in Canada
- United States group matches in the United States

Knockout rows are placeholders with `TBD` teams and venues, using the requested date windows.

## Elo Ratings

`intl_elo_ratings.csv` seeds every team with a reasonable international Elo rating ordered by seeded FIFA rank, ranging from about 2100 for the top team to about 1500 for the lowest seeded team. These are placeholders for phase 1 and should be verified or replaced with values from <https://www.eloratings.net/> before model calibration.
