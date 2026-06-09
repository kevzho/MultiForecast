"""
Pure scraper for remaining Premier League fixtures.
Returns:
    HomeTeam,AwayTeam,Date
"""

from pathlib import Path
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

from premier_league.engine.team_names import normalize_team, CANONICAL_TEAMS

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parents[1]
DATA_DIR = PROJECT_ROOT / "data"

URL = "https://www.espn.com/soccer/story/_/id/45522470/premier-league-fixtures-schedule-2025-26-full"

MANUAL_FIXTURE_OVERRIDES = [
    # Crystal Palace vs Manchester City was postponed; rescheduled for May 22, 2026.
    {"HomeTeam": "Crystal Palace", "AwayTeam": "Man City", "Date": "2026-05-22"},
]


def _apply_manual_fixture_overrides(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    updated = df.copy()

    for fix in MANUAL_FIXTURE_OVERRIDES:
        home = normalize_team(fix["HomeTeam"])
        away = normalize_team(fix["AwayTeam"])
        date = pd.to_datetime(fix["Date"]).strftime("%Y-%m-%d")

        mask = (updated["HomeTeam"] == home) & (updated["AwayTeam"] == away)
        if mask.any():
            updated.loc[mask, "Date"] = date
        else:
            updated = pd.concat(
                [updated, pd.DataFrame([{"HomeTeam": home, "AwayTeam": away, "Date": date}])],
                ignore_index=True,
            )

    updated = updated.drop_duplicates(subset=["HomeTeam", "AwayTeam", "Date"]).reset_index(drop=True)
    return updated


def get_all_fixtures():
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(URL, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    date_pattern = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
        r"([A-Za-z]{3,9}\.?)\s+(\d{1,2}),\s+(202[56])$"
    )

    fixture_pattern = re.compile(
        r"^(.*?)\s+vs\.\s+(.*?)(?:\s+\((.*?)\))?$"
    )

    rows = []
    current_date = None

    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()

        date_match = date_pattern.match(line)
        if date_match:
            clean_date = pd.to_datetime(line, format="%A, %b. %d, %Y", errors="coerce")
            if pd.isna(clean_date):
                clean_date = pd.to_datetime(line, errors="coerce")
            if pd.notna(clean_date):
                current_date = clean_date.strftime("%Y-%m-%d")
            continue

        fixture_match = fixture_pattern.match(line)
        if fixture_match and current_date:
            home = normalize_team(fixture_match.group(1))
            away = normalize_team(fixture_match.group(2))

            # Only keep rows where both clubs normalize to our canonical set.
            if home in CANONICAL_TEAMS and away in CANONICAL_TEAMS:
                rows.append({
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "Date": current_date
                })

    df = pd.DataFrame(rows).drop_duplicates()

    if df.empty:
        raise ValueError("No fixtures parsed from page")

    df = _apply_manual_fixture_overrides(df)

    df["DateObj"] = pd.to_datetime(df["Date"])
    df = df.sort_values(["DateObj", "HomeTeam", "AwayTeam"]).drop(columns="DateObj")
    df = df.reset_index(drop=True)

    return df[["HomeTeam", "AwayTeam", "Date"]]

def get_fixtures_by_date_range(start_date=None, end_date=None):
    df = get_all_fixtures()
    if start_date:
        df = df[df["Date"] >= start_date]
    if end_date:
        df = df[df["Date"] <= end_date]
    return df.reset_index(drop=True)

def get_next_n_fixtures(n=10):
    df = get_all_fixtures()
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    df = df[df["Date"] >= today]
    return df.head(n).reset_index(drop=True)

def get_remaining_fixtures():
    df = get_all_fixtures().copy()
    df["Date"] = pd.to_datetime(df["Date"])
    today = pd.Timestamp.today().normalize()
    df = df[df["Date"] >= today]
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)

def save_fixtures_to_csv(season="2526"):
    df = get_remaining_fixtures()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / f"remaining_fixtures{season}.csv"

    df.to_csv(csv_path, index=False)
    print(f"Saved {len(df)} fixtures to {csv_path}")

    return df

if __name__ == "__main__":
    save_fixtures_to_csv()
