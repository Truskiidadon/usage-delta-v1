"""Injury join — separating priced deltas from unpriced ones.

Roughly half of all usage deltas are injury-driven. Those are priced by the
market within hours of the injury report, so they are not an edge. The
valuable alerts are the deltas with no injury attached: a coaching decision
nobody noticed.

This module tags each delta with *why* it is explained, not merely whether,
because the reasons have different shelf lives:

  self_injured      player is on this week's report      -> may persist
  self_returning    player was on last week's, not this  -> reverting to normal
  teammate_out      a real competitor sat this week      -> EXPIRES on his return
  teammate_back     a competitor returned this week      -> the drop is permanent
  unexplained       nothing in the report accounts for it -> the edge

The teammate tags matter most for action. A receiver whose share jumped
because the starter sat is a one-week rental. A receiver whose share jumped
with the depth chart intact has actually been promoted.

KNOWN LIMITATION
----------------
The injury report is published *before* kickoff, so a player who exits
mid-game is absent from that week's report entirely. In 2026 Week 5 both
KC Concepcion (concussion) and Tre Harris (hamstring) posted large snap
drops with no report row, because both were hurt during the game.

Such a player appears on the FOLLOWING week's report. Pass
`lookahead=True` to use it -- correct for backtesting, but that report is
not published until midweek, so it is unavailable at Tuesday decision time.
Without lookahead, treat a large unexplained *decline* as suspect and check
the news before acting.
"""

import numpy as np
import pandas as pd

from .fetch import _load, NFLVERSE

INJURIES = f"{NFLVERSE}/injuries/injuries_{{season}}.parquet"

# Statuses that meaningfully reduce or eliminate a player's workload.
SIDELINED = {"Out", "Doubtful"}
LIMITED = {"Questionable"}
NON_INJURY = NON_INJURY = {"Not injury related - resting player"}

# A teammate only explains a delta if he was a real competitor for the
# snaps, not a fourth-stringer who happened to be on the report.
TEAMMATE_MIN_SHARE = 0.30


def load_injuries(season: int, refresh: bool = False) -> pd.DataFrame:
    """Weekly injury reports, keyed on gsis_id (same ID the usage table carries)."""
    df = _load(
        INJURIES.format(season=season),
        f"injuries_{season}.parquet",
        refresh,
    )
    df = df[df["season_type"] == "REG"].copy()

    df["injury_detail"] = df["report_primary_injury"].fillna(df["practice_primary_injury"])
    df["is_injury"] = df["injury_detail"].notna() & ~df["injury_detail"].isin(NON_INJURY)
    df["dnp"] = (df["practice_status"] == "Did Not Participate In Practice") & df["is_injury"]
    # A DNP with no game-status designation still signals a reduced week.
    df["dnp"] = df["practice_status"] == "Did Not Participate In Practice"

    return df[
        [
            "season",
            "week",
            "team",
            "gsis_id",
            "position",
            "full_name",
            "report_primary_injury",
            "practice_primary_injury",
            "injury_detail",
            "is_injury",
            "report_status",
            "practice_status",
            "sidelined",
            "limited",
            "dnp",
        ]
    ]


def _gap_injury(deltas: pd.DataFrame, injuries: pd.DataFrame) -> pd.Series:
    """Was the player sidelined at any point since his last appearance?

    This is the piece that naive joins miss. A player's snap share is
    compared against his previous *appearance*, so the injury that explains
    a jump usually sits in the weeks BETWEEN the two rows, not on either of
    them. Justin Jefferson played week 3 at 12%, was Out in week 4, and
    returned week 5 at 89%. Looking only at weeks 3 and 5 makes that rise
    look like a promotion.
    """
    sidelined = injuries[injuries["sidelined"]][["season", "gsis_id", "week"]]

    keys = deltas[["season", "gsis_id", "prev_week", "week"]].reset_index()
    merged = keys.merge(sidelined, on=["season", "gsis_id"], how="left",
                        suffixes=("", "_inj"))

    # Strictly between the two appearances, inclusive of the missed weeks.
    in_gap = (
        merged["week_inj"].notna()
        & (merged["week_inj"] > merged["prev_week"])
        & (merged["week_inj"] < merged["week"])
    )
    hit = merged[in_gap].groupby("index").size()

    out = pd.Series(False, index=deltas.index)
    out.loc[out.index.intersection(hit.index)] = True
    return out


