"""Pull weekly NFL usage data from nflverse.

nflverse publishes season files as parquet on GitHub Releases -- no API key,
no rate limit. Read directly rather than through a wrapper library so the
data source stays visible and the dependency list stays short.

Snap counts are keyed on pfr_player_id and weekly stats on gsis_id, so
players.parquet provides the crosswalk. Join on IDs, never names: the snap
file lists "Tre Harris", other sources list "Tre' Harris".
"""

from pathlib import Path

import pandas as pd

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"

SNAP_COUNTS = f"{NFLVERSE}/snap_counts/snap_counts_{{season}}.parquet"
WEEKLY_STATS = f"{NFLVERSE}/stats_player/stats_player_week_{{season}}.parquet"
PLAYERS = f"{NFLVERSE}/players/players.parquet"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(url: str, cache_name: str, refresh: bool = False) -> pd.DataFrame:
    """Read a parquet from nflverse, caching it locally.

    The season files are rewritten in place as the season progresses, so
    pass refresh=True to pick up a new week.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / cache_name

    if cached.exists() and not refresh:
        return pd.read_parquet(cached)

    df = pd.read_parquet(url)
    df.to_parquet(cached, index=False)
    return df


def load_snap_counts(season: int, refresh: bool = False) -> pd.DataFrame:
    """Per-player, per-game offensive snap counts and share."""
    df = _load(
        SNAP_COUNTS.format(season=season),
        f"snap_counts_{season}.parquet",
        refresh,
    )
    # Regular season only. Preseason snap shares are meaningless for role.
    df = df[df["game_type"] == "REG"]
    return df[
        [
            "season",
            "week",
            "player",
            "pfr_player_id",
            "position",
            "team",
            "opponent",
            "offense_snaps",
            "offense_pct",
        ]
    ].copy()


def load_weekly_stats(season: int, refresh: bool = False) -> pd.DataFrame:
    """Per-player, per-week receiving and rushing usage."""
    df = _load(
        WEEKLY_STATS.format(season=season),
        f"stats_player_week_{season}.parquet",
        refresh,
    )
    keep = [
        "season",
        "week",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "targets",
        "target_share",
        "air_yards_share",
        "receptions",
        "receiving_yards",
        "carries",
        "rushing_yards",
        "fantasy_points_ppr",
    ]
    present = [c for c in keep if c in df.columns]
    return df[present].copy()


def load_id_crosswalk(refresh: bool = False) -> pd.DataFrame:
    """gsis_id <-> pfr_id mapping, so the two sources can be joined."""
    df = _load(PLAYERS, "players.parquet", refresh)
    out = df[["gsis_id", "pfr_id"]].dropna()
    return out.drop_duplicates(subset=["pfr_id"])


def team_plays(snaps: pd.DataFrame) -> pd.DataFrame:
    """Approximate offensive plays run, per team per week.

    The highest offensive snap count on a team is almost always an offensive
    lineman, who plays nearly every down. That max is a free, close proxy for
    team plays -- which is the game-context filter the README calls for.
    A team running 82 plays instead of 62 inflates everyone's counting stats.
    """
    return (
        snaps.groupby(["season", "week", "team"], as_index=False)["offense_snaps"]
        .max()
        .rename(columns={"offense_snaps": "team_plays"})
    )


def team_carries(stats: pd.DataFrame) -> pd.DataFrame:
    """Rush attempts per team per week -- the denominator for carry share.

    nflverse ships target_share and air_yards_share but no rushing
    equivalent, which is why this repo went five months without one.
    Summing the player rows includes quarterback scrambles and kneels,
    and that is correct: those are carries the backs did not get.
    """
    return (
        stats.groupby(["season", "week", "team"], as_index=False)["carries"]
        .sum()
        .rename(columns={"carries": "team_carries"})
    )


def build_usage(season: int, refresh: bool = False) -> pd.DataFrame:
    """One row per player per week, with every usage metric we can get free.

    Snap data is the spine: a player who took no snaps has no role, and that
    is the first filter in the README's hierarchy.
    """
    snaps = load_snap_counts(season, refresh)
    stats = load_weekly_stats(season, refresh)
    xwalk = load_id_crosswalk(refresh)

    usage = snaps.merge(xwalk, left_on="pfr_player_id", right_on="pfr_id", how="left")

    usage = usage.merge(
        stats.drop(columns=["position", "team", "player_display_name"], errors="ignore"),
        left_on=["season", "week", "gsis_id"],
        right_on=["season", "week", "player_id"],
        how="left",
    )

    usage = usage.merge(team_plays(snaps), on=["season", "week", "team"], how="left")
    usage = usage.merge(team_carries(stats), on=["season", "week", "team"], how="left")

    # Players with no receiving line genuinely had zero, not missing data.
    for col in ("targets", "target_share", "air_yards_share", "carries"):
        if col in usage.columns:
            usage[col] = usage[col].fillna(0)

    # Derived here because nflverse does not publish it. A back's role lives
    # in this column; without it, corroboration gates every position on a
    # receiving stat and backs confirm at 28% against a receiver's 40%.
    usage["carry_share"] = (
        usage["carries"] / usage["team_carries"].where(usage["team_carries"] > 0)
    ).fillna(0)

    usage = usage.drop(columns=["pfr_id", "player_id"], errors="ignore")
    return usage.sort_values(["player", "week"]).reset_index(drop=True)


if __name__ == "__main__":
    df = build_usage(2026, refresh=True)
    print(f"rows: {len(df)}  weeks: {sorted(df['week'].unique())}")
    print(df.columns.tolist())
