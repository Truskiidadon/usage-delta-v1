"""Week-over-week usage diffs.

The market prices levels. This prices change.
"""

import numpy as np
import pandas as pd

# Thresholds, as fractions (0.09 == 9 percentage points).
#
# These were originally guesses. The backtest (13 seasons, 75k player-weeks)
# showed lift rising monotonically with the threshold -- 0.53 at 9pp, 1.00 at
# 20pp, 1.53 at 30pp, 1.96 at 40pp -- and that the shipped defaults flagged
# 45% of all player-weeks, which is not a screen. ACTIONABLE moved 0.15 -> 0.25
# on that evidence. ALERT stays loose on purpose: it is a watch list, not a
# decision.
ALERT_PP = 0.09
ACTIONABLE_PP = 0.25

# A snap-share rise alone says the player was on the field more. Pairing it
# with a target-share rise says he was on the field more AND getting the ball,
# which is a different claim and removes most of the false positives -- the
# blowout snaps, the move into a blocking role.
#
# Backtested and it replicates: hit rate vs matched controls goes 54% -> 66%
# on the holdout, lift 1.66 -> 2.89. Adding air-yards share on top made it
# worse. Table in the README.
CONFIRM_TARGET_PP = 0.05

# The same bar applied to carry share. Inherited from the target bar rather
# than tuned independently: carry share is more concentrated than target
# share -- a lead back holds 60-70% of carries where a WR1 holds 25% of
# targets -- so this is probably too loose and is a flagged follow-up.
CONFIRM_CARRY_PP = 0.05

# A move at a small baseline matters more than the same move at a large one.
# 30% -> 45% is a role change; 75% -> 90% is often just a long game.
# Trigger on whichever is easier to clear: the flat threshold or this.
RELATIVE_TRIGGER = 0.25

# Team plays outside this band around the team's season average make that
# week's snap shares unreliable -- too few plays and shares get noisy, too
# many (a blowout, a long overtime) and backups eat garbage-time snaps.
PLAYS_BAND = 0.20

# Metrics that get diffed. Efficiency metrics are deliberately excluded:
# they explain a flag after it fires, they do not generate one.
USAGE_METRICS = ["offense_pct", "target_share", "air_yards_share", "carry_share"]

# Below this, snap share is too jumpy to read as role.
MIN_SNAPS = 5


def _tier(delta: float, prior: float) -> str:
    """Classify a single delta as actionable, alert, or nothing.

    Absolute move clears the flat bar, OR a smaller move clears the
    relative bar at a low baseline.
    """
    if pd.isna(delta) or pd.isna(prior):
        return "none"

    size = abs(delta)
    relative = abs(delta) / prior if prior > 0 else np.inf

    if size >= ACTIONABLE_PP or (relative >= RELATIVE_TRIGGER and size >= ALERT_PP):
        return "actionable"
    if size >= ALERT_PP or (relative >= RELATIVE_TRIGGER and size >= ALERT_PP / 2):
        return "alert"
    return "none"


def flag_game_context(usage: pd.DataFrame) -> pd.DataFrame:
    """Mark weeks where team play volume was abnormal.

    A delta from a flagged week still surfaces, but carries lower confidence
    and does not satisfy the two-week confirmation requirement on its own.
    """
    df = usage.copy()
    avg = (
        df.groupby(["season", "team"], as_index=False)["team_plays"]
        .mean()
        .rename(columns={"team_plays": "team_plays_avg"})
    )
    df = df.merge(avg, on=["season", "team"], how="left")

    deviation = (df["team_plays"] - df["team_plays_avg"]).abs() / df["team_plays_avg"]
    df["context_ok"] = deviation <= PLAYS_BAND
    return df


