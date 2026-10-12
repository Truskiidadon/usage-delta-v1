"""Command line entry point.

    python -m usage_delta.cli --week 5
    python -m usage_delta.cli --week 5 --metric target_share --confirmed-only
"""

import argparse

import pandas as pd

from .diff import compute_deltas, confirmed_trend, report
from .fetch import build_usage
from .injuries import load_injuries, tag


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
        "--corroborated-only",
        action="store_true",
        help="require target share to move with snap share (highest precision)",
    )
    p.add_argument(
        "--all-tags",
        action="store_true",
        help="include injury-explained deltas (default: unexplained only)",
    )
    p.add_argument(
        "--no-lookahead",
        action="store_true",
        help="ignore next week's injury report (simulates Tuesday knowledge)",
    )
    p.add_argument(
        "--min-vacancy-weeks",
        type=int,
        default=2,
        help=(
            "a teammate-driven rise counts as actionable once the vacancy "
            "has run this many weeks; below it, treated as a rental (default 2)"
        ),
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="re-download instead of using the local cache",
    )
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", None)

    usage = build_usage(args.season, refresh=args.refresh)
    deltas = confirmed_trend(compute_deltas(usage), metric=args.metric)
    deltas = tag(
        deltas,
        usage,
        load_injuries(args.season, refresh=args.refresh),
        lookahead=not args.no_lookahead,
        min_vacancy_weeks=args.min_vacancy_weeks,
    )

    out = report(
        deltas,
        week=args.week,
        metric=args.metric,
        positions=tuple(args.positions.split(",")),
        min_tier=args.min_tier,
        corroborated_only=args.corroborated_only,
    )
    total = len(out)

    if args.confirmed_only:
        out = out[out["confirmed"]]
    if not args.all_tags:
        out = out[~out["priced"]]

    if out.empty:
        print(f"No {args.metric} moves flagged in week {args.week}.")
        return

    kept = "all" if args.all_tags else "unexplained"
    print(f"\n{args.metric} — week {args.week} ({len(out)} of {total} flagged, {kept})\n")
    print(out.head(args.limit).to_string(index=False))

    if not args.all_tags:
        print(
            "\nShowing unexplained deltas only. Injury-driven moves are "
            "filtered out -- they are priced within hours. Use --all-tags "
            "to see them with their reason."
        )
    print(
        "A player hurt mid-game is absent from that week's pre-game report, "
        "so a large unexplained DECLINE in the latest week may still be an "
        "injury. Check the news before acting."
    )


if __name__ == "__main__":
    main()
