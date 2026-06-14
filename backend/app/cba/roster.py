"""Roster construction rules: 15 standard + up to 3 two-way contracts per team."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.teams import TEAMS
from app.db.schema import Contract, Player


STANDARD_ROSTER_MAX = 15
TWO_WAY_MAX = 3


def enforce_roster_max(db: Session) -> dict:
    """Enforce roster construction rules across every team.

    For each team:
      - Active contracts are ranked by OVR (desc).
      - First 15 (non-two-way) keep their standard contracts.
      - Slots 16-18 are eligible for two-way (rookies are preferred); they get
        is_two_way=True if not already.
      - Anything beyond 18: deactivate the contract, send the player to FA.
    """
    summary = {"teams_trimmed": 0, "players_released": 0, "two_way_assigned": 0, "details": []}

    for team in TEAMS:
        contracts = (
            db.query(Contract, Player)
            .join(Player, Player.id == Contract.player_id)
            .filter(Contract.team_tricode == team.tricode, Contract.is_active == True)
            .all()
        )
        if len(contracts) <= STANDARD_ROSTER_MAX:
            # Still ensure rookies on the bench are two-way if they're the lowest
            # OVR guys (cleans up draft-day assignments).
            continue
        # Sort by (is_two_way ASC so standard contracts come first within tier,
        # then by overall DESC so the best players are kept standard).
        # Prefer rookies (years_of_service == 0) for two-way slot relegation.
        contracts.sort(key=lambda cp: (
            -(cp[1].overall or 0),                       # OVR descending
        ))

        released = 0
        two_way = 0
        for idx, (c, p) in enumerate(contracts):
            if idx < STANDARD_ROSTER_MAX:
                if c.is_two_way:
                    c.is_two_way = False                  # promote rookie if he made the top 15
                continue
            if idx < STANDARD_ROSTER_MAX + TWO_WAY_MAX:
                # Two-way slot
                if not c.is_two_way:
                    c.is_two_way = True
                    two_way += 1
                continue
            # Release surplus
            c.is_active = False
            if p.team_tricode == team.tricode:
                p.team_tricode = None
                p.is_free_agent = True
                p.fa_type = "UFA"
            released += 1

        if released or two_way:
            summary["teams_trimmed"] += 1
            summary["players_released"] += released
            summary["two_way_assigned"] += two_way
            summary["details"].append({
                "team": team.tricode,
                "released": released,
                "two_way_assigned": two_way,
            })

    db.commit()
    return summary
