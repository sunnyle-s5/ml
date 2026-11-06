# Experiments from the Netflix and Shopify recommender research (6 Nov 2026)

**Goal:** test the ideas from [the research note](../../notes/2026-11-06-netflix-shopify-recsys.md) that fit S5's game
lists.

## Tracks and bars

Both tracks are judged on 20 scored clusters × 2 frozen weeks.
- **HR@10 track:** ≥ +0.5 pt pooled HR@10, better on ≥ 15/20 clusters, new-game HR not lower.
- **Discovery track:** ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters, HR@10 no worse than −0.2 pt pooled.

## Rules

- **Stage 0 runs before any build.**
  - Each Tier A issue has an oracle ceiling in
    [experiments/2026-11-06-research-bounds/](../../experiments/2026-11-06-research-bounds/README.md).
  - An issue goes to stage 1 only if its ceiling clears its track's bar in both weeks.
- **Re-open rule.** An idea rejected earlier here is re-opened only when a source addresses the reason it failed, and only
  as an issue whose first step is a ceiling check against a pre-registered bar.
- **[ADR 0001](../../docs/adr/0001-player-data-stays-on-the-vm.md):** player data stays on the VM. Catalogue-only data
  may reach an external LLM/VLM API only with sunny's explicit OK for each run.
- **Online challengers** go one at a time, inside the holdout design (`drafts/plan-after-poc.md` §4).
- **AGENTS.md §1 hard rules** apply to every issue.
- **Order:** 02 waits for 01. 03 and 04 are independent of each other and of 01.

## Issues

|NN|Title|Tier|Track|Status|
|---|---|---|---|---|
|01|[New candidate sources, judged by the hits they add](issues/01-candidate-sources.md)|A|both|ready-for-agent|
|02|[Sequence model trained on the next-7-day set](issues/02-horizon-set-sequence-model.md)|A|both|ready-for-agent, blocked by 01|
|03|[Adoption-weighted ranker labels](issues/03-adoption-weighted-labels.md)|A|discovery|wontfix (v4a: ±0.01 pt)|
|04|[A per-player "will discover" prediction sets the new-slot count](issues/04-discover-intent-split.md)|A|both|ready-for-agent (intent features tested in v4: flat; threshold policy open)|
|05|[Cold start for fresh games](issues/05-fresh-game-cold-start.md)|A|both|wontfix (stage 0 failed)|
|06|[Exploration slot with a logged draw probability](issues/06-exploration-slot.md)|B|discovery|needs-triage, blocked by the POC|
|07|[Does the list cause play? Randomised nudges](issues/07-randomised-nudges.md)|B|—|needs-triage, blocked by the POC|
|08|[POC and rollout measurement inputs](issues/08-poc-rollout-measurement.md)|B|—|needs-triage|
