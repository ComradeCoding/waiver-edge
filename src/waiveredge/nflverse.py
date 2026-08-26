"""
All free, public nflverse data pulls, plus the derived per-player metrics the
Opportunity Score is built from.

Every loader returns a pandas DataFrame keyed (eventually, after merge_ids)
by Sleeper's own player_id string, so the rest of the app never has to think
about gsis_id / pfr_id / yahoo_id again - that crosswalk happens once, here.

Nothing in this file is league-specific. It's the same NFL data for every
visitor, so app.py caches these functions globally (st.cache_data with no
per-league key), not per-league - only the Sleeper roster/FAAB data in
sleeper.py needs a per-league cache key.
"""

from __future__ import annotations

import re

import pandas as pd
import nflreadpy as nfl


def _name_key(series: pd.Series) -> pd.Series:
    """Normalize a player name for fuzzy-free joining: lowercase, strip
    punctuation/suffixes, collapse whitespace. Used to join the ECR table
    (which has no gsis/sleeper id) to everything else by (name, position)."""
    s = series.astype(str).str.lower()
    s = s.str.replace(r"[^\w\s]", "", regex=True)
    s = s.str.replace(r"\b(jr|sr|ii|iii|iv|v)\b", "", regex=True)
    return s.str.replace(r"\s+", " ", regex=True).str.strip()

# Two of nflreadr/nflreadpy's loaders (load_ff_playerids, load_ff_rankings)
# pull CSVs from a GitHub "raw" redirect URL. Some network environments
# (proxies, certain sandboxes) block that specific redirect path while
# allowing raw.githubusercontent.com directly. If the library call fails,
# we retry once against the same file on raw.githubusercontent.com with a
# normal browser User-Agent before giving up. This changes nothing about the
# data - it's the identical CSV, just a different way of asking for it.
_DYNASTYPROCESS_RAW = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/{}.csv"


def _with_raw_fallback(loader_fn, filename: str) -> pd.DataFrame:
    try:
        return loader_fn().to_pandas()
    except Exception:
        return pd.read_csv(
            _DYNASTYPROCESS_RAW.format(filename),
            storage_options={"User-Agent": "Mozilla/5.0"},
            low_memory=False,
        )


def load_id_crosswalk() -> pd.DataFrame:
    """sleeper_id <-> gsis_id <-> pfr_id <-> yahoo_id, one row per player."""
    df = _with_raw_fallback(nfl.load_ff_playerids, "db_playerids")
    df = df[["sleeper_id", "gsis_id", "pfr_id", "yahoo_id", "name", "position", "team"]].copy()
    df["sleeper_id"] = df["sleeper_id"].dropna().astype("Int64").astype(str)
    df["name_key"] = _name_key(df["name"])
    # A handful of entries in dynastyprocess's table share a sleeper_id
    # (data-entry duplicates on their end) - keep the first so every
    # downstream merge stays one-row-per-player.
    return df.dropna(subset=["sleeper_id"]).drop_duplicates(subset=["sleeper_id"])


def load_ecr() -> pd.DataFrame:
    """
    Redraft, overall (cross-position) expert consensus rank - lower ecr = more valued.

    This table carries no gsis/sleeper/pfr id at all (FantasyPros' "overall"
    page doesn't export one), so it's joined back to everything else by
    normalized (name, position) instead of an id crosswalk.
    """
    df = _with_raw_fallback(nfl.load_ff_rankings, "db_fpecr_latest")
    df = df[df["page_type"] == "redraft-overall"].copy()
    df["name_key"] = _name_key(df["player"])
    df = df.drop_duplicates(subset=["name_key", "pos"])
    return df[["name_key", "pos", "ecr"]]


