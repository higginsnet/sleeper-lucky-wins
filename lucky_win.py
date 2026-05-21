import os
import webbrowser

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sleeper_api import get_users, get_rosters, get_matchups

# League chain: oldest → newest
LEAGUES = [
    {"league_id": "1004495314675503104", "season": 2023, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1048281198428049408", "season": 2024, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1180428546027991040", "season": 2025, "playoff_week_start": 15, "last_scored_leg": 17},
    {"league_id": "1312185578673934336", "season": 2026, "playoff_week_start": 15, "last_scored_leg": 1},
]


def build_matchup_df():
    rows = []

    for league in LEAGUES:
        league_id = league["league_id"]
        season = league["season"]
        playoff_start = league["playoff_week_start"]
        last_week = league["last_scored_leg"]

        users = get_users(league_id)
        rosters = get_rosters(league_id)

        user_map = {u["user_id"]: u.get("display_name", u["user_id"]) for u in users}
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
                        "season": season,
                        "week": week,
                        "is_playoff": week >= playoff_start,
                        "team": roster_map.get(team["roster_id"], f"Roster {team['roster_id']}"),
                        "opp": roster_map.get(opp["roster_id"], f"Roster {opp['roster_id']}"),
                        "score": float(team["points"] or 0),
                        "opp_score": float(opp["points"] or 0),
                    })

    df = pd.DataFrame(rows)
    df["win"] = df["score"] > df["opp_score"]

    # Weekly benchmark: one row per team per week, so agg of "score" gives the league stat
    grp = df.groupby(["season", "week"])["score"]
    avg = grp.mean().rename("avg")
    med = grp.median().rename("med")
    df = df.join(avg, on=["season", "week"]).join(med, on=["season", "week"])

    df["score_rel_avg"] = df["score"] - df["avg"]
    df["opp_rel_avg"]   = df["opp_score"] - df["avg"]
    df["score_rel_med"] = df["score"] - df["med"]
    df["opp_rel_med"]   = df["opp_score"] - df["med"]

    return df


def _make_hover(subset, x_col, y_col):
    bmark = "avg" if "avg" in x_col else "median"
    return [
        f"<b>{r['team']}</b> — Wk {r['week']} {r['season']}<br>"
        f"vs {r['opp']}<br>"
        f"Score: {r['score']:.2f} – {r['opp_score']:.2f}<br>"
        f"Team vs {bmark}: {r[x_col]:+.2f} · Opp vs {bmark}: {r[y_col]:+.2f}"
        for _, r in subset.iterrows()
    ]


