"""Market attention: how many managers are adding a player right now.

The premise of this repo is that a role change is visible before it is
priced. That claim has never been tested, because nflverse carries no
rostership or ADP -- the README lists it as the largest open limitation.

Sleeper publishes add/drop counts for the last N hours, free and without
auth. That is sentiment revealed by behaviour rather than inferred from
text: a manager filing a waiver claim is a stronger signal than a manager
posting. Joined to a flag, it answers the question the backtest cannot --
was this player still available when the screen fired, and how long until
the market arrived?

THE VALUE IS THE LOG, NOT THE READING. A single snapshot says nothing. A
snapshot taken every Tuesday across a season produces the panel that tests
acquirability: flag week, add count at flag, add count one and two weeks
later. Until that log has depth, this module is an availability check and
nothing more.

Three things it is not:
  - Sleeper's market is not your league. It measures attention across all
    of Sleeper, which is the right instrument for "has the market noticed"
    and the wrong one for "can I claim him on Wednesday".
  - Current season only. There is no historical endpoint, so this cannot
    retrofit the 2013-2025 backtest. It starts accumulating from the first
    run and not before.
  - Counts are absolute, not normalised by rostership, so widely-held
    players dominate the raw list. Compare a player against his own prior
    snapshots, not against the leaderboard.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SLEEPER = "https://api.sleeper.app/v1"
TRENDING = f"{SLEEPER}/players/nfl/trending/{{kind}}"
PLAYERS = f"{SLEEPER}/players/nfl"

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"

# Deliberately NOT under data/, which is gitignored as a regenerable cache.
# Sleeper has no historical endpoint: a snapshot not taken this week can
# never be recovered. These are the only files in this repo that cannot be
# rebuilt from source, so they are versioned.
SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "attention"

TIMEOUT = 30


def _get(url: str, params: dict | None = None):
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def load_player_map(refresh: bool = False) -> pd.DataFrame:
    """sleeper_id -> gsis_id, so trending counts can join the usage panel.

    The full index is several MB and changes rarely, so it is cached. Rows
    without a gsis_id are dropped: they cannot be joined to anything here.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "sleeper_players.parquet"

    if cached.exists() and not refresh:
        return pd.read_parquet(cached)

    raw = _get(PLAYERS)
    rows = [
        {
            "sleeper_id": pid,
            "gsis_id": p.get("gsis_id"),
            "player": p.get("full_name"),
            "position": p.get("position"),
            "team": p.get("team"),
        }
        for pid, p in raw.items()
    ]
    df = pd.DataFrame(rows)
    df = df[df["gsis_id"].notna() & (df["gsis_id"] != "")]
    df = df.drop_duplicates(subset=["gsis_id"])
    df.to_parquet(cached, index=False)
    return df


def trending(kind: str = "add", lookback_hours: int = 24, limit: int = 200) -> pd.DataFrame:
    """Players most added (or dropped) across Sleeper in the window."""
    if kind not in ("add", "drop"):
        raise ValueError("kind must be 'add' or 'drop'")

    data = _get(
        TRENDING.format(kind=kind),
        {"lookback_hours": lookback_hours, "limit": limit},
    )
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["sleeper_id", f"{kind}_count"])
    return df.rename(
        columns={"player_id": "sleeper_id", "count": f"{kind}_count"}
    )


def attach(deltas: pd.DataFrame, lookback_hours: int = 24,
           refresh: bool = False) -> pd.DataFrame:
    """Add add_count and drop_count to a flag table, joined on gsis_id.

    Players absent from the trending list are genuinely untrending, so the
    counts fill to zero rather than NaN. A flagged player at zero adds is
    the case this repo was built to find.
    """
    xmap = load_player_map(refresh)
    out = deltas.copy()

    for kind in ("add", "drop"):
        t = trending(kind, lookback_hours).merge(
            xmap[["sleeper_id", "gsis_id"]], on="sleeper_id", how="inner"
        )
        out = out.merge(
            t[["gsis_id", f"{kind}_count"]], on="gsis_id", how="left"
        )
        out[f"{kind}_count"] = out[f"{kind}_count"].fillna(0).astype(int)

    return out


def snapshot(deltas: pd.DataFrame, season: int, week: int,
             lookback_hours: int = 24) -> Path:
    """Write one dated row-set to data/attention/ and return the path.

    Run this on the same weekday each week. The filename carries the stamp
    so repeated runs in a week do not overwrite each other, and the whole
    directory concatenates into the acquirability panel later.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    df = attach(deltas, lookback_hours)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    keep = [
        c
        for c in (
            "season", "week", "player", "position", "team", "gsis_id",
            "offense_pct_prior", "offense_pct", "offense_pct_delta",
            "offense_pct_tier", "target_share_delta", "injury_tag",
            "vacancy_weeks", "confirmed", "corroborated",
            "add_count", "drop_count",
        )
        if c in df.columns
    ]
    path = SNAPSHOT_DIR / f"attention_{season}_wk{week}_{stamp}.csv"
    df[keep].to_csv(path, index=False)
    return path


def load_snapshots() -> pd.DataFrame:
    """Every snapshot taken so far, concatenated. The acquirability panel."""
    if not SNAPSHOT_DIR.exists():
        return pd.DataFrame()
    files = sorted(SNAPSHOT_DIR.glob("attention_*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat(
        (pd.read_csv(f).assign(snapshot=f.stem) for f in files),
        ignore_index=True,
    )
