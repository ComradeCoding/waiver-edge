"""
Waiver Edge - Streamlit entry point.

Run locally with:  streamlit run app.py
Deployed on Railway, this is started by the Procfile.

=== How this fits the house standards for this tool suite ===
This is a public, single-page tool. Any visitor types in THEIR OWN Sleeper
username or league, never something we bake in. A local .env can pre-fill
those fields for local dev convenience (see .env.example) but the app works
with an empty .env - nothing here requires it, and nothing in it is ever
shared between visitors (each visitor's session state is private to their
own browser tab).

There are no accounts, no login, no stored personal data. Every request
this app makes is a read-only call to Sleeper's public API or nflverse's
public data releases.
"""

from __future__ import annotations

import os
import re
from dataclasses import fields

import streamlit as st
from dotenv import load_dotenv

# Only affects local dev: pre-fills the "Find My League" form from a .env
# file so you don't retype your own username every restart (see
# .env.example). Does nothing in production unless those vars happen to be
# set there too - never required either way.
load_dotenv()

from waiveredge import pipeline, report, sleeper
from waiveredge.config import WaiverEdgeConfig
from waiveredge.sleeper import SleeperError

try:
    # nflreadpy's own definition of "the current NFL season" - it treats a
    # season as not existing yet until the Thursday after Labor Day, which
    # matters a lot here: this app will very often be opened in the
    # preseason, before that season's nflverse data exists at all.
    from nflreadpy.utils_date import get_current_season
except ImportError:  # pragma: no cover - defensive only, see fallback below
    from datetime import date

    def get_current_season() -> int:
        today = date.today()
        return today.year if today.month >= 9 else today.year - 1

st.set_page_config(page_title="Waiver Edge", page_icon="🏈", layout="wide")

