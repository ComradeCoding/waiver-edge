"""
Renders the final ranked add/drop table (feature 5) as Markdown or a
self-contained HTML page, so a visitor can download it instead of only
looking at the on-screen Streamlit table - handy for pasting into a group
chat before the waiver deadline.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

REPORT_COLUMNS = [
    "rank", "name", "position", "team", "opportunity_score",
    "ecr", "recommended_bid", "rationale",
]


def _prep(results: pd.DataFrame) -> pd.DataFrame:
    df = results.sort_values("opportunity_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df[REPORT_COLUMNS]


def to_markdown(results: pd.DataFrame, league_name: str) -> str:
    df = _prep(results)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Waiver Edge report - {league_name}",
        f"_Generated {generated}_",
        "",
        "| Rank | Player | Pos | Team | Score | ECR | Bid ($) | Why |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, row in df.iterrows():
        ecr = f"{row['ecr']:.0f}" if pd.notna(row["ecr"]) else "-"
        lines.append(
            f"| {row['rank']} | {row['name']} | {row['position']} | {row['team']} | "
            f"{row['opportunity_score']:.0f} | {ecr} | ${row['recommended_bid']} | {row['rationale']} |"
        )
    lines.append("")
    lines.append(
        "_Opportunity Score and bid formula are fully configurable - see the "
        "sidebar and the README for exactly how these numbers were computed. "
        "ECR is shown for context only and does not feed into the score or bid._"
    )
    return "\n".join(lines)


def to_html(results: pd.DataFrame, league_name: str) -> str:
    df = _prep(results)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    def _row_html(r: pd.Series) -> str:
        ecr = f"{r['ecr']:.0f}" if pd.notna(r["ecr"]) else "-"
        return (
            f"<tr><td>{r['rank']}</td><td>{r['name']}</td><td>{r['position']}</td>"
            f"<td>{r['team']}</td><td>{r['opportunity_score']:.0f}</td>"
            f"<td>{ecr}</td>"
            f"<td>${r['recommended_bid']}</td><td>{r['rationale']}</td></tr>"
        )

    rows = "\n".join(_row_html(r) for _, r in df.iterrows())
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Waiver Edge - {league_name}</title>
<style>
body {{ font-family: -apple-system, sans-serif; background:#0e1117; color:#e6e6e6; padding:2rem; }}
h1 {{ font-size:1.4rem; }}
table {{ border-collapse: collapse; width:100%; margin-top:1rem; }}
th, td {{ border:1px solid #333; padding:6px 10px; text-align:left; font-size:0.9rem; }}
th {{ background:#1c1f26; }}
tr:nth-child(even) {{ background:#171a21; }}
footer {{ margin-top:1.5rem; font-size:0.8rem; color:#888; }}
</style></head>
<body>
<h1>Waiver Edge report - {league_name}</h1>
<p>Generated {generated}</p>
<table>
<tr><th>Rank</th><th>Player</th><th>Pos</th><th>Team</th><th>Score</th><th>ECR</th><th>Bid</th><th>Why</th></tr>
{rows}
</table>
<footer>Opportunity Score and bid formula are fully configurable - see the README for exactly how these numbers were computed. ECR is shown for context only and does not feed into the score or bid.</footer>
</body></html>"""
