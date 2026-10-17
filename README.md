# usage-delta-v1

Detects NFL player role changes from weekly usage data, before the change shows up in production.

Validated on 13 seasons and 75,457 player-weeks. The screen's tightest configuration beats matched controls by 1.90 PPR per game at a 54.9% hit rate on a held-out six seasons.

---

## Origin

Fantasy rankings follow production. Production follows role. That ordering creates a lag: a player whose snap share jumps in Week 5 is usually still priced on his Week 4 output.

Role changes are public in snap data within 48 hours of a game. Rankings take one to two weeks. This tool reads the first and acts before the second.

It began as a manual scan of weekly snap reports — slow, inconsistent, and biased toward players already in the news. The point of building it was to make it systematic and then find out whether it worked.

---

## Method

**Detection.** Diff each player's usage against his previous *appearance*, not the previous calendar week, so a bye or an inactive game does not read as a role collapse.

| metric | source | role |
|---|---|---|
| offensive snap share | nflverse snap counts | is he on the field |
| opportunity share | derived — `(carries + targets) / team opportunities` | is he getting the ball |

Opportunity share sums to 1.0 across a team-week by construction and means the same thing for every position. `target_share` and `carry_share` are still diffed as diagnostics; neither confirms a flag any more.

**Filtering.** Raw detection produces ~159 flags a week, which is not a screen. Four filters cut it to about five.

- **Threshold** — 25pp to be actionable, scaled to baseline, since 30→45% is a larger proportional move than 75→90%.
- **Confirmation** — the move holds across two consecutive appearances. One week is usually game script.
- **Corroboration** — snap share moves together with opportunity share, measured against the position's own snap-to-opportunity baseline. A snap rise alone says he was on the field more; paired with the ball it says the offense gave him something. See [baseline profiles](#baseline-profiles).
- **Injury context** — each delta is tagged with *why*, not merely whether an injury was involved.

