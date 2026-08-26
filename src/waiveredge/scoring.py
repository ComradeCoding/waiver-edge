"""
Turns the raw per-player metrics from nflverse.py into a single 0-100
"Opportunity Score" per free agent.

The approach, in plain English: for each of the five signals (snap-share
trend, target/rush-share trend, buy-low, red-zone-share trend, vacated
opportunity), rank every available player AT THE SAME POSITION against each
other, 0-100th percentile. A player in the 90th percentile on a signal has
more of that signal than 90% of the other free agents at their position.
Percentile ranking (rather than raw min-max scaling) means one outlier week
can't blow the whole scale out, and every sub-score is naturally 0-100 and
comparable across signals - which is what makes the weighted sum in
config.py meaningful and easy to reason about.

Every sub-score survives in the output table specifically so the UI/rationale
text can say *why* a player scored well, not just what the final number was.
"""

from __future__ import annotations

import pandas as pd

from .config import WaiverEdgeConfig

RAW_SIGNAL_COLUMNS = {
    "snap_share_trend": "snap_score",
    "target_share_trend": "target_score",
    "rush_share_trend": "rush_score",
    "buy_low_score": "buy_low_pctile",
    "rz_share_trend": "rz_score",
    "vacated_share": "vacated_pctile",
}


def _percentile_by_position(df: pd.DataFrame, raw_col: str, position_col: str = "position") -> pd.Series:
    """0-100 percentile rank of raw_col, computed separately within each position group."""
    return df.groupby(position_col)[raw_col].rank(pct=True, method="average") * 100


def compute_opportunity_scores(metrics: pd.DataFrame, config: WaiverEdgeConfig) -> pd.DataFrame:
    """
    metrics: output of nflverse.build_player_metrics(), already filtered down
    to just this league's free agents (see pipeline.py).

    Returns the same dataframe with added columns: snap_score, target_score,
    rush_score, buy_low_pctile, rz_score, vacated_pctile (each 0-100), and
    opportunity_score (the weighted 0-100 combination of all six).
    """
    df = metrics.copy()

    df["snap_score"] = _percentile_by_position(df, "snap_share_trend")
    # Target share and rush share are two different signals collapsed into
    # one "volume trend" sub-score by taking whichever is higher for that
    # player - a WR's rush-share trend is nearly always 0 and shouldn't drag
    # their score down, and vice versa for a pure rushing back.
    df["_volume_trend_raw"] = df[["target_share_trend", "rush_share_trend"]].max(axis=1)
    df["target_score"] = _percentile_by_position(df, "_volume_trend_raw")
    df["buy_low_pctile"] = _percentile_by_position(df, "buy_low_score")
    df["rz_score"] = _percentile_by_position(df, "rz_share_trend")
    df["vacated_pctile"] = _percentile_by_position(df, "vacated_share")

    df["opportunity_score"] = (
        config.weight_snap_share_trend * df["snap_score"]
        + config.weight_target_rush_share_trend * df["target_score"]
        + config.weight_buy_low * df["buy_low_pctile"]
        + config.weight_red_zone_share_trend * df["rz_score"]
        + config.weight_vacated_opportunity * df["vacated_pctile"]
    ) / config.weights_sum()

    return df.drop(columns=["_volume_trend_raw"])


def rationale(row: pd.Series) -> str:
    """One-line, human-readable explanation of why a player scored the way they did."""
    parts = []
    if row["snap_score"] >= 70:
        parts.append(f"snap share trending up ({row['snap_share_trend']:+.0%})")
    if row["target_score"] >= 70:
        vol = max(row["target_share_trend"], row["rush_share_trend"])
        parts.append(f"volume share trending up ({vol:+.0%})")
    if row["buy_low_pctile"] >= 70:
        parts.append(f"buy-low: {row['buy_low_score']:+.1f} exp-vs-actual fantasy pts/wk")
    if row["rz_score"] >= 70:
        parts.append(f"red-zone share trending up ({row['rz_share_trend']:+.0%})")
    if row["vacated_pctile"] >= 70 and row.get("vacated_from"):
        parts.append(f"opportunity vacated by {row['vacated_from']}")
    if not parts:
        parts.append("modest, broad-based opportunity signal - no single standout factor")
    return "; ".join(parts)
