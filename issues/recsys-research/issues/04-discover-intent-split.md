# 04 · A per-player "will discover" prediction sets the new-slot count

Status: ready-for-agent
Tier: A
Track: both
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Netflix predicts continue vs discover first.** Sources: FM-Intent
  (https://netflixtechblog.com/fm-intent-predicting-user-session-intent-with-hierarchical-multi-task-learning-94c75e18f4b8)
  and IntentRec (https://arxiv.org/abs/2408.05353).
  - One intent head is the action type: "discovering new content versus continuing previously started content".
  - Feeding the intents into the item head gave "7.4% in next-item prediction accuracy compared to the best baseline
    (TransAct)".
- **Netflix: effects differ by kind of user.** Source: "Treatment Effect Modification by Latent Classes"
  (https://arxiv.org/abs/2610.10851, abstract only). Effects differ between heavy, less-active and rewatch-oriented users.
- **Here: everyone gets the same split.**
  - The 3/5 split of continue slots and new slots is the same for every player.
  - Rule-based adaptive splits (`n7`) lost 2.3–7.1 pt HR@10 (`notes/2026-11-04-findings.md` §5).
  - So a learned split must first beat an oracle.

## Question

Can a per-player prediction of "will play a new game this week" choose between more continue slots and more new slots,
and beat the fixed 3/5 split?

## Stage 0

- **Bounds.** `b04_hr` / `b04_adopt` = the per-player best of three lists, minus the default, on HR@10 / adopted-game HR:
  - `rebuilt default`;
  - `heavy 10`: up to 10 own games for players with ≥ 3 own games, then ranker new;
  - `heavy 3`: 3 own games, then ranker new.
- **Result** (pt of scored players; experiments/2026-11-06-research-bounds/):

  |Bound|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
  |---|---|---|---|---|---|
  |`b04_hr`|1.73|1.71|0.83–3.03; 0.89–2.51|20/20; 20/20|PASS|
  |`b04_adopt`|0.37|0.40|0.15–0.59; 0.15–0.63|15/20; 12/20|PASS|

- **Reading.**
  - The HR@10 room is about 3× the bar.
  - The discovery room passes pooled but is thin: only 12 of 20 clusters clear 0.3 pt in the 27 Oct–2 Nov week.

## Stage 1 (both tracks)

- **Discover model.** One LightGBM binary model per cluster, trained on the week before the test week.
  - Label: the player plays ≥ 1 new game in the label week. For the discovery track: adopts ≥ 1.
- **Features,** from that week's history:
  - `p_games`, `p_rounds_log`, `p_days_max`, `p_rec_days`;
  - the share of rounds on games first played in the window's last 7 days (market cache);
  - the share of own games with play_days ≥ 2;
  - the top lobby-tab share.
- **Policy:** P ≥ τ_high → `heavy 3`; P < τ_low → `heavy 10`; otherwise the default.
- **Thresholds.**
  - Pick (τ_low, τ_high) on the training week from deciles of P, maximising the track metric under the track guard.
  - Apply the pair unchanged to the test week.

## Bar

Both tracks, on 20 scored clusters × 2 frozen weeks:
- **HR@10:** ≥ +0.5 pt pooled HR@10, better on ≥ 15/20 clusters, new-game HR not lower.
- **Discovery:** ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters, HR@10 no worse than −0.2 pt pooled.

## Comments

**6 Nov, v4 run** (`experiments/2026-11-06-v4/`, one forward week). Four intent features were added to the unified ranker
instead of the threshold policy: `p_new7`, `p_new7_rshare`, `p_try_share`, `first_days`.
- `p_try_share` and `p_new7` hold 1.3 % of gain each.
- Together with issue 01's sources: +0.08 pt HR@10 (top 10). The 3/5 split loses 0.03 pt against v3 learned continue.
- The threshold policy in Stage 1 above is still untested. Its stage-0 room is 1.71 pt HR@10.
