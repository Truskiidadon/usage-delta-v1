"""Historical backtest.

Every threshold in this repo was chosen to fit a handful of 2026 cases whose
answers were already known. That is a curve fit. This measures whether the
screen predicts anything.

Design is documented in the README. The parts that matter in code:

  Two outcomes, separately. Snap share answers "did the role hold" and tests
  the detector. PPR per game answers "did it pay" and tests the premise that
  role predicts production. If roles hold and points do not follow, the
  detector works and the thesis is wrong -- one metric cannot tell those apart.

  Matched controls are mandatory. A player flagged for a snap-share jump
  almost by definition had a low baseline, so comparing him to his own prior
  weeks is mechanically biased toward success: regression to the mean alone
  produces a positive result. Controls are unflagged player-weeks in the same
  season and position with a similar baseline.

  Players injured during the outcome window stay in the sample. Excluding
  them deletes the downside. Reported both ways.
"""

import numpy as np
import pandas as pd

from .diff import ALERT_PP, MIN_SNAPS, compute_deltas, confirmed_trend
from .fetch import build_usage
from .injuries import load_injuries, tag

# Snap counts begin in 2012, which is the binding constraint on how far back
# this can go. 2012 itself has malformed week values upstream.
SEASONS = range(2013, 2026)
TUNE = range(2013, 2020)
HOLDOUT = range(2020, 2026)

BASELINE_GAMES = 3
OUTCOME_GAMES = 4

POSITIONS = ("WR", "RB", "TE")

# Flag week buckets. A week 3 flag and a week 15 flag have different
# implications; stratifying answers that rather than assuming it.
WEEK_BUCKETS = [(2, 6, "early"), (7, 12, "mid"), (13, 18, "late")]

# Controls are matched within these baseline PPR bands.
BASELINE_BINS = [-0.01, 2, 5, 8, 12, 17, 100]


def _bucket_week(w: int) -> str:
    for lo, hi, name in WEEK_BUCKETS:
        if lo <= w <= hi:
            return name
    return "other"


