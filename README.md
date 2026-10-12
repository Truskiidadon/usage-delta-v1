# usage-delta-v1

Diff NFL weekly usage data week over week to surface role changes before the fantasy market prices them.

**v1**

---

## Why

The market prices *levels*. A receiver running 85% of routes is already valued correctly by anyone looking at a rankings page.

The market misses *deltas* — the player who went from 60% to 85% last week. Role changes show up in usage data days before they show up in production, and production is what rankings follow.

This tool diffs usage week over week and flags movement.

---

## Core logic

Each week, diff the current usage report against the prior week. Flag players whose role moved.

### Thresholds

| Tier | Trigger | Action |
|---|---|---|
| **Alert** | ±9 percentage points | Watch. Confirm next week. |
| **Actionable** | ±15 percentage points | Add / drop / trade decision now. |

### Two modifiers

**Scale to baseline.** A move from 30% → 45% is a larger proportional change than 75% → 90%. Trigger on the *lower* of 9 points or a 25% relative increase, so smaller roles aren't under-weighted.

**Require confirmation for single-week spikes.** One week of movement is often game script. A 9-point move that *holds* two consecutive weeks is the real signal.

---

## Game context filter

Don't dismiss moves at a high baseline. **Discount low-quality weeks.**

A move from 75% → 90% in a normal game script with the depth chart intact is a genuine signal. The same move in a 31-point blowout is noise. The baseline isn't what makes a delta suspect — the game context is.

Score each source week before diffing. Four filters, in order of how easily the data is obtained:

**Team plays run.** Cheapest and most useful. A team running 82 plays instead of 62 inflates everyone's counting stats, and snap *percentage* can move for reasons unrelated to role. Flag any game outside a sane band around the team's season average.

**Score differential by quarter.** A game decided by the third quarter produces garbage-time snaps for backups and inflated pass volume. Flag any week where the margin exceeded ~17 points for a meaningful stretch. Those weeks don't count toward two-week confirmation.

**Teammate availability.** If the player ahead on the depth chart was inactive, the delta is explained and expires when he returns. Same join as the injury report, applied to teammates rather than the player.

**Snaps vs. snap share, tracked separately.** A player can hold a flat 75% share while his raw snap count rises 15 — real added work hiding inside an unchanged percentage. The reverse happens too.

A delta from a flagged week still surfaces; it carries a lower confidence score and does not satisfy the confirmation requirement on its own.

### Down-side alerts

Flag declines at the same thresholds. Declines tell you when to sell, and selling early is where most of the value is. A back going 61% → 42% → 32% is the coaching staff telling you something.

---

## The injury join

Roughly half of all deltas are injury-driven, and those are priced by the market within hours of the injury report.

**Join usage data against the injury report and tag each delta as explained or unexplained.**

- *Injury-explained* — already priced. Low value.
- *Unexplained* — a coaching decision nobody noticed. **This is the edge.**

---

## Metrics by position

Route participation is the master key for every pass-catching position, running backs included. It is the metric that most often moves before production does, and the one the market is slowest to price, because the public looks at snap counts.

**If you build only one diff, build that one.**

### WR
- Route participation — best role marker; snaps mislead, since a receiver can be on the field blocking
- Targets per route run (TPRR) — whether he earns targets when out there; >22% is alpha territory
- Air yards share — what *kind* of role, which predicts variance
- First-read share — earliest tell of a changing pecking order

*The chain:* routes rise → TPRR holds → genuinely ascending. Routes rise → TPRR falls → he's a body on the field.

### RB
- Route participation — most underrated RB metric in PPR; separates a committee back with a floor from one without
- Carry share and snap share, tracked separately
- Goal-line carries (inside the 5) — moves independently of total volume
- Third-down snap share — the leading indicator; staffs give passing downs before they give carries

*A back can lose carries, keep passing downs, and barely lose value. The reverse is fatal.*

### TE
- Route participation — more critical here than anywhere; 85% snaps at 40% routes is a blocker
- Target share and red zone target share
- Inline vs. slot alignment — a move to the slot is a usage promotion

### QB
Role rarely changes incrementally. Track rush attempts and designed runs, where QB fantasy separation lives.

### Secondary markers that precede a role change
- A teammate's snap decline — the vacancy appears before the beneficiary rises
- Two-minute drill participation — who's on the field when the offense is pure passing
- Red zone snap share — separate from overall snaps, and a staff's clearest statement about trust

---

## Acting on a flag

Applied after the alert fires:

1. **Role** — does the player have snaps? Elite separation at a 12% snap share is worthless.
2. **Offense** — is the team functional? Role on a broken offense is a trap: 93% snaps behind an offensive line that can't pass protect produces nothing.
3. **Efficiency** — last. Buy the role, bet on production catching up.

### Three reasons efficiency lags. Only one reverses cleanly.

