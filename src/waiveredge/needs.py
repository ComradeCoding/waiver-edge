"""
Cross-references the Opportunity Score against YOUR roster's positional
depth (feature 3/4 in the spec: "positional needs" + "positional scarcity"
feeding the bid formula).

Deliberately simple and see-through: a position is "needed" in proportion to
how far below a configurable comfortable-depth threshold you are at it.
Nothing here tries to model bye weeks, injuries on your own roster, or
"my WR3 is bad so I need a better WR3" - that's a judgment call the human
using the tool is better placed to make than a heuristic. The score is a
depth count, not a quality opinion; the README says so explicitly.
"""

from __future__ import annotations

from .config import WaiverEdgeConfig
from .sleeper import SCORABLE_POSITIONS


def positional_need(my_player_positions: list[str], config: WaiverEdgeConfig) -> dict[str, float]:
    """
    my_player_positions: the `position` of every player on your roster
    (from Sleeper's player directory - already resolved from your roster's
    list of player_ids by the caller).

    Returns {position: need_score} where need_score is 0 (fully stocked or
    deeper than the comfortable threshold) to 1 (own zero players there).
    """
    counts = {pos: my_player_positions.count(pos) for pos in SCORABLE_POSITIONS}
    needs = {}
    for pos in SCORABLE_POSITIONS:
        depth_target = config.need_depth_by_position.get(pos, 3)
        have = counts.get(pos, 0)
        needs[pos] = max(0.0, (depth_target - have) / depth_target)
    return needs
