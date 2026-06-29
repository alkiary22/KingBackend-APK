"""TheSportsDB integration for auto-updating World Cup 2026 match results (free tier).

API: https://www.thesportsdb.com/api/v1/json/3/eventsseason.php?id=4429&s=2026
"""

import httpx
import logging

logger = logging.getLogger(__name__)

THESPORTSDB_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsseason.php"
WORLD_CUP_LEAGUE_ID = "4429"
SEASON = "2026"

# Map TheSportsDB team names → our team codes (from teams_data.py)
TSDB_TEAM_MAP = {
    # Hosts
    "Mexico": "mx",
    "Canada": "ca",
    "USA": "us",
    "United States": "us",
    # UEFA
    "England": "gb-eng",
    "France": "fr",
    "Germany": "de",
    "Spain": "es",
    "Portugal": "pt",
    "Netherlands": "nl",
    "Belgium": "be",
    "Croatia": "hr",
    "Switzerland": "ch",
    "Austria": "at",
    "Norway": "no",
    "Czech Republic": "cz",
    "Bosnia-Herzegovina": "ba",
    "Bosnia and Herzegovina": "ba",
    "Scotland": "gb-sct",
    "Sweden": "se",
    "Turkey": "tr",
    # CONMEBOL
    "Brazil": "br",
    "Argentina": "ar",
    "Uruguay": "uy",
    "Colombia": "co",
    "Ecuador": "ec",
    "Paraguay": "py",
    # AFC
    "Japan": "jp",
    "South Korea": "kr",
    "Korea Republic": "kr",
    "Iran": "ir",
    "Australia": "au",
    "Saudi Arabia": "sa",
    "Qatar": "qa",
    "Iraq": "iq",
    "Jordan": "jo",
    "Uzbekistan": "uz",
    # CAF
    "Morocco": "ma",
    "Egypt": "eg",
    "Senegal": "sn",
    "Algeria": "dz",
    "Tunisia": "tn",
    "Ghana": "gh",
    "Ivory Coast": "ci",
    "Cote d'Ivoire": "ci",
    "South Africa": "za",
    "Cape Verde": "cv",
    "Cape Verde Islands": "cv",
    "Congo DR": "cd",
    "DR Congo": "cd",
    "Democratic Republic of Congo": "cd",
    # CONCACAF / OFC
    "Panama": "pa",
    "Haiti": "ht",
    "Curacao": "cw",
    "Curaçao": "cw",
    "New Zealand": "nz",
}

FINISHED_STATUSES = {"match finished", "ft", "finished", "aet", "pen"}


async def fetch_world_cup_events():
    """Fetch all World Cup 2026 events from TheSportsDB."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            THESPORTSDB_URL,
            params={"id": WORLD_CUP_LEAGUE_ID, "s": SEASON},
        )
        r.raise_for_status()
        return r.json().get("events") or []


def normalize_team_code(name):
    if not name:
        return None
    n = name.strip()
    if n in TSDB_TEAM_MAP:
        return TSDB_TEAM_MAP[n]
    # case-insensitive fallback
    nl = n.lower()
    for k, v in TSDB_TEAM_MAP.items():
        if k.lower() == nl:
            return v
    return None


def parse_score(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
