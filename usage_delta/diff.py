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
# How each position converts snaps into opportunities, fit by least squares
# on 2013-2019 and frozen. opp_share = intercept + slope * snap_share.
#
# The slopes are the point. A back turns nearly half his snaps into a touch;
# a tight end a quarter of that, with the loosest fit of the three. That gap
# is blocking -- a receiver on the field is running a route, a tight end on
# the field may be a sixth lineman. It is why a flat confirmation bar made
# the screen NEGATIVE on tight ends: added snaps were read as added
# opportunity and for that position they frequently are not.
#
#                    intercept   slope      r
POSITION_PROFILES = {
    "RB": (-0.0038, 0.4814),   # r = 0.875
    "WR": (-0.0088, 0.1509),   # r = 0.724
    "TE": (-0.0134, 0.1182),   # r = 0.680
}

# Where the conversion is tight, raw opportunity share is the better signal
# and the residual is mostly noise. Where it is loose, the residual is what
# separates a weapon from a blocker. The cut is on the fit's own r, not on
# position identity -- add a position, fit it, and this decides for you.
RESIDUAL_ABOVE_R = 0.80

# Corroboration bars. Raw-share bars are ~1.6x that position's median
# week-over-week move; the residual bar is one number because residuals are
# already centred by the profile.
CONFIRM_OPP_PP = {"RB": 0.08, "WR": 0.04, "TE": 0.03}
CONFIRM_RESID_PP = 0.04

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
#
# offense_pct and opp_share carry the screen -- on the field, and getting
# the ball. target_share and carry_share are diagnostics only: useful to
# read on a flag, no longer used to confirm one. air_yards_share was tested
# as a third confirmer, made flags worse, and is gone.
USAGE_METRICS = ["offense_pct", "opp_share", "target_share", "carry_share"]

