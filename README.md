# Sleeper Dynasty Dashboard

Interactive fantasy football analytics built on the [Sleeper API](https://docs.sleeper.com/).

## What is a Lucky Win?

Each week, every team scores some points relative to the weekly median. The scatter plots show:

- **X-axis** — how far above or below the weekly median *your* team scored
- **Y-axis** — how far above or below the weekly median *your opponent* scored
- **Diagonal line** — the win/loss boundary (above = your opponent outscored you, below = you outscored them)

The four shaded zones tell the story:

| Zone | Color | Meaning |
|---|---|---|
| Q1 upper-left triangle | 🔴 Pink | **Unlucky loss** — both teams above median, but your opponent scored more |
| Q1 lower-right triangle | 🔵 Blue | **Lucky win** — both teams above median, but you scored more |
| Q3 upper-left triangle | 🔵 Blue | **Lucky win** — both teams below median, but you scored more |
| Q3 lower-right triangle | 🔴 Pink | **Unlucky loss** — both teams below median, but your opponent scored more |

A **lucky win** means you won a week where both teams struggled — fortune favored you. An **unlucky loss** means you played well but your opponent happened to play better in a high-scoring week.

## Leagues

| League | File | Link |
|---|---|---|
| Pretend GMs Fantasy League | `lucky_wins_pretend_gms.html` | [View](https://higginsnet.github.io/sleeper-lucky-wins/lucky_wins_pretend_gms.html) |
| On the Clock Fantasy League | `lucky_wins_on_the_clock.html` | [View](https://higginsnet.github.io/sleeper-lucky-wins/lucky_wins_on_the_clock.html) |
| The Empire Strikes Back | `lucky_wins_empire.html` | [View](https://higginsnet.github.io/sleeper-lucky-wins/lucky_wins_empire.html) |
| 2 Minute Drill | `lucky_wins_2_minute_drill.html` | [View](https://higginsnet.github.io/sleeper-lucky-wins/lucky_wins_2_minute_drill.html) |

## Features

- **Season selector** — toggle between All-time and individual seasons
- **Per-season rosters** — only teams active in a given season are shown (no blank charts)
- **Lucky/Unlucky summary** — identifies the luckiest and unluckiest team for the selected view
- **Responsive** — desktop (4-column) and mobile (2-column) layouts auto-switch based on screen width
- **Playoff highlighting** — red markers = playoff weeks, blue = regular season

## Running Locally

**Requirements:** Python 3.9+, packages in `requirements.txt` (pandas, plotly)

```bash
# Install dependencies
pip install pandas plotly requests

# Regenerate all HTML files
C:/Users/Dylan/anaconda3/python.exe build_all.py
```

Output files are written to the project directory and opened in your browser automatically.

## Files

| File | Purpose |
|---|---|
| `lucky_win.py` | Core data fetching, plot building, and HTML generation |
| `build_all.py` | Entry point — loops over all league configs and calls `lucky_win.py` |
| `sleeper_api.py` | Thin wrapper around the Sleeper REST API |
| `index.html` | Landing page linking to all league dashboards |

## Data

All data is fetched live from the [Sleeper API](https://docs.sleeper.com/) at build time. No data is stored in this repo. Re-run `build_all.py` at any point during the season to pick up the latest week's results.
