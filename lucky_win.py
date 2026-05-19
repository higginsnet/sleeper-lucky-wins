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


def lucky_win_plot(df, output="lucky_wins.html"):
    teams = sorted(df["team"].unique())
    ncols = 4
    nrows = -(-len(teams) // ncols)

    fig = make_subplots(
        rows=nrows, cols=ncols,
        subplot_titles=teams,
        horizontal_spacing=0.07,
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
    # visible="legendonly" means they appear in the legend but don't plot data.
    # Because they never hide, the legend stays visible no matter which
    # data traces the toggles show or conceal.
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
    trace_meta = []   # one entry per data trace, parallel to fig.data[N_ANCHORS:]
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
    data_range = list(range(N_ANCHORS, total))

    # ── Benchmark visibility list ────────────────────────────────────────────
    # Anchor traces are always "legendonly"; data traces flip between T/F.
    def _bench_vis(show_indices):
        show_set = set(show_indices)
        return ["legendonly"] * N_ANCHORS + [i in show_set for i in range(N_ANCHORS, total)]

    # ── Year restyle args ────────────────────────────────────────────────────
    # Restyling x/y/hovertext is independent of the benchmark visibility toggle,
    # so the two controls compose correctly without knowing each other's state.
    def _year_restyle(season_filter):
        fdf = df if season_filter == "All" else df[df["season"] == season_filter]
        xs, ys, hs = [], [], []
        for m in trace_meta:
            sub = fdf[
                (fdf["team"] == m["team"]) &
                (fdf["is_playoff"] == m["is_playoff"]) &
                (fdf["win"] == m["win"])
            ]
            xs.append(sub[m["x_col"]].tolist())
            ys.append(sub[m["y_col"]].tolist())
            hs.append(_make_hover(sub, m["x_col"], m["y_col"]))
        return [{"x": xs, "y": ys, "hovertext": hs}, data_range]

    seasons = ["All"] + sorted(df["season"].unique().tolist())

    # ── Background fills + diagonal + zero-lines (per subplot) ──────────────
    # Shapes use each subplot's own axis reference so coordinates are in data
    # space. A large range (±500) safely exceeds any realistic score delta;
    # Plotly clips the fill to the visible axis range automatically.
    # Global symmetric axis range — centers every subplot at zero and prevents
    # shape coordinates from inflating the auto-range.
    max_val = (
        df[["score_rel_avg", "opp_rel_avg", "score_rel_med", "opp_rel_med"]]
        .abs().values.max() * 1.15
    )
    R = max_val  # shorthand used in shapes below

    LUCKY_FILL   = "rgba(173, 198, 245, 0.40)"   # periwinkle blue — below diagonal
    UNLUCKY_FILL = "rgba(255, 160, 160, 0.35)"    # light pink-red  — above diagonal

    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xax = "x" if ax_n == 1 else f"x{ax_n}"
        yax = "y" if ax_n == 1 else f"y{ax_n}"

        # Blue: below the y=x diagonal (triangle: SW corner → diagonal → SE corner)
        fig.add_shape(type="path",
            path=f"M {-R},{-R} L {R},{R} L {R},{-R} Z",
            fillcolor=LUCKY_FILL, line_width=0,
            xref=xax, yref=yax, layer="below",
        )
        # Pink: above the y=x diagonal (triangle: SW corner → diagonal → NW corner)
        fig.add_shape(type="path",
            path=f"M {-R},{-R} L {R},{R} L {-R},{R} Z",
            fillcolor=UNLUCKY_FILL, line_width=0,
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

    # ── Corner watermark annotations (Lucky / Unlucky per subplot) ──────────
    # xref/yref "xN domain" places the annotation at a fraction (0–1) of that
    # subplot's own plot area, independent of the data scale on each axis.
    # Both labels sit in the upper-right quadrant (domain x>0.5, y>0.5).
    # "Unlucky Loss" is above the diagonal (y_domain > x_domain → pink zone).
    # "Lucky Win"    is below the diagonal (y_domain < x_domain → blue zone).
    # The same colors bleed into lower-left, making that quadrant self-explanatory.
    LUCKY_TXT   = dict(showarrow=False, font=dict(size=11, color="rgba(31,119,180,0.60)"))
    UNLUCKY_TXT = dict(showarrow=False, font=dict(size=11, color="rgba(214,39,40,0.60)"))
    corner_annots = []
    for i in range(len(teams)):
        r, c = divmod(i, ncols)
        ax_n = r * ncols + c + 1
        xd = "x domain" if ax_n == 1 else f"x{ax_n} domain"
        yd = "y domain" if ax_n == 1 else f"y{ax_n} domain"
        corner_annots += [
            # Upper-right, above diagonal → pink zone
            dict(**UNLUCKY_TXT, xref=xd, yref=yd,
                 x=0.78, y=0.94, xanchor="center", yanchor="top", text="Unlucky<br>Loss"),
            # Upper-right, below diagonal → blue zone
            dict(**LUCKY_TXT, xref=xd, yref=yd,
                 x=0.92, y=0.72, xanchor="center", yanchor="top", text="Lucky<br>Win"),
        ]

    # ── Layout: buttons + labels + title ────────────────────────────────────
    existing_annots = list(fig.layout.annotations)
    label_annots = [
        dict(text="<b>Season</b>", xref="paper", yref="paper",
             x=0.0, y=1.19, xanchor="left", yanchor="bottom",
             showarrow=False, font=dict(size=11, color="#444")),
        dict(text="<b>Benchmark</b>", xref="paper", yref="paper",
             x=1.0, y=1.19, xanchor="right", yanchor="bottom",
             showarrow=False, font=dict(size=11, color="#444")),
    ]

    fig.update_layout(
        updatemenus=[
            dict(  # Season filter — top left
                type="buttons", direction="right",
                x=0.0, xanchor="left", y=1.14, yanchor="top",
                buttons=[dict(label=str(s), method="restyle", args=_year_restyle(s))
                         for s in seasons],
                showactive=True,
                bgcolor="#f0f0f0", bordercolor="#aaa", font_size=12,
                pad={"r": 5, "t": 0},
            ),
            dict(  # Benchmark toggle — top right
                type="buttons", direction="right",
                x=1.0, xanchor="right", y=1.14, yanchor="top",
                buttons=[
                    dict(label="Weekly Average", method="update",
                         args=[{"visible": _bench_vis(avg_indices)}]),
                    dict(label="Weekly Median",  method="update",
                         args=[{"visible": _bench_vis(med_indices)}]),
                ],
                showactive=True,
                bgcolor="#f0f0f0", bordercolor="#aaa", font_size=12,
            ),
        ],
        annotations=existing_annots + corner_annots + label_annots,
        title=dict(
            text=(
                "Lucky Wins — Pretend GMs Fantasy League<br>"
                "<sup>Circles = Wins · X = Losses · Blue = Regular Season · Red = Playoffs</sup>"
            ),
            x=0.5, font_size=15,
        ),
        height=310 * nrows,
        width=1400,
        template="plotly_white",
        margin=dict(t=200, b=90),
        legend=dict(
            orientation="h", yanchor="top", y=-0.05,
            xanchor="center", x=0.5, font_size=12,
        ),
    )

    fig.write_html(output)
    abs_path = os.path.abspath(output)
    print(f"Saved: {abs_path}")
    webbrowser.open(f"file:///{abs_path}")


if __name__ == "__main__":
    print("Fetching matchup data from Sleeper API...")
    df = build_matchup_df()
    print(f"Loaded {len(df)} matchup records across seasons: {sorted(df['season'].unique())}")
    print("Building plot...")
    lucky_win_plot(df)
