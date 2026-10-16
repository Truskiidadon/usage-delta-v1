# usage-delta-v1

Detects NFL player role changes from weekly usage data, before the change shows up in production.

Validated on 13 seasons. Flagged players outproduce matched controls by 2.9 PPR points per game at a 65% hit rate.

---

## Origin

Fantasy football rankings follow production. Production follows role. That ordering creates a lag: a player whose snap share jumps in Week 5 is usually still priced on his Week 4 output.

Role changes are visible in public snap data within 48 hours of a game. Rankings take one to two weeks to catch up. This tool reads the first and acts before the second.

The project started as a manual process. Scanning weekly snap reports by hand surfaced several useful adds, but the scan was slow, inconsistent, and biased toward players already in the news. The goal here was to make it systematic and then find out whether it actually worked.

---

## Method

### Detection

Diff each player's usage against his previous appearance, not the previous calendar week. A bye or an inactive game would otherwise read as a role collapse.

Three metrics are diffed:

| metric | source |
|---|---|
| offensive snap share | nflverse snap counts |
| target share | nflverse weekly stats |
| air yards share | nflverse weekly stats |

### Filtering

Raw detection produces roughly 159 flags per week, which is not a screen. Four filters reduce that to about five.

**Threshold.** A move must clear 25 percentage points to be actionable. Scaled to baseline, since a move from 30% to 45% is a larger proportional change than 75% to 90%.

**Confirmation.** The move must hold across two consecutive appearances. One week of movement is usually game script.

**Corroboration.** Snap share and target share must move together. A snap rise alone says the player was on the field more. Paired with targets it says he was on the field more and getting the ball.

**Injury context.** Each delta is tagged with why it happened, not merely whether an injury was involved:

