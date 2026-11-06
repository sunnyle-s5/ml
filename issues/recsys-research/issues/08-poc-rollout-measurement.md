# 08 · POC and rollout measurement inputs

Status: needs-triage
Tier: B
Track: — (measurement; not applied to the drafts; for decision)
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **Guardrails will be looked at every day.** The POC ticket allows "no early stop except on a guardrail breach"
  (drafts/spec-game-list-impression-and-ab.md §5).
  - Classical tests under repeated looks raise false alarms. In Netflix's simulation, "66 out of 100 A/A simulations
    falsely rejected the null hypothesis" under peeking ("Sequential A/B Testing Keeps the World Streaming Netflix Part 1:
    Continuous Data", Figure 2 caption,
    https://netflixtechblog.com/sequential-a-b-testing-keeps-the-world-streaming-netflix-part-1-continuous-data-cba6c7ed49df).
  - Netflix's Part 2 ("Counting Processes",
    https://netflixtechblog.com/sequential-testing-keeps-the-world-streaming-netflix-part-2-counting-processes-da6805341642)
    computes a sequential p-value from per-arm counts and assignment probabilities only.
  - Lindon et al. (https://arxiv.org/abs/2210.08589, listed in Netflix's sequential-testing post) make regression-adjusted
    (CUPED-like) inference anytime-valid.
- **Better recommenders change what is played, not only how much.** Netflix, "Recommendation Quality and the
  Concentration of Consumption" (https://arxiv.org/abs/2608.21274, abstract only): improvements diffused consumption from
  the most popular titles toward moderately popular ones.
- **Rollout goes one brand per market** (drafts/plan-after-poc.md §2). Netflix's causal-inference survey
  (https://netflixtechblog.com/round-2-a-survey-of-causal-inference-applications-at-netflix-fd78328ee0bb) evaluates
  game- or country-level changes with the synthetic-control family. It picks the variant by pre-period fit and checks it
  by backdating.

## Question

Which measurement changes should go into the POC ticket and the rollout plan?

## Design

Three proposals. None is applied to `drafts/`; each is for sunny and Yann to decide.

1. **Anytime-valid guardrail tests:**
   - opens and fallback counts per arm: the Part 2 count test, with the 17/17/33/33 assignment probabilities;
   - `listApiMs` p95: the Part 1 sequential quantile test;
   - opens per player: anytime-valid regression adjustment on the 28-day pre-period. On ADDA7, CUPED halves the variance
     of active days and bet (notes/2026-11-05-v2-spec-review.md, X9).
2. **A new secondary metric:** the share of opens and rounds by the brand's live Popular tier on the exposure day (ranks
   1–10, 11–50, 51+).
3. **Rollout analysis:**
   - synthetic control or synthetic difference-in-differences per market, with the market's other brands as donors;
   - choose the variant by pre-period fit and check it by backdating.

## Bar

No ship bar: these are measurement changes.