def _recent_prior_split(weeks: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Given the distinct weeks present in a df, return (recent_weeks, prior_weeks) sets."""
    all_weeks = sorted(weeks.unique())
    recent = set(all_weeks[-window:])
    prior = set(all_weeks[-2 * window : -window])
    return recent, prior


def load_snap_share_trend(season: int, window: int = 3) -> pd.DataFrame:
    """
    Offense snap-share trend per player, keyed by pfr_player_id.

    Returns columns: pfr_player_id, snap_pct_recent, snap_pct_prior, snap_share_trend
    (trend = recent - prior; positive means the coaching staff is playing them more).
    """
    snaps = nfl.load_snap_counts(seasons=[season]).to_pandas()
    # Drop playoff weeks: only two teams are still playing by the
    # conference-championship/Super Bowl weeks, so counting them in the
    # "distinct recent weeks" window starves every eliminated team's
    # players of a recent window entirely. Redraft FAAB season is over by
    # the time the playoffs start anyway.
    snaps = snaps[snaps["game_type"] == "REG"]
    if snaps.empty:
        return pd.DataFrame(columns=["pfr_player_id", "snap_pct_recent", "snap_pct_prior", "snap_share_trend"])

    recent_weeks, prior_weeks = _recent_prior_split(snaps["week"], window)
    recent = snaps[snaps["week"].isin(recent_weeks)].groupby("pfr_player_id")["offense_pct"].mean()
    prior = snaps[snaps["week"].isin(prior_weeks)].groupby("pfr_player_id")["offense_pct"].mean()

    out = pd.DataFrame({"snap_pct_recent": recent, "snap_pct_prior": prior}).reset_index()
    out["snap_pct_prior"] = out["snap_pct_prior"].fillna(out["snap_pct_recent"])
    out["snap_share_trend"] = out["snap_pct_recent"] - out["snap_pct_prior"]
    return out


def load_opportunity_metrics(season: int, window: int = 3) -> pd.DataFrame:
    """
    Target share / rush share trends + the expected-vs-actual "buy low" signal,
    keyed by gsis_id (nflverse's player_id in this dataset).

    buy_low_score = expected fantasy points - actual fantasy points, averaged
    over the recent window. Positive = the player has been getting the same
    volume/quality of opportunity as their output would suggest they're
    "due" - the box score hasn't caught up to the role yet.
    """
    opp = nfl.load_ff_opportunity(seasons=[season]).to_pandas()
    opp = opp.dropna(subset=["player_id"])
    # No game_type column here, but week numbering is consistent across
    # nflverse tables - regular season is weeks 1-18, see load_snap_share_trend.
    opp = opp[opp["week"] <= 18]
    if opp.empty:
        return pd.DataFrame(columns=[
            "player_id", "target_share_recent", "target_share_trend",
            "rush_share_recent", "rush_share_trend", "buy_low_score",
        ])

    opp["target_share"] = opp["rec_attempt"] / opp["rec_attempt_team"].replace(0, pd.NA)
    opp["rush_share"] = opp["rush_attempt"] / opp["rush_attempt_team"].replace(0, pd.NA)
    opp[["target_share", "rush_share"]] = opp[["target_share", "rush_share"]].fillna(0)

    recent_weeks, prior_weeks = _recent_prior_split(opp["week"], window)
    recent = opp[opp["week"].isin(recent_weeks)]
    prior = opp[opp["week"].isin(prior_weeks)]

    recent_agg = recent.groupby("player_id").agg(
        target_share_recent=("target_share", "mean"),
        rush_share_recent=("rush_share", "mean"),
        fantasy_points_exp_recent=("total_fantasy_points_exp", "mean"),
        fantasy_points_actual_recent=("total_fantasy_points", "mean"),
    )
    prior_agg = prior.groupby("player_id").agg(
        target_share_prior=("target_share", "mean"),
        rush_share_prior=("rush_share", "mean"),
    )

    out = recent_agg.join(prior_agg, how="left").reset_index()
    out["target_share_prior"] = out["target_share_prior"].fillna(out["target_share_recent"])
    out["rush_share_prior"] = out["rush_share_prior"].fillna(out["rush_share_recent"])
    out["target_share_trend"] = out["target_share_recent"] - out["target_share_prior"]
    out["rush_share_trend"] = out["rush_share_recent"] - out["rush_share_prior"]
    out["buy_low_score"] = out["fantasy_points_exp_recent"] - out["fantasy_points_actual_recent"]
    out = out.rename(columns={"player_id": "gsis_id"})
    return out


def load_red_zone_share_trend(season: int, window: int = 3) -> pd.DataFrame:
    """
    Share of the TEAM's red-zone (own yardline_100 <= 20) targets + carries
    that belong to each player, trended recent-vs-prior. Keyed by gsis_id.
    """
    pbp = nfl.load_pbp(seasons=[season]).to_pandas()
    pbp = pbp[pbp["season_type"] == "REG"]
    rz = pbp[(pbp["yardline_100"] <= 20) & (pbp["play_type"].isin(["pass", "run"]))].copy()
    if rz.empty:
        return pd.DataFrame(columns=["gsis_id", "rz_share_recent", "rz_share_trend"])

    rz["toucher_id"] = rz["receiver_player_id"].fillna(rz["rusher_player_id"])
    rz = rz.dropna(subset=["toucher_id", "posteam"])

    team_touches = rz.groupby(["posteam", "week"]).size().rename("team_rz_touches")
    player_touches = (
        rz.groupby(["posteam", "week", "toucher_id"]).size().rename("player_rz_touches").reset_index()
    )
    merged = player_touches.merge(team_touches, on=["posteam", "week"])
    merged["rz_share"] = merged["player_rz_touches"] / merged["team_rz_touches"]

    recent_weeks, prior_weeks = _recent_prior_split(merged["week"], window)
    recent = merged[merged["week"].isin(recent_weeks)].groupby("toucher_id")["rz_share"].mean()
    prior = merged[merged["week"].isin(prior_weeks)].groupby("toucher_id")["rz_share"].mean()

    out = pd.DataFrame({"rz_share_recent": recent, "rz_share_prior": prior}).reset_index()
    out = out.rename(columns={"toucher_id": "gsis_id"})
    out["rz_share_prior"] = out["rz_share_prior"].fillna(out["rz_share_recent"])
    out["rz_share_trend"] = out["rz_share_recent"] - out["rz_share_prior"]
    return out


def load_vacated_opportunity(season: int, opportunity_metrics: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    For each (team, position), how much recent target-share + rush-share
    belonged to a teammate who is now Out / Doubtful / IR? That share is
    "vacated" - up for grabs by whoever on the roster (or on waivers) steps
    into the role. Keyed by (team, position).

    This is necessarily an approximation: it tells you volume is opening up
    on a given team/position, not which specific backup inherits it. The UI
    surfaces this as a bonus signal, not a guarantee - see the README.

    Returns (grouped, self_contribution) - see the self_contribution comment
    below for why the second frame exists.
    """
    empty_grouped = pd.DataFrame(columns=["team", "position", "vacated_share", "vacated_from"])
    empty_self = pd.DataFrame(columns=["gsis_id", "team", "position", "own_vacated_contribution"])

    injuries = nfl.load_injuries(seasons=[season]).to_pandas()
    injuries = injuries[injuries["game_type"] == "REG"]
    if injuries.empty:
        return empty_grouped, empty_self

    latest_week = injuries["week"].max()
    out_now = injuries[
        (injuries["week"] == latest_week)
        & (injuries["report_status"].isin(["Out", "Doubtful", "IR"]))
    ]
    if out_now.empty:
        return empty_grouped, empty_self

    crosswalk = load_id_crosswalk()[["gsis_id", "name"]]
    merged = out_now.merge(crosswalk, on="gsis_id", how="left")
    merged = merged.merge(
        opportunity_metrics[["gsis_id", "target_share_recent", "rush_share_recent"]],
        on="gsis_id",
        how="left",
    )
    merged[["target_share_recent", "rush_share_recent"]] = merged[
        ["target_share_recent", "rush_share_recent"]
    ].fillna(0)
    merged["vacated_share"] = merged["target_share_recent"] + merged["rush_share_recent"]

    grouped = merged.groupby(["team", "position"]).agg(
        vacated_share=("vacated_share", "sum"),
        vacated_from=("name", lambda s: ", ".join(n for n in s if pd.notna(n))),
    ).reset_index()
    grouped = grouped[grouped["vacated_share"] > 0]

    # An injured player who is themselves a free agent (dropped because of
    # the injury, or a backup who just lost their own job) would otherwise
    # be credited with "vacating" opportunity to himself. self_contribution
    # lets build_player_metrics subtract each player's own share back out of
    # their own (team, position) group total.
    self_contribution = merged[["gsis_id", "team", "position", "vacated_share"]].rename(
        columns={"vacated_share": "own_vacated_contribution"}
    )
    return grouped, self_contribution


def build_player_metrics(season: int, window: int = 3) -> pd.DataFrame:
    """
    One row per player who has ANY nflverse data this season, keyed by
    sleeper_id, with every raw metric the Opportunity Score needs plus ECR.
    Everything downstream (scoring.py) reads from this single table.
    """
    crosswalk = load_id_crosswalk()

    snap_trend = load_snap_share_trend(season, window)
    opp_metrics = load_opportunity_metrics(season, window)
    rz_trend = load_red_zone_share_trend(season, window)
    vacated, vacated_self = load_vacated_opportunity(season, opp_metrics, window)
    ecr = load_ecr()

    # crosswalk join keys: pfr_id <-> pfr_player_id, gsis_id <-> gsis_id, yahoo_id <-> yahoo_id
    df = crosswalk.merge(
        snap_trend.rename(columns={"pfr_player_id": "pfr_id"}), on="pfr_id", how="left"
    )
    df = df.merge(opp_metrics, on="gsis_id", how="left")
    df = df.merge(rz_trend, on="gsis_id", how="left")
    df = df.merge(vacated, on=["team", "position"], how="left")
    df = df.merge(vacated_self, on=["gsis_id", "team", "position"], how="left")
    df["vacated_share"] = (df["vacated_share"].fillna(0) - df["own_vacated_contribution"].fillna(0)).clip(lower=0)
    df = df.drop(columns=["own_vacated_contribution"])
    df = df.merge(ecr, left_on=["name_key", "position"], right_on=["name_key", "pos"], how="left")

    numeric_cols = [
        "snap_share_trend", "target_share_trend", "rush_share_trend",
        "buy_low_score", "rz_share_trend", "vacated_share",
        "target_share_recent", "rush_share_recent",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    return df.rename(columns={"sleeper_id": "player_id"})