def build_panel(season: int) -> pd.DataFrame:
    """One row per player-week with baseline, outcome, and flag status."""
    usage = build_usage(season)
    deltas = confirmed_trend(compute_deltas(usage))
    # No lookahead: the backtest must only know what was knowable at the time.
    deltas = tag(deltas, usage, load_injuries(season), lookahead=False)

    df = deltas[deltas["position"].isin(POSITIONS)].copy()
    df = df.sort_values(["pfr_player_id", "week"])
    df["fantasy_points_ppr"] = df["fantasy_points_ppr"].fillna(0)

    grp = df.groupby("pfr_player_id", sort=False)

    # Baseline: mean over the player's prior appearances, excluding this week.
    df["baseline_ppr"] = (
        grp["fantasy_points_ppr"]
        .shift(1)
        .groupby(df["pfr_player_id"])
        .rolling(BASELINE_GAMES, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["baseline_snap"] = (
        grp["offense_pct"]
        .shift(1)
        .groupby(df["pfr_player_id"])
        .rolling(BASELINE_GAMES, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Outcome: the next OUTCOME_GAMES calendar weeks, counting only games the
    # player actually appeared in. Appearing in none is the injured case.
    out = []
    for pid, g in df.groupby("pfr_player_id", sort=False):
        weeks = g["week"].to_numpy()
        ppr = g["fantasy_points_ppr"].to_numpy()
        snap = g["offense_pct"].to_numpy()
        for i, w in enumerate(weeks):
            m = (weeks > w) & (weeks <= w + OUTCOME_GAMES)
            out.append((g.index[i], m.sum(), ppr[m].mean() if m.any() else np.nan,
                        snap[m].mean() if m.any() else np.nan))
    o = pd.DataFrame(out, columns=["idx", "games_after", "outcome_ppr", "outcome_snap"]).set_index("idx")
    df = df.join(o)

    df["flagged"] = (
        df["offense_pct_tier"].isin(["alert", "actionable"])
        & (df["offense_snaps"] >= MIN_SNAPS)
    )
    df["group"] = np.where(
        ~df["flagged"], "control",
        np.where(df["priced"], "priced", "unexplained"),
    )
    df["rose"] = df["offense_pct_delta"] > 0
    df["week_bucket"] = df["week"].map(_bucket_week)
    df["baseline_bin"] = pd.cut(df["baseline_ppr"], BASELINE_BINS)
    return df


def load_panel(seasons=SEASONS) -> pd.DataFrame:
    frames = []
    for s in seasons:
        try:
            frames.append(build_panel(s))
        except Exception as e:  # a bad season should not kill the run
            print(f"  season {s} failed: {type(e).__name__}: {e}")
    return pd.concat(frames, ignore_index=True)


def _weighted_control(panel: pd.DataFrame, treated: pd.DataFrame, col: str) -> float:
    """Control mean, reweighted to the treated group's baseline distribution.

    Comparing raw group means would compare different kinds of player. This
    reweights controls so their baseline mix matches the flagged players',
    which is what isolates the flag from regression to the mean.
    """
    ctl = panel[(panel["group"] == "control") & panel[col].notna()]
    if ctl.empty or treated.empty:
        return np.nan

    w = treated["baseline_bin"].value_counts(normalize=True)
    means = ctl.groupby("baseline_bin", observed=True)[col].mean()
    shared = means.index.intersection(w.index)
    if len(shared) == 0:
        return np.nan
    ww = w[shared] / w[shared].sum()
    return float((means[shared] * ww).sum())


def compare(panel: pd.DataFrame, col: str = "outcome_ppr",
            require_appearance: bool = True) -> pd.DataFrame:
    """Lift over matched controls, by group, for one outcome column."""
    df = panel[panel["baseline_ppr"].notna()].copy()

    if require_appearance:
        df = df[df["games_after"] > 0]
    else:
        # Injured out of the whole window scores zero rather than vanishing.
        df = df[df["games_after"].notna()]
        df.loc[df["games_after"] == 0, col] = 0.0

    rows = []
    for g in ("unexplained", "priced"):
        t = df[(df["group"] == g) & df[col].notna()]
        if t.empty:
            continue
        ctl = _weighted_control(df, t, col)
        rows.append({
            "group": g,
            "n": len(t),
            "mean": t[col].mean(),
            "control": ctl,
            "lift": t[col].mean() - ctl,
            "hit_rate_vs_ctl": (t[col] > ctl).mean(),
        })
    return pd.DataFrame(rows)


def compare_by(panel: pd.DataFrame, by: str, col: str = "outcome_ppr") -> pd.DataFrame:
    """Same comparison, split by a column (week_bucket, season era, etc)."""
    out = []
    for key, sub in panel.groupby(by, observed=True):
        r = compare(sub, col)
        r[by] = key
        out.append(r)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ---------------------------------------------------------------------------
# NEGATIVE RESULT — paired teammate vacancy
#
# Idea: snap share within a position group is close to zero-sum, so a sharp
# rise in player B is mechanically paired with a fall in player A. The
# pairing itself should be the signal -- it says a real role was vacated,
# rather than the riser just collecting snaps in a long game. The appeal is
# that it is computable on Tuesday from snap counts alone, with no injury
# report, which is exactly the blind spot where the biggest historical
# returns live (Charcandrick West / Jamaal Charles, DeAngelo Williams /
# Le'Veon Bell, Mike Davis / McCaffrey -- all tagged `unexplained` because
# the starter went down mid-game and never hit a pre-game report).
#
# First implementation missed its own best case: a player who is inactive
# has no snap row at all, so he contributes no negative delta. The version
# below counts both reduced roles and outright absences.
#
# RESULT: did not replicate. Lift by vacated_share bucket --
#
#   bucket     tune    holdout
#   none       3.64     1.12     (n=28 / n=21, too small to read)
#   <30pp      1.20     2.01
#   30-60pp    1.98     1.36
#   60pp+      2.73     1.84
#
# The tune set is cleanly monotonic above `none` (1.20 -> 1.98 -> 2.73),
# which is the shape you want. The holdout does not reproduce it: <30pp
# lands above both middle buckets and the ordering collapses. Tuning alone
# would have shipped this.
#
# The one thread that survives: hit rate is highest in the 60pp+ bucket in
# both sets (66% tune, 58% holdout), more consistently than lift. Weak
# evidence the mechanism is real but smaller than the tune set implied.
#
# Likely explanation: the signal is already largely captured upstream. A
# confirmed 25pp rise usually IS a vacancy, so conditioning on vacated share
# adds less than it appears to.
#
# To revisit properly: per-bucket samples here are 21-112, too small to
# resolve. Pool more seasons, or treat vacated_share as a continuous feature
# in a model rather than bucketing it.
# ---------------------------------------------------------------------------

VACANCY_MIN_ROLE = 0.30


def add_vacated_share(panel: pd.DataFrame) -> pd.DataFrame:
    """Share given up by same-position teammates: reduced role or absent.

    Retained for the follow-up described above. Not used by the live tool.
    """
    d = panel[["season", "week", "team", "position", "pfr_player_id",
               "offense_pct", "offense_pct_prior"]].copy()

    d["given"] = np.where(
        d["offense_pct"] < d["offense_pct_prior"],
        (d["offense_pct_prior"] - d["offense_pct"]).where(
            d["offense_pct_prior"] >= VACANCY_MIN_ROLE, 0),
        0.0,
    )
    present = (
        d.groupby(["season", "week", "team", "position"], as_index=False)["given"]
        .sum().rename(columns={"given": "pool_present"})
    )

    # Teammates who held a real role last week and did not appear this week.
    last = panel[["season", "week", "team", "position", "pfr_player_id", "offense_pct"]].copy()
    last["week"] += 1
    last = last.rename(columns={"offense_pct": "prev_share"})
    seen = panel[["season", "week", "pfr_player_id"]].assign(played=1)
    gone = last.merge(seen, on=["season", "week", "pfr_player_id"], how="left")
    gone = gone[gone["played"].isna() & (gone["prev_share"] >= VACANCY_MIN_ROLE)]
    absent = (
        gone.groupby(["season", "week", "team", "position"], as_index=False)["prev_share"]
        .sum().rename(columns={"prev_share": "pool_absent"})
    )

    out = (
        panel.merge(present, on=["season", "week", "team", "position"], how="left")
             .merge(absent, on=["season", "week", "team", "position"], how="left")
             .merge(d[["season", "week", "pfr_player_id", "given"]],
                    on=["season", "week", "pfr_player_id"], how="left")
    )
    out["vacated_share"] = (
        out["pool_present"].fillna(0) + out["pool_absent"].fillna(0) - out["given"].fillna(0)
    ).clip(lower=0)
    return out
