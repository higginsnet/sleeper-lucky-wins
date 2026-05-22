import os
import webbrowser

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sleeper_api import get_users, get_rosters, get_matchups

# ── League configs ─────────────────────────────────────────────────────────────
# Each list is ordered oldest → newest season.
LEAGUES_PRETEND_GMS = [
    {"league_id": "1004495314675503104", "season": 2023, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1048281198428049408", "season": 2024, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1180428546027991040", "season": 2025, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1312185578673934336", "season": 2026, "playoff_week_start": 15, "last_scored_leg": 1},
]

LEAGUES_ON_THE_CLOCK = [
    {"league_id": "787161656173146112",  "season": 2022, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "917119106866905088",  "season": 2023, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1048284306612903936", "season": 2024, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1180430303260946432", "season": 2025, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1312191361411198976", "season": 2026, "playoff_week_start": 15, "last_scored_leg": 1},
]

LEAGUES_EMPIRE = [
    {"league_id": "1241891314337857536", "season": 2025, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1312221661323341824", "season": 2026, "playoff_week_start": 15, "last_scored_leg": 1},
]

# Redraft league — same API structure, last_scored_leg goes to week 18 each season.
LEAGUES_2_MINUTE_DRILL = [
    {"league_id": "595099547647139840",  "season": 2020, "playoff_week_start": 14, "last_scored_leg": 17},
    {"league_id": "693247414072610816",  "season": 2021, "playoff_week_start": 15, "last_scored_leg": 18},
    {"league_id": "825083697853218816",  "season": 2022, "playoff_week_start": 15, "last_scored_leg": 18},
    {"league_id": "970063665728700416",  "season": 2023, "playoff_week_start": 15, "last_scored_leg": 18},
    {"league_id": "1065330758425997312", "season": 2024, "playoff_week_start": 15, "last_scored_leg": 18},
    {"league_id": "1245955182097866752", "season": 2025, "playoff_week_start": 15, "last_scored_leg": 18},
]


# ── Data fetching ──────────────────────────────────────────────────────────────

def build_matchup_df(leagues):
    rows = []

    for league in leagues:
        league_id     = league["league_id"]
        season        = league["season"]
        playoff_start = league["playoff_week_start"]
        last_week     = league["last_scored_leg"]

        users   = get_users(league_id)
        rosters = get_rosters(league_id)

        user_map   = {u["user_id"]: u.get("display_name", u["user_id"]) for u in users}
        roster_map = {
            r["roster_id"]: user_map.get(r["owner_id"], f"Roster {r['roster_id']}")
            for r in rosters
        }

        print(f"  {season}: fetching weeks 1–{last_week}...")

        for week in range(1, last_week + 1):
            matchups = get_matchups(league_id, week)
            if not matchups:
                continue

            by_mid = {}
            for m in matchups:
                mid = m.get("matchup_id")
                if mid is None:
                    continue
                by_mid.setdefault(mid, []).append(m)

            for pair in by_mid.values():
                if len(pair) != 2:
                    continue
                for team, opp in [pair, pair[::-1]]:
                    rows.append({
                        "season":     season,
                        "week":       week,
                        "is_playoff": week >= playoff_start,
                        "team":  roster_map.get(team["roster_id"], f"Roster {team['roster_id']}"),
                        "opp":   roster_map.get(opp["roster_id"],  f"Roster {opp['roster_id']}"),
                        "score":     float(team["points"] or 0),
                        "opp_score": float(opp["points"]  or 0),
                    })

    df = pd.DataFrame(rows)
    df["win"] = df["score"] > df["opp_score"]

    grp = df.groupby(["season", "week"])["score"]
    avg = grp.mean().rename("avg")
    med = grp.median().rename("med")
    df  = df.join(avg, on=["season", "week"]).join(med, on=["season", "week"])

    df["score_rel_avg"] = df["score"]     - df["avg"]
    df["opp_rel_avg"]   = df["opp_score"] - df["avg"]
    df["score_rel_med"] = df["score"]     - df["med"]
    df["opp_rel_med"]   = df["opp_score"] - df["med"]

    return df


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_hover(subset, x_col, y_col):
    return [
        f"<b>{r['team']}</b> — Wk {r['week']} {r['season']}<br>"
        f"vs {r['opp']}<br>"
        f"Score: {r['score']:.2f} – {r['opp_score']:.2f}<br>"
        f"Team vs median: {r[x_col]:+.2f} · Opp vs median: {r[y_col]:+.2f}"
        for _, r in subset.iterrows()
    ]


def _lucky_summary(fdf, xc, yc, sep="    |    "):
    """Return a luckiest/unluckiest summary string.

    Lucky win  = any win  (circle) landing in a blue shaded zone  (Q1 or Q3).
    Unlucky loss = any loss (X)    landing in a pink shaded zone  (Q1 or Q3).
    Both Q1 (x>0, y>0) and Q3 (x<0, y<0) are counted.
    """
    in_q1_or_q3 = ((fdf[xc] > 0) & (fdf[yc] > 0)) | ((fdf[xc] < 0) & (fdf[yc] < 0))
    lucky   = fdf[in_q1_or_q3 &  fdf["win"]]
    unlucky = fdf[in_q1_or_q3 & ~fdf["win"]]
    if lucky.empty:   luckiest,   n_l = "N/A", 0
    else: c = lucky.groupby("team").size();   luckiest,   n_l = c.idxmax(), int(c.max())
    if unlucky.empty: unluckiest, n_u = "N/A", 0
    else: c = unlucky.groupby("team").size(); unluckiest, n_u = c.idxmax(), int(c.max())
    return (
        f"<b>Luckiest Team:</b> {luckiest} ({n_l} lucky wins)"
        f"{sep}"
        f"<b>Unluckiest Team:</b> {unluckiest} ({n_u} unlucky losses)"
    )


# ── Figure builder ─────────────────────────────────────────────────────────────

def _build_figure(df, ncols=4):
    """
    Build one Lucky Win scatter figure for the data in `df`.
    The caller pre-filters df to the desired season(s) and teams.
    ncols=4 → desktop layout; ncols=2 → mobile layout.
    """
    teams = sorted(df["team"].unique())
    if not teams:
        return go.Figure()

    nrows     = -(-len(teams) // ncols)
    h_spacing = 0.07 if ncols >= 4 else 0.12
    # More vertical space per gap when there are few rows so subplot titles
    # don't collide with the x-axis labels of the row above.
    v_spacing = max(0.10, round(0.36 / nrows, 3))

    fig = make_subplots(
        rows=nrows, cols=ncols,
        subplot_titles=teams,
        horizontal_spacing=h_spacing,
        vertical_spacing=v_spacing,
    )

    STYLES = [
        (False, True,  "#1f77b4", "circle", "Regular Win"),
        (False, False, "#1f77b4", "x",      "Regular Loss"),
        (True,  True,  "#d62728", "circle", "Playoff Win"),
        (True,  False, "#d62728", "x",      "Playoff Loss"),
    ]

    # ── Permanent legend anchors ─────────────────────────────────────────────
    for is_playoff, win, color, symbol, label in STYLES:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(symbol=symbol, color=color, size=9, opacity=0.8,
                        line=dict(width=1.5, color="white" if win else color)),
            name=label, showlegend=True, legendgroup=label,
            visible="legendonly", hoverinfo="skip",
        ))

    # ── Data traces (median only) ─────────────────────────────────────────────
    for i, team in enumerate(teams):
        r, c = divmod(i, ncols)
        tdf = df[df["team"] == team]
        for is_playoff, win, color, symbol, label in STYLES:
            sub = tdf[(tdf["is_playoff"] == is_playoff) & (tdf["win"] == win)]
            if sub.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub["score_rel_med"].tolist(), y=sub["opp_rel_med"].tolist(),
                    mode="markers",
                    marker=dict(symbol=symbol, color=color, size=9, opacity=0.80,
                                line=dict(width=1.5, color="white" if win else color)),
                    name=label, showlegend=False, legendgroup=label,
                    hovertext=_make_hover(sub, "score_rel_med", "opp_rel_med"),
                    hoverinfo="text",
                ),
                row=r + 1, col=c + 1,
            )

    # ── Background fills + diagonal + zero-lines (per subplot) ───────────────
    max_val = (
        df[["score_rel_med", "opp_rel_med"]]
        .abs().values.max() * 1.15
    )
    R = max_val

    LUCKY_FILL   = "rgba(173, 198, 245, 0.40)"
    UNLUCKY_FILL = "rgba(255, 160, 160, 0.35)"

    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xax  = "x" if ax_n == 1 else f"x{ax_n}"
        yax  = "y" if ax_n == 1 else f"y{ax_n}"

        fig.add_shape(type="path", path=f"M 0,0 L 0,{R} L {R},{R} Z",
                      fillcolor=UNLUCKY_FILL, line_width=0,
                      xref=xax, yref=yax, layer="below")
        fig.add_shape(type="path", path=f"M 0,0 L {R},{R} L {R},0 Z",
                      fillcolor=LUCKY_FILL, line_width=0,
                      xref=xax, yref=yax, layer="below")
        fig.add_shape(type="path", path=f"M 0,0 L {-R},0 L {-R},{-R} Z",
                      fillcolor=UNLUCKY_FILL, line_width=0,
                      xref=xax, yref=yax, layer="below")
        fig.add_shape(type="path", path=f"M 0,0 L 0,{-R} L {-R},{-R} Z",
                      fillcolor=LUCKY_FILL, line_width=0,
                      xref=xax, yref=yax, layer="below")
        fig.add_shape(type="line", x0=-R, y0=-R, x1=R, y1=R,
                      line=dict(dash="dash", color="#999", width=1),
                      xref=xax, yref=yax)
        fig.add_hline(y=0, line_dash="dot", line_color="#bbb", line_width=0.8, row=r+1, col=c+1)
        fig.add_vline(x=0, line_dash="dot", line_color="#bbb", line_width=0.8, row=r+1, col=c+1)

    fig.update_xaxes(
        tickfont_size=9, title_text="Team pts vs median", title_font_size=9,
        zeroline=False, range=[-max_val, max_val], tickmode="auto", nticks=6,
    )
    fig.update_yaxes(
        tickfont_size=9, title_text="Opp pts vs median", title_font_size=9,
        zeroline=False, range=[-max_val, max_val], tickmode="auto", nticks=6,
    )

    # Mobile: axis titles only on edge subplots to prevent label collision.
    # Y-axis: col=1 only (left edge of every row).
    # X-axis: use paper-coordinate annotations centered between each pair (x=0.5).
    if ncols < 4:
        fig.update_xaxes(title_text="")
        fig.update_yaxes(title_text="")
        fig.update_yaxes(title_text="Opp pts vs median", title_font_size=9, col=1)
        # Compute the bottom y of each row in paper coords, then annotate centered
        sub_h = (1.0 - (nrows - 1) * 0.10) / nrows
        for row_i in range(1, nrows + 1):
            y_bottom = 1.0 - row_i * sub_h - (row_i - 1) * 0.10
            fig.add_annotation(
                text="Team pts vs median",
                xref="paper", yref="paper",
                x=0.5, y=y_bottom - 0.012,
                xanchor="center", yanchor="top",
                showarrow=False,
                font=dict(size=9, color="#444"),
            )

    # ── Corner watermark annotations ──────────────────────────────────────────
    LUCKY_TXT   = dict(showarrow=False, font=dict(size=11, color="rgba(31,119,180,0.60)"))
    UNLUCKY_TXT = dict(showarrow=False, font=dict(size=11, color="rgba(214,39,40,0.60)"))
    corner_annots = []
    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xd = "x domain" if ax_n == 1 else f"x{ax_n} domain"
        yd = "y domain" if ax_n == 1 else f"y{ax_n} domain"
        corner_annots += [
            dict(**UNLUCKY_TXT, xref=xd, yref=yd, x=0.667, y=0.833,
                 xanchor="center", yanchor="middle", text="Unlucky<br>Loss"),
            dict(**LUCKY_TXT,   xref=xd, yref=yd, x=0.833, y=0.667,
                 xanchor="center", yanchor="middle", text="Lucky<br>Win"),
        ]

    # ── Layout ────────────────────────────────────────────────────────────────
    # Title and season selector live in HTML above the figure; the figure only
    # needs room for the summary line.
    MARGIN_T = 80 if ncols >= 4 else 90
    MARGIN_B = 90
    fig_h    = 310 * nrows
    plot_h   = fig_h - MARGIN_T - MARGIN_B

    def _py(px_from_top):
        return 1.0 + (MARGIN_T - px_from_top) / plot_h

    existing_annots = list(fig.layout.annotations)

    # Summary annotation (single, median-based)
    _sep     = "<br>" if ncols < 4 else "    |    "
    med_text = _lucky_summary(df, "score_rel_med", "opp_rel_med", _sep)
    summary_y = _py(40) if ncols >= 4 else _py(45)

    summary_annot = dict(
        xref="paper", yref="paper",
        x=0.5, y=summary_y, xanchor="center", yanchor="bottom",
        showarrow=False, text=med_text,
        font=dict(size=11, color="#333"),
    )

    margin = (dict(t=MARGIN_T, b=MARGIN_B) if ncols >= 4
              else dict(t=MARGIN_T, b=MARGIN_B, l=55, r=10))

    fig.update_layout(
        annotations=(existing_annots + corner_annots + [summary_annot]),
        title_text="",
        height=fig_h,
        template="plotly_white",
        margin=margin,
        legend=dict(
            orientation="h", yanchor="top", y=-0.05,
            xanchor="center", x=0.5, font_size=12,
        ),
    )

    return fig


