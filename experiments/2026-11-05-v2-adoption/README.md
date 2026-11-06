# v2-adoption (X2)

Started: 2026-11-05 · Status: done

## Question
The v2 spec's primary metric (NGA-7) counts a new game only if the player comes back to it. Of our lists' new-game hits, how many are *adopted* rather than tried once? Does the ranker's discovery edge over plain popularity survive that stricter test?

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26.
- **New game:** not in the player's 60-day `hist`.
- **Adopted:** a new game the player played on ≥ 2 distinct market-local days of the test week. All rounds count, because the data has no real-money flag.
- **Data:** test-week days come from the market caches (`mlkit.plays_sql`, read-only). Snapshot `truth` has no day field.
- **Checks:** on all 40 cluster-weeks, the rebuilt truth covers the snapshot's truth (rows ≥ 99.5 %, rounds within 0.5 %), and the default's HR@10 and new-game HR equal `mlkit.score()` within 0.1 pt. No exclusions: `grep -c '!!' out/run_all.out` = 0.

## Result (all 20 clusters, player-weighted; per market in `out/summary.md`)
| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Default: new-game HR / adopted | 17.6 % / 3.3 % | 19.4 % / 3.6 % |
| Ranker (new only): new-game HR / adopted | 21.7 % / 4.2 % | 23.7 % / 4.6 % |
| Popular 30/70 minus played: new-game HR / adopted | 18.2 % / 3.3 % | 20.0 % / 3.7 % |
| Adopted ÷ new-game hits (all three lists) | 18–19 % | 18–19 % |
| Ceiling: scored players who try / adopt ≥ 1 new game | 38.8 % / 8.9 % | 41.7 % / 9.7 % |

- About four in five new-game hits are one-day tries. The share is the same for the ranker, popular and the default list, and in every market (13–24 %).
- The ranker beats popular by +3.6 / +3.7 pt in new-game HR, but only by +0.9 pt in adopted.
- Only ~9–10 % of scored players adopt any new game in a week. Discovery that sticks is a small population.

## Decision / next
- Offline new-game HR overstates discovery value about five-fold. The ranker's edge is real but small once adoption is required.
- **R4:** add the adoption metric to the POC as an online secondary. Definition: first open of a new game from `main_list` within 7 days, then plays on ≥ 2 distinct days within 7 days of that open. Expect a small base rate, ~3–5 % of exposed players, to compare against.