def compute_deltas(usage: pd.DataFrame, metrics=None) -> pd.DataFrame:
    """One row per player per week, with the change from the prior week.

    Diffs are taken against the player's previous *appearance*, not the
    previous calendar week, so a bye or an inactive game does not read as
    a role collapse.
    """
    metrics = metrics or USAGE_METRICS
    df = flag_game_context(usage).sort_values(["pfr_player_id", "week"]).copy()

    grp = df.groupby("pfr_player_id", sort=False)

    df["prev_week"] = grp["week"].shift(1)
    df["weeks_since"] = df["week"] - df["prev_week"]

    for m in metrics:
        if m not in df.columns:
            continue
        prior = grp[m].shift(1)
        df[f"{m}_prior"] = prior
        df[f"{m}_delta"] = df[m] - prior
        df[f"{m}_tier"] = [
            _tier(d, p) for d, p in zip(df[f"{m}_delta"], prior)
        ]

    # Raw snaps alongside share: a flat 75% share can hide 15 extra snaps.
    df["offense_snaps_prior"] = grp["offense_snaps"].shift(1)
    df["offense_snaps_delta"] = df["offense_snaps"] - df["offense_snaps_prior"]

    # Snap share moving together with the metric that carries that position's
    # role. See CONFIRM_TARGET_PP.
    #
    # This used to gate every position on target share, which made the filter
    # structurally blind to running backs: 2026 flags corroborated at 28% for
    # RBs against 40% for WRs, and a back who went from a 37% committee role
    # to a 97% bellcow while doubling his carries never corroborated once,
    # because his targets stayed flat at four to six. A back's job is carries.
    # A receiving back still confirms on targets, so RB takes either.
    def _moved(col, bar, up):
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col] >= bar if up else df[col] <= -bar

    tgt_up = _moved("target_share_delta", CONFIRM_TARGET_PP, True)
    tgt_dn = _moved("target_share_delta", CONFIRM_TARGET_PP, False)
    car_up = _moved("carry_share_delta", CONFIRM_CARRY_PP, True)
    car_dn = _moved("carry_share_delta", CONFIRM_CARRY_PP, False)

    is_rb = df["position"].eq("RB") if "position" in df.columns else False
    conf_up = (tgt_up | car_up) & is_rb | tgt_up & ~is_rb
    conf_dn = (tgt_dn | car_dn) & is_rb | tgt_dn & ~is_rb

    df["corroborated"] = (
        (df["offense_pct_delta"] > 0) & conf_up
    ) | (
        (df["offense_pct_delta"] < 0) & conf_dn
    )

    return df


def confirmed_trend(deltas: pd.DataFrame, metric: str = "offense_pct") -> pd.DataFrame:
    """Flag players whose move held for two consecutive appearances.

    One week of movement is often game script. A move that holds is a role.
    """
    df = deltas.sort_values(["pfr_player_id", "week"]).copy()
    col = f"{metric}_delta"

    grp = df.groupby("pfr_player_id", sort=False)
    prior_delta = grp[col].shift(1)

    same_direction = np.sign(df[col]) == np.sign(prior_delta)
    both_real = (df[col].abs() >= ALERT_PP / 2) & (prior_delta.abs() >= ALERT_PP / 2)

    df["confirmed"] = same_direction & both_real & df[col].notna()
    return df


def report(
    deltas: pd.DataFrame,
    week: int,
    metric: str = "offense_pct",
    positions=("WR", "RB", "TE"),
    min_tier: str = "alert",
    corroborated_only: bool = False,
) -> pd.DataFrame:
    """Sorted list of flagged role changes for one week, both directions."""
    tiers = {"alert": ["alert", "actionable"], "actionable": ["actionable"]}[min_tier]

    out = deltas[
        (deltas["week"] == week)
        & (deltas["position"].isin(positions))
        & (deltas[f"{metric}_tier"].isin(tiers))
        & (deltas["offense_snaps"] >= MIN_SNAPS)
    ].copy()

    cols = [
        "week",
        "player",
        "position",
        "team",
        # Join key for attention.py. Carried through even though it is noise
        # on screen, because without it a flag table cannot be matched to any
        # other source.
        "gsis_id",
        f"{metric}_prior",
        metric,
        f"{metric}_delta",
        f"{metric}_tier",
        "offense_snaps_delta",
        "context_ok",
        "confirmed",
        "corroborated",
        "injury_tag",
        "vacancy_weeks",
        "priced",
    ]
    cols = [c for c in cols if c in out.columns]

    if corroborated_only:
        out = out[out["corroborated"]]

    return out[cols].sort_values(f"{metric}_delta", key=abs, ascending=False)
