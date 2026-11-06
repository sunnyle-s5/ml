# v3-unified

Started: 2026-11-05 · Status: done (provisional: one forward week)

## Question
The v3 reference architecture's serving core is "retrieve candidates → rank them". We already rank the new slots, but the continue slots are a fixed rule: the player's 3 or 5 most recent games. Does one learned model that scores the player's own games *and* the new candidates together raise HR@10? And does it beat simply giving own games more slots?

## Setup
- **Training.** Per cluster, LightGBM (binary, early stopping on a 10 % player holdout), trained on the frozen as-of 2026-10-19 week (up to 50,000 scored players) and tested on as-of 2026-10-26 (all scored players, test week 27 Oct–2 Nov). The label is "played this candidate in the following week".
- **Candidates:**
  - the player's 20 most recent own games;
  - the ranker's 10 new games;
  - the stored popular-minus-played 10;
  - the brand's live Popular top 20 minus played.
- **Features (22):**
  - own-game history: recency, play days, rounds and bet share, days ratio;
  - candidate ranks: ranker, popular, live;
  - game popularity and repeat rate in the brand;
  - lobby type;
  - the player's type and provider shares;
  - player activity.
- **Variants:**
  - rules with 8 or 10 continue slots (for players with ≥ 3 own games);
  - "learned continue": the same 3/5 slots, but the model picks which own games;
  - "top 10": the 10 highest-scored candidates, any mix.
- **Checks, on all 20 clusters** (`grep -c '!!' out/run_all.out` = 0):
  - the rebuilt default equals the stored default;
  - `rule: 8 continue` equals the slot-split experiment's `heavy 8` (e.g. bdk1 0.93752, mx96g1 0.83761).
- **Model fit.** 84–441 trees; holdout AUC 0.877–0.939; test AUC 0.864–0.935.
- **Cost.** 9.2 min for all 20 clusters; peak 9.3 GB (bdk1).

## Result (27 Oct–2 Nov, all 20 clusters, player-weighted; per market in `out/summary.md`)
| Variant | HR@10 | Δ vs default | Clusters above default | New-game HR | Hits beyond the 5 most recent own games |
|---|---|---|---|---|---|
| Stored default (3/5 recent + ranker new) | 92.05 % | — | — | 19.4 % | 19.4 % |
| Rule: 8 continue | 92.78 % | +0.73 | 20/20 | 16.1 % | 27.3 % |
| Rule: 10 continue | 92.84 % | +0.79 | 20/20 | 12.6 % | 28.3 % |
| **Unified: learned continue (3/5)** | 92.83 % | **+0.77** | 20/20 | **19.4 %** | 28.0 % |
| **Unified: top 10** | **93.18 %** | **+1.13** | **20/20** (min +0.39) | 14.0 % | 30.4 % |

- **Gains in every market:** top 10 adds +0.38 (CO) to +1.70 (MX) pt. ADDA7 goes from 93.77 % to 94.46 % (+0.69); learned continue gives 94.30 %.
- **Where it comes from:** choosing *which* own games to show. The top features are days ratio (25 %), play days (23 %), days since last play (21 %) and recency rank (10 %). Everything else is under 3 % each.
- **Learned continue (3/5) is the notable one:** about the same gain as 10 rule slots, with **no loss of new-game HR**. It keeps the same slots and only changes which own games fill them.

## Decision / next
- **The ship bar passes for "unified: top 10"** (+1.13 pt, 20/20 clusters, +0.40 pt over the 8-slot rule), so it's the recommended list. It stays provisional until the second forward week: after Wed 11 Nov 07:00 +07, run `bin/py experiments/2026-11-05-v3-unified/run.py all`.
- If discovery matters to Product, "learned continue (3/5)" gives about two-thirds of the gain (+0.77 pt) and keeps new-game HR unchanged.
- **For production:** one more LightGBM per cluster in `build_recs.py`, trained on the previous week, of the same size as the step-14 ranker. That is a patch for Yann; nothing has been changed.
