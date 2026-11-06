# 05 · Cold start for fresh games

Status: wontfix
Tier: A
Track: both
Re-opens: LLM content enrichment ("not worth it" in `notes/2026-11-05-v3-arch-review.md` §5), under the re-open rule in
[spec.md](../spec.md)
Links: [spec](../spec.md) · [note](../../../notes/2026-11-06-netflix-shopify-recsys.md) ·
[stage 0](../../../experiments/2026-11-06-research-bounds/README.md) (`out/summary.md`)

## Why

- **The v3 bound was narrow.** It counted name-stem sequels only: 0.20 pt. The same-provider bucket was 4.11 pt
  (`experiments/2026-11-05-v3-misses/README.md`).
- **More content exists than v3 used.**
  - The snapshot has thumbnails (`games.img`).
  - The market cache has provider game codes (`game_<c>.rawData`: `productId`, `code`).
- **Netflix MAPS: image plus ID, and only the combination won.** Source:
  https://netflixtechblog.com/maps-netflixs-multimodal-asset-personalization-at-scale-32f96320785e.
  - The per-asset CLIP image embedding (768-d) is concatenated with the learned ID embedding.
  - "V1 and V2 were both flat and non-significant, and only V3 won a statistically significant lift".
  - A linear probe gates new embedding versions.
- **Netflix Foundation Model: lean on metadata while an item is new.** Source:
  https://netflixtechblog.com/foundation-model-for-personalized-recommendation-1a0bd8e02d39.
  - The title embedding mixes metadata and ID through "an attention mechanism based on the 'age' of the entity".
  - "Introducing some randomness during training encourages the model to learn from metadata rather than relying solely
    on ID embeddings".
- **Shopify: deterministic keys first.** Source: https://shopify.engineering/catalog-clustering: "Only a small percentage
  of shops actually require LLM-based clustering. The rest can be resolved deterministically". Here `productId` + `code`
  resolves every title, so matching needs no LLM.
- **Netflix on similarity features.**
  - Cosine is meaningful only on embeddings trained for it (https://arxiv.org/abs/2403.05440).
  - A "1 − max similarity to history" novelty feature
    (https://netflixtechblog.com/optimizing-recommendation-systems-with-jdks-vector-api-30d2830401ec).

## Question

How much HR@10 or adopted-game HR could a cold-start model for fresh games add at most, and is it enough to build one?

## Stage 0

- **Bounds.** `b05_hr` / `b05_adopt` = misses who played a new fresh game / not-adopted players who adopted a fresh game.
  Fresh = the title first appears in the cluster's catalogue in the 30 days up to the as-of date.
- **Result** (pt of scored players; experiments/2026-11-06-research-bounds/):

  |Bound|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
  |---|---|---|---|---|---|
  |`b05_hr`|0.09|0.13|0.01–0.26; 0.00–0.53|0/20; 1/20|FAIL|
  |`b05_adopt`|0.09|0.14|0.00–0.23; 0.00–0.55|0/20; 3/20|FAIL|

- **Reference.**
  - 0.75 / 0.87 % of scored players played a new fresh game at all.
  - 0.03 / 0.05 % played a game launched during the test week.
  - Misses on a sparse game (< 20 players in the brand's 60 days) are 0.49 / 0.61 pt.
  - Fresh titles summed over clusters: 1,973 / 6,760. The jump is bulk catalogue additions, not launches:
    - one `createdAt` day carries most of the window on TH clusters (22 Oct: 923 titles on 96g1, 455 on wdb1, 183 on kzg1);
    - kzg1 also had 492 titles on 30 Sep.
  - Fresh by catalogue date is therefore not fresh to players. The bound counts plays, so the verdict holds.
- **The bound already overstates.** The catalogue is the 2026-11-03 snapshot, so a title whose older id was removed looks
  fresh. It fails anyway.

## Decision

wontfix: `b05_hr` 0.09 / 0.13 pt < 0.5 pt and `b05_adopt` 0.09 / 0.14 pt < 0.3 pt in both weeks. Re-open if the bound
reaches the bar, e.g. after a catalogue or list change. The bar can only be reached if fresh games become a much larger
share of what scored players play.

## Stage 1 (only if re-opened)

Ordered; stop at the first step that clears a bar.
1. **Cross-cluster title prior, no ML.**
   - Measure coverage first: the share of fresh titles, and of their test-week plays, that have ≥ 14 days of history on
     another cluster.
   - Then add v3-unified features: the other clusters' 7-day player share for the title, and days since the title was
     first seen anywhere.
2. **Thumbnail embeddings** (local; ADR 0001).
   - CLIP ViT-B/32 via open_clip on CPU, in a venv at `scratch/venv-emb`, with the HF cache at `scratch/hf` (both
     gitignored).
   - Embed each distinct `img` once, in memory (no image files kept). Store the result in `out/emb_<c>.parquet`.
   - Features: max and mean cosine to the player's 5 most recent own games, and max cosine to the brand's live top 20.
3. **API tags** (optional).
   - Only with sunny's explicit OK for each run (ADR 0001).
   - Send only game `name`, provider and `img` URL: no player, member or brand ids.
   - Read the API key from an environment variable set in the shell. Never store it in a file under `/home/sunny/ml`,
     including `scratch/` (AGENTS.md §1 rule 8).
   - Tags: theme, mechanic and volatility cues from name + thumbnail.
   - A two-stage prompt (type → attributes, as in https://shopify.engineering/evolution-product-classification) and a
     schema pinned in the experiment.
- **Report** all scored players, plus the subset whose test-week new games include a fresh game.

## Bar

Both tracks, on 20 scored clusters × 2 frozen weeks:
- **HR@10:** ≥ +0.5 pt pooled HR@10, better on ≥ 15/20 clusters, new-game HR not lower.
- **Discovery:** ≥ +0.3 pt pooled adopted-game HR, better on ≥ 15/20 clusters, HR@10 no worse than −0.2 pt pooled.
