# v3-misses

Started: 2026-11-05 · Status: done

## Question
Where do the default list's misses go? A miss is a scored player who plays none of the list's first 10 games. Which idea in the v3 reference architecture ("LLM-based casino game recommender") could recover them? The main test is LLM-enriched game content, for which the closest stand-in we can measure is a sequel or edition of a game the player already plays.

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26, stored default `hybrid (recent continue + ranker new)`. Snapshots and market caches are read-only.
- For every miss, the games they did play are flagged. The flags overlap, and each one is the most HR@10 that lever could recover:
  - an own game ranked 6–10 / 11–20 / 21+ by recency;
  - a ranker pick that was ranked 1–10 but not shown;
  - a lapsed game: played in the market cache (from 6–9 Jul) but not in the 60-day history;
  - a series-mate: same provider and same name stem as an own game. Stem = lowercase, edition words and numbers dropped;
  - a live Popular top-50 game;
  - a game from a provider the player already plays.
- **Exclusive buckets**, first match: own replay → ranker unshown → lapsed → series → live top 50 → other new.
- **Check:** the "any own replay" share equals the headroom experiment's oracle-continue gain on all 40 cluster-weeks, within 0.05 pt (`grep -c '!!' out/run_all.out` = 0).

## Result (all 20 clusters, pt of scored players; per market in `out/summary.md`)
| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Misses | 7.6 % | 7.9 % |
| Any own replay (own game outside the list) | 2.14 | 2.11 |
| … of which own rank 6–10 | 1.46 | 1.44 |
| Ranker pick ranked but not shown | 0.96 | 1.00 |
| Lapsed game | 0.47 | 0.50 |
| **Series-mate (sequel/edition of an own game)** | **0.20** | **0.20** |
| Live Popular top 50 | 2.98 | 3.43 |
| Same provider as an own game | 4.11 | 4.11 |
| Exclusive: other new game (none of the above) | 2.58 | 2.54 |

- The levers that ordering can reach are own games just outside the list (~2.1 pt, two-thirds at ranks 6–10) and ranker picks ranked 6–10 (~1.0 pt).
- Series similarity, the content signal an LLM pass could add on our names-only catalogue, reaches 0.20 pt pooled. The worst cluster-week is 0.95 pt (pk96g1, 20–26 Oct, 414 players).
- MX has the most misses (11.7–13.8 %), and most of them go to live top-50 games (5.6–7.2 pt).

## Decision / next
- **LLM content enrichment: not worth it for HR@10.** The pooled bound is 0.20 pt, below the 1.0 pt bar.
- **What to try instead:** learn the order inside the list. This is the unified ranker in `experiments/2026-11-05-v3-unified/`.
