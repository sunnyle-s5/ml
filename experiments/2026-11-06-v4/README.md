# v4

Started: 2026-11-06 · Status: done

## Question
Does v3 plus the Netflix/Shopify findings that can be applied offline now beat v1, v2 and v3? Answer on both tracks
(HR@10 and adopted-game HR), on the same frozen week. Sources: `issues/recsys-research/` and
`notes/2026-11-06-netflix-shopify-recsys.md`.

## Setup
**Data and checks**
- **Weeks.** 20 scored clusters; train on as-of 2026-10-19, test on as-of 2026-10-26 (27 Oct–2 Nov). Only two snapshots
  exist, so this is one forward week, as in v3.
- **Checks.** Each job is invalid on failure, and the run requires `grep -c '!!' out/run_all.out` = 0.
  - Truth rebuild for both weeks.
  - The rebuilt default equals the stored default.
  - The re-trained v3 equals `experiments/2026-11-05-v3-unified/out/` exactly: training rows, then HR@10 and new-game HR
    for both v3 variants.
  - The default's adopted-game HR equals X2's.
  - v2 equals `experiments/2026-11-05-v2-arms/` "own + live" where every brand has a live list.

**Variants**

|Variant|What|
|---|---|
|v1|the stored default: 3/5 own recent games + ranker new|
|v2|3/5 own recent games + the live Popular list minus played (no ML; pct-rank list where a brand has no live list)|
|v3 top 10 / v3 learned continue|the v3 unified LightGBM over own 20 + ranker new 10 + popular 10 + live 20, re-trained here|
|v4 top 10 / v4 3/5 split|v3 + the additions below. The split keeps 3/5 own slots (the own games with the highest p), then new games by p|
|v4a top 10 / v4a 3/5 split|v4 trained with adoption weights|

**What v4 adds** (pinned before the run):
- **Issue 01: two new candidate sources,** 10 new games each, plus their scores as features.
  - **rp3:** RP3beta-style co-play. It uses the 20 most recent games of up to 100,000 sampled players per cluster,
    β = 0.5 and 20 neighbours per game. A player's score sums over their 10 most recent games.
  - **trans:** next-game transitions from the player's most recent game. They come from 60 days of market-cache plays,
    with 20 neighbours per game.
- **Issue 04: intent features** (FM-Intent):
  - `p_new7`: own games first played in the window's last 7 days;
  - `p_new7_rshare`: their share of the player's last-7-day rounds;
  - `p_try_share`: the share of own games played on one day only;
  - `first_days`: days since the player first played the candidate in the window.
- **Issue 03: v4a adoption weights** (Exp-RSFT):
  - Positives get weight exp(r / 0.5), with r = (label-week play days − 1) / 6.
  - Issue 03 proposed raw r = days − 1 with λ ∈ {0.5, 1}. That gives weights up to e¹², so r is scaled to [0, 1]; weights
    then run 1–7.4.

**Not in v4**
- 02, the sequence model: it is blocked by 01's full stage 1.
- 05, fresh-game cold start: wontfix.
- 01's other sources, iALS sweeps and cross-cluster popularity: their stage 1 is still to come.
- 06–08: they need the POC.
- Cold players keep the v3 fallback (own older games for returning players), unchanged
  (`experiments/2026-11-05-v3-cold-day1/`).

**Bars vs v1** (`issues/recsys-research/spec.md`)
- **HR@10 track:** Δ ≥ +0.5 pt pooled, ≥ 15/20 clusters above v1, new-game HR not lower.
- **Discovery track:** adopted-game HR Δ ≥ +0.3 pt pooled, ≥ 15/20 clusters above v1, HR@10 Δ ≥ −0.2 pt.
- v4 also reports its change over the v3 counterpart, cluster by cluster.

Usage (from /home/sunny/ml):

    bin/py experiments/2026-11-06-v4/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-06-v4/run.py all
    bin/py experiments/2026-11-06-v4/run.py summarize

