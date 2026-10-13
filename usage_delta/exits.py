"""In-game exit detection from play-by-play participation.

The injury report is published before kickoff, so a player hurt during a game
has no row that week. This finds those exits directly: the last offensive play
a player appeared in, relative to how many his team ran.

Validated against the following week's injury report -- a player whose last
snap came before 65% of his team's plays is ~4x likelier to appear on it.
Table in the README.

USE IT FOR knowing when your own player got hurt before the report says so:
a hold/sell and lineup signal.

NOT FOR improving waiver flags, which was the original motive. Adding
"a teammate exited" makes those flags WORSE in both the tune and holdout
sets. It fails for the same reason the paired-vacancy feature in backtest.py
failed, and the shared reason is the finding worth keeping: the riser's own
snap jump already encodes the vacancy. If a backup played 92% of snaps, that
92% IS the vacancy. Cause-of-vacancy features are redundant with the effect
being measured. Numbers in the README.

NOT USABLE ON THE CURRENT SEASON. nflverse's pbp_participation ends after
2025 and the 2026 file returns 404, so everything here is retrospective.
The live use above is unavailable until a current-season source exists,
which means mid-game exits in a live week are invisible to this repo and
have to be supplied by someone who watched the game.
"""

import pandas as pd

from .fetch import NFLVERSE, _load

PARTICIPATION = f"{NFLVERSE}/pbp_participation/pbp_participation_{{season}}.parquet"
PBP = f"{NFLVERSE}/pbp/play_by_play_{{season}}.parquet"

# Last snap before this share of team plays reads as an exit rather than a
# rotation. 0.65 is where the next-week injury rate is still ~2x baseline.
EXIT_THRESHOLD = 0.65

# Below this, snap counts are too sparse for the ratio to mean anything.
MIN_SNAPS = 10

FIRST_SEASON = 2016


def load_exits(season: int, refresh: bool = False) -> pd.DataFrame:
    """Per player-game: snaps, and how far into the game their last one came."""
    if season < FIRST_SEASON:
        raise ValueError(f"participation data starts in {FIRST_SEASON}")

    weeks = _load(PBP.format(season=season), f"pbp_{season}.parquet", refresh)
    weeks = weeks.drop_duplicates("game_id").set_index("game_id")["week"]

    d = _load(PARTICIPATION.format(season=season), f"participation_{season}.parquet", refresh)
    d = d[d["offense_players"].notna() & (d["offense_players"] != "")]

    d["rank"] = d.groupby(["nflverse_game_id", "possession_team"])["play_id"].rank(method="dense")
    team_plays = (
        d.groupby(["nflverse_game_id", "possession_team"])["rank"].max().rename("team_plays")
    )

    e = d.assign(pid=d["offense_players"].str.split(";")).explode("pid")
    last = (
        e.groupby(["nflverse_game_id", "possession_team", "pid"])
        .agg(last_rank=("rank", "max"), snaps=("rank", "count"))
        .reset_index()
        .merge(team_plays, on=["nflverse_game_id", "possession_team"])
    )

    last["exit_frac"] = last["last_rank"] / last["team_plays"]
    last["week"] = last["nflverse_game_id"].map(weeks)
    last["season"] = season
    last = last.dropna(subset=["week"])
    last["week"] = last["week"].astype(int)
    last["exited"] = (last["exit_frac"] < EXIT_THRESHOLD) & (last["snaps"] >= MIN_SNAPS)

    return last.rename(columns={"possession_team": "team", "pid": "gsis_id"})[
        ["season", "week", "team", "gsis_id", "snaps", "exit_frac", "exited"]
    ]


def exits_for_week(season: int, week: int, refresh: bool = False) -> pd.DataFrame:
    """Players who appear to have left a given week's game early."""
    df = load_exits(season, refresh)
    out = df[(df["week"] == week) & df["exited"]]
    return out.sort_values("exit_frac")
