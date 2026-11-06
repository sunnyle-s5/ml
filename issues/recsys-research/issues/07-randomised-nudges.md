# 07 · Does the list cause play? Randomised nudges

Status: needs-triage
Blocked by: POC launch with impression logging (drafts/spec-game-list-impression-and-ab.md), external
Tier: B
Track: — (a measurement, not a challenger)
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Netflix, "The Value of Personalized Recommendations: Evidence from Netflix"** (https://arxiv.org/abs/2511.07280;
  blog https://netflixtechblog.com/measuring-the-impact-of-personalized-recommendations-4c26be3a4d96).
  - Reverting to random, popularity or matrix factorization "would reduce engagement by 16%, 12%, and 4%".
  - The targeting effect is "nearly 7 times larger" than the exposure effect.
  - The effect of a recommendation is identified with small randomised "nudge" tests.
- **Netflix, RecSys '23 "Navigating the Feedback Loop in Recommender Systems"**
  (https://recsys.acm.org/recsys23/accepted-contributions, abstract only) **and "Beyond Raw Engagement: A
  Counterfactual Observability Framework for Recommender Systems at Netflix"** (https://arxiv.org/abs/2609.22747, abstract
  only). Raw engagement mixes the recommender's effect with what users would have done anyway.
- **Here: offline HR@10 credits games players would have found anyway.**
  - The POC ticket says so (drafts/spec-game-list-impression-and-ab.md §2).
  - 88–98 % of the offline gain over the Popular list comes from pinning the player's own games
    (notes/2026-11-05-v2-spec-review.md, X1).

## Question

How much does showing a new game at a given position raise the chance that it is opened and played, compared with not
showing it?

## Design

- **The nudge.** For 10 % of arm-B player-days (a hash of player + `list_date`), position 8 is replaced with a new game
  drawn uniformly from the ranker's new candidates ranked 11–30.
- **Logging.** The nudged row gets `slot = 'nudge'`.
- **Outcome.**
  - Compare the open and play rate of nudged games with the same games among the other 90 % of player-days. The
    difference is the causal exposure effect.
  - Then compare that effect with the offline HR@10 credit at position 8.
- **Needs:** Product's OK, and the same ticket change as issue 06 (file column, event field).

## Bar

No ship bar. The result tells us how much of the offline HR@10 credit to believe.