def _build_figure(df, ncols=4):
    """
    Build the Lucky Win Plotly figure.
    ncols=4 for the desktop layout, ncols=2 for the mobile layout.
    """
    teams = sorted(df["team"].unique())
    nrows = -(-len(teams) // ncols)
    h_spacing = 0.07 if ncols >= 4 else 0.12

    fig = make_subplots(
        rows=nrows, cols=ncols,
        subplot_titles=teams,
        horizontal_spacing=h_spacing,
        vertical_spacing=0.10,
    )

    STYLES = [
        # (is_playoff, win, color, symbol, label)
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
    N_ANCHORS = len(STYLES)  # 4

    # ── Data traces ──────────────────────────────────────────────────────────
    trace_meta = []
    avg_indices, med_indices = [], []

    def _add_metric_traces(x_col, y_col, visible, index_list):
        for i, team in enumerate(teams):
            r, c = divmod(i, ncols)
            tdf = df[df["team"] == team]
            for is_playoff, win, color, symbol, label in STYLES:
                sub = tdf[(tdf["is_playoff"] == is_playoff) & (tdf["win"] == win)]
                if sub.empty:
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=sub[x_col].tolist(), y=sub[y_col].tolist(),
                        mode="markers",
                        marker=dict(symbol=symbol, color=color, size=9, opacity=0.80,
                                    line=dict(width=1.5, color="white" if win else color)),
                        name=label, showlegend=False, legendgroup=label,
                        visible=visible,
                        hovertext=_make_hover(sub, x_col, y_col),
                        hoverinfo="text",
                    ),
                    row=r + 1, col=c + 1,
                )
                index_list.append(len(fig.data) - 1)
                trace_meta.append(dict(team=team, is_playoff=is_playoff, win=win,
                                       x_col=x_col, y_col=y_col))

    _add_metric_traces("score_rel_avg", "opp_rel_avg", True,  avg_indices)
    _add_metric_traces("score_rel_med", "opp_rel_med", False, med_indices)

    total = len(fig.data)

    def _bench_vis(show_indices):
        show_set = set(show_indices)
        return ["legendonly"] * N_ANCHORS + [i in show_set for i in range(N_ANCHORS, total)]

    # ── Lucky / Unlucky summary ──────────────────────────────────────────────
    def _lucky_summary(fdf, xc, yc):
        lucky   = fdf[(fdf[xc] < 0) & (fdf[yc] < 0) & (fdf[xc] > fdf[yc]) &  fdf["win"]]
        unlucky = fdf[(fdf[xc] > 0) & (fdf[yc] > 0) & (fdf[yc] > fdf[xc]) & ~fdf["win"]]
        if lucky.empty:   luckiest,   n_l = "N/A", 0
        else: c = lucky.groupby("team").size();   luckiest,   n_l = c.idxmax(), int(c.max())
        if unlucky.empty: unluckiest, n_u = "N/A", 0
        else: c = unlucky.groupby("team").size(); unluckiest, n_u = c.idxmax(), int(c.max())
        return (
            f"<b>Luckiest Team:</b> {luckiest} ({n_l} lucky wins)"
            f"    |    "
            f"<b>Unluckiest Team:</b> {unluckiest} ({n_u} unlucky losses)"
        )

    seasons = ["All"] + sorted(df["season"].unique().tolist())
    summary_avg_texts = {
        s: _lucky_summary(df if s == "All" else df[df["season"] == s],
                          "score_rel_avg", "opp_rel_avg")
        for s in seasons
    }
    summary_med_texts = {
        s: _lucky_summary(df if s == "All" else df[df["season"] == s],
                          "score_rel_med", "opp_rel_med")
        for s in seasons
    }

    # ── Year update args ─────────────────────────────────────────────────────
    def _year_update(season_filter):
        fdf = df if season_filter == "All" else df[df["season"] == season_filter]
        xs = [[None]] * N_ANCHORS
        ys = [[None]] * N_ANCHORS
        hs = [[]] * N_ANCHORS
        for m in trace_meta:
            sub = fdf[
                (fdf["team"] == m["team"]) &
                (fdf["is_playoff"] == m["is_playoff"]) &
                (fdf["win"] == m["win"])
            ]
            xs.append(sub[m["x_col"]].tolist())
            ys.append(sub[m["y_col"]].tolist())
            hs.append(_make_hover(sub, m["x_col"], m["y_col"]))
        return [
            {"x": xs, "y": ys, "hovertext": hs},
            {
                f"annotations[{_avg_sidx[0]}].text": summary_avg_texts[season_filter],
                f"annotations[{_med_sidx[0]}].text": summary_med_texts[season_filter],
            },
        ]

    _avg_sidx = [None]
    _med_sidx = [None]

    # ── Background fills + diagonal + zero-lines (per subplot) ──────────────
    max_val = (
        df[["score_rel_avg", "opp_rel_avg", "score_rel_med", "opp_rel_med"]]
        .abs().values.max() * 1.15
    )
    R = max_val

    LUCKY_FILL   = "rgba(173, 198, 245, 0.40)"
    UNLUCKY_FILL = "rgba(255, 160, 160, 0.35)"

    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xax = "x" if ax_n == 1 else f"x{ax_n}"
        yax = "y" if ax_n == 1 else f"y{ax_n}"

        # Q1 pink (above diagonal)
        fig.add_shape(type="path",
            path=f"M 0,0 L 0,{R} L {R},{R} Z",
            fillcolor=UNLUCKY_FILL, line_width=0,
            xref=xax, yref=yax, layer="below",
        )
        # Q1 blue (below diagonal)
        fig.add_shape(type="path",
            path=f"M 0,0 L {R},{R} L {R},0 Z",
            fillcolor=LUCKY_FILL, line_width=0,
            xref=xax, yref=yax, layer="below",
        )
        # Q3 pink (above diagonal)
        fig.add_shape(type="path",
            path=f"M 0,0 L {-R},0 L {-R},{-R} Z",
            fillcolor=UNLUCKY_FILL, line_width=0,
            xref=xax, yref=yax, layer="below",
        )
        # Q3 blue (below diagonal)
        fig.add_shape(type="path",
            path=f"M 0,0 L 0,{-R} L {-R},{-R} Z",
            fillcolor=LUCKY_FILL, line_width=0,
            xref=xax, yref=yax, layer="below",
        )
        # Diagonal y = x
        fig.add_shape(type="line",
            x0=-R, y0=-R, x1=R, y1=R,
            line=dict(dash="dash", color="#999", width=1),
            xref=xax, yref=yax,
        )
        # Zero-lines
        fig.add_hline(y=0, line_dash="dot", line_color="#bbb", line_width=0.8, row=r+1, col=c+1)
        fig.add_vline(x=0, line_dash="dot", line_color="#bbb", line_width=0.8, row=r+1, col=c+1)

    fig.update_xaxes(
        tickfont_size=9, title_text="Team pts vs benchmark", title_font_size=9,
        zeroline=False, range=[-max_val, max_val], tickmode="auto", nticks=6,
    )
    fig.update_yaxes(
        tickfont_size=9, title_text="Opp pts vs benchmark", title_font_size=9,
        zeroline=False, range=[-max_val, max_val], tickmode="auto", nticks=6,
    )

    # ── Corner watermark annotations ─────────────────────────────────────────
    LUCKY_TXT   = dict(showarrow=False, font=dict(size=11, color="rgba(31,119,180,0.60)"))
    UNLUCKY_TXT = dict(showarrow=False, font=dict(size=11, color="rgba(214,39,40,0.60)"))
    corner_annots = []
    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xd = "x domain" if ax_n == 1 else f"x{ax_n} domain"
        yd = "y domain" if ax_n == 1 else f"y{ax_n} domain"
        corner_annots += [
            dict(**UNLUCKY_TXT, xref=xd, yref=yd,
                 x=0.667, y=0.833, xanchor="center", yanchor="middle", text="Unlucky<br>Loss"),
            dict(**LUCKY_TXT, xref=xd, yref=yd,
                 x=0.833, y=0.667, xanchor="center", yanchor="middle", text="Lucky<br>Win"),
        ]

    # ── Layout: buttons + labels + summary + title ──────────────────────────
    existing_annots = list(fig.layout.annotations)
    label_annots = [
        dict(text="<b>Season</b>", xref="paper", yref="paper",
             x=0.0, y=1.17, xanchor="left", yanchor="bottom",
             showarrow=False, font=dict(size=11, color="#444")),
        dict(text="<b>Benchmark</b>", xref="paper", yref="paper",
             x=1.0, y=1.17, xanchor="right", yanchor="bottom",
             showarrow=False, font=dict(size=11, color="#444")),
    ]
    _summary_base = dict(xref="paper", yref="paper",
                         x=0.5, y=1.07, xanchor="center", yanchor="bottom",
                         showarrow=False)
    avg_summary_annot = dict(**_summary_base, text=summary_avg_texts["All"],
                             font=dict(size=11, color="#333"))
    med_summary_annot = dict(**_summary_base, text=summary_med_texts["All"],
                             font=dict(size=11, color="rgba(0,0,0,0)"))

    _base_idx = len(existing_annots) + len(corner_annots) + len(label_annots)
    _avg_sidx[0] = _base_idx
    _med_sidx[0] = _base_idx + 1

    year_buttons = [dict(label=str(s), method="update", args=_year_update(s))
                    for s in seasons]

    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons", direction="right",
                x=0.0, xanchor="left", y=1.14, yanchor="top",
                buttons=year_buttons,
                showactive=True,
                bgcolor="#f0f0f0", bordercolor="#aaa", font_size=12,
                pad={"r": 5, "t": 0},
            ),
            dict(
                type="buttons", direction="right",
                x=1.0, xanchor="right", y=1.14, yanchor="top",
                buttons=[
                    dict(label="Weekly Average", method="update",
                         args=[
                             {"visible": _bench_vis(avg_indices)},
                             {
                                 f"annotations[{_avg_sidx[0]}].font.color": "#333",
                                 f"annotations[{_med_sidx[0]}].font.color": "rgba(0,0,0,0)",
                             },
                         ]),
                    dict(label="Weekly Median", method="update",
                         args=[
                             {"visible": _bench_vis(med_indices)},
                             {
                                 f"annotations[{_avg_sidx[0]}].font.color": "rgba(0,0,0,0)",
                                 f"annotations[{_med_sidx[0]}].font.color": "#333",
                             },
                         ]),
                ],
                showactive=True,
                bgcolor="#f0f0f0", bordercolor="#aaa", font_size=12,
            ),
        ],
        annotations=existing_annots + corner_annots + label_annots + [avg_summary_annot, med_summary_annot],
        title=dict(
            text=(
                "Lucky Wins — Pretend GMs Fantasy League<br>"
                "<sup>Circles = Wins · X = Losses · Blue = Regular Season · Red = Playoffs</sup>"
            ),
            x=0.5, font_size=15,
        ),
        height=310 * nrows,
        template="plotly_white",
        margin=dict(t=250, b=90),
        legend=dict(
            orientation="h", yanchor="top", y=-0.05,
            xanchor="center", x=0.5, font_size=12,
        ),
    )

    return fig