def _self_status(deltas: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """Attach the player's own injury status for this week and his prior one."""
    inj = injuries[["season", "week", "gsis_id", "report_status", "sidelined", "limited", "dnp",
                    "report_primary_injury"]]

    df = deltas.merge(
        inj.rename(
            columns={
                "report_status": "inj_status",
                "sidelined": "inj_sidelined",
                "limited": "inj_limited",
                "dnp": "inj_dnp",
                "report_primary_injury": "inj_detail",
            }
        ),
        on=["season", "week", "gsis_id"],
        how="left",
    )

    # Status in the week the player last appeared, not week-1, so a bye or
    # a healthy scratch does not silently drop the comparison.
    prior = inj.rename(
        columns={
            "week": "prev_week",
            "report_status": "prev_inj_status",
            "sidelined": "prev_inj_sidelined",
            "limited": "prev_inj_limited",
            "dnp": "prev_inj_dnp",
        }
    ).drop(columns=["report_primary_injury"])

    df = df.merge(prior, on=["season", "prev_week", "gsis_id"], how="left")

    for c in ("inj_sidelined", "inj_limited", "inj_dnp",
              "prev_inj_sidelined", "prev_inj_limited", "prev_inj_dnp"):
        df[c] = df[c].fillna(False).astype(bool)

    df["missed_games"] = _gap_injury(df, injuries)
    return df


def injury_duration(injuries: pd.DataFrame) -> pd.DataFrame:
    """How long has each injury been going on, as of each week?

    Two signals, both cumulative and backward-looking (nothing here peeks
    at the future):

      report_weeks  how many weeks this player has appeared on the report
                    with this same primary injury
      games_missed  how many weeks he has been ruled Out so far

    A hamstring appearing for the first time could clear in days. A foot
    that has been on the report three separate weeks is chronic, and the
    vacancy behind it is worth acting on.
    """
    df = injuries.sort_values(["season", "gsis_id", "week"]).copy()

    # Same-injury streak, keyed on the reported body part.
    df["report_weeks"] = 0
    real = df["is_injury"]
    df.loc[real, "report_weeks"] = (
        df[real].groupby(["season", "gsis_id", "injury_detail"]).cumcount() + 1
    )
    df["games_missed"] = (
        df.groupby(["season", "gsis_id"])["sidelined"].cumsum().astype(int)
    )

    return df)


def _teammate_availability(
    usage: pd.DataFrame, injuries: pd.DataFrame
) -> pd.DataFrame:
    """Same-position teammates sidelined, per team per week, with duration.

    "Meaningful" means the teammate had held at least TEAMMATE_MIN_SHARE of
    snaps in a prior week. A fourth-string receiver being Out explains
    nothing about anyone's workload.

    vacancy_weeks is the longest-running injury among those teammates. It is
    what separates a one-week rental from a role you can actually trade for.
    """
    peak = (
        usage.groupby(["season", "gsis_id"], as_index=False)["offense_pct"]
        .max()
        .rename(columns={"offense_pct": "peak_share"})
    )

    inj = injury_duration(injuries)
    inj = inj[inj["sidelined"]].merge(peak, on=["season", "gsis_id"], how="left")
    inj = inj[inj["peak_share"] >= TEAMMATE_MIN_SHARE]

    inj["vacancy_weeks"] = inj[["report_weeks", "games_missed"]].max(axis=1)

    return inj.groupby(["season", "week", "team", "position"], as_index=False).agg(
        sidelined_at_pos=("gsis_id", "nunique"),
        vacancy_weeks=("vacancy_weeks", "max"),
    )


def _hurt_next_week(deltas: pd.DataFrame, injuries: pd.DataFrame) -> pd.Series:
    """Did a new injury appear on the FOLLOWING week's report?

    This is how a mid-game exit becomes visible. A player hurt during week W
    is absent from week W's pre-game report but shows up on week W+1's.
    Ja'Marr Chase took a concussion in week 4, played 20% of snaps, and first
    appears on the week 5 report.

    Only usable in hindsight: week W+1's report is not published until
    midweek, so this cannot inform a Tuesday waiver decision about week W.
    It is correct for backtesting and for re-reading last week.
    """
    inj = injuries[injuries["sidelined"] | injuries["limited"] | injuries["dnp"]]
    inj = inj[["season", "gsis_id", "week"]].rename(columns={"week": "inj_week"})

    keys = deltas[["season", "gsis_id", "week"]].reset_index()
    merged = keys.merge(inj, on=["season", "gsis_id"], how="left")

    hit = merged[merged["inj_week"] == merged["week"] + 1].groupby("index").size()

    out = pd.Series(False, index=deltas.index)
    out.loc[out.index.intersection(hit.index)] = True
    return out


