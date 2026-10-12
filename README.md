# usage-delta-v1
# usage-delta

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

## Roadmap

- [ ] v1: snap share and route participation diff, single position
- [ ] Injury report join
- [ ] All positions, position-specific metric sets
- [ ] Confirmation logic (two-week hold)
- [ ] Offense quality context layer
- [ ] Historical backtest — did flagged players outproduce their rank over the following three weeks?
