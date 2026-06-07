"""Canonical NBA team metadata. Tricodes are the primary key everywhere."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    tricode: str            # e.g. "BOS"
    full_name: str          # e.g. "Boston Celtics"
    city: str
    nickname: str
    conference: str         # "East" | "West"
    division: str
    bbr_code: str           # Basketball-Reference uses different codes (e.g. CHA -> CHO)
    primary_color: str
    secondary_color: str


# NBA.com official stats team IDs — used to build logo URLs:
# https://cdn.nba.com/logos/nba/<nba_id>/primary/L/logo.svg
NBA_TEAM_IDS: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}


TEAMS: list[Team] = [
    # East - Atlantic
    Team("BOS", "Boston Celtics", "Boston", "Celtics", "East", "Atlantic", "BOS", "#007A33", "#BA9653"),
    Team("BKN", "Brooklyn Nets", "Brooklyn", "Nets", "East", "Atlantic", "BRK", "#000000", "#FFFFFF"),
    Team("NYK", "New York Knicks", "New York", "Knicks", "East", "Atlantic", "NYK", "#006BB6", "#F58426"),
    Team("PHI", "Philadelphia 76ers", "Philadelphia", "76ers", "East", "Atlantic", "PHI", "#006BB6", "#ED174C"),
    Team("TOR", "Toronto Raptors", "Toronto", "Raptors", "East", "Atlantic", "TOR", "#CE1141", "#000000"),
    # East - Central
    Team("CHI", "Chicago Bulls", "Chicago", "Bulls", "East", "Central", "CHI", "#CE1141", "#000000"),
    Team("CLE", "Cleveland Cavaliers", "Cleveland", "Cavaliers", "East", "Central", "CLE", "#860038", "#FDBB30"),
    Team("DET", "Detroit Pistons", "Detroit", "Pistons", "East", "Central", "DET", "#C8102E", "#1D42BA"),
    Team("IND", "Indiana Pacers", "Indiana", "Pacers", "East", "Central", "IND", "#002D62", "#FDBB30"),
    Team("MIL", "Milwaukee Bucks", "Milwaukee", "Bucks", "East", "Central", "MIL", "#00471B", "#EEE1C6"),
    # East - Southeast
    Team("ATL", "Atlanta Hawks", "Atlanta", "Hawks", "East", "Southeast", "ATL", "#E03A3E", "#C1D32F"),
    Team("CHA", "Charlotte Hornets", "Charlotte", "Hornets", "East", "Southeast", "CHO", "#1D1160", "#00788C"),
    Team("MIA", "Miami Heat", "Miami", "Heat", "East", "Southeast", "MIA", "#98002E", "#F9A01B"),
    Team("ORL", "Orlando Magic", "Orlando", "Magic", "East", "Southeast", "ORL", "#0077C0", "#C4CED4"),
    Team("WAS", "Washington Wizards", "Washington", "Wizards", "East", "Southeast", "WAS", "#002B5C", "#E31837"),
    # West - Northwest
    Team("DEN", "Denver Nuggets", "Denver", "Nuggets", "West", "Northwest", "DEN", "#0E2240", "#FEC524"),
    Team("MIN", "Minnesota Timberwolves", "Minnesota", "Timberwolves", "West", "Northwest", "MIN", "#0C2340", "#236192"),
    Team("OKC", "Oklahoma City Thunder", "Oklahoma City", "Thunder", "West", "Northwest", "OKC", "#007AC1", "#EF3B24"),
    Team("POR", "Portland Trail Blazers", "Portland", "Trail Blazers", "West", "Northwest", "POR", "#E03A3E", "#000000"),
    Team("UTA", "Utah Jazz", "Utah", "Jazz", "West", "Northwest", "UTA", "#002B5C", "#00471B"),
    # West - Pacific
    Team("GSW", "Golden State Warriors", "Golden State", "Warriors", "West", "Pacific", "GSW", "#1D428A", "#FFC72C"),
    Team("LAC", "LA Clippers", "Los Angeles", "Clippers", "West", "Pacific", "LAC", "#C8102E", "#1D428A"),
    Team("LAL", "Los Angeles Lakers", "Los Angeles", "Lakers", "West", "Pacific", "LAL", "#552583", "#FDB927"),
    Team("PHX", "Phoenix Suns", "Phoenix", "Suns", "West", "Pacific", "PHO", "#1D1160", "#E56020"),
    Team("SAC", "Sacramento Kings", "Sacramento", "Kings", "West", "Pacific", "SAC", "#5A2D81", "#63727A"),
    # West - Southwest
    Team("DAL", "Dallas Mavericks", "Dallas", "Mavericks", "West", "Southwest", "DAL", "#00538C", "#002B5E"),
    Team("HOU", "Houston Rockets", "Houston", "Rockets", "West", "Southwest", "HOU", "#CE1141", "#000000"),
    Team("MEM", "Memphis Grizzlies", "Memphis", "Grizzlies", "West", "Southwest", "MEM", "#5D76A9", "#12173F"),
    Team("NOP", "New Orleans Pelicans", "New Orleans", "Pelicans", "West", "Southwest", "NOP", "#0C2340", "#C8102E"),
    Team("SAS", "San Antonio Spurs", "San Antonio", "Spurs", "West", "Southwest", "SAS", "#C4CED4", "#000000"),
]


BY_TRICODE: dict[str, Team] = {t.tricode: t for t in TEAMS}
BBR_TO_TRICODE: dict[str, str] = {t.bbr_code: t.tricode for t in TEAMS}


def get(tricode: str) -> Team:
    return BY_TRICODE[tricode]


def logo_url(tricode: str) -> str:
    """NBA.com CDN logo URL (SVG, primary, large)."""
    nba_id = NBA_TEAM_IDS.get(tricode)
    if not nba_id:
        return ""
    return f"https://cdn.nba.com/logos/nba/{nba_id}/primary/L/logo.svg"