def lucky_win_plot(df, output="lucky_wins.html"):
    print("  Building desktop layout (4 columns)...")
    desktop_fig = _build_figure(df, ncols=4)
    print("  Building mobile layout (2 columns)...")
    mobile_fig = _build_figure(df, ncols=2)

    kw = dict(full_html=False, include_plotlyjs=False, config={"responsive": True})
    desktop_div = desktop_fig.to_html(**kw)
    mobile_div  = mobile_fig.to_html(**kw)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lucky Wins — Pretend GMs</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 0; background: #fff; }}
    .layout-wrap {{ width: 100%; }}
  </style>
</head>
<body>
  <div id="desktop-wrap" class="layout-wrap">{desktop_div}</div>
  <div id="mobile-wrap"  class="layout-wrap" style="display:none;">{mobile_div}</div>
  <script>
    function applyLayout() {{
      var mobile = window.innerWidth < 769;
      var dw = document.getElementById('desktop-wrap');
      var mw = document.getElementById('mobile-wrap');
      dw.style.display = mobile ? 'none' : 'block';
      mw.style.display = mobile ? 'block' : 'none';
      var wrap = mobile ? mw : dw;
      var gdiv = wrap.querySelector('.js-plotly-plot');
      if (gdiv) Plotly.Plots.resize(gdiv);
    }}
    window.addEventListener('load', applyLayout);
    window.addEventListener('resize', applyLayout);
  </script>
</body>
</html>"""

    with open(output, "w", encoding="utf-8") as f:
        f.write(html_content)

    abs_path = os.path.abspath(output)
    print(f"Saved: {abs_path}")
    webbrowser.open(f"file:///{abs_path}")


if __name__ == "__main__":
    print("Fetching matchup data from Sleeper API...")
    df = build_matchup_df()
    print(f"Loaded {len(df)} matchup records across seasons: {sorted(df['season'].unique())}")
    print("Building plot...")
    lucky_win_plot(df)
