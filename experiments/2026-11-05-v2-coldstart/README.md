# v2-coldstart (X3)

Started: 2026-11-05 · Status: done

## Question
Every backtest so far scores only players with a personal list. What about the test-week players without one (cold players)? How many are there? What should they see instead of the brand list: the v2 spec's "one-game cold start" (L2), or their own older games (L3)?

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26, read-only.
- **Cold player:** plays in the test week but has no row in the snapshot's `hist` (no play in the 30 days before the as-of date).
- **Newcomer:** a cold player with no earlier play in the ~120-day market cache. **Returning player:** a cold player who did play earlier.
- **Scoring:** as in `pull/step13_coldstart.py` ("HR@10 rest"). Only players with ≥ 2 distinct test games count. Their first test game is removed from every list; a hit is one of their other test games in the top 10. Outside mx96g1 the data is hourly, so "first game" means earliest hour, ties broken by game id.
- **Lists:**
  - L1: the brand's `live (as stored)` list.
  - L2: snapshot `coldstart` (newcomers' first game → their next games, training data only), then L1.
  - L3: the player's 5 most recent earlier games, then L1.
- **Checks:**
  - The rebuilt cold count matches the snapshot on all 40 cluster-weeks (mx96g1 2026-10-26: 7,533 of 17,115).
  - newcomers + returning = cold.
  - L2 coverage (first game has a `coldstart` row) is 84–98 %, so L2 really differs from L1: it's not a fallback artefact.

## Result (all 20 clusters, player-weighted; per market in `out/summary.md`)
| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Cold players / test-week players | 442,329 / 1,807,409 (24 %) | 552,323 / 1,935,988 (29 %) |
| … of which newcomers | 347,110 (78 %) | 442,661 (80 %) |
| HR@10 rest: L1 brand list vs L2 after first game | 69.8 % vs 71.4 % (+1.6) | 69.1 % vs 69.0 % (−0.1) |
| Returning players: L1 vs L3 own older games | 61.7 % vs 73.3 % (+11.5) | 63.9 % vs 73.1 % (+9.2) |
| bdk1: Δ L2 / Δ L3 (pt) | +10.1 / +10.4 | +1.6 / +7.5 |

- **The players the backtests never score are large in number.** About a quarter to a third of each week's players have no personal list. Most of them are newcomers.
- **L2 (one-game cold start) is a wash overall** (+1.6, −0.1). It's inconsistent by market: MX −5.5 / −5.6, BD +8.7 / +1.2.
- **L3 wins clearly and consistently** for returning players: +9.2 to +11.5 pt overall, and positive in every market-week except CO 27 Oct–2 Nov (−2.1; CO has only 584 returning cold players that week).

## Decision / next
- **R5 fires for L3.** Recommend serving "own older games first, then the brand list" to returning cold players in the treatment arm, instead of the plain brand list (`fallbackReason = no_list` today). The build only keeps players active in the last 30 days, so this needs an extra lookup of their earlier games in the plays (the cache holds ~120 days).
- **R5 does not fire for L2.** Newcomers keep the brand list.
- **Always:** pre-register the POC stratum "had a personal list at exposure". A quarter or more of exposed players won't have one, which dilutes the measured effect.
