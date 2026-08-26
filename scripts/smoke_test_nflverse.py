"""
Quick manual smoke test for the nflverse data half of Waiver Edge.

Not part of the app - proves nflreadpy's loaders work and shows us the actual
column names/shapes we'll build the Opportunity Score on top of. Run:

    python3 scripts/smoke_test_nflverse.py [season]
"""

import sys
import nflreadpy as nfl

season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025


def show(label, df, cols=None, n=8):
    print(f"\n=== {label}: {df.shape[0]} rows x {df.shape[1]} cols ===")
    pdf = df.to_pandas() if hasattr(df, "to_pandas") else df
    if cols:
        cols = [c for c in cols if c in pdf.columns]
        print(pdf[cols].head(n).to_string(index=False))
    else:
        print(list(pdf.columns))


print(f"Pulling nflverse data for season={season} (set as an arg if you want a different year)...")

snaps = nfl.load_snap_counts(seasons=[season])
show("Snap counts", snaps, ["player", "position", "team", "week", "offense_pct"])

opp = nfl.load_ff_opportunity(seasons=[season])
show("FF opportunity (expected vs actual fantasy points)", opp,
     ["player_name", "position", "week", "team", "rec_fantasy_points_exp", "rec_fantasy_points"])

rankings = nfl.load_ff_rankings()
show("FF rankings (ECR)", rankings)

print("\nAll three loaders returned data. Column names above are what scoring.py will key off of.")
