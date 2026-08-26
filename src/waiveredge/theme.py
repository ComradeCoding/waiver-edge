"""
"Commish" theme - the shared dark scoreboard look for this tool suite.

Streamlit's own [theme] config (.streamlit/config.toml) handles the parts
it understands natively - background/text/accent colors, which flow into
buttons, sliders, tabs, and links automatically. Everything Streamlit's
theme engine can't express (custom fonts, the chalk-grid texture, flat
matte surfaces with zero shadows, semantic win/loss/warning colors) is
layered on top here as one injected CSS block.

Keep this file the single source of truth for the palette - app.py should
never hardcode a hex color, so the two can't drift apart.
"""

from __future__ import annotations

# --- Palette --------------------------------------------------------------
# Navy "ink" scale (surfaces), not neutral black/grey.
INK_950 = "#050B14"
INK_900 = "#0B162A"
INK_850 = "#0F1D33"
INK_800 = "#13243D"
INK_750 = "#182B47"
INK_700 = "#1F3454"
INK_600 = "#2B446A"
INK_500 = "#445F87"
INK_400 = "#6B83A6"
INK_300 = "#9AACC6"
INK_200 = "#C2CEDE"
INK_100 = "#E0E7F0"
INK_50 = "#F2F6FA"

# "Signal" orange - the one hero accent, used sparingly.
SIGNAL_500 = "#FF6B2C"
SIGNAL_400 = "#FF8347"
SIGNAL_600 = "#ED4E0B"

# Semantic: turf (positive), clay (negative), tape (caution). Reserved for
# clear win/loss/warning meaning only - never used as decoration.
TURF = "#22C77B"
TURF_DARK = "#06301D"
CLAY = "#EF4A54"
CLAY_DARK = "#3A1013"
TAPE = "#F2B705"
TAPE_DARK = "#3A2C05"

EASE_OUT_QUINT = "cubic-bezier(0.22, 1, 0.36, 1)"


def faab_tier(remaining: int, total: int) -> tuple[str, str]:
    """(color, label) for a remaining-FAAB scoreboard tile, by % left."""
    if total <= 0:
        return INK_200, "N/A"
    pct = remaining / total
    if pct >= 0.5:
        return TURF, "HEALTHY"
    if pct >= 0.2:
        return TAPE, "GETTING THIN"
    return CLAY, "CRITICAL"


def score_tier_color(score: float) -> str:
    """Text color for an Opportunity Score cell - a hot/cold read, not a verdict."""
    if score >= 80:
        return TURF
    if score >= 50:
        return TAPE
    return INK_300


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@600;700;800&display=swap');

:root {{
  --ink-950: {INK_950}; --ink-900: {INK_900}; --ink-850: {INK_850}; --ink-800: {INK_800};
  --ink-750: {INK_750}; --ink-700: {INK_700}; --ink-600: {INK_600}; --ink-500: {INK_500};
  --ink-400: {INK_400}; --ink-300: {INK_300}; --ink-200: {INK_200}; --ink-100: {INK_100}; --ink-50: {INK_50};
  --signal-400: {SIGNAL_400}; --signal-500: {SIGNAL_500}; --signal-600: {SIGNAL_600};
  --turf: {TURF}; --clay: {CLAY}; --tape: {TAPE};
  --ease-out-quint: {EASE_OUT_QUINT};
}}

/* Flat matte surfaces everywhere - the look explicitly avoids shadows/glass. */
* {{ box-shadow: none !important; }}

html, body, [class^="st-"], [class*=" st-"], .stApp, p, span, div, label, li {{
  font-family: 'Barlow', -apple-system, BlinkMacSystemFont, sans-serif;
}}

h1, h2, h3, h4,
[data-testid="stMetricValue"] {{
  font-family: 'Barlow Condensed', sans-serif !important;
  font-weight: 800 !important;
  letter-spacing: -0.01em;
}}

