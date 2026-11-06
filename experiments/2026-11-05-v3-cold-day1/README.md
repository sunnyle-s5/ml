# v3-cold-day1

Started: 2026-11-05 · Status: done

## Question
Cold players (no personal list: no play in the 30 days before the as-of date) see the fallback list only on their first day of play. The daily build gives them a personal list the next day. Which fallback maximises **day-one HR@10**? Options: the live Popular list (today), a "newcomer list" (the v3 guide's cold-start routing / segment popularity), or, for returning players, their own older games.

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26. Snapshots and market caches are read-only.
- **Day one:** a cold player's first market-local day of play in the test week.
- **Lists:**
  - **L1:** the brand's live Popular top 10 (pct-rank list where a brand has none).
  - **L4 newcomer list:** per brand, the 10 games most played on their first day by the brand's newcomers of the 28 days before the test week. A brand with < 50 such players falls back to L1; that happened for 1–4 brands in a few clusters.
  - **L3:** returning players only: their 5 most recent earlier games, then L1.
- **Checks:**
  - The cold counts match `experiments/2026-11-05-v2-coldstart` on all 40 cluster-weeks (e.g. bdk1 2026-10-26: 119,761).
  - So does the weekly L1 HR@10 (bdk1 0.745).
  - `grep -c '!!' out/run_all.out` = 0.
- **Note:** `th.duckdb` and `ph.duckdb` were reloaded on 5 Nov 04:32 and 05:37 +07, after the v2 run. The reload dropped the oldest cached day (6 Jul), so 0.2–0.5 % of v2's returning players in TH and PH count as newcomers here. Cold counts and test-week data are unchanged.

## Result (all 20 clusters, player-weighted; per market in `out/summary.md`)
| Day-one HR@10 | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| All cold: L1 live list | 64.2 % | 62.9 % |
| All cold: L4 newcomer list | 67.4 % (+3.1) | 64.9 % (+2.1) |
| Newcomers: L1 vs L4 | 65.8 % vs 69.0 % | 63.2 % vs 65.4 % |
| **Returning: L1 vs L3 own older games** | 58.4 % vs **76.2 % (+17.8)** | 61.7 % vs **74.4 % (+12.7)** |
| bdk1: L4 − L1 / L3 − L1 (pt) | +9.2 / +12.7 | +1.4 / +9.8 |

- On their first day back, returning players mostly replay a game they played before. Their own older games beat the live list by +8 to +23 pt in every market-week.
- The newcomer list helps a little overall (+2.1 / +3.1 pt). It fails the bar on bdk1 in the 27 Oct–2 Nov week (+1.4) and in MX in the 20–26 Oct week (−0.9).

## Decision / next
- **L3 fires.** Serve returning cold players their 5 most recent earlier games, then the live list, instead of the plain live list. This agrees with the weekly v2 result (rule R5).
- **L4 does not fire.** Newcomers keep the live list. The bdk1 gain is +1.4 pt in the 27 Oct–2 Nov week, below the 2.0 pt bar.