| Cause | Reverses? | Action |
|---|---|---|
| Variance (TDs, deep balls connecting) | Yes, reliably | **Buy** |
| QB or scheme | Only when the input changes | Buy on a timeline, not a hope |
| The player | Often never | **Avoid** |

**The tell that separates #2 from #3:** does the opportunity hold while efficiency is bad? If the snap share stays, it's variance or situation. If the snap share falls, the staff is telling you it's the player.

---

## Efficiency metrics — context, not alerts

These don't get diffed. They explain a flag after it fires.

- **YPRR** — headline receiver efficiency
- **Yards after contact per attempt** — backs
- **Yards after catch per reception** — recovery tracking post-injury
- **Expected fantasy points (xFP)** — converts opportunity into a projected point total; the gap between xFP and actual *is* the regression candidate list

---

## Timing constraint

Usage data lands Tuesday–Wednesday from most sources. Waiver claims process Wednesday morning.

If the pipeline doesn't beat the waiver deadline, **this is a trade tool, not a claim tool.**

---

## Data sources

- `nfl_data_py` — Python port of nflverse. Free, no API key, weekly player stats and snap counts.
- PFF — route participation, TPRR, YPRR. Paid.
- FantasyPros / RotoWire — weekly snap reports
- ESPN API — injury report, for the join

Join on **player IDs, not names.** Name matching across sources is always messier than it looks.

---

## Minimum viable version

1. Pull weekly usage data into a table
2. Diff against prior week; compute point change and relative change
3. Join injury report; tag each delta explained / unexplained
4. Output a sorted list of unexplained deltas over threshold, both directions

Everything past that — confirmation logic, baseline scaling, historical backtest — is refinement.

---

## Stack

Python. `pandas` for the diff, `requests` for data pulls, `nfl_data_py` for the source data.

---

## Usage

```bash
pip install -r requirements.txt

python -m usage_delta.cli --week 5
python -m usage_delta.cli --week 5 --confirmed-only
python -m usage_delta.cli --week 5 --metric target_share --positions RB
python -m usage_delta.cli --week 5 --refresh   # re-pull instead of using cache
```

Route participation is not in the free nflverse feed — it comes from PFF.
v1 uses snap share, target share, and air yards share as the usage set.

---

## Roadmap

- [x] v1: snap share / target share / air yards share diff, all skill positions
- [x] Confirmation logic (two-week hold)
- [x] Game context flag (team play volume)
- [x] Injury report join — gap injuries, mid-game exits, teammate availability
- [x] Vacancy duration — separates a rental role from a durable one

- [x] Coalesce `report_primary_injury` → `practice_primary_injury`.
      57% of rows carried only the practice field, so `injury_duration()`
      bucketed them under `"unspecified"` and computed one shared streak
      across unrelated injuries. Identified injuries: 601 → 1266 of 1413.
- [x] Exclude `"Not injury related - resting player"` from injury logic
      (147 rows) and gate `dnp` on it, so a rested veteran is no longer
      tagged `self_injured`. dnp: 373 → 331.

**Injury identity resolution.** The streak currently keys on an exact body
part string, so any re-label resets it to 1 — a confident answer to an
ambiguous question, and it fails in the direction that matters: a chronic
problem re-labeled once reads as fresh, understating durability exactly
when you would want to trust it. 159 week-to-week body part changes in
2026 so far (Mike Evans Hip → Ribs, Juszczyk Finger → Knee).

- [ ] Group body parts into regions (Foot/Ankle/Toe/Heel; Knee/Quad/
      Hamstring/Groin) and compare regions, not strings. A re-label inside
      a region continues the streak; across regions it is a new injury.
      Resolves most of the 159 without needing a pending state.
- [ ] Secondary injury as a duration-confidence multiplier, not a second
      streak. Rare (44 report / 91 practice rows) but a player carrying two
      injuries has a materially longer expected absence.
- [ ] `duration_confidence: low | medium | high`, surfaced in output. For
      what regions and multipliers cannot resolve — a body part jumping
      regions *while* a secondary injury is present is genuinely ambiguous
      between one worsening situation and two separate ones. Surface the row
      with a caveat rather than inventing a number.

**Next, and it should jump the queue.**

- [ ] **Historical backtest.** Design settled, not yet built — see below.

**Correctness, known and unfixed.**

- [ ] Consecutive vs. cumulative games missed — `games_missed` counts
      cumulatively, so two unrelated absences in weeks 1 and 9 score the
      same as two straight weeks out
- [ ] `confirmed_trend` requires same-direction movement across two
      appearances, so a player who jumps once and then holds flat fails
      confirmation. "Jump then hold" is arguably the more common shape of a
      real promotion than "climb steadily"
- [ ] `MIN_SNAPS = 5` and the `ALERT_PP / 2` floor in `_tier()` are both
      arbitrary. The backtest is what would set them

**Coverage.**

- [ ] Route participation (needs a PFF source) — the single most
      predictive field and the one the free feed does not carry