# ── HTML writer ────────────────────────────────────────────────────────────────

def lucky_win_plot(df, output="lucky_wins.html", league_name=""):
    """
    Build per-season figures (only teams active that season) and write a single
    responsive HTML file with an external season selector.
    """
    seasons = ["All"] + sorted(df["season"].unique().tolist())

    # ── Build one desktop+mobile figure pair per season ───────────────────────
    season_htmls = {}   # s -> {"desktop": str, "mobile": str}
    kw = dict(full_html=False, include_plotlyjs=False, config={"responsive": True})

    for s in seasons:
        df_s = df if s == "All" else df[df["season"] == s]
        print(f"    Season {s}: {sorted(df_s['team'].unique()).__len__()} teams")

        desktop_div = _build_figure(df_s, ncols=4).to_html(**kw)
        mobile_div  = _build_figure(df_s, ncols=2).to_html(**kw)
        season_htmls[s] = {"desktop": desktop_div, "mobile": mobile_div}

    # ── Assemble HTML pieces (avoid f-string on Plotly content) ──────────────
    # Season selector buttons
    btn_parts = []
    for i, s in enumerate(seasons):
        active = " active" if i == 0 else ""
        btn_parts.append(
            '<button class="season-btn' + active + '" '
            'id="btn-season-' + str(s) + '" '
            "onclick=\"setSeason('" + str(s) + "')\">" + str(s) + "</button>"
        )
    season_buttons_html = "\n    ".join(btn_parts)

    # Season figure divs
    div_parts = []
    for i, s in enumerate(seasons):
        active   = " active" if i == 0 else ""
        desktop  = season_htmls[s]["desktop"]
        mobile   = season_htmls[s]["mobile"]
        div_parts.append(
            '<div id="season-' + str(s) + '" class="season-wrap' + active + '">\n'
            '  <div class="layout-wrap desktop-wrap">' + desktop + '</div>\n'
            '  <div class="layout-wrap mobile-wrap" style="display:none">' + mobile + '</div>\n'
            '</div>'
        )
    season_divs_html = "\n\n".join(div_parts)

    # ── Static head (f-string safe: only league_name substituted) ────────────
    html_head = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '  <title>Lucky Wins — ' + league_name + '</title>\n'
        '  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>\n'
        '  <style>\n'
        '    *, *::before, *::after { box-sizing: border-box; }\n'
        '    body { margin: 0; padding: 0; background: #fff;\n'
        '           font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }\n'
        '    #page-header { padding: 16px 20px 4px; text-align: center; }\n'
        '    #page-header h2 { margin: 0 0 4px; font-size: 1.15rem; color: #1a1a2e; }\n'
        '    #page-header p  { margin: 0; font-size: 0.8rem; color: #666; }\n'
        '    #season-selector { padding: 8px 20px 0; display: flex; flex-wrap: wrap;\n'
        '                       gap: 8px; align-items: center; justify-content: center; }\n'
        '    .season-label { font-size: 11px; font-weight: 700; color: #444;\n'
        '                    width: 100%; margin-bottom: 2px; text-align: center; }\n'
        '    .season-btn {\n'
        '      padding: 5px 13px; font-size: 12px; cursor: pointer; border-radius: 4px;\n'
        '      background: #f0f0f0; border: 1px solid #aaa; color: #333; white-space: nowrap;\n'
        '    }\n'
        '    .season-btn.active {\n'
        '      background: #e8ecff; border-color: #667eea;\n'
        '      font-weight: 700; color: #3730a3;\n'
        '    }\n'
        '    .season-wrap { display: none; width: 100%; }\n'
        '    .season-wrap.active { display: block; }\n'
        '    .layout-wrap { width: 100%; }\n'
        '  </style>\n'
        '</head>\n'
        '<body>\n'
        '  <div id="page-header">\n'
        '    <h2>Lucky Wins &mdash; ' + league_name + '</h2>\n'
        '    <p>Circles = Wins &middot; X = Losses &middot; Blue = Regular Season &middot; Red = Playoffs</p>\n'
        '  </div>\n\n'
        '  <div id="season-selector">\n'
        '    <div class="season-label">Season</div>\n'
        '    ' + season_buttons_html + '\n'
        '  </div>\n\n'
    )

    html_script = (
        '\n  <script>\n'
        '    function setSeason(s) {\n'
        '      document.querySelectorAll(".season-btn").forEach(b => b.classList.remove("active"));\n'
        '      document.getElementById("btn-season-" + s).classList.add("active");\n'
        '      document.querySelectorAll(".season-wrap").forEach(w => w.classList.remove("active"));\n'
        '      document.getElementById("season-" + s).classList.add("active");\n'
        '      applyLayout();\n'
        '    }\n\n'
        '    function applyLayout() {\n'
        '      var mobile = window.innerWidth < 769;\n'
        '      var active = document.querySelector(".season-wrap.active");\n'
        '      if (!active) return;\n'
        '      var dw = active.querySelector(".desktop-wrap");\n'
        '      var mw = active.querySelector(".mobile-wrap");\n'
        '      if (dw) dw.style.display = mobile ? "none" : "block";\n'
        '      if (mw) mw.style.display = mobile ? "block" : "none";\n'
        '      var wrap = mobile ? mw : dw;\n'
        '      if (wrap) {\n'
        '        var gdiv = wrap.querySelector(".js-plotly-plot");\n'
        '        if (gdiv) Plotly.Plots.resize(gdiv);\n'
        '      }\n'
        '    }\n\n'
        '    window.addEventListener("load", applyLayout);\n'
        '    window.addEventListener("resize", applyLayout);\n'
        '  </script>\n'
        '</body>\n'
        '</html>'
    )

    html_content = html_head + season_divs_html + html_script

    with open(output, "w", encoding="utf-8") as f:
        f.write(html_content)

    abs_path = os.path.abspath(output)
    print(f"  Saved: {abs_path}")
    webbrowser.open(f"file:///{abs_path}")


if __name__ == "__main__":
    import build_all
    build_all.main(open_browser=True)
