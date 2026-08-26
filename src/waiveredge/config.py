"""
Every tunable knob in the Opportunity Score and FAAB bid formula lives here,
in one place, with a plain-English comment on what raising/lowering it does.

This is the "make the formula transparent and configurable" requirement:
nothing about how a bid is computed is hidden in scoring.py or bidding.py -
those files just read numbers out of this dataclass. The Streamlit sidebar
exposes these as sliders so a visitor can see (and change) exactly how much
weight each factor gets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WaiverEdgeConfig:
    # --- Opportunity Score weights (must sum to 1.0 - the UI warns if not) ---
    # How many of the last N weeks count as "recent" vs. the N weeks before
    # that ("prior"). Trends are recent-minus-prior, so a bigger window is
    # smoother/slower to react, a smaller window is noisier/faster to react.
    trend_window_weeks: int = 3

    weight_snap_share_trend: float = 0.25   # rising snap share = coach trusts them more
    weight_target_rush_share_trend: float = 0.30  # rising target/carry share = more volume coming
    weight_buy_low: float = 0.20             # actual points well below expected = due for positive regression
    weight_red_zone_share_trend: float = 0.15  # rising RZ share = more scoring opportunity
    weight_vacated_opportunity: float = 0.10   # teammate injury freeing up touches/targets

    # --- Positional need (feature 3) ---
    # A position counts as "needed" if you own fewer than this many players
    # at it. 0..1 need score = linear scale between (need_depth) and 0 owned.
    need_depth_by_position: dict = field(
        default_factory=lambda: {"QB": 2, "RB": 5, "WR": 6, "TE": 2}
    )

    # --- FAAB bid formula (feature 4) ---
    # Ceiling: the fraction of your REMAINING budget a perfect-100,
    # high-need, scarce, hotly-contested player could command.
    base_bid_rate: float = 0.30

    # How much a positional need multiplies the bid up. need_factor =
    # 1 + need_weight * need_score (need_score is 0..1).
    need_weight: float = 0.40

    # Static per-position scarcity dial - raise a position if, in your
    # league, that position is generally harder to replace on waivers.
    scarcity_by_position: dict = field(
        default_factory=lambda: {"QB": 0.90, "RB": 1.15, "WR": 1.00, "TE": 1.10}
    )

    # How strongly rivals' spare FAAB pushes your suggested bid up or down.
    # competition_factor = 1 + competition_weight * (rival_remaining_pct - your_remaining_pct)
    # i.e. if the field has proportionally more dry powder than you, the
    # model nudges the bid up (you'll need more to win it); if you're
    # relatively flush compared to the field, it nudges down (save budget).
    competition_weight: float = 0.50

    # Safety rails so the formula can never suggest something silly.
    min_bid: int = 1
    hard_cap_pct_of_remaining: float = 0.60  # never suggest more than this share of what you have left

    def weights_sum(self) -> float:
        return (
            self.weight_snap_share_trend
            + self.weight_target_rush_share_trend
            + self.weight_buy_low
            + self.weight_red_zone_share_trend
            + self.weight_vacated_opportunity
        )