- [ ] Offense quality context layer — plays per game, points per drive,
      PROE. EPA alone answers "is this offense good?" when the question is
      "does this offense generate opportunity in my player's phase?"
- [ ] Red zone and goal-line usage, tracked separately from total volume

---

## Backtest design

Every threshold in this repo — 9 and 15 percentage points, `MIN_SNAPS = 5`,
two-week confirmation, two-week vacancy — was chosen to fit five 2026 cases
whose answers we already knew. That is a curve fit, not a validation. This
is the design to replace it.

**Window.** 2012–2025. Snap counts do not exist before 2012, which is the
binding constraint; the injury feed goes back to 2009 and weekly stats to
1999, but the tool's spine is snap share.

### Two outcomes, measured separately

| Question | Outcome | What it tests |
|---|---|---|
| Did the role hold? | snap share, W+1..W+4 | the detector |
| Did it pay? | PPR points per game, W+1..W+4 | the thesis that role predicts production |

The decomposition is the point. If roles hold but points do not follow, the
detector works and the premise is wrong. If roles do not hold, it is
detecting noise. One metric cannot distinguish those.

### Three comparison groups

| Group | What it tests |
|---|---|
| unexplained flags | the edge |
| priced flags (injury-driven) | whether the injury join earns its keep |
| matched unflagged controls | regression to the mean |

The control group is not optional. A player flagged for a snap-share jump
almost by definition had a low baseline, so comparing him to his own prior
three weeks is **mechanically biased toward success** — regression to the
mean alone produces a positive result. Controls are matched on position and
prior production.

If unexplained beats controls and priced does not, the whole design
validates at once. If priced also beats controls, the injury filter is
discarding signal.

### Settled parameters

- **Primary window: 4 games**, per game rather than cumulative. Ten games
  would only be testable for flags in weeks 2–8, which would study the
  early season exclusively — the noisiest regime, when roles are still
  forming.
- **Stratify by flag week**: early (2–6), mid (7–12), late (13–17).
  A week 3 flag and a week 15 flag have different implications; stratifying
  *answers* that rather than assuming it.
- **Secondary: rest-of-season**, reported alongside, where there is room.
- **Players injured during the outcome window stay in the sample.**
  Excluding them deletes the downside and inflates the result. Report both
  numbers.

### The null, committed in advance

**If unexplained flags do not beat matched controls by at least 0.5 PPR per
game, the screen is not earning its complexity.**

Writing this down before seeing results is the point. Deciding afterward
that some number is meaningful is how motivated reasoning gets in.

### Holdout

Tune on 2012–2019. Validate once, at the end, on 2020–2025. Do not look at
the holdout while tuning. Sweeping thresholds across all seasons and
reporting the best one measures fit to history, not predictive power.

2020 is a COVID season — no preseason, modified practice rules, inflated
injury reports. Flag it as a control and check whether results move.

### Reporting

Report **hit rate alongside mean effect**. A mean lift of 1.4 does not mean
any given flagged player gains 1.4; the distribution decides whether to act
on a specific flag. Action bands get set after the spread is visible, not
before — and 3.5 PPR per game is a WR3 becoming a WR1, so a top tier set
there may never fire.

---

## A design principle

When the data is ambiguous, the output should say so rather than silently
resolving in one direction.

Every ambiguity in this tool has a default, and defaults are not neutral.
A body-part re-label currently resolves toward "new injury" every time,
which is a systematic bias toward understating vacancy durability. The fix
is not always a better guess — sometimes it is surfacing the uncertainty
and letting the reader apply judgment.

### Current state

v1 runs end to end on live data. Validated against known 2026 cases:

| Player | Season snap share | What the tool does |
|---|---|---|
| Omarion Hampton | 58 → 63 → 42 → 35 → 30% | Flags the W2→W3 drop at −21pp |
| Jaylen Warren | 37 → 71 → 90 → 97 → 87% | Fires actionable in W2, confirms in W3 |
| Denzel Boston | 92 → 93 → 89 → 95 → 91% | Silent — role never moved, only production |

**The funnel.** Week 5 produces 159 raw flags. The injury join and the
confirmation filter cut that to 21 worth reading:

| Stage | Rows |
|---|---|
| flagged | 159 |
| unexplained by injury | 127 |
| + held two appearances | 20 |
| + normal game context | 17 |
| + durable teammate vacancy | 21 |

**The structural limitation.** The injury report is published before
kickoff, so a player hurt *during* a game has no row that week. KC
Concepcion (92→16%, concussion) and Tre Harris (93→45%, hamstring) both
sit in the Week 5 unexplained bucket for this reason. They appear on the
following week's report, which `lookahead` picks up — Week 4 shows 10
`self_exited` tags because Week 5's report exists to look back from. For
the current week it is unavailable, so treat a large unexplained *decline*
as suspect and check the news.
