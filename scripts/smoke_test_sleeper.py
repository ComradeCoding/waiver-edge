"""
Quick manual smoke test for the Sleeper half of Waiver Edge.

This is NOT part of the app - it's a throwaway script to prove the Sleeper
API calls work before we build anything on top of them. Run it directly:

    python3 scripts/smoke_test_sleeper.py <sleeper_username> [season]

It looks up your leagues, picks the first one, and prints:
  - every rostered player (grouped by team)
  - every free agent (i.e. every NFL player NOT on any roster)
  - each team's FAAB budget used / remaining

Sleeper's API is public and read-only - no auth token needed for any of this.
"""

import sys
import requests

BASE = "https://api.sleeper.app/v1"


def get_user(username: str) -> dict:
    r = requests.get(f"{BASE}/user/{username}", timeout=10)
    r.raise_for_status()
    return r.json()


def get_leagues(user_id: str, season: str) -> list[dict]:
    r = requests.get(f"{BASE}/user/{user_id}/leagues/nfl/{season}", timeout=10)
    r.raise_for_status()
    return r.json()


def get_rosters(league_id: str) -> list[dict]:
    r = requests.get(f"{BASE}/league/{league_id}/rosters", timeout=10)
    r.raise_for_status()
    return r.json()


def get_users(league_id: str) -> list[dict]:
    r = requests.get(f"{BASE}/league/{league_id}/users", timeout=10)
    r.raise_for_status()
    return r.json()


def get_all_players() -> dict:
    # Sleeper asks integrators to cache this heavily - it's a big, slow-changing
    # blob (all NFL players, ~5MB). The real app caches this to disk; this
    # smoke test just fetches it once.
    r = requests.get(f"{BASE}/players/nfl", timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    season = sys.argv[2] if len(sys.argv) > 2 else "2026"

    print(f"Looking up Sleeper user '{username}'...")
    user = get_user(username)
    user_id = user["user_id"]
    print(f"  -> user_id={user_id}, display_name={user.get('display_name')}")

    print(f"\nFetching {season} leagues for this user...")
    leagues = get_leagues(user_id, season)
    if not leagues:
        print(f"No {season} leagues found for this user.")
        sys.exit(1)

    for lg in leagues:
        print(f"  - {lg['name']} (league_id={lg['league_id']}, "
              f"{lg['total_rosters']} teams, FAAB budget={lg['settings'].get('waiver_budget', 'N/A')})")

    league = leagues[0]
    league_id = league["league_id"]
    print(f"\nUsing league: {league['name']} ({league_id})")

    print("\nFetching rosters + league users...")
    rosters = get_rosters(league_id)
    users = get_users(league_id)
    users_by_id = {u["user_id"]: u for u in users}

    print("\nFetching full NFL player directory (cached blob, ~5MB, may take a few seconds)...")
    all_players = get_all_players()
    print(f"  -> {len(all_players)} total players in Sleeper's directory")

    rostered_ids = set()
    print("\n--- Rosters ---")
    for roster in rosters:
        owner = users_by_id.get(roster.get("owner_id"), {})
        team_name = owner.get("metadata", {}).get("team_name") or owner.get("display_name", "Unknown")
        budget_used = roster.get("settings", {}).get("waiver_budget_used", 0)
        player_ids = roster.get("players") or []
        rostered_ids.update(player_ids)
        print(f"\n{team_name} (FAAB used: {budget_used})")
        for pid in player_ids[:5]:  # just a preview, not the whole roster
            p = all_players.get(pid, {})
            print(f"    {p.get('full_name', pid)} ({p.get('position')}, {p.get('team')})")
        if len(player_ids) > 5:
            print(f"    ... and {len(player_ids) - 5} more")

    print(f"\n--- Free agents (available in THIS league only) ---")
    free_agent_ids = [
        pid for pid, p in all_players.items()
        if pid not in rostered_ids
        and p.get("position") in ("QB", "RB", "WR", "TE")
        and p.get("team")  # skip players not currently on an NFL roster
    ]
    print(f"{len(free_agent_ids)} skill-position free agents available. First 15:")
    for pid in free_agent_ids[:15]:
        p = all_players[pid]
        print(f"    {p.get('full_name')} ({p.get('position')}, {p.get('team')})")


if __name__ == "__main__":
    main()
