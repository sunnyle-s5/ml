# research-bounds

Started: 2026-11-06 · Status: done

## Question
Before building any experiment proposed from the Netflix/Shopify research (`issues/recsys-research/`), how much could each
add at most? Each bound is an oracle ceiling on the 2 frozen weeks. An issue goes to stage 1 only if its ceiling clears its
track's bar in both weeks.

## Setup
- **Data**
  - 20 scored clusters × as-of 2026-10-19 and 2026-10-26, read-only.
  - Baseline: the stored `hybrid (recent continue + ranker new)`.
  - Test-week play days come from the market caches via the X2 SQL (`experiments/2026-11-05-v2-adoption/run.py`).
- **Bounds** (each in pt of scored players):

  |Issue|HR@10-track bound|Discovery-track bound|
  |---|---|---|
  |01/02 candidate sources|`b01_hr`|`b01_adopt`|
  |03 adoption-weighted labels|—|`b03_adopt`|
  |04 per-player split|`b04_hr`|`b04_adopt`|
  |05 fresh games|`b05_hr`|`b05_adopt`|

- **Definitions.** A "miss" played none of the stored default's top 10. A "not adopted" player has no adopted game in the
  stored default's top 10.
  - `b01_hr`: misses who played a new game outside U. `b01_adopt`: not-adopted players who adopted a game outside U.
    - U = the stored `ranker (new games only)`, `als (new games only)` and `popular 30/70 minus played` top 10s.
    - U is expected to be a subset of the ranker's real pool (same build's popularity and ALS; not verified), so the bound
      should only overstate.
    - Issue 01's stage 1 rebuilds the real pool and measures again.
  - `b03_adopt`: not-adopted players who adopted a game inside C. C = the unified ranker's new candidates: ranker new 10,
    popular 10 and the brand live top 20, minus played (`experiments/2026-11-05-v3-unified/`).
  - `b04_hr` / `b04_adopt`: the per-player best of {rebuilt default, heavy 10, heavy 3}, minus the default, on HR@10 /
    adopted-game HR. heavy 10 = up to 10 own games (players with ≥ 3 own games), then ranker new; heavy 3 = 3 own games,
    then ranker new.
  - `b05_hr` / `b05_adopt`: misses who played a new fresh game / not-adopted players who adopted a fresh game.
    - Fresh = the title (`productId` + `code` in the market cache's `game_<c>.rawData`) first appears in the cluster's
      catalogue in the 30 days up to the as-of date.
    - The catalogue is the 2026-11-03 snapshot of `game_<c>`. A title whose older id was removed from it would look fresh,
      so this bound too can only overstate.
- **Gates**
  - HR@10 bound ≥ 0.5 pt pooled in both weeks, or discovery bound ≥ 0.3 pt pooled in both weeks.
  - Pooled = player-weighted over valid cluster-weeks.
  - With fewer than 18 valid clusters in a week, the gate reads INCOMPLETE.
- **Checks** (any failure prints a `!!` line and marks the job invalid; required: `!!` count = 0 in `out/run_all.out`)
  - Truth rebuild: test-week days from the market cache cover the snapshot's truth (rows ≥ 99.5 %, rounds within 0.5 %).
  - A: the rebuilt default equals the stored default exactly (players, HR@10, new-game HR).
  - B: heavy 3 HR@10 within 0.02 pt of `experiments/2026-11-04-slot-split/` `heavy 3`.
  - C: the default's HR@10 over all scored players equals the stored default's.
  - D: the default's adopted-game HR and the adopt ceiling equal X2's (`experiments/2026-11-05-v2-adoption/out/`) within
    0.001 pt.

Usage (from /home/sunny/ml):

    bin/py experiments/2026-11-06-research-bounds/run.py mx96g1 2026-10-26   # one cluster-week
    bin/py experiments/2026-11-06-research-bounds/run.py all                 # 20 clusters × the 2 pinned weeks, then summarize
    bin/py experiments/2026-11-06-research-bounds/run.py summarize

## Result

**All 40 cluster-weeks are valid,** and `grep -c '!!' out/run_all.out` = 0.
- **Sanity.** The pooled default reproduces the known numbers:
  - HR@10 92.40 / 92.05 %;
  - adopted-game HR 3.27 / 3.64 %;
  - new and adopt ceilings 38.77 / 41.73 % and 8.91 / 9.75 %.
- **Run time:** 163 s for all 40 jobs.

Pooled bounds (pt of scored players; per market in `out/summary.md`):

|Bound|Bar|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
|---|---|---|---|---|---|---|
|`b01_hr`|0.50|4.77|5.15|3.48–8.90; 3.82–12.94|20/20; 20/20|PASS|
|`b01_adopt`|0.30|4.29|4.69|1.84–6.54; 1.93–6.96|20/20; 20/20|PASS|
|`b03_adopt`|0.30|1.61|1.70|0.62–2.67; 0.81–2.34|20/20; 20/20|PASS|
|`b04_hr`|0.50|1.73|1.71|0.83–3.03; 0.89–2.51|20/20; 20/20|PASS|
|`b04_adopt`|0.30|0.37|0.40|0.15–0.59; 0.15–0.63|15/20; 12/20|PASS|
|`b05_hr`|0.50|0.09|0.13|0.01–0.26; 0.00–0.53|0/20; 1/20|FAIL|
|`b05_adopt`|0.30|0.09|0.14|0.00–0.23; 0.00–0.55|0/20; 3/20|FAIL|

|Issue|HR@10 gate|Discovery gate|Stage 1|
|---|---|---|---|
|01 candidate sources|`b01_hr` PASS|`b01_adopt` PASS|yes|
|02 next-7-day sequence model (shares 01's bound)|`b01_hr` PASS|`b01_adopt` PASS|yes|
|03 adoption-weighted labels|—|`b03_adopt` PASS|yes|
|04 per-player split|`b04_hr` PASS|`b04_adopt` PASS|yes|
|05 fresh games|`b05_hr` FAIL|`b05_adopt` FAIL|no|

**Reference.**
- U (the stored new-game top 10s) holds a new test-week game for 25.87 / 27.97 % of scored players.
- 0.75 / 0.87 % of scored players played a new fresh game at all, and 0.03 / 0.05 % a game launched during the test week.
- Misses on a sparse game (< 20 players in the brand's 60 days) are 0.49 / 0.61 pt.
- Fresh titles summed over clusters: 1,973 / 6,760. TH's 7 clusters account for most of the jump (487–957 fresh titles
  each as of 26 Oct).
  - It is a bulk catalogue addition: one `createdAt` day, 22 Oct, carries 923 titles on 96g1 and 455 on wdb1.
  - kzg1 also had 492 titles on 30 Sep.
  - The bounds count plays, so the addition only inflates `fresh_titles`.

## Decision / next

- **01 candidate sources:** stage 1. The bound is loose (any new game outside U), so stage 1 must show reach.
- **02 next-7-day sequence model:** stage 1 after 01, only if room remains once 01's best source is in.
- **03 adoption-weighted labels:** stage 1 (discovery track).
- **04 per-player split:** stage 1. The HR@10 room is about 3× the bar; the discovery room is thin (12/20 clusters clear
  it in the second week).
- **05 fresh games:** wontfix. `b05_hr` 0.09 / 0.13 < 0.5 and `b05_adopt` 0.09 / 0.14 < 0.3, and both bounds overstate.
- **Re-run** on the as-of 2026-11-02 week once its snapshot and an X2 CSV for it exist. That snapshot is the first one
  built with EASE on.