def tag(
    deltas: pd.DataFrame,
    usage: pd.DataFrame,
    injuries: pd.DataFrame,
    lookahead: bool = True,
    min_vacancy_weeks: int = 2,
) -> pd.DataFrame:
    """Add `injury_tag` and `priced` to a delta table.

    lookahead uses the following week's injury report to catch mid-game
    exits. Leave it on for backtests and for reviewing a past week; it has
    no effect on the most recent week, where no later report exists yet.

    min_vacancy_weeks splits teammate-driven rises by how long the vacancy
    has already run. Below the threshold it is a rental and gets filtered
    out as priced; at or above it the role is durable enough to act on and
    stays in the list as `teammate_out_durable`.

    This matters more than it sounds. Germie Bernard's 40% -> 92% jump in
    2026 week 5 is caused by Michael Pittman's absence, so a naive join
    discards it -- but Pittman's foot had been on the report three separate
    weeks and he had already missed two games. That is not a rental.
    """
    df = _self_status(deltas, injuries)

    if lookahead:
        df["hurt_next_week"] = _hurt_next_week(df, injuries)

    avail = _teammate_availability(usage, injuries)

    df = df.merge(
        avail.rename(columns={"sidelined_at_pos": "pos_out_now"}),
        on=["season", "week", "team", "position"],
        how="left",
    )
    df = df.merge(
        avail.rename(
            columns={
                "week": "prev_week",
                "sidelined_at_pos": "pos_out_prev",
                "vacancy_weeks": "_vw_prev",
            }
        ),
        on=["season", "prev_week", "team", "position"],
        how="left",
    )
    df["pos_out_now"] = df["pos_out_now"].fillna(0)
    df["pos_out_prev"] = df["pos_out_prev"].fillna(0)
    df["vacancy_weeks"] = df["vacancy_weeks"].fillna(0).astype(int)
    df = df.drop(columns=["_vw_prev"], errors="ignore")

    # The player himself is counted above if he was out; remove him so a
    # player's own absence doesn't read as a teammate vacancy.
    df["pos_out_now"] -= df["inj_sidelined"].astype(int)
    df["pos_out_prev"] -= df["prev_inj_sidelined"].astype(int)

    vacancy_opened = df["pos_out_now"] > df["pos_out_prev"]
    competitor_back = df["pos_out_now"] < df["pos_out_prev"]

    rose = df["offense_pct_delta"] > 0
    fell = df["offense_pct_delta"] < 0

    self_hurt_now = df["inj_sidelined"] | df["inj_limited"] | df["inj_dnp"]
    self_hurt_prev = df["prev_inj_sidelined"] | df["prev_inj_limited"] | df["prev_inj_dnp"]

    # An injury never *causes* a player's snap share to rise. So any rise
    # attached to an injury marker -- his own, past or present, or games
    # missed in between -- is a return to normal, not a promotion. This
    # catches the player still carrying a Questionable tag in the week he
    # comes back, which is the usual shape of a recovery.
    returning = (df["missed_games"] | self_hurt_prev | self_hurt_now) & rose

    # Exited mid-game: no row on this week's report, but one appears next
    # week. Only available with lookahead.
    exited = df.get("hurt_next_week", pd.Series(False, index=df.index)) & fell

    durable = df["vacancy_weeks"] >= min_vacancy_weeks

    # Order matters: a return to health outranks a vacancy as the explanation
    # for a rise, and the player's own status outranks a teammate's.
    conditions = [
        returning,
        self_hurt_now & fell,
        exited,
        vacancy_opened & rose & durable,
        vacancy_opened & rose,
        competitor_back & fell,
        self_hurt_now,
    ]
    labels = [
        "self_returning",
        "self_injured",
        "self_exited",
        "teammate_out_durable",
        "teammate_out",
        "teammate_back",
        "self_injured",
    ]

    df["injury_tag"] = np.select(conditions, labels, default="unexplained")

    # "Priced" means the market already knows AND the situation reverts.
    # A durable vacancy is known but not reverting, so it stays actionable.
    df["priced"] = ~df["injury_tag"].isin(["unexplained", "teammate_out_durable"])

    return df
