"""
Wires every module together. Split into two stages on purpose:

  gather_league_data()  - everything expensive and config-independent
                           (Sleeper roster/FAAB pulls, the full nflverse
                           metrics build). app.py wraps this in
                           @st.cache_data so it only runs once per league
                           per cache window, and in the concurrency
                           semaphore, since it's the "expensive build step".

  score_and_bid()        - takes gathered data + your current config
                           sliders and produces the ranked table. This is
                           cheap pandas math (~1000 rows), so app.py calls
                           it fresh on every rerun - dragging a weight
                           slider re-ranks instantly without re-pulling
                           any data.

Keeping these separate is what makes the "configurable" part of the spec
actually feel configurable instead of requiring a multi-second data pull
every time a visitor nudges a weight.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import bidding, needs, nflverse, scoring, sleeper
from .concurrency import PIPELINE_SEMAPHORE
from .config import WaiverEdgeConfig

SIGNAL_COLUMNS = [
    "snap_share_trend", "target_share_trend", "rush_share_trend",
    "buy_low_score", "rz_share_trend", "vacated_share",
]


@dataclass
class GatheredLeagueData:
    league_name: str
    my_team_name: str
    my_remaining_budget: int
    league_total_budget: int
    rival_remaining_budgets: list[int]
    my_positions: list[str]
    free_agents_with_metrics: pd.DataFrame  # one row per free agent, raw signals only


@dataclass
class PipelineResult:
    league_name: str
    my_team_name: str
    my_remaining_budget: int
    results: pd.DataFrame  # one row per free agent, ranked by opportunity_score


def gather_league_data(league_id: str, my_user_id: str, season: int, trend_window_weeks: int) -> GatheredLeagueData:
    with PIPELINE_SEMAPHORE:
        league = sleeper.get_league(league_id)
        rosters = sleeper.get_rosters(league_id)
        users = sleeper.get_league_users(league_id)
        users_by_id = {u["user_id"]: u for u in users}
        all_players = sleeper.get_all_players()

        my_roster = sleeper.my_roster(rosters, my_user_id)
        if my_roster is None:
            raise ValueError("Could not find a roster owned by this user in this league.")
        my_team_name = sleeper.team_name(my_roster, users_by_id)

        faab = sleeper.faab_summary(league, rosters, users_by_id)
        my_faab = next(f for f in faab if f["roster_id"] == my_roster["roster_id"])
        rival_remaining = [f["faab_remaining"] for f in faab if f["roster_id"] != my_roster["roster_id"]]

        my_positions = [
            all_players.get(pid, {}).get("position")
            for pid in (my_roster.get("players") or [])
        ]
        my_positions = [p for p in my_positions if p]

        fa_ids = sleeper.free_agent_ids(rosters, all_players)
        fa_rows = [
            {
                "player_id": pid,
                "name": all_players[pid].get("full_name"),
                "position": all_players[pid].get("position"),
                "team": all_players[pid].get("team"),
            }
            for pid in fa_ids
        ]
        free_agents = pd.DataFrame(fa_rows)

        metrics = nflverse.build_player_metrics(season, window=trend_window_weeks)
        merged = free_agents.merge(metrics, on="player_id", how="left", suffixes=("", "_nflverse"))
        # A free agent nflverse has no data for yet (rookie who hasn't
        # debuted, practice-squad callup) still deserves a row - just with
        # every signal at 0, at the bottom of the pile.
        for col in SIGNAL_COLUMNS:
            if col not in merged.columns:
                merged[col] = 0.0
            merged[col] = merged[col].fillna(0.0)
        if "vacated_from" not in merged.columns:
            merged["vacated_from"] = ""
        merged["vacated_from"] = merged["vacated_from"].fillna("")

        return GatheredLeagueData(
            league_name=league.get("name", "Your League"),
            my_team_name=my_team_name,
            my_remaining_budget=my_faab["faab_remaining"],
            league_total_budget=my_faab["faab_budget"],
            rival_remaining_budgets=rival_remaining,
            my_positions=my_positions,
            free_agents_with_metrics=merged,
        )


def score_and_bid(gathered: GatheredLeagueData, config: WaiverEdgeConfig) -> PipelineResult:
    need_scores = needs.positional_need(gathered.my_positions, config)
    comp_factor = bidding.competition_factor(
        gathered.my_remaining_budget,
        gathered.league_total_budget,
        gathered.rival_remaining_budgets,
        gathered.league_total_budget,
        config,
    )

    scored = scoring.compute_opportunity_scores(gathered.free_agents_with_metrics, config)

    bids = []
    rationales = []
    for _, row in scored.iterrows():
        need_score = need_scores.get(row["position"], 0.0)
        breakdown = bidding.recommend_bid(
            player_id=row["player_id"],
            opportunity_score=row["opportunity_score"],
            position=row["position"],
            need_score=need_score,
            my_remaining_budget=gathered.my_remaining_budget,
            comp_factor=comp_factor,
            config=config,
        )
        bids.append(breakdown.recommended_bid)
        rationales.append(f"{scoring.rationale(row)} | {breakdown.rationale()}")

    scored["recommended_bid"] = bids
    scored["rationale"] = rationales
    scored = scored.sort_values("opportunity_score", ascending=False).reset_index(drop=True)

    return PipelineResult(
        league_name=gathered.league_name,
        my_team_name=gathered.my_team_name,
        my_remaining_budget=gathered.my_remaining_budget,
        results=scored,
    )
