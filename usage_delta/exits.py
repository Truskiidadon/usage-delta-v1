"""In-game exit detection from play-by-play participation.

The injury report is published before kickoff, so a player hurt during a game
has no row that week. This finds those exits directly: the last offensive play
a player appeared in, relative to how many his team ran.

VALIDATION (2025, players with >=10 snaps). Probability of appearing on the
FOLLOWING week's injury report, by exit fraction:

    exit_frac     n      on report next week
    <0.50         131          58.0%
    0.50-0.65     110          52.7%
    0.65-0.75     188          28.7%
    0.75-0.90    1239          14.5%
    0.90+        9226          11.5%
    baseline                   13.2%

Monotonic, and a player whose last snap came before 65% of his team's plays
is roughly 4x likelier to land on next week's report. The detector works.

WHAT IT IS NOT FOR. The original motive was to cover the blind spot where the
biggest historical returns live -- Charcandrick West, DeAngelo Williams, Mike
Davis, all beneficiaries of a starter going down mid-game and all tagged
`unexplained` because no pre-game report existed. Knowing a teammate exited
turns out NOT to improve those flags:

    filter                        tune hit   holdout hit
    baseline (25pp confirmed)       59.0%       53.9%
    + teammate exited in-game       51.9%       51.2%
    + no teammate exit              60.4%       54.9%

Worse in both sets. Lift is higher (2.34 vs 1.52) while hit rate is lower,
so those flags pay big occasionally and usually do not -- variance, not
reliability. Most in-game exits are minor and the vacancy closes.

This fails for the same reason the paired-vacancy feature in backtest.py
failed, and the shared reason is the useful finding: THE RISER'S OWN SNAP
JUMP ALREADY ENCODES THE VACANCY. If a backup played 92% of snaps, that 92%
IS the vacancy. Cause-of-vacancy features are redundant with the effect
being measured.

WHAT IT IS FOR. Knowing when YOUR OWN player got hurt, before the injury
report says so -- a hold/sell and lineup signal rather than a waiver one.

LIMITATION. Participation data exists for 2016-2025 only. No current-season
file until nflverse publishes it, so this is retrospective until then.
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