# A little CSS so the tab labels read like the rest of the suite
# (uppercase, letter-spaced) - purely cosmetic, no behavior here.
st.markdown(
    """
    <style>
    button[data-baseweb="tab"] p { text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached data-fetching helpers
#
# Two different cache scopes on purpose (see the house standards doc this
# project follows): nflverse metrics are the same NFL data for every visitor,
# so they're cached GLOBALLY (no league_id in the cache key). Sleeper data is
# specific to one visitor's league, so it's cached PER-LEAGUE (league_id is
# an argument, which Streamlit automatically folds into the cache key) -
# one visitor's roster/FAAB data can never leak into another visitor's view.
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)  # 6h: nflverse data, shared by everyone
def cached_gather(league_id: str, my_user_id: str, season: int, trend_window_weeks: int):
    return pipeline.gather_league_data(league_id, my_user_id, season, trend_window_weeks)


@st.cache_data(ttl=60 * 15, show_spinner=False)  # 15m: this specific league's Sleeper user list
def cached_user_leagues(username: str, season: str):
    user = sleeper.get_user(username)
    leagues = sleeper.get_leagues_for_user(user["user_id"], season)
    return user, leagues


@st.cache_data(ttl=60 * 15, show_spinner=False)
def cached_league_lookup(league_id: str):
    league = sleeper.get_league(league_id)
    rosters = sleeper.get_rosters(league_id)
    users = sleeper.get_league_users(league_id)
    return league, rosters, users


def extract_league_id(text: str) -> str:
    """Accepts a bare ID or a full sleeper.com/leagues/<id>/... URL."""
    match = re.search(r"(\d{5,})", text.strip())
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Landing / league-selection state
# ---------------------------------------------------------------------------

if "league_id" not in st.session_state:
    st.session_state.league_id = None
    st.session_state.my_user_id = None
    st.session_state.season = None

st.title("🏈 Waiver Edge")
st.write(
    "An opportunity-based waiver-wire and FAAB bid recommender for **redraft** "
    "Sleeper leagues. It pulls the free agents genuinely available in your "
    "league, scores them on real snap-share, target-share, red-zone, and "
    "expected-vs-actual production trends from public NFL data, and suggests "
    "a transparent FAAB bid based on your roster's needs and how much budget "
    "your rivals have left."
)

if st.session_state.league_id is None:
    st.info(
        "**New here?** Enter your Sleeper username below and we'll find your "
        "leagues for you - or paste your league's link directly. Your league "
        "ID is the number in `sleeper.com/leagues/THIS-NUMBER/...`. Nothing "
        "you enter is stored anywhere; it only lives in this browser tab."
    )

    tab_username, tab_link = st.tabs(["Find My League", "I Have a League Link"])

    with tab_username:
        col1, col2 = st.columns([3, 1])
        default_username = os.environ.get("WAIVER_EDGE_DEV_USERNAME", "")
        username = col1.text_input("Your Sleeper username", value=default_username)
        season = col2.text_input("Season", value=os.environ.get("WAIVER_EDGE_DEV_SEASON", "2026"))

        if st.button("Find my leagues", type="primary"):
            if not username:
                st.warning("Enter a username first.")
            else:
                try:
                    user, leagues = cached_user_leagues(username, season)
                    st.session_state["_found_leagues"] = leagues
                    st.session_state["_found_user_id"] = user["user_id"]
                    st.session_state["_found_season"] = season
                except SleeperError as e:
                    st.error(str(e))

        found = st.session_state.get("_found_leagues")
        if found:
            st.write(f"Found {len(found)} league(s):")
            for lg in found:
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{lg['name']}** - {lg['total_rosters']} teams")
                if c2.button("Analyze", key=f"pick_{lg['league_id']}"):
                    st.session_state.league_id = lg["league_id"]
                    st.session_state.my_user_id = st.session_state["_found_user_id"]
                    st.session_state.season = int(lg.get("season", st.session_state["_found_season"]))
                    st.rerun()

    with tab_link:
        link_text = st.text_input("League URL or ID", placeholder="https://sleeper.com/leagues/1234567890123456789")
        if st.button("Look up league", type="primary"):
            league_id = extract_league_id(link_text)
            if not league_id:
                st.warning("Couldn't find a league ID in that text - paste the full URL or just the number.")
            else:
                try:
                    league, rosters, users = cached_league_lookup(league_id)
                    st.session_state["_link_league"] = league
                    st.session_state["_link_league_id"] = league_id
                    st.session_state["_link_rosters"] = rosters
                    st.session_state["_link_users"] = {u["user_id"]: u for u in users}
                except SleeperError as e:
                    st.error(str(e))

        link_league = st.session_state.get("_link_league")
        if link_league:
            st.write(f"**{link_league['name']}** - {link_league['total_rosters']} teams")
            rosters = st.session_state["_link_rosters"]
            users_by_id = st.session_state["_link_users"]
            team_options = {
                sleeper.team_name(r, users_by_id): r.get("owner_id")
                for r in rosters
                if r.get("owner_id")
            }
            picked_team = st.selectbox("Which team is yours?", list(team_options.keys()))
            if st.button("Analyze this league", type="primary"):
                st.session_state.league_id = st.session_state["_link_league_id"]
                st.session_state.my_user_id = team_options[picked_team]
                st.session_state.season = int(link_league.get("season", 2026))
                st.rerun()

    st.stop()


# ---------------------------------------------------------------------------
# A league is selected - run the pipeline and show results
# ---------------------------------------------------------------------------

if st.button("← Choose a different league"):
    for key in ("league_id", "my_user_id", "season"):
        st.session_state[key] = None
    st.rerun()

config = WaiverEdgeConfig()

with st.sidebar:
    st.header("Opportunity Score weights")
    st.caption(
        "These five weights don't need to add to 1.0 - they're auto-normalized. "
        "Raising one just makes that signal count for relatively more."
    )
    config.weight_snap_share_trend = st.slider("Snap-share trend", 0.0, 1.0, config.weight_snap_share_trend, 0.05)
    config.weight_target_rush_share_trend = st.slider("Target/rush-share trend", 0.0, 1.0, config.weight_target_rush_share_trend, 0.05)
    config.weight_buy_low = st.slider("Buy-low (expected vs actual pts)", 0.0, 1.0, config.weight_buy_low, 0.05)
    config.weight_red_zone_share_trend = st.slider("Red-zone-share trend", 0.0, 1.0, config.weight_red_zone_share_trend, 0.05)
    config.weight_vacated_opportunity = st.slider("Vacated opportunity (injuries)", 0.0, 1.0, config.weight_vacated_opportunity, 0.05)
    config.trend_window_weeks = st.slider("Trend window (weeks)", 1, 6, config.trend_window_weeks)

    st.header("FAAB bid formula")
    config.base_bid_rate = st.slider("Base bid rate (% of remaining budget for a perfect score)", 0.0, 1.0, config.base_bid_rate, 0.05)
    config.need_weight = st.slider("Positional-need multiplier strength", 0.0, 1.0, config.need_weight, 0.05)
    config.competition_weight = st.slider("Rival dry-powder sensitivity", 0.0, 1.0, config.competition_weight, 0.05)
    config.hard_cap_pct_of_remaining = st.slider("Hard cap (% of remaining budget, max)", 0.1, 1.0, config.hard_cap_pct_of_remaining, 0.05)

    with st.expander("Per-position scarcity + depth targets"):
        for pos in list(config.scarcity_by_position):
            config.scarcity_by_position[pos] = st.number_input(f"{pos} scarcity multiplier", 0.5, 2.0, config.scarcity_by_position[pos], 0.05)
        for pos in list(config.need_depth_by_position):
            config.need_depth_by_position[pos] = st.number_input(f"{pos} comfortable depth", 1, 10, config.need_depth_by_position[pos])

    # Default to whichever is earlier: the Sleeper league's own season, or
    # nflverse's idea of "the current season" - avoids landing every
    # preseason visitor straight on a season with no released data yet.
    default_season = min(st.session_state.season, get_current_season())
    season_override = st.number_input("Stats season (nflverse data)", 2012, 2030, default_season)

used_fallback_season = None
try:
    with st.spinner("Pulling free agents from Sleeper and building Opportunity Scores from nflverse data..."):
        try:
            gathered = cached_gather(
                st.session_state.league_id, st.session_state.my_user_id, season_override, config.trend_window_weeks
            )
        except ValueError as e:
            if "must be between" not in str(e):
                raise
            # nflverse genuinely has nothing published for this season yet
            # (almost always: it's still the preseason). Fall back one year
            # so a visitor gets a working preview instead of a dead end.
            used_fallback_season = season_override - 1
            gathered = cached_gather(
                st.session_state.league_id, st.session_state.my_user_id, used_fallback_season, config.trend_window_weeks
            )
    result = pipeline.score_and_bid(gathered, config)
except ValueError as e:
    st.error(str(e))
    st.stop()

if used_fallback_season is not None:
    st.info(
        f"nflverse has no released stats for {season_override} yet (the season hasn't started, or "
        f"Week 1 data hasn't landed). Showing **{used_fallback_season}** results instead so you can "
        "see how the tool works - switch back once your season is under way, using the sidebar."
    )

st.subheader(f"{result.league_name} - {result.my_team_name}")
st.metric("Your remaining FAAB", f"${result.my_remaining_budget}")

st.dataframe(
    result.results[["name", "position", "team", "opportunity_score", "ecr", "recommended_bid", "rationale"]]
    .rename(columns={
        "name": "Player", "position": "Pos", "team": "Team",
        "opportunity_score": "Score", "ecr": "ECR (context only)",
        "recommended_bid": "Bid ($)", "rationale": "Why",
    })
    .style.format({"Score": "{:.0f}", "ECR (context only)": "{:.0f}"}),
    use_container_width=True,
    height=600,
)
st.caption(
    "ECR = FantasyPros' redraft expert consensus rank (lower is more "
    "well-regarded). It's shown for context only - it does not feed into "
    "the Opportunity Score or the bid, and won't be populated for deep "
    "bench players nobody ranks."
)

col1, col2 = st.columns(2)
col1.download_button(
    "Download Markdown report",
    report.to_markdown(result.results, result.league_name),
    file_name="waiver_edge_report.md",
)
col2.download_button(
    "Download HTML report",
    report.to_html(result.results, result.league_name),
    file_name="waiver_edge_report.html",
    mime="text/html",
)

with st.expander("What this tool can't actually see (read before you trust a number)"):
    st.markdown(
        "- **Positional need** only counts how many players you own at a "
        "position, not whether they're any good - a stacked-but-mediocre "
        "bench won't lower your need score.\n"
        "- **Vacated opportunity** flags that a teammate at the same "
        "position is Out/Doubtful/IR and estimates how much of their "
        "target/carry share is up for grabs - it does NOT know which "
        "specific backup the coaching staff will actually feature.\n"
        "- **Red-zone share** and **buy-low** are both computed over a "
        "small recent window (see the sidebar) - a couple of unusual games "
        "can swing them more than a full-season trend would.\n"
        "- **Expert consensus rank (ECR)** is shown as its own column purely "
        "for context (\"is this a name experts already like, or a stat-only "
        "find?\") - it does not feed into the Opportunity Score or the bid "
        "in any way, and is blank for players with no consensus ranking.\n"
        "- The FAAB bid is a suggestion from a transparent formula (see the "
        "sidebar for every weight), not a guarantee you'll win the player at "
        "that price."
    )