/* Faint chalk field-line grid on the main background only - sparingly. */
.stApp {{
  background-color: var(--ink-900);
  background-image:
    repeating-linear-gradient(0deg, rgba(147,161,172,0.055) 0px, rgba(147,161,172,0.055) 1px, transparent 1px, transparent 56px),
    repeating-linear-gradient(90deg, rgba(147,161,172,0.055) 0px, rgba(147,161,172,0.055) 1px, transparent 1px, transparent 56px);
}}

section[data-testid="stSidebar"] {{
  background-color: var(--ink-850);
  background-image: none;
  border-right: 1px solid var(--ink-700);
}}
section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {{
  text-transform: uppercase;
  font-size: 0.9rem;
  letter-spacing: 0.06em;
  color: var(--ink-200);
}}

/* Tabs - jersey-label style */
button[data-baseweb="tab"] p {{
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.85rem;
}}
button[data-baseweb="tab"], [data-baseweb="tab-highlight"] {{
  transition: all 0.25s var(--ease-out-quint);
}}

/* Buttons: flat, rounded, one loud orange primary */
.stButton button, .stDownloadButton button {{
  border-radius: 10px;
  border: 1px solid var(--ink-600);
  transition: background-color 0.2s var(--ease-out-quint), border-color 0.2s var(--ease-out-quint);
  font-weight: 600;
}}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {{
  background-color: var(--signal-500);
  border-color: var(--signal-500);
  color: var(--ink-950);
  font-weight: 700;
}}
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover {{
  background-color: var(--signal-400);
  border-color: var(--signal-400);
}}
.stButton button:not([kind="primary"]) {{
  background-color: var(--ink-800);
  color: var(--ink-100);
}}
.stButton button:not([kind="primary"]):hover {{
  border-color: var(--signal-500);
  color: var(--signal-500);
}}

/* Inputs */
input, textarea, [data-baseweb="select"] > div, [data-baseweb="base-input"] {{
  background-color: var(--ink-800) !important;
  border-radius: 8px !important;
  border: 1px solid var(--ink-600) !important;
  color: var(--ink-100) !important;
}}
input:focus {{ border-color: var(--signal-400) !important; }}

/* Tabular numerals wherever scores/stats show up */
[data-testid="stMetricValue"], [data-testid="stDataFrame"], .scoreboard-tile .stat {{
  font-variant-numeric: tabular-nums;
}}

[data-testid="stDataFrame"] {{
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--ink-700);
}}
[data-testid="stExpander"] {{
  background-color: var(--ink-800);
  border-radius: 12px;
  border: 1px solid var(--ink-700);
}}
[data-testid="stAlert"] {{
  border-radius: 10px;
  border: 1px solid var(--ink-700);
}}

/* Custom scoreboard stat tile (used for remaining FAAB) */
.scoreboard-tile {{
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  background-color: var(--ink-800);
  border: 1px solid var(--ink-700);
  border-radius: 12px;
  padding: 0.85rem 1.4rem;
  margin: 0.25rem 0 1rem 0;
}}
.scoreboard-tile .label {{
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-300);
}}
.scoreboard-tile .stat {{
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 800;
  font-size: 2.4rem;
  line-height: 1;
  letter-spacing: -0.01em;
}}
.scoreboard-tile .tier {{
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}

/* Small status pill - e.g. the "all features free" marker below the title */
.pill {{
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  margin: 0.1rem 0 0.75rem 0;
}}
</style>
"""


def scoreboard_tile_html(label: str, value: str, color: str, tier_label: str) -> str:
    return (
        f'<div class="scoreboard-tile">'
        f'<span class="label">{label}</span>'
        f'<span class="stat" style="color:{color}">{value}</span>'
        f'<span class="tier" style="color:{color}">{tier_label}</span>'
        f"</div>"
    )


def pill_html(text: str, color: str = TURF) -> str:
    """Small rounded-full status pill, e.g. the free-for-now marker under the title."""
    return f'<span class="pill" style="background-color:{color}22; color:{color};">{text}</span>'