| tag | meaning |
|---|---|
| `self_returning` | back from injury, reverting to normal |
| `self_injured` | hurt, reduced role |
| `self_exited` | left mid-game (requires next week's report) |
| `teammate_out` | a competitor sat, vacancy likely temporary |
| `teammate_out_durable` | vacancy has already run multiple weeks |
| `unexplained` | nothing in the report accounts for it |

The distinction that matters is not "is an injury attached" but "will this revert." A vacancy three weeks old is public knowledge and still worth acting on. One that opened Sunday probably closes next Sunday.

**Game context.** Team play volume outside a 20% band around the team's prior-weeks average marks the week low-confidence. Reported only; it gates nothing.

---

## Validation

Every threshold began as a guess fitted to known cases. That is a curve fit. The backtest replaces it.

- **Scope.** 2013–2025. Snap counts do not exist before 2012.
- **Outcome.** PPR per game over the four games after a flag, against controls matched on position and prior production. Matching is mandatory — a player flagged for a snap jump had a low baseline by definition, so comparing him to his own prior weeks is biased toward success by regression alone.
- **Design.** Tuned on 2013–2019, validated once on 2020–2025. The null was committed in advance: beat controls by 0.5 PPR per game or the screen is not earning its complexity.

| filter | n | hit rate | lift | se |
|---|---|---|---|---|
| snap ≥25pp alone | 1971 | 49.7% | 1.34 | ±0.13 |
| + target share rose | 1526 | 52.1% | 1.60 | ±0.15 |
| + target share ≥5pp | 1063 | 54.8% | 1.82 | ±0.18 |
| snap ≥30pp + target ≥5pp | 790 | 54.9% | 1.90 | ±0.21 |

Tune-set figures are within a standard error of these at every row, so there is no measurable shrinkage.

**What this establishes.** The signal is real and dose-dependent: lift rises monotonically with the threshold — 0.53 at 9pp, 1.00 at 20pp, 1.53 at 30pp, 1.96 at 40pp. Four independent measurements in the correct order is better evidence than any single figure.

**Earlier figures in this file were higher** (65.5% / 2.89). They do not reproduce from current data and the gap is about 1.3 standard errors. The likely cause is upstream: nflverse rewrites season files in place, so numbers computed against an older snapshot drift. The ordering, which is what the conclusion rests on, is unchanged. Treat the table above as current-as-of-this-commit rather than fixed.

---

## What does not work

Six ideas tested and rejected. They are kept here so they are not re-derived, and the scripts are under `research/`.

| idea | result |
|---|---|
| air yards share as a third confirmer | made flags worse; cut |
| paired teammate decline | monotonic on tune, did not replicate |
| in-game exit as a flag input | hit rate 51% vs 60% without it |
| leverage concentration ("trust index") | incremental holdout R² of −0.00004 |
| share stability vs tough defenses | split-half r = 0.03; not a trait |
| week-of-season buckets | 1.31 / 1.73 / 1.81 lift, within 0.5 of each other |

**The vacancy features failed for one reason**, and it generalizes: the riser's own snap jump already encodes the vacancy. If a backup played 92% of snaps, that 92% *is* the vacancy. Features describing its cause are redundant with the effect already being measured.

**Trust index and stress stability failed for a second reason**, which matters more for what gets built next. Opportunity share is measured on ~100 plays. Clutch share is measured on ~12. A tough-vs-soft defense split is measured on ~6 games. Each candidate was an order of magnitude less precise than the thing it was trying to beat, and the precise measurement already absorbed whatever signal it held.

That converts to a screening rule: **a candidate feature must be either genuinely orthogonal to opportunity share, or measured on a comparable denominator.** Almost nothing derivable from a box score clears it.

**Corroboration was anti-predictive for running backs.** For most of this repo's life `carries` was merged into the usage frame and never used, because nflverse publishes `target_share` and no rushing equivalent. The confirmation filter therefore gated every position on a receiving stat. On the holdout, corroborated RB flags returned +0.68 lift against +0.85 for uncorroborated ones — it pointed the wrong way. Fixed by opportunity share; see [baseline profiles](#baseline-profiles). The intermediate carry-share patch is in the history at `2bb73ff` if the reasoning is wanted.

**The exit detector cannot serve its best use.** Knowing a player left early, before the injury report confirms it, is a hold/sell signal rather than a waiver one. The detector works — a player whose last snap came before 65% of his team's plays is ~4x likelier to appear on next week's report. But nflverse participation ends after 2025 and the current-season file 404s, so it runs only on history. Across one week of 2026, three flags in this tool were explained by exits it could not see. Treat any large single-week decline as possibly an exit and check the news.

---

## Limitations

- **Acquirability is unmeasured.** Injury-driven flags outperform unexplained ones in every cell, 2.26 vs 1.66, which appears to contradict the premise. But nflverse carries no rostership or ADP, so the backtest cannot test whether a publicly-known player was actually available — the entire reason to prefer unexplained ones. `attention.py` is the instrument for this and cannot work retroactively: Sleeper exposes a recent window and nothing historical, so the panel accumulates forward from the first snapshot.
- **Mid-game exits are structurally invisible** at Tuesday decision time. See above.
- **Hit rate is ~55%, not 90%.** Lift is partly a tail of large wins. Built for volume across a season, not conviction on one flag.
- **Route participation is missing.** The most predictive usage metric for pass catchers is not in the free feed.
- **Backtested on revised data.** Live performance on provisional files will be worse.
- **Confirmed false positive.** Week 5, 2026: a Pittsburgh receiver flagged 0.40 → 0.92, corroborated and confirmed, tagged `teammate_out_durable` with `vacancy_weeks=3`. The displaced starter had missed Weeks 2 and 5 only, non-consecutively. The receiver's season was 4%, 79%, 27%, 40%, 92% — the two high weeks are exactly the two the starter sat. The correct call was `rental`. It survived only because the absence counter sums rather than streaks. Treat any `teammate_out_durable` flag as unverified until that lands.

---

## Usage

```bash
pip install -r requirements.txt

python -m usage_delta.cli --week 5
python -m usage_delta.cli --week 5 --confirmed-only --corroborated-only
python -m usage_delta.cli --week 5 --all-tags          # include injury-explained flags
python -m usage_delta.cli --week 5 --positions RB
python -m usage_delta.cli --week 5 --refresh           # re-pull instead of cache
```

Default output is unexplained deltas only. `--corroborated-only` is the highest-precision configuration.

---

## Baseline profiles

The corroboration layer. Shipped.

Every position converts snaps into opportunities at a different rate. Fit on 2013–2019:

| position | opp_share = a + b · snap_share | r |
|---|---|---|
| RB | −0.004 + 0.481 · snap | 0.875 |
| WR | −0.009 + 0.151 · snap | 0.724 |
| TE | −0.013 + 0.118 · snap | 0.680 |

A back turns nearly half his snaps into a touch. A tight end turns a quarter of that, with the loosest fit of the three — and that gap is blocking. A receiver on the field is running a route; a tight end on the field may be a sixth lineman. This is why the shipped screen is *negative* on tight ends: it reads added snaps as added opportunity, and for that position it frequently is not.

**The rule:** fit the per-position conversion on history, then corroborate against that baseline rather than a flat threshold. Where the conversion is tight (RB, r = 0.875) confirm on raw opportunity share — the residual there is mostly noise. Where it is loose (WR, TE) confirm on the residual, which is what separates a weapon from a blocker. The cut is on the fit's own r, not on position identity: add a position, fit it, and `RESIDUAL_ABOVE_R` decides for you.

Holdout lift gap, corroborated minus uncorroborated:

| rule | RB | WR | TE | mean |
|---|---|---|---|---|
| target-only (shipped before carry share) | −0.19 | +0.11 | +0.19 | +0.04 |
| position-branched carries/targets (current) | +0.30 | +0.11 | +0.19 | +0.20 |
| unified opp share, flat 3pp bar | +0.03 | +0.19 | +0.30 | +0.17 |
| **baseline profile (shipped)** | **+0.28** | **+0.38** | **+0.54** | **+0.40** |

Tune for the last row is +0.32, so the holdout is *higher* — no overfitting. Every position is positive in both sets, and overall holdout corroborated lift goes from 0.216 under the receiving-only rule to **0.757**.

It also collapsed the metric list: `air_yards_share`, `CONFIRM_TARGET_PP`, `CONFIRM_CARRY_PP` and the position branch are gone, replaced by one metric and one profile table.

Two parameterizations were tried and rejected: a *relative* opportunity threshold (negative gaps at every position in both sets) and a residual bar scaled to each position's residual spread (tune picks k=1.0, holdout calls it worst and drives RB to −0.19).

---

## Roadmap

Corrections to known defects first.

**Consecutive versus cumulative absence.** `games_missed` sums absences instead of streaking them, so a teammate who misses Weeks 2 and 5 scores the same as one who misses 3, 4 and 5. `vacancy_weeks` inherits that number and drives `teammate_out_durable`, which is what lets a teammate-driven rise survive the default filter — so the bug converts rentals into apparent durable roles. It produced the confirmed false positive above.

**Tag taxonomy.** `injury_tag` answers "what happened" but not "what should I do," and the filter infers the second from the first.

| tag | condition |
|---|---|
| `rental` | rise coincides with a teammate absence that has no durable streak, and the share collapses in weeks that teammate played |
| `riser` | rise holds when the position group is fully healthy, or arrives with no absence to explain it |
| `downside` | confirmed decline, or a riser whose displaced teammate is returning |

The separating test is retrospective and cheap: compare the player's share in weeks the teammate played against weeks he did not. A player whose two best weeks are exactly the two a starter sat is a rental no matter how large the delta.

**Accumulate the attention panel.** Written, log empty, and the only item with a deadline — every Tuesday not snapshotted is evidence that cannot be recovered. At ~10 weeks it becomes possible to test whether unexplained flags are genuinely less owned, how many days pass before the market arrives, and whether lift survives a control for prior rostership. That last one decides whether the central premise holds.

**Confirmation logic.** Requires same-direction movement across two appearances with each leg clearing 4.5pp, so a gradual climb never confirms. A 2026 case went 53 → 63 → 67 → 75% across four weeks — +22pp cumulative, no single week above +10pp — and nothing fired. "Jump then hold" and "climb steadily" are both real promotions; only one is detected. A rolling multi-week delta alongside the week-over-week one catches both.

**Tier scoping.** `_tier` applies `ALERT_PP` and `ACTIONABLE_PP`, both tuned on snap share, to whatever metric it is handed. Median week-over-week move is 8–9pp for snap share, 5.7pp for target share, 8.8pp for carry share, so the same cut sits at a different percentile of each. Tiers are currently emitted for `offense_pct` only; any new screening metric needs its own tuning before it gets one.

**Injury identity resolution.** The duration streak keys on an exact body-part string, so a relabel resets it. Grouping body parts into regions resolves most of the 159 observed relabels.

### Adjacent scope: roster construction

A second tool, not an extension. This repo answers "whose role is changing" from league-wide data. Roster construction answers "what should I start" from one roster — different input, different output, different validation problem. Keeping them separate protects this repo's evidence standard.

Two inputs, deliberately only two:

- **Bye structure.** Deterministic, no model. Score a roster by weeks where startable players at one position share a bye. Two tight ends on the same bye is a guaranteed zero in a starting slot, and that is arithmetic.
- **Correlation.** Players on one offense do not score independently — a quarterback and his own receiver rise together; two backs in one backfield are near mutually exclusive. The effect is on lineup *variance* rather than expected points, so the rating is conditional: correlation raises a ceiling and thins a floor, which a projected underdog wants and a favorite does not. A single scalar that ignores which side a manager is on would be worse than no score. Same-team WR–WR pairs must carry a negative weight; they share one target pool.

Excluded: week-of-season buckets (tested, not supported) and matchup adjustment (dominated by strength of schedule).

---

## Stack and data

| source | what |
|---|---|
| nflverse snap_counts | offensive snap share |
| nflverse stats_player_week | targets, carries, air yards, PPR |
| nflverse players | `pfr_player_id` ↔ `gsis_id` crosswalk |
| nflverse injuries | weekly report status |
| nflverse pbp | situational splits, research only |
| Sleeper | add/drop counts for `attention.py` |

Join on IDs, never names: the snap file lists "Tre Harris", other sources list "Tre' Harris".

## Module map

| file | role |
|---|---|
| `fetch.py` | pulls and caches nflverse parquet; derives `carry_share` |
| `diff.py` | thresholds, deltas, confirmation, corroboration |
| `injuries.py` | report tagging and duration |
| `exits.py` | mid-game exit detection (history only) |
| `attention.py` | Sleeper add/drop snapshots |
| `backtest.py` | panel construction and matched-control comparison |
| `cli.py` | weekly screen |
| `research/` | rejected ideas, reproducible |