## Result

**Checks.** All 20 clusters are valid and `grep -c '!!' out/run_all.out` = 0.
- v3 was reproduced exactly on every cluster.
- The run took 44 min, at most 9.2 GB RSS.
- Deviation from the harness design: the work tables live in a scratch DuckDB file, and the candidate table is built in
  player chunks. bdk1 ran out of memory at the 8 GB cap three times before this. The results are unchanged on mx96g1.

Test week 27 Oct–2 Nov, 1,383,665 scored players (per market and ADDA7 in `out/summary.md`):

|Variant|HR@10|Δ vs v1|Δ vs v3 counterpart|Clusters > v3 counterpart|New-game HR|Adopted-game HR|HR@10 track|Discovery track|
|---|---|---|---|---|---|---|---|---|
|v1 default|92.05 %|—|—|—|19.4 %|3.64 %|—|—|
|v2 own + live|91.04 %|−1.02|—|—|16.4 %|2.90 %|fail|fail|
|v3 unified top 10|93.18 %|+1.13|—|—|14.0 %|2.50 %|fail (new-game HR)|fail|
|v3 learned continue|92.83 %|+0.77|—|—|19.4 %|3.64 %|pass|fail|
|v4 top 10|93.26 %|+1.21|+0.08|17/20|14.3 %|2.60 %|fail (new-game HR)|fail|
|v4 3/5 split|92.80 %|+0.75|−0.03|7/20|19.4 %|3.63 %|fail (new-game HR −0.01)|fail|
|v4a top 10|93.27 %|+1.21|+0.08|17/20|14.3 %|2.60 %|fail (new-game HR)|fail|
|v4a 3/5 split|92.81 %|+0.76|−0.02|8/20|19.4 %|3.64 %|pass|fail|

**v4 top 10 vs v3 top 10.**
- HR@10 by cluster: −0.48 to +0.44 pt; brlkz1, ph96g1 and pk96g1 are worse.
- New-game HR +0.35 pt; adopted-game HR +0.10 pt, better on 20/20 clusters.
- ADDA7: 94.46 → 94.54 % HR@10.

**v4 3/5 split vs v3 learned continue:** −0.72 to +0.17 pt by cluster.

**Candidate recall.**
- The two new sources reach a new test-week game for +1.61 pt more scored players (clusters 0.87–2.66) than v3's new
  candidates, which reach 27.3 %.
- For adopted games: +0.45 pt on 5.3 %.
- The ranker turns little of that into list hits: +0.08 pt HR@10, +0.10 pt adopted-game HR.

**Features.** The 8 new features hold 6.8 % of v4's gain. The largest are `p_try_share` and `p_new7` (1.3 % each); own-game
history still dominates (`days_ratio`, `play_days`, `rec_days`, `rec_rank`: 76 %).

**Adoption weights (v4a) change nothing:** ±0.01 pt on every pooled metric.

## Decision / next

- **v4 ≈ v3, so it is not worth shipping.** The research additions move HR@10 by +0.08 pt (top 10) or −0.03 pt (3/5
  split), below v3's 0.2 pt margin for calling one list better (`RULE_MARGIN_PT`).
  They add a 60-day market-cache read and two candidate sources to the build. The POC treatment stays v3: unified top 10,
  or learned continue if Product keeps discovery.
- **No variant passes the discovery track.**
  - Weighting labels by play days (issue 03) does not raise adopted-game HR.
  - A ranker trained on "played next week" cannot be steered toward adoption by weights alone. The stage-0 room (1.6 pt)
    needs a different objective or online data (issues 06, 07).
- **The only list that passes the HR@10 track** with new-game HR held is the 3/5 form: v3 learned continue, or v4a split
  by a hair.
- **The 01 and 04 additions were tested together,** so their +0.08 pt is not attributed between them. An ablation is not
  worth running at this size.
- **Re-run** with the as-of 2026-11-02 week once it exists (a second forward week).