| tag | meaning |
|---|---|
| `self_returning` | player back from injury, reverting to normal |
| `self_injured` | player hurt, reduced role |
| `self_exited` | left mid-game (requires next week's report) |
| `teammate_out` | a competitor sat, vacancy likely temporary |
| `teammate_out_durable` | vacancy has already run multiple weeks |
| `unexplained` | nothing in the report accounts for it |

The distinction that matters is not "is an injury attached" but "will this revert." A vacancy that has run three weeks is public knowledge and still worth acting on. One that opened Sunday probably closes next Sunday.

### Game context

Snap share is unreliable in abnormal games. Team play volume outside a 20% band around the team's season average flags the week as low confidence and disqualifies it from satisfying the confirmation requirement.

---

## Validation

Every threshold started as a guess fitted to a handful of known cases. That is a curve fit, not evidence. The backtest replaces it.

**Scope.** 2013 to 2025, 75,457 player-weeks. Snap counts do not exist before 2012.

**Outcome.** PPR points per game over the four games following a flag, measured against controls matched on position and prior production. Matched controls are mandatory: a player flagged for a snap-share jump almost by definition had a low baseline, so comparing him to his own prior weeks is biased toward success by regression to the mean alone.

**Design.** Tuned on 2013 to 2019. Validated once on 2020 to 2025, not inspected during tuning. The null was committed in advance: if flagged players did not beat controls by at least 0.5 PPR per game, the screen was not earning its complexity.

### Results

| filter | holdout hit rate | holdout lift |
|---|---|---|
| snap ≥25pp alone | 53.9% | 1.66 |
| + target share rose | 58.5% | 2.13 |
| + target share ≥5pp | 63.2% | 2.37 |
| snap ≥30pp + target ≥5pp | **65.5%** | **2.89** |

Tune set reached 70.3% and 2.27. Shrinkage from tune to holdout is ordinary, not collapse. Excluding 2020 as a COVID control moves the result slightly upward, so pandemic conditions were not driving it.

### What the validation established

**The signal is real and dose-dependent.** Lift rises monotonically with the threshold: 0.53 at 9pp, 1.00 at 20pp, 1.53 at 30pp, 1.96 at 40pp. Four independent measurements landing in the correct order is stronger evidence than any single figure.

**Declines predict too.** Flagged drops underperform controls by 0.61, and injury-driven drops by 1.30. The tool is a sell signal as well as a buy signal.

**Original thresholds were far too loose.** The first version flagged 45% of all player-weeks. Actionable moved from 15pp to 25pp on this evidence.

**Flag timing does not matter.** Early-season, mid-season, and late-season flags perform within 0.5 of each other. The hypothesis that Week 3 and Week 15 flags differ in production terms was tested and not supported.

---

## What does not work

### Vacancy-cause features

Two separate attempts to detect *why* a role opened both failed, and they failed the same way.

**Paired teammate decline.** Share within a position group is near zero-sum, so a rise in one player should pair with a fall in another. Monotonic on the tune set, did not replicate on the holdout.

**In-game exit detection.** Play-by-play participation identifies players who left early. The detector itself works well: a player whose last snap came before 65% of his team's plays is roughly 4x likelier to appear on next week's injury report than baseline. But adding "a teammate exited" made flags *worse* in both sets, 51% versus 60%.

**The shared reason is the finding.** The riser's own snap jump already encodes the vacancy. If a backup played 92% of snaps, that 92% *is* the vacancy. Features describing its cause are redundant with the effect already being measured.

Both are retained in the codebase with results documented inline, so the idea is not re-derived and tune-set numbers are not mistaken for validation.

### The exit detector has a different use, which it cannot currently serve

Knowing when a player left a game early, before the injury report confirms it, is a hold, sell and lineup signal rather than a waiver one. That is the use the detector was kept for.

It cannot do it. nflverse's participation feed ends after 2025 and the current-season file returns 404, so `exits.py` works only on history. Mid-game exits in a live week are therefore invisible to this repo entirely, and the gap is not theoretical: across one week of 2026, three separate flags in this tool were explained by exits it could not see — a receiver's single target that was a finger injury, a back's truncated snap share that was a hip, and a decline tagged `unexplained` that was neither. Every one had to be supplied by a human who watched the game.

Until a live participation source exists, mid-game exits are a known blind spot filled manually or not at all. Treat any large single-week decline as possibly an exit rather than a role change, and check the news before acting on it.

### Leverage concentration does not predict

The idea: measure how much of a team's offense a player commands in one-score fourth quarters relative to his baseline share. A positive value means the offense goes *to* him when the game is live, which separates a player his coaches trust from one whose volume is an artifact of trailing. The descriptive output is legible and the extremes are interesting — a 2026 sample had one receiver at +18.9 and one back at −21.3 on 81 opportunities.

It has no predictive value. Pre-registered on ten seasons, 50,814 player-weeks, trained on 2016-2022 and evaluated on a 2023-2025 holdout, with a +0.005 incremental R² kill criterion stated before the run:

| model | holdout R² |
|---|---|
| baseline opportunity share + trailing 3-week scoring | 0.2299 |
| the same, plus leverage concentration | 0.2298 |

Incremental R² of −0.00004, a faintly negative fitted coefficient, and a correlation with next-week points of 0.033 against 0.364 for opportunity share and 0.461 for recent scoring. The quintile table is non-monotonic: lift appears in the third and fourth base-share bands and vanishes in the first, second and fifth, which is the shape of noise.

It is not a small-sample artifact. Raising the entry bar from 25 prior opportunities to 200, and requiring 20 prior clutch opportunities, leaves the incremental R² negative at every step but the last, where 315 rows produce +0.0047 — still under the kill line and on a sample thin enough to be chance.

The honest read is that opportunity share already contains it. A player the offense concentrates on late is a player with a high share, and the share is measured more precisely because its denominator is twenty times larger.

Retained as a descriptive view only. It is useful for arguing a trade, where the counterparty is pricing off box scores, and it must not be presented as a forecast.

---

## Limitations

**Acquirability is unmeasured.** Injury-driven flags outperform unexplained ones in every cell, 2.26 versus 1.66. That appears to contradict the tool's premise. But nflverse carries no rostership or ADP data, so the backtest cannot test whether a publicly-known player could actually have been acquired, which is the entire reason to prefer unexplained ones. The finding is real; the conclusion it appears to support is not yet earned.

`attention.py` is the instrument built to close this, and it cannot close it retroactively. Sleeper exposes add/drop counts for a recent window and nothing historical, so the panel starts from the first snapshot taken and accumulates forward. Until it has ten or so weeks of depth, the acquirability question stays open.

**Mid-game exits are structurally invisible.** The injury report is published before kickoff, so a player hurt during a game has no row that week. He appears on the following week's report, which the lookahead option uses, but that is unavailable at Tuesday decision time.

**Hit rate is 65%, not 90%.** Mean lift is driven partly by a tail of large wins. The tool is built for volume across a season, not conviction on any single flag.

**Route participation is missing.** The most predictive usage metric for pass catchers is not in the free feed.

**Backtested on revised data.** nflverse files are corrected over time. Live performance on provisional data will likely be worse than 65%.

**Confirmed false positive: durable vacancy.** Week 5, 2026. A Pittsburgh receiver was flagged at 0.40 to 0.92, corroborated and confirmed, tagged `teammate_out_durable` with `vacancy_weeks=3`. The displaced starter had in fact missed Weeks 2 and 5 only, non-consecutively. The receiver's snap share across the season was 4%, 79%, 27%, 40%, 92% — the two high weeks are precisely the two the starter sat, and he drew zero, one and two targets in the three weeks the starter played. The correct classification was a rental, which the default filter would have suppressed. The flag survived solely because the absence counter summed rather than streaked. Any `teammate_out_durable` flag should be treated as unverified until that fix lands.

---

## Usage

```bash
pip install -r requirements.txt

python -m usage_delta.cli --week 5
python -m usage_delta.cli --week 5 --confirmed-only --corroborated-only
python -m usage_delta.cli --week 5 --all-tags          # show injury-explained flags too
python -m usage_delta.cli --week 5 --metric target_share --positions RB
python -m usage_delta.cli --week 5 --refresh           # re-pull instead of cache
```

Default output shows unexplained deltas only. `--corroborated-only` applies the highest-precision configuration.

---

## Growth opportunities

Ordered by value. The first two are corrections to known defects and should land before any new feature.

**Consecutive versus cumulative absence.** `games_missed` sums absences instead of streaking them, so a teammate who misses Weeks 2 and 5 scores the same as one who misses Weeks 3, 4 and 5. Since `vacancy_weeks` drives the `teammate_out_durable` tag, and that tag is what lets a teammate-driven rise survive the default filter, the bug converts rentals into apparent durable roles. It produced a confirmed false positive in Week 5 of 2026 (see Limitations). Fix is to streak consecutive missed weeks rather than count them.

**Tag taxonomy.** The current `injury_tag` field answers "what happened" but not "what should I do," and the filter has to infer the second from the first. Three decision tags would replace that inference:

| tag | meaning | condition |
|---|---|---|
| `rental` | role reverts when the absent player returns | rise coincides with a teammate absence that has no durable streak, and the riser's share collapses in weeks that teammate played |
| `riser` | role is the player's own, not borrowed | rise holds in weeks when the position group is fully healthy, or arrives with no absence to explain it |
| `downside` | sell or bench signal | confirmed decline, or a riser whose displaced teammate is returning |

The separating test for `rental` versus `riser` is retrospective and cheap: compare the player's share in weeks the relevant teammate played against weeks he did not. A player whose two best weeks are exactly the two weeks a starter sat is a rental no matter how large the delta. This also subsumes the `teammate_out` / `teammate_out_durable` split, which is currently doing the job badly.

**Accumulate the attention panel.** `attention.py` is written but the log is empty, and it is the only work here with a deadline attached — every Tuesday not snapshotted is a week of evidence that cannot be recovered. Once roughly ten weeks exist, three things become testable for the first time: whether unexplained flags are genuinely less owned than injury-driven ones, how many days pass between a flag and the market arriving, and whether lift survives a control for how widely held the player already was. That last one decides whether the central premise of this repo is true.

**Route participation.** Requires a PFF source. The single most predictive missing input.

**Confirmation logic.** Requires same-direction movement across two appearances with each leg clearing 4.5pp, so a gradual climb never confirms. A 2026 case: a receiver went 53% to 63% to 67% to 75% across four weeks, a cumulative +22pp, with no single week above +10pp and one leg at +4pp. Nothing fired. "Jump then hold" and "climb steadily" are both common shapes of a real promotion and neither is currently detected. A rolling multi-week delta alongside the week-over-week one would catch both.

**Position-specific thresholds.** Running back and receiver role changes have different signatures and are currently pooled.

**Injury identity resolution.** The duration streak keys on an exact body-part string, so any relabel resets it. Grouping body parts into regions would resolve most of the 159 observed relabels without needing a pending state.

**Archetype decompiler.** The largest piece of new work here, and a different question from the one this repo currently answers. `diff.py` asks whether a role changed this week. A decompiler asks what *kind* of role it is, season to date: share of the team's red-zone and inside-five touches, share of third-down targets, average depth of target, catch rate, game-script distribution. Those features assign an archetype — bellcow, early-down, passing-down, goal-line, committee for backs; hub, alpha, field-stretcher, chain-mover, decoy, underneath for receivers.

Three design constraints, all learned the hard way elsewhere in this file:

- **Rules, not clustering.** Every threshold in this repo is an explicit constant with a backtested justification. A k-means cluster whose membership flips week to week cannot be defended in a commit message and would not survive the standard applied to `ACTIONABLE_PP`.
- **Cumulative, not week-over-week.** The median back has four red-zone carries in five weeks. A weekly share off that denominator is noise, and bolting it onto the existing `ALERT_PP` logic would fire constantly. This is a season-to-date profile.
- **Classify nothing below a floor.** Same discipline as `MIN_SNAPS`, one layer up: under roughly 30 touches or four appearances, output `unclassified`. A bellcow label off nine carries is worse than no label. A confidence tier — provisional below 50 opportunities, qualified above — is cheaper than a hard cutoff and more honest.

The predictive claim is that *archetype transitions* carry signal where the archetype itself does not: a back who was passing-down in Weeks 1-3 and is a bellcow in Weeks 4-6 is a role change with a name attached, and more legible than a snap-share delta. That claim is untested and must be pre-registered against plain `offense_pct` deltas before any of it is believed. The leverage-concentration result above is the cautionary case — an interpretable metric that described something real and predicted nothing.

One input is unavailable. Route-running quality needs tracking or charting data; nflverse carries neither. Depth of target and catch rate proxy the field-stretcher versus chain-mover split and nothing proxies separation. Document it as a gap rather than approximating it.

### Adjacent scope: roster construction

A second tool, not an extension of this one. This repo answers "whose role is changing" from league-wide data. Roster construction answers "what should I start" given one roster, which is a different input, a different output, and a different validation problem. Keeping them separate protects this repo's evidence standard; folding them together would mix a validated screen with unvalidated heuristics.

A roster synergy rating built on two inputs, and deliberately only two.

**Bye structure.** Deterministic, no model required. Score a roster by the weeks in which it cannot field a competitive lineup because startable players at the same position share a bye. Two tight ends on the same bye is a guaranteed zero in a starting slot, and that is arithmetic. Cheapest real value in this section.

**Correlation.** Players on the same offense do not score independently: a quarterback and his own receiver rise and fall together, and two running backs in one backfield are close to mutually exclusive. The effect is on lineup *variance* rather than expected points, which makes the rating conditional rather than absolute — correlation raises a ceiling and thins a floor, so a projected underdog wants it and a favorite does not. A single scalar "synergy score" that ignores which side of that a manager is on would be worse than no score. Testable against the panel already built here: within-lineup covariance by team, comparing the distribution of stacked and unstacked lineups.

Deliberately excluded:

- **Week-of-season buckets.** Already tested in this repo and not supported: 1.31, 1.73 and 1.81 PPR of lift across early, mid and late flags, within 0.5 of each other. Reusing a failed split in a new context because the labels already exist is how a tool starts fitting noise.
- **Matchup adjustment.** Defensive points-allowed-by-position is dominated by strength of schedule and reverts hard. Out of the basis until something shows otherwise.

---

## Stack and data

Python, pandas, pyarrow. No API keys.

| source | coverage | used for |
|---|---|---|
| nflverse snap counts | 2012– | snap share, team play volume |
| nflverse weekly stats | 1999– | targets, air yards, PPR |
| nflverse injuries | 2009– | context tagging |
| nflverse participation | 2016–2025 | in-game exit detection |
| Sleeper trending | current window only | market attention, acquirability |

Snap counts key on `pfr_player_id` and weekly stats on `gsis_id`, so `players.parquet` provides the crosswalk. Joins are on IDs, never names: the snap file lists "Tre Harris" where other sources list "Tre' Harris".

---

## Module map

| file | role |
|---|---|
| `fetch.py` | data pulls, ID crosswalk, team play volume |
| `diff.py` | delta computation, tiering, confirmation, corroboration |
| `injuries.py` | context tagging, vacancy duration |
| `exits.py` | in-game exit detection |
| `attention.py` | market add/drop counts, acquirability snapshots |
| `backtest.py` | validation harness, documented negative results |
| `cli.py` | command line interface |
