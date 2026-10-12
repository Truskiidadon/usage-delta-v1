"""Command line entry point.

    python -m usage_delta.cli --week 5
    python -m usage_delta.cli --week 5 --metric target_share --confirmed-only
"""

import argparse

import pandas as pd

from .diff import compute_deltas, confirmed_trend, report
from .fetch import build_usage


def main() -> None:
    p = argparse.ArgumentParser(description="Flag week-over-week NFL usage changes.")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--week", type=int, required=True, help="week to report on")
    p.add_argument(
        "--metric",
        default="offense_pct",
        choices=["offense_pct", "target_share", "air_yards_share"],
    )
    p.add_argument(
        "--positions",
        default="WR,RB,TE",
        help="comma separated, e.g. RB or WR,TE",
    )
    p.add_argument(
        "--min-tier",
        default="alert",
        choices=["alert", "actionable"],
    )
    p.add_argument(
        "--confirmed-only",
        action="store_true",
        help="only moves that held for two consecutive appearances",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="re-download instead of using the local cache",
    )
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", None)

    usage = build_usage(args.season, refresh=args.refresh)
    deltas = confirmed_trend(compute_deltas(usage), metric=args.metric)

    out = report(
        deltas,
        week=args.week,
        metric=args.metric,
        positions=tuple(args.positions.split(",")),
        min_tier=args.min_tier,
    )

    if args.confirmed_only:
        out = out[out["confirmed"]]

    if out.empty:
        print(f"No {args.metric} moves flagged in week {args.week}.")
        return

    print(f"\n{args.metric} — week {args.week} ({len(out)} flagged)\n")
    print(out.head(args.limit).to_string(index=False))

    # Until the injury join lands, most of the largest moves are players
    # returning from or exiting with injury -- already priced by the market.
    print(
        "\nNote: no injury join yet. Large moves are often injury-driven "
        "and already priced. See README."
    )


if __name__ == "__main__":
    main()
