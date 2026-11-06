# 03 · Adoption-weighted ranker labels

Status: wontfix (6 Nov: v4a weights moved every metric by ±0.01 pt; see Comments). Re-open only with a different
objective or online adoption data.
Tier: A
Track: discovery
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Netflix: exp(r/λ) sample weights beat RL.** Source: "Exponential Reward Weighting for Fine-Tuning Generative
  Recommenders under Sparse and Noisy Feedback" (https://arxiv.org/abs/2608.00816).
  - "each logged interaction is weighted by exp(r/λ)". It needs no reward model and no propensities.
  - On StreamCo, against linear reward-weighted fine-tuning: NDCG@10 +106.20 %, HR@10 +98.07 %, MRR +86.31 %.
  - PPO: HR@10 −14.66 %.
  - Best at "λ≈0.5–1.0".
  - "Reward-model score does not correlate with recommendation quality … evidence of reward hacking".
- **Netflix: reweight, don't run RL, when propensities are unknown.** Source: "Post-Training Generative Recommenders with
  Advantage-Weighted Supervised Finetuning"
  (https://netflixtechblog.com/post-training-generative-recommenders-with-advantage-weighted-supervised-finetuning-61a538d717a9).
- **Netflix: train on a proxy closer to the long-term goal.** Source: "Recommending for Long-Term Member Satisfaction at
  Netflix" (https://netflixtechblog.com/recommending-for-long-term-member-satisfaction-at-netflix-ac15cada49ef). It
  predicts delayed feedback where needed.
- **Netflix Foundation Model:** "a 5-minute trailer play should not carry the same weight as a 2-hour full movie watch"
  (https://netflixtechblog.com/foundation-model-for-personalized-recommendation-1a0bd8e02d39).
- **Here: one-day tries count like adoptions.**
  - About four in five new-game hits are one-day tries (`experiments/2026-11-05-v2-adoption/README.md`).
  - The ranker's label counts a single try the same as a game played all week.

## Question

Does weighting or relabelling the ranker's positives by play days raise adopted-game HR without costing HR@10?

## Stage 0

- **Bound.** `b03_adopt` = not-adopted players who adopted a game inside C. C = the unified ranker's new candidates:
  ranker new 10, popular 10 and the brand live top 20, minus played.
- **Result** (pt of scored players; experiments/2026-11-06-research-bounds/):

  |Bound|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
  |---|---|---|---|---|---|
  |`b03_adopt`|1.61|1.70|0.62–2.67; 0.81–2.34|20/20; 20/20|PASS|

- **Reference:** the default's adopted-game HR is 3.27 / 3.64 %; the adopt ceiling is 8.91 / 9.75 %.

## Stage 1 (discovery track)

- **Harness.** Copy the v3-unified harness (`experiments/2026-11-05-v3-unified/run.py`). Add label-week play days for
  candidates, using the X2 `tdays` SQL (`experiments/2026-11-05-v2-adoption/run.py`) on the training week.
- **Variants.** LightGBM binary with the harness's parameters, three variants:
  - (a) the current label;
  - (b) positives weighted exp(r/λ), with r = label-week play days − 1 and λ ∈ {0.5, 1.0};
  - (c) label = adopted (≥ 2 play days).
- **Report** `unified: learned continue (3/5)` and `unified: top 10` for each variant: HR@10, new-game HR and
  adopted-game HR.

## Bar

Discovery track, on 20 scored clusters × 2 frozen weeks: ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters,
HR@10 no worse than −0.2 pt pooled.

## Comments

**6 Nov, v4 run** (`experiments/2026-11-06-v4/`, one forward week). Variant (b) was tested as v4a: exp(r / 0.5) with r
scaled to (days − 1) / 6. The issue's raw r = days − 1 would give weights up to e¹².
- Result: ±0.01 pt on HR@10, new-game HR and adopted-game HR in both list forms.
- Not yet tested: variant (c), label = adopted. Given (b), expect little.
- The 1.6 pt stage-0 room probably needs online data (issues 06, 07) rather than reweighting.
