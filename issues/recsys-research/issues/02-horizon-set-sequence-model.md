# 02 · Sequence model trained on the next-7-day set

Status: ready-for-agent
Blocked by: 01
Tier: A
Track: both
Re-opens: SASRec ("not recommended" in `notes/2026-11-05-model-options.md` §3), under the re-open rule in
[spec.md](../spec.md)
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Netflix: next-item targets go stale when lists are cached.** Source: "Towards Generalizable and Efficient
  Large-Scale Generative Recommenders" (blog
  https://netflixtechblog.com/towards-generalizable-and-efficient-large-scale-generative-recommenders-a7db648aa257,
  1 Jan 2026; the numbers are from the paper, https://arxiv.org/abs/2605.23312).
  - With next-token training, Task B is "dropping 31% at 24 hours and 41% at 48 hours".
  - Training on a weighted set of future items over the serving horizon (multi-token prediction) fixes much of this:
    "Under the 48-hour horizon, MTP improves all three tasks, with the best five-token window yielding +22.1%, +27.8%,
    and +27.9% relative MRR for Tasks A, B, and C".
  - Target weights are w_i = r_i·exp(−ln2·(t_i−t_context)/β).
- **This addresses why SASRec failed here.**
  - The 31 Oct SASRec run (`pipeline/sasrec/sasrec_backtest.py`) trained on the next game.
  - Our lists are built once a night and judged on the whole next week: the cached, set-valued setting where Netflix
    saw the gain.
  - SASRec lost to or tied the recency default (`notes/2026-11-05-model-options.md` §3).
- **Shopify: encode time, not only order.** Source: T-RoPE (https://arxiv.org/abs/2609.30576) puts timestamps instead of
  positions into the rotary encoding.
  - Amazon Books HR@10: 7.65 vs 6.89 for the best baseline (+11.0 %).
  - Shop app A/B: conversion "+0.33%, p=0.037".
  - SASRec saw only the order of plays, not the gaps between them.
- **Netflix Foundation Model** (https://netflixtechblog.com/foundation-model-for-personalized-recommendation-1a0bd8e02d39)
  uses a multi-token prediction objective. It also notes that "a 5-minute trailer play should not carry the same weight
  as a 2-hour full movie watch".

## Question

Does a small sequence model trained on next-7-day sets, with time gaps as input, add new-game hits beyond the pool and
issue 01's best source?

## Stage 0

Shares issue 01's bound: `b01_hr` 4.77 / 5.15 pt and `b01_adopt` 4.29 / 4.69 pt (20–26 Oct / 27 Oct–2 Nov), PASS.
Issue 02 starts only after 01 has measured how much of that room a cheap source reaches.

## Stage 1 (both tracks)

- **Start condition:** after 01's best source, `b01` minus 01's measured incremental gain is still ≥ the track bar.
- **Copy** `pipeline/sasrec/sasrec_backtest.py` into a new experiment.
  - Replace its `~/ml/pull` import (`market.db_path`, `ep`, `plays_expr`) with `mlkit.market_db`, `mlkit.ep` and
    `mlkit.plays_sql`.
  - Write outputs to the experiment's `out/` instead of `~/ml/sasrec` (AGENTS.md §5 trap).
- **Change four things:**
  - **Target:** the multi-label set of games the player plays in the 7 market days after each training cut, with uniform
    weights. Loss = mean full-softmax log-likelihood over the set, over the brand catalogue.
  - **Inputs:** a log-bucketed time-gap embedding per event: the gap to the previous event and the gap to the prediction
    time.
  - **Cuts:** weekly training cuts across the 60-day window.
  - **Size:** the script's defaults (`--dim 64 --maxlen 50 --blocks 2 --epochs 10 --threads 6 --max-minutes 40`).
- **First run:** mx96g1 and mxk1 × 2 weeks. Score the model two ways:
  - as a list: HR@10, new-game HR, adopted-game HR;
  - as a source: incremental recall over the pool plus 01's best source.
- **Go to all 20 clusters** only if, pooled over those two clusters, the incremental recall on misses is ≥ 0.5 pt or the
  incremental recall on adopted games is ≥ 0.3 pt.

## Bar

Both tracks, on 20 scored clusters × 2 frozen weeks:
- **HR@10:** ≥ +0.5 pt pooled HR@10, better on ≥ 15/20 clusters, new-game HR not lower.
- **Discovery:** ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters, HR@10 no worse than −0.2 pt pooled.
