# Slot split for the recency-continue default

Started: 2026-11-04 · Status: done

## Question
The 3/5 continue-slot split was tuned on ALS continue slots (step 12). Is it still right now that the continue slots are the player's own games, newest first?

## Setup
20 scored clusters × as-of 2026-10-19 and 2026-10-26. The default, rebuilt from `hist` plus the stored ranker list, matches
the stored default on all 40 cluster-weeks (0.0 pt). `slot_split.py` predates `lib/mlkit.py` and runs on its own.

## Result (player-weighted, vs default)
| Continue slots for players with 3+ games | HR@10 | new-game HR |
|---|---|---|
| 2 | −5.0 | +2.6 |
| 3 | −2.0 | +1.7 |
| 4 | −0.7 | +0.9 |
| 5 (default) | — | — |
| 6 | +0.4 | −0.9 |
| 7 | +0.6 | −2.0 |
| 8 | +0.7 | −3.1 |

Giving light players 1 slot: −1.6 / +0.1. Sizing by games played in the last 7 days: −2.3 to −7.1 / +0.1 to +1.3. Both are worse than a fixed split.

## Decision / next
Keep 3/5. Moving to 4 is a Product choice: about 1 pt HR@10 for 1.3 pt of new-game hits. Details: `out/slot_split_all.out`, `out/*.csv`.
