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

## stress stability

`stress_build.py` joins opponent defensive EPA per play onto the player-week
panel and buckets each game as tough (top 10), soft (bottom 10) or middle.
`stress_test.py` asks whether a player's tough-minus-soft share gap in the
first half of a season persists into the second half -- that is, whether
stability under pressure is a trait at all.

Result: split-half r = 0.03 at a two-game-per-bucket minimum (n=542), against
a pre-registered bar of 0.15. The control is the damning part: plain share
persists across halves at r = 0.92. The level of a player's role is one of
the most stable things in football; his gap against better defenses is noise.

H1 failed, so the predictive test H2 was never run. That was the condition.

## baseline profiles

`baseline_profiles.py` fits the per-position conversion of snap share into
opportunity share on 2013-2019, then tests corroborating against the residual
rather than against a flat threshold. This one worked -- see "v2: baseline
profiles" in the top-level README. Kept here because the fit and the rejected
parameterizations are reproducible from it.
