# 01 · New candidate sources, judged by the hits they add

Status: ready-for-agent
Tier: A
Track: both
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Shopify judges a new source by what the others miss.** Source: "The generative recommender behind Shopify's commerce
  engine" (https://shopify.engineering/generative-recommendations, 25 Feb 2026).
  - Their HSTU-based retriever is one of several candidate generators.
  - Shopify uses "a boosting-inspired approach that increases training pressure on the parts of the space where the
    ensemble is weak, and can also treat other models' predictions as hard negatives".
  - Online, "Shop orders increased by 0.94% relative" and "Conversion rate increased by 0.71% relative".
  - What transfers is the yardstick: a new source counts only for the hits the existing ones miss.
- **Netflix: weighting positives is not a free win.** Source: "Does Weighting Improve Matrix Factorization for
  Recommender Systems?" (https://arxiv.org/abs/2510.10440, WWW '25): "training with unweighted data can perform
  comparably to, and sometimes outperform, training with weighted data, especially for large models". Our ALS source
  weights positives, so α and model size should be tuned together.
- **Already proposed here:** `notes/2026-11-05-model-options.md` §3.2 suggested tuned iALS and RP3beta as extra
  candidate sources.
- **Step-16 EASE added +0.0–0.1 pt HR@10.** Its λ was tuned on the standalone EASE list, not on what EASE adds to the
  pool (`notes/2026-11-05-model-options.md` §1).

## Question

Which extra candidate source adds new-game hits that the current pool (popular 100 + ALS 30 + EASE 30) misses, and adds
enough of them to clear a bar once the ranker uses it?

## Stage 0

- **Bounds.**
  - `b01_hr` = misses who played a new game outside U.
  - `b01_adopt` = not-adopted players who adopted a game outside U.
  - U = the stored ranker-new, ALS-new and popular-minus-played top 10s. The snapshot does not store the real pool, so U
    stands in for it.
- **Result** (pt of scored players; experiments/2026-11-06-research-bounds/):

  |Bound|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
  |---|---|---|---|---|---|
  |`b01_hr`|4.77|5.15|3.48–8.90; 3.82–12.94|20/20; 20/20|PASS|
  |`b01_adopt`|4.29|4.69|1.84–6.54; 1.93–6.96|20/20; 20/20|PASS|

- **Reading.**
  - U holds a new test-week game for 25.9 / 28.0 % of scored players; the ceiling is 38.8 / 41.7 %.
  - The bound is loose. It counts any new game a miss played outside U, and U is only the stored top 10s, not the real
    pool.
  - The real pool reaches more: popular 100 + ALS 10 + EASE 30 holds a new test-week game for 24–42 % of scored players
    on 11 clusters (`notes/2026-11-05-model-options.md` §3.2), against U's 26–28 % pooled.
  - Do not read 4.8–5.2 pt as headroom. The bound shows that room may exist; stage 1 measures it against the real pool.

## Stage 1 (both tracks)

- **Rebuild the real pool** per cluster-week.
  - Copy the popular, ALS and EASE candidate code from `pipeline/pull/step14_ltr.py` (`prepare_brand`) and
    `pipeline/sasrec/ease_backtest.py` (`fit_ease`, λ = 200) into the new experiment.
  - Never import from `/home/ubuntu/ml`.
  - Replace every `~/ml/...` path in the copied code with `mlkit`'s absolute paths and `out/`. As sunny, `~/ml` is
    `/home/sunny/ml` (AGENTS.md §5 trap).
- **Sources.** Each gives the top 30 unplayed games in the brand catalogue.
  - **iALS** (implicit 0.7.3): factors {64, 256} × α {1, 10} × regularization {0.01, 0.1}, 15 iterations.
    - In implicit's ALS, the matrix value is the confidence and positives add (c − 1)·yyᵀ (`implicit/cpu/als.py`
      504–512). So α = 1 on binary input weights positives like negatives: the paper's unweighted case.
  - **RP3beta:** β {0.3, 0.6}, 100 neighbours.
  - **Play transitions:** per brand, distinct-player counts of consecutive distinct-game plays in the 60-day
    `plays_sql()` window, read from the player's most recent game.
  - **Cross-cluster popularity:** the same title's (`productId` + `code`) 7-day player share on the market's other
    clusters.
- **Metric.** A source's incremental recall = the share of scored players with a test-week new game that is in its
  top 30 and not in the pool. Report it for all scored players, for default misses only, and for adopted games.
- **Ranker test.**
  - Add the best source (most incremental recall on misses; ties broken by adopted games) to the v3-unified harness
    (`experiments/2026-11-05-v3-unified/run.py`, `build()` → `cand`) as 10 extra candidates plus a `src_rank` feature.
  - Compare `unified: learned continue (3/5)` and `unified: top 10` with and without it.
- **Memory:** run clusters one at a time (AGENTS.md §5).

## Bar

Both tracks, on 20 scored clusters × 2 frozen weeks:
- **HR@10:** ≥ +0.5 pt pooled HR@10, better on ≥ 15/20 clusters, new-game HR not lower.
- **Discovery:** ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters, HR@10 no worse than −0.2 pt pooled.

## Comments

**6 Nov, v4 run** (`experiments/2026-11-06-v4/`, one forward week). Two of the sources were tested inside the unified
ranker, together with issue 04's intent features:
- co-play (RP3beta-style, β = 0.5);
- next-game transitions.

Result:
- The two sources reach a new test-week game for +1.61 pt more scored players than v3's candidates (clusters 0.87–2.66),
  and +0.45 pt more for adopted games.
- In the list, that became only +0.08 pt HR@10 (top 10; 17/20 clusters) and +0.10 pt adopted-game HR.
- Still open: the iALS sweep and cross-cluster popularity. Their likely size is bounded by this conversion rate.