# ALERT_PP and ACTIONABLE_PP were tuned on SNAP SHARE and are applied by
# _tier to every metric in that list. They do not transfer: the median
# week-over-week move is 5.7pp for target share and 8.8pp for carry share,
# so the same cut sits at a different percentile of each distribution.
#
# Only offense_pct_tier is consumed anywhere. The other tier columns are
# computed, unread, and wrong, and `screen --metric target_share` routes
# one of them straight to the user. Either tune per metric or stop
# emitting tiers for metrics nobody screens on -- see the README roadmap.
TIERED_METRICS = ["offense_pct"]

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

    Reported alongside a flag as a confidence note. It does NOT gate
    anything -- an earlier docstring claimed it blocked two-week
    confirmation and no such code ever existed.

    The reference average expands over prior weeks rather than averaging the
    whole season. A season mean is not knowable in week 3, and the backtest
    states it only uses what was knowable at the time; computing this one
    column off the full season quietly broke that promise.
    """
    df = usage.copy().sort_values(["season", "team", "week"])

    prior = (
        df.groupby(["season", "team"])["team_plays"]
        .apply(lambda s: s.shift(1).expanding(min_periods=1).mean())
        .reset_index(level=[0, 1], drop=True)
    )
    df["team_plays_avg"] = prior

    deviation = (df["team_plays"] - df["team_plays_avg"]).abs() / df["team_plays_avg"]
    # Week 1 has no prior and is neither confirmed nor impugned.
    df["context_ok"] = (deviation <= PLAYS_BAND) | df["team_plays_avg"].isna()
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
        # Tiers only where the thresholds were actually tuned. See
        # TIERED_METRICS for why this is not every metric.
        if m in TIERED_METRICS:
            df[f"{m}_tier"] = [
                _tier(d, p) for d, p in zip(df[f"{m}_delta"], prior)
            ]

    # Raw snaps alongside share: a flat 75% share can hide 15 extra snaps.
    df["offense_snaps_prior"] = grp["offense_snaps"].shift(1)
    df["offense_snaps_delta"] = df["offense_snaps"] - df["offense_snaps_prior"]

    df = add_baseline_residual(df)
    df["corroborated"] = corroborate(df)
    return df


def add_baseline_residual(df: pd.DataFrame) -> pd.DataFrame:
    """Opportunity share above what this position's snap count predicts.

    The baseline is a line, not a constant. Measuring a player against it
    separates "he was on the field more" from "the offense gave him more,"
    which for a blocking position are very different events.
    """
    out = df.copy()
    inter = out["position"].map(lambda p: POSITION_PROFILES.get(p, (np.nan,) * 2)[0])
    slope = out["position"].map(lambda p: POSITION_PROFILES.get(p, (np.nan,) * 2)[1])

    out["opp_expected"] = inter + slope * out["offense_pct"]
    out["opp_resid"] = out["opp_share"] - out["opp_expected"]

    grp = out.sort_values(["pfr_player_id", "week"]).groupby("pfr_player_id", sort=False)
    prior = grp["opp_resid"].shift(1).reindex(out.index)
    out["opp_resid_prior"] = prior
    out["opp_resid_delta"] = out["opp_resid"] - prior
    return out


def corroborate(df: pd.DataFrame) -> pd.Series:
    """Did the snap move come with the ball?

    One rule, parameterised by the position's own snap-to-opportunity fit.
    Tight fit (RB, r=0.875) confirms on raw opportunity share, because the
    residual there is mostly noise. Loose fit (WR 0.724, TE 0.680) confirms
    on the residual, because that is where a route is distinguished from a
    block. Measured on the holdout: RB +0.27, WR +0.38, TE +0.52 lift gap,
    against +0.04 for the receiving-only rule this replaces.
    """
    up = df["offense_pct_delta"] > 0
    dn = df["offense_pct_delta"] < 0

    use_resid = df["position"].map(
        lambda p: _profile_r(p) < RESIDUAL_ABOVE_R if p in POSITION_PROFILES else False
    )
    bar = df["position"].map(CONFIRM_OPP_PP)

    moved = pd.Series(np.nan, index=df.index, dtype=float)
    moved = moved.mask(use_resid, df["opp_resid_delta"])
    moved = moved.mask(~use_resid, df["opp_share_delta"])
    threshold = pd.Series(
        np.where(use_resid, CONFIRM_RESID_PP, bar), index=df.index, dtype=float
    )

    return ((up & (moved >= threshold)) | (dn & (moved <= -threshold))).fillna(False)


# r of each profile fit, recorded alongside the coefficients it came from.
_PROFILE_R = {"RB": 0.875, "WR": 0.724, "TE": 0.680}


def _profile_r(pos: str) -> float:
    return _PROFILE_R.get(pos, 0.0)


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


def for_display(out: pd.DataFrame, metric: str = "offense_pct") -> pd.DataFrame:
    """Format a report for a human.

    Every number in a report is a share, so every number is a percentage.
    Printing 0.158 when the fact is "fifteen points of his team's touches"
    makes the reader do the conversion, and they will do it wrong for the
    residual, which is the one column whose units are not obvious.
    """
    df = out.copy()
    pct = lambda s: (s * 100).round(0).astype("Int64")
    pp = lambda s: (s * 100).round(1)

    show = pd.DataFrame(index=df.index)
    show["player"] = df["player"]
    show["pos"] = df["position"]
    show["team"] = df["team"]
    if f"{metric}_prior" in df and metric in df:
        show["snap%"] = (
            pct(df[f"{metric}_prior"]).astype(str) + " → " + pct(df[metric]).astype(str)
        )
    if "opp_share_delta" in df:
        show["opp Δ"] = pp(df["opp_share_delta"]).map(lambda v: f"{v:+.1f}pp")
    if "opp_resid_delta" in df:
        show["vs base"] = pp(df["opp_resid_delta"]).map(lambda v: f"{v:+.1f}pp")
    for col, name in (
        ("confirmed", "held"),
        ("corroborated", "ball"),
        ("injury_tag", "why"),
    ):
        if col in df:
            show[name] = (
                df[col].map({True: "yes", False: "—"}) if df[col].dtype == bool
                else df[col]
            )
    return show


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
        "opp_share_delta",
        "opp_resid_delta",
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
