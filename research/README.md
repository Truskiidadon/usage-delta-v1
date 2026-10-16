# research/

Scripts for tests that did not make it into the package. Kept so a negative
result is reproducible rather than re-derived.

## leverage concentration ("trust index")

`leverage_build.py` pulls nflverse play-by-play for 2016-2025 and reduces it to
a player-week opportunity panel: total opportunities, opportunities taken in
one-score fourth quarters, and PPR points, with the matching team denominators.

`leverage_test.py` builds an expanding-window trust index from that panel --
cumulative clutch share minus cumulative baseline share, with no lookahead --
and tests whether it improves next-week prediction over baseline share plus
trailing three-week scoring. Train 2016-2022, holdout 2023-2025.

Result: incremental holdout R^2 of -0.00004 against a pre-registered kill
criterion of +0.005. See "Leverage concentration does not predict" in the
top-level README. The metric is retained as a descriptive view only.

Run order:

    python research/leverage_build.py     # ~15s, writes panel.parquet
    python research/leverage_test.py
