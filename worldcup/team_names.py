"""Canonical team names for the 2026 World Cup data layer."""

CANONICAL_WC_TEAMS = {
    "Mexico",
    "South Korea",
    "South Africa",
    "Czechia",
    "Canada",
    "Switzerland",
    "Qatar",
    "Bosnia and Herzegovina",
    "Brazil",
    "Morocco",
    "Scotland",
    "Haiti",
    "United States",
    "Paraguay",
    "Australia",
    "Turkiye",
    "Germany",
    "Ecuador",
    "Ivory Coast",
    "Curacao",
    "Netherlands",
    "Japan",
    "Sweden",
    "Tunisia",
    "Belgium",
    "Egypt",
    "Iran",
    "New Zealand",
    "Spain",
    "Uruguay",
    "Saudi Arabia",
    "Cape Verde",
    "France",
    "Senegal",
    "Norway",
    "Iraq",
    "Argentina",
    "Austria",
    "Algeria",
    "Jordan",
    "Portugal",
    "Colombia",
    "Uzbekistan",
    "DR Congo",
    "England",
    "Croatia",
    "Panama",
    "Ghana",
}

TEAM_NAME_MAP = {
    "Czech Republic": "Czechia",
    "Czechia": "Czechia",
    "Turkey": "Turkiye",
    "Türkiye": "Turkiye",
    "Turkiye": "Turkiye",
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "IR Iran": "Iran",
    "Iran": "Iran",
    "Congo DR": "DR Congo",
    "DR Congo": "DR Congo",
    "Cote d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "USA": "United States",
    "United States": "United States",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
}


def normalize_intl_team(name: str) -> str:
    """Return the canonical World Cup team name when a known variant is supplied."""
    if name is None:
        return name
    clean_name = name.strip()
    return TEAM_NAME_MAP.get(clean_name, clean_name)

