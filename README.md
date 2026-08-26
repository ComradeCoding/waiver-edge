# Waiver Edge

An opportunity-based waiver-wire and FAAB bid recommender for **redraft**
Sleeper leagues, built on free, public data. Anyone can open the app,
type in their own Sleeper username or league, and get a ranked list of
free agents worth adding - with a transparent, configurable dollar bid
suggestion for each one.

**This is a public web tool, not a personal script.** It never has your
league baked in. Every visitor brings their own username/league; nothing
is stored, no login exists, and one visitor's data never leaks into
another's view (see [Privacy & caching](#privacy--caching) below).

## Pricing

Tabled for now. Every feature and every detailed stat is available to
every visitor, unrestricted - not as an announced product decision, just
because free/paid hasn't been decided yet. No feature-gating or paywall
scaffolding exists in the code; if that gets designed later, build it
fresh against whatever the actual plan is rather than assuming this note.

## What it actually does

1. **Pulls your league from Sleeper** - every rostered player and every
   genuinely available free agent, plus every team's remaining FAAB
   budget (`league FAAB budget - waiver_budget_used`).
2. **Scores every free agent** on five real signals computed from public
   [nflverse](https://nflverse.com) data:
   - Snap-share trend (are they playing more, recently?)
   - Target-share / rush-share trend (is volume trending up?)
   - "Buy-low" signal - expected fantasy points (from `load_ff_opportunity`)
     minus actual - a player getting more opportunity than their box
     score shows is due for positive regression.
   - Red-zone touch-share trend (computed from play-by-play - nflverse
     doesn't ship this as a ready-made column, so it's built here from
     `load_pbp`).
   - Vacated opportunity - is a teammate at the same position freshly
     Out/Doubtful/IR (`load_injuries`), freeing up touches?
3. **Cross-references your roster** - a position you're thin at counts
   for more.
4. **Suggests a FAAB bid** using a fully transparent formula (see
   [The FAAB bid formula](#the-faab-bid-formula)) that factors in the
   player's score, your positional need, how scarce the position
   generally is, and how much spare budget your rivals are sitting on.
5. **Outputs a ranked table** with one-line, human-readable rationale for
   every recommendation, downloadable as Markdown or a self-contained
   HTML report.

## Try it

Open the deployed app (see the hub, or run locally - below) and either:

- **Find My League**: type your Sleeper username, and it looks up every
  league you're in for the season you pick.
- **I Have a League Link**: paste your league's URL (or just the numeric
  ID from `sleeper.com/leagues/THIS-NUMBER/...`) and pick which team is
  yours from a dropdown.

Nothing you type is saved anywhere - it lives only in your browser tab's
session and disappears when you close it.

## Running it yourself

```bash
git clone <this repo>
cd waiver-edge
pip install -r requirements.txt
cp .env.example .env   # optional - only pre-fills the username field for you
streamlit run app.py
```

Requires Python 3.11+. No API keys, no accounts, nothing to sign up for -
Sleeper's API and nflverse's data releases are both free and public.

### The two smoke-test scripts

Before any of the scoring logic was written, two throwaway scripts proved
the raw data pulls work - they're kept in `scripts/` as a reference for
anyone extending this:

```bash
python3 scripts/smoke_test_sleeper.py <your_sleeper_username> [season]
python3 scripts/smoke_test_nflverse.py [season]
```

The first prints your league's rosters and free agents straight from
Sleeper's API. The second prints raw snap-count and expected-fantasy-point
data straight from nflverse, so you can see exactly what columns the real
scoring model (`src/waiveredge/`) is built on top of.

## Project structure

```
app.py                       Streamlit UI - the only file with any UI code
src/waiveredge/
  sleeper.py                 Sleeper API client (rosters, free agents, FAAB)
  nflverse.py                nflverse data pulls + derived per-player metrics
  scoring.py                 Opportunity Score (percentile-based, see below)
  needs.py                   Positional-need calculation from your roster
  bidding.py                 FAAB bid formula
  config.py                  Every tunable weight, in one place, documented
  pipeline.py                Wires the above together (2-stage: gather + score)
  report.py                  Markdown/HTML report rendering
  concurrency.py             Small semaphore around the expensive data pull
scripts/                     Standalone smoke-test scripts (see above)
```

## The Opportunity Score

For each of five signals, every available free agent is ranked against
**other free agents at the same position**, as a percentile (0-100). A
running back in the 90th percentile on "target/rush-share trend" has a
bigger recent volume increase than 90% of the other available backs -
not than every player in the league, which wouldn't be a fair comparison
between, say, a QB and a TE.

The five percentiles are combined into one 0-100 score using the weights
in the sidebar (and `src/waiveredge/config.py`):

```
opportunity_score = (
      w_snap    * snap_share_trend_percentile
    + w_volume  * max(target_share_trend, rush_share_trend)_percentile
    + w_buy_low * buy_low_percentile
    + w_rz      * red_zone_share_trend_percentile
    + w_vacated * vacated_opportunity_percentile
) / (w_snap + w_volume + w_buy_low + w_rz + w_vacated)
```

The weights don't need to sum to 1 - they're auto-normalized, so raising
one just makes it count for relatively more.

## The FAAB bid formula

```
bid = my_remaining_budget
      * base_bid_rate                        # ceiling, as a % of your remaining budget
      * (opportunity_score / 100)             # 0..1, how good is this player
      * (1 + need_weight * positional_need)   # do YOU need this position
      * scarcity_by_position[pos]             # is this position generally hard to replace
      * competition_factor                    # do rivals have more/less spare FAAB than you
```

then rounded to a dollar and clamped between `min_bid` and
`hard_cap_pct_of_remaining * my_remaining_budget`.

- **`positional_need`** (0-1): how far below a configurable "comfortable
  depth" you are at that position. It counts players, not quality - see
  [What this can't see](#what-this-tool-cant-see).
- **`scarcity_by_position`**: a static, per-position dial you set. Raise
  a position if it's generally hard to replace on waivers in your league.
- **`competition_factor`**: compares the field's average remaining-budget
  percentage to yours. If rivals have proportionally more dry powder than
  you, the model nudges the bid up (you'll need to bid more to actually
  win it); if you're flusher than the field, it nudges down.

Every one of these is a slider in the app - nothing about the bid is
hidden math.

## What this tool can't see

Being upfront about approximations (rather than letting a confident
number stand in for a guess):

- **Positional need** only counts how many players you own at a
  position, not whether any of them are good.
- **Vacated opportunity** tells you volume is opening up on a
  team/position, not which specific backup will actually get it.
- **Red-zone share** and **buy-low** are computed over a small recent
  window (configurable, default 3 weeks) - a couple of unusual games can
  swing them more than a full-season number would.
- **ECR** (expert consensus rank) is shown as a column for context only.
  It does not feed into the score or the bid in any way, and it will be
  blank for deep bench players nobody ranks.
- The suggested bid is a formula's opinion, not a guarantee you'll win
  the player at that price - other managers don't see the same numbers
  and don't have to bid rationally.
- Before a season's Week 1 games are played, nflverse has no data for
  that season yet (nflverse's own rule: a season "exists" starting the
  Thursday after Labor Day). The app detects this and automatically
  shows the most recent season with real data instead, clearly labeled,
  so you can see the tool work before your season kicks off.

## Privacy & caching

- No accounts, no login, no API keys, no stored personal data - every
  call is a read-only request to Sleeper's public API or nflverse's
  public data releases.
- **nflverse data is cached globally** (`st.cache_data`, no league in the
  key) - it's the same public NFL data for every visitor, so there's
  nothing league-specific to leak.
- **Sleeper roster/FAAB data is cached per-league** (the league ID is
  part of the cache key) - one visitor's roster or budget can never show
  up in another visitor's session.
- A small semaphore (`src/waiveredge/concurrency.py`) caps the expensive
  data-gathering step to ~2 concurrent runs, so a burst of visitors can't
  take the server down at once.

## Deployment

Deploys to Railway as its own service (`Procfile` + `railway.json` are
both in the repo root). The start command binds `$PORT` and `0.0.0.0`, so
it boots correctly on Railway without any extra configuration.

### Adding this to the hub (`foot.comradecoding.com`)

This repo doesn't include the hub itself - the hub lives in the
`draftroom` repo at `hub/index.html` (its own Railway service). To list
Waiver Edge there once it's deployed, add a card matching the existing
cards' markup/tokens with:

- **Name**: Waiver Edge
- **One-paragraph description**: an opportunity-based waiver-wire and
  FAAB bid recommender for redraft Sleeper leagues, built on free public
  NFL data.
- **Feature tags**: e.g. "Opportunity Score", "Smart FAAB bids", "Free
  agents only"
- **Link**: the deployed subdomain (e.g. `waiver-edge.comradecoding.com`)

Per this suite's house standards, hub registration is done from whichever
session owns the `draftroom`/hub repo, not from here.

## Configuration reference

Every knob lives in `src/waiveredge/config.py` (`WaiverEdgeConfig`), with
a plain-English comment on what it does, and every one of them is exposed
as a slider in the app's sidebar. Nothing about the formula requires
reading code to understand or change.
