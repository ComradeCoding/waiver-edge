"""
Thin wrapper around Sleeper's public, read-only API.

No API key exists for Sleeper and none is needed - every endpoint here is
public. We never touch anything that would require a logged-in session
(there is no way to place a waiver claim through this API, and we don't try).

All functions are plain requests calls; Streamlit's @st.cache_data decorators
live in app.py (not here) so this module stays framework-agnostic and easy
to unit-test or reuse in a plain script (see scripts/smoke_test_sleeper.py).
"""

from __future__ import annotations

import requests

BASE_URL = "https://api.sleeper.app/v1"

# Skill positions we score. Sleeper's player directory also contains kickers,
# defenses, and a long tail of retired/practice-squad players we don't want
# cluttering the recommender.
SCORABLE_POSITIONS = {"QB", "RB", "WR", "TE"}


class SleeperError(RuntimeError):
    """Raised when Sleeper returns something we can't use (bad username, etc)."""


def _get(path: str, timeout: int = 15) -> dict | list:
    resp = requests.get(f"{BASE_URL}{path}", timeout=timeout)
    if resp.status_code == 404:
        raise SleeperError(f"Sleeper returned 'not found' for {path}")
    resp.raise_for_status()
    return resp.json()


def get_user(username: str) -> dict:
    """Look up a Sleeper user by their display username (not a numeric ID)."""
    data = _get(f"/user/{username}")
    if not data:
        raise SleeperError(f"No Sleeper user found for username '{username}'")
    return data


def get_leagues_for_user(user_id: str, season: str) -> list[dict]:
    """All NFL leagues a user belongs to for a given season (e.g. '2026')."""
    return _get(f"/user/{user_id}/leagues/nfl/{season}")


def get_league(league_id: str) -> dict:
    return _get(f"/league/{league_id}")


def get_rosters(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/rosters")


def get_league_users(league_id: str) -> list[dict]:
    return _get(f"/league/{league_id}/users")


def get_all_players() -> dict:
    """
    The full Sleeper NFL player directory, keyed by sleeper player_id.

    Sleeper explicitly asks integrators not to hit this more than once a day
    (it's a slow-changing ~5MB blob) - the caller MUST cache this aggressively.
    In app.py this is wrapped in an st.cache_data(ttl=24h) call; we don't cache
    it here so this module has no dependency on Streamlit.
    """
    return _get("/players/nfl", timeout=30)


def rostered_player_ids(rosters: list[dict]) -> set[str]:
    ids: set[str] = set()
    for roster in rosters:
        ids.update(roster.get("players") or [])
    return ids


def free_agent_ids(rosters: list[dict], all_players: dict) -> list[str]:
    """Every skill-position player on an active NFL roster who is NOT rostered in this league."""
    taken = rostered_player_ids(rosters)
    return [
        pid
        for pid, p in all_players.items()
        if pid not in taken
        and p.get("position") in SCORABLE_POSITIONS
        and p.get("team")  # excludes free-agent-from-the-NFL's-perspective players
    ]


def team_name(roster: dict, users_by_id: dict[str, dict]) -> str:
    """Best-effort human-readable team name for a roster."""
    owner = users_by_id.get(roster.get("owner_id"), {})
    metadata_name = (owner.get("metadata") or {}).get("team_name")
    return metadata_name or owner.get("display_name") or f"Team {roster.get('roster_id')}"


def faab_summary(league: dict, rosters: list[dict], users_by_id: dict[str, dict]) -> list[dict]:
    """
    Remaining FAAB per team: league-wide budget minus what each roster has
    already used this season (Sleeper tracks waiver_budget_used per roster).
    """
    total_budget = int(league.get("settings", {}).get("waiver_budget", 100))
    out = []
    for roster in rosters:
        used = int(roster.get("settings", {}).get("waiver_budget_used", 0) or 0)
        out.append(
            {
                "roster_id": roster.get("roster_id"),
                "team_name": team_name(roster, users_by_id),
                "faab_budget": total_budget,
                "faab_used": used,
                "faab_remaining": max(total_budget - used, 0),
            }
        )
    return out


def my_roster(rosters: list[dict], my_user_id: str) -> dict | None:
    for roster in rosters:
        if roster.get("owner_id") == my_user_id:
            return roster
    return None
