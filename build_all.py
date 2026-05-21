# build_all.py — Generate Lucky Win pages for every configured league.
# Run with: C:/Users/Dylan/anaconda3/python.exe build_all.py

import os
import webbrowser

from lucky_win import (
    LEAGUES_PRETEND_GMS,
    LEAGUES_ON_THE_CLOCK,
    build_matchup_df,
    lucky_win_plot,
)

LEAGUES_CONFIG = [
    {
        "leagues":     LEAGUES_PRETEND_GMS,
        "league_name": "Pretend GMs Fantasy League",
        "output":      "lucky_wins_pretend_gms.html",
    },
    {
        "leagues":     LEAGUES_ON_THE_CLOCK,
        "league_name": "On the Clock Fantasy League",
        "output":      "lucky_wins_on_the_clock.html",
    },
]


def main(open_browser=False):
    for cfg in LEAGUES_CONFIG:
        print(f"\n=== {cfg['league_name']} ===")
        print("Fetching matchup data from Sleeper API...")
        df = build_matchup_df(cfg["leagues"])
        print(f"Loaded {len(df)} records across seasons: {sorted(df['season'].unique())}")
        print("Building plot...")
        lucky_win_plot(df, output=cfg["output"], league_name=cfg["league_name"])

    if open_browser:
        for cfg in LEAGUES_CONFIG:
            abs_path = os.path.abspath(cfg["output"])
            webbrowser.open(f"file:///{abs_path}")

    print("\nDone. Files generated:")
    for cfg in LEAGUES_CONFIG:
        print(f"  {cfg['output']}")


if __name__ == "__main__":
    main(open_browser=True)
