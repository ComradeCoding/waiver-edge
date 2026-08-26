"""
Feature 4: turn an Opportunity Score into a recommended FAAB dollar bid.

The whole formula is four multipliers applied to a base rate, in this order:

    bid = my_remaining_budget
          * base_bid_rate                      (config: the ceiling, as a % of your budget)
          * (opportunity_score / 100)           (how good is this player, 0..1)
          * (1 + need_weight * positional_need) (do YOU specifically need this position)
          * scarcity_by_position[pos]           (is this position generally hard to replace)
          * competition_factor                  (do rivals have more/less spare FAAB than you)

...then rounded to a whole dollar and clamped to [min_bid, hard cap].

Nothing here is hidden: every factor above is a plain number the UI can show
next to the final bid, and every one of them is a slider in config.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import WaiverEdgeConfig


@dataclass
class BidBreakdown:
    player_id: str
    opportunity_score: float
    position: str
    need_score: float
    scarcity_multiplier: float
    competition_factor: float
    my_remaining_budget: int
    recommended_bid: int

    def rationale(self) -> str:
        return (
            f"score {self.opportunity_score:.0f}/100 x need {self.need_score:+.0%} "
            f"x scarcity {self.scarcity_multiplier:.2f} x competition {self.competition_factor:.2f} "
            f"of your ${self.my_remaining_budget} remaining"
        )


def competition_factor(my_remaining: int, my_total_budget: int, rival_remaining: list[int], rival_total_budget: int, config: WaiverEdgeConfig) -> float:
    """
    How much spare FAAB does the field have, relative to you? Expressed as a
    ratio of "remaining budget as a % of total budget" so it's fair between
    teams that started with different-sized budgets (rare, but leagues can
    differ mid-season if the commish adjusts it).

    > 1.0 : rivals are proportionally flusher than you -> bid a bit more to win it
    < 1.0 : you're proportionally flusher than the field -> you can win it cheaper
    """
    if not rival_remaining or rival_total_budget == 0 or my_total_budget == 0:
        return 1.0
    my_pct = my_remaining / my_total_budget
    rival_pct = (sum(rival_remaining) / len(rival_remaining)) / rival_total_budget
    raw = 1.0 + config.competition_weight * (rival_pct - my_pct)
    return max(0.5, min(raw, 1.5))


def recommend_bid(
    player_id: str,
    opportunity_score: float,
    position: str,
    need_score: float,
    my_remaining_budget: int,
    comp_factor: float,
    config: WaiverEdgeConfig,
) -> BidBreakdown:
    scarcity = config.scarcity_by_position.get(position, 1.0)
    need_mult = 1.0 + config.need_weight * need_score

    raw_bid = (
        my_remaining_budget
        * config.base_bid_rate
        * (opportunity_score / 100.0)
        * need_mult
        * scarcity
        * comp_factor
    )

    hard_cap = my_remaining_budget * config.hard_cap_pct_of_remaining
    bid = max(config.min_bid, min(round(raw_bid), round(hard_cap), my_remaining_budget))

    return BidBreakdown(
        player_id=player_id,
        opportunity_score=opportunity_score,
        position=position,
        need_score=need_score,
        scarcity_multiplier=scarcity,
        competition_factor=comp_factor,
        my_remaining_budget=my_remaining_budget,
        recommended_bid=bid,
    )
