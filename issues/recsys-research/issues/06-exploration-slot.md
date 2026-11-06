# 06 · Exploration slot with a logged draw probability

Status: needs-triage
Blocked by: POC launch with impression logging (drafts/spec-game-list-impression-and-ab.md), external
Tier: B
Track: discovery
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Shopify, RecSys '22** ("Optimizing product recommendations for millions of merchants", Falk & Karako,
  https://recsys.acm.org/recsys22/session-9/, abstract only). Shopify picks the best strategy per merchant segment by
  offline evaluation and starts new stores with it. The system "will start out with the best strategy for a given
  merchant, and then adjust to the current environment using multi-armed bandits". Our segments would be markets or
  clusters.
- **Netflix MAPS** (https://netflixtechblog.com/maps-netflixs-multimodal-asset-personalization-at-scale-32f96320785e,
  28 Aug 2026). Offline evaluation uses IPS on an exploration slice with logged propensities.
- **Netflix, "Simulation-Based Inference for Adaptive Experiments"** (https://arxiv.org/abs/2506.02881, abstract only).
  It gives valid inference for arm means after bandit-style allocation.
- **Here: nothing in a list is random.** The POC ticket logs the shown `gameIds`, `rk` and `slot`
  (drafts/spec-game-list-impression-and-ab.md §3–4), but no list position is drawn at random.
  - So no off-policy estimate of a new-game ranker is possible.
  - Every challenger needs its own A/B arm (drafts/plan-after-poc.md §4).
- **Discovery can only be measured online.** Offline, about four in five new-game hits are one-day tries
  (experiments/2026-11-05-v2-adoption/README.md).

## Question

Does one randomised slot give a logged, unbiased estimate of which new games players adopt, at an HR@10 cost Product
accepts?

## Design

- **The slot.** Position 10 of arm B's list becomes the exploration slot.
  - It holds a new game drawn from the ranker's top 30 new candidates that are not already in the list.
  - The draw probability is ∝ exp(score / T). T is fixed per build and written to the build's metadata; its value is set
    when the ticket change is written.
- **File and events.**
  - A new daily-file column `draw_p` holds the draw probability (NULL for other slots), with `slot = 'explore'`.
  - The BE and FE pass both through to `evt:home_game_list_shown`.
- **Uses.**
  1. IPS estimates of the adopted-game HR any new-game ranker would reach.
  2. A per-market strategy choice, then a bandit (Shopify RecSys '22).
  3. If a bandit follows, inference after adaptive allocation as in arXiv 2506.02881.
- **Outcome:** online adoption, the ticket's §5 secondary metric (first open of a new game from `main_list`, then play on
  ≥ 2 distinct days within 7 days).
- **Needs:**
  - Product's OK: the slot costs HR@10 by construction, because position 10 loses its ranked game.
  - A ticket change for Yann: the file column and the event field.

## Bar

- **Offline:** any ranker judged through the logged slot must pass the discovery track in [spec.md](../spec.md).
- **Online:** the POC decision rule (drafts/spec-game-list-impression-and-ab.md §5).
