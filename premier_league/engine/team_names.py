"""
Team-name normalization utilities.

Why this exists:
- External fixture sources sometimes include annotations like times, TV notes,
  or footnote markers (e.g. "Fulham (15:00 UK)*").
- Different data sources use different long/short club names.
"""

from __future__ import annotations

import re


TEAM_NAME_MAP: dict[str, str] = {
    "AFC Bournemouth": "Bournemouth",
    "Bournemouth": "Bournemouth",
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Brentford": "Brentford",
    "Brighton & Hove Albion": "Brighton",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds United": "Leeds",
    "Leeds": "Leeds",
    "Liverpool": "Liverpool",
    "Manchester City": "Man City",
    "Man City": "Man City",
    "Manchester United": "Man United",
    "Man United": "Man United",
    "Newcastle United": "Newcastle",
    "Newcastle": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Nottm Forest": "Nott'm Forest",
    "Nott'm Forest": "Nott'm Forest",
    "Sunderland": "Sunderland",
    "Tottenham Hotspur": "Tottenham",
    "Tottenham": "Tottenham",
    "West Ham United": "West Ham",
    "West Ham": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Wolves": "Wolves",
}

CANONICAL_TEAMS = set(TEAM_NAME_MAP.values())

_FOOTNOTE_RE = re.compile(r"[\*\u2020\u2021]+$")  # *, dagger, double-dagger
_TRAILING_PARENS_RE = re.compile(r"\s*\([^)]*\)\s*$")


def clean_team_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name)).strip()
    # Remove trailing footnote markers first (they can appear after parentheses).
    name = _FOOTNOTE_RE.sub("", name).strip()
    # Remove trailing parenthetical annotations (times, TV notes, etc).
    name = _TRAILING_PARENS_RE.sub("", name).strip()
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_team(name: str) -> str:
    cleaned = clean_team_name(name)
    return TEAM_NAME_MAP.get(cleaned, cleaned)

