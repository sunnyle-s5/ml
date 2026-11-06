# Netflix and Shopify recommender research: what S5 should test (6 Nov 2026, read-only, sunny)

**Scope**
- **What was read:** 70 first-party items (48 Netflix, 22 Shopify), dated Apr 2022 – Oct 2026, all read on 6 Nov.
  - All but three are from 2023 on. The three 2022 items (C19, S1, S12) are kept because later work builds on them.
  - Sources: the Netflix tech blog and research site, the Shopify engineering blog, arXiv, ACL and RecSys pages.
- **Blog access:** netflixtechblog.com returns HTTP 403, so its posts were read through Wayback `id_` snapshots and the
  blog's tag feeds.
- **Verification:**
  - The 12 claims that the suggestions rest on (V1–V12) were re-opened at source by a second reader.
  - Numbers in this note come only from those 12 claims or from our own data. Every other item gets a description and
    a URL.
- **Out of scope:** responsible gambling.
- **Paths:** repo paths are under `/home/ubuntu/ml/` unless they start with `experiments/`, `notes/`, `drafts/`,
  `issues/`, `docs/` or `pipeline/` (this folder).

## 1 · Bottom line

- **Four ideas pass stage 0 and are ready to build** (`issues/recsys-research/`):
  - **01 new candidate sources, judged by the hits they add** (Shopify): room `b01_hr` 4.77 / 5.15 pt HR@10 and
    `b01_adopt` 4.29 / 4.69 pt adopted-game HR (20–26 Oct / 27 Oct–2 Nov). This room is measured against the stored
    top 10s, not the ranker's real pool, which reaches more, so it is the loosest of the bounds.
  - **02 a sequence model trained on next-7-day sets** (Netflix, Shopify): shares 01's room and runs only after 01.
  - **03 adoption-weighted ranker labels** (Netflix): room 1.61 / 1.70 pt adopted-game HR.
  - **04 a per-player "will discover" split** (Netflix): room 1.73 / 1.71 pt HR@10, and a thin 0.37 / 0.40 pt
    adopted-game HR.
  - These are oracle ceilings, not gains. Each issue's stage 1 must show how much of the room a real model reaches.
- **One idea fails stage 0:** **05 cold start for fresh games.** Its room is 0.09 / 0.13 pt HR@10 and 0.09 / 0.14 pt
  adopted-game HR, against bars of 0.5 and 0.3. Fresh games are too small a share of what scored players play, so
  thumbnail embeddings and LLM tags are not worth building now.
- **What does not transfer:**
  - GPU-scale foundation and LLM models (G9–G11) and LLM agent simulation (L12, L14). Reasons: the catalogue scale, the
    CPU-only VM, and ADR 0001 (player data stays on the VM).
  - The transferable parts of Netflix's and Shopify's generative recommenders are their training targets and yardsticks
    (issues 01–03), not the models.
- **Two corrections to the v3 review** (`notes/2026-11-05-v3-arch-review.md`):
  - Its 0.20-pt content bound covered name-stem sequels only. Content is now bounded by issue 05's stage 0, and that
    bound fails too.
  - The catalogue has a deterministic title key (`productId` + `code` in `game_<c>.rawData`), so matching a game across
    clusters needs no LLM.
- **Decisions recorded:**
  - Two tracks with bars ([spec](../issues/recsys-research/spec.md)).
  - [ADR 0001](../docs/adr/0001-player-data-stays-on-the-vm.md).
  - New glossary terms Game, Fresh game, Adopted-game HR and Exploration slot; revised Personal list and Continue slots
    (`GLOSSARY.md`).

## 2 · Experiments

|#|Experiment|Tier|Track|Borrowed from|Stage-0 bound, 20–26 Oct / 27 Oct–2 Nov (pt)|Status|
|---|---|---|---|---|---|---|
|01|New candidate sources (iALS, RP3beta, play transitions, cross-cluster popularity), judged by incremental recall|A|both|L1, C5|`b01_hr` 4.77 / 5.15; `b01_adopt` 4.29 / 4.69|ready-for-agent|
|02|Sequence model trained on the next-7-day set, with time gaps|A|both|G3, L2, G1|shares 01|ready-for-agent, blocked by 01|
|03|Adoption-weighted ranker labels, exp(r/λ)|A|discovery|G8, C1, G7|`b03_adopt` 1.61 / 1.70|ready-for-agent|
|04|A per-player "will discover" prediction sets the new-slot count|A|both|G6, C26|`b04_hr` 1.73 / 1.71; `b04_adopt` 0.37 / 0.40|ready-for-agent|
|05|Cold start for fresh games: cross-cluster prior → CLIP thumbnails → optional API tags|A|both|G13, G1, L7|`b05_hr` 0.09 / 0.13; `b05_adopt` 0.09 / 0.14|wontfix|
|06|Exploration slot with a logged draw probability|B|discovery|S1, G13|after the POC|needs-triage|
|07|Randomised nudges: does the list cause play?|B|—|C15|after the POC|needs-triage|
|08|POC and rollout measurement inputs|B|—|C16–C19, C24|—|needs-triage|

## 3 · Stage-0 bounds

Source: [experiments/2026-11-06-research-bounds/](../experiments/2026-11-06-research-bounds/README.md). The run covered
20 scored clusters × as-of 19 and 26 Oct, and all 40 cluster-weeks passed every check:
- the rebuilt default equals the stored default exactly;
- heavy 3 equals slot-split's heavy 3;
- adopted-game HR equals X2's.

Bounds are oracle ceilings, in pt of scored players.

|Bound|Bar|20–26 Oct|27 Oct–2 Nov|Cluster range|Clusters ≥ bar|Gate|
|---|---|---|---|---|---|---|
|`b01_hr`|0.50|4.77|5.15|3.48–8.90; 3.82–12.94|20/20; 20/20|PASS|
|`b01_adopt`|0.30|4.29|4.69|1.84–6.54; 1.93–6.96|20/20; 20/20|PASS|
|`b03_adopt`|0.30|1.61|1.70|0.62–2.67; 0.81–2.34|20/20; 20/20|PASS|
|`b04_hr`|0.50|1.73|1.71|0.83–3.03; 0.89–2.51|20/20; 20/20|PASS|
|`b04_adopt`|0.30|0.37|0.40|0.15–0.59; 0.15–0.63|15/20; 12/20|PASS|
|`b05_hr`|0.50|0.09|0.13|0.01–0.26; 0.00–0.53|0/20; 1/20|FAIL|
|`b05_adopt`|0.30|0.09|0.14|0.00–0.23; 0.00–0.55|0/20; 3/20|FAIL|

- **Stand-in for the real pool.** The stored new-game top 10s (U) hold a new test-week game for 25.9 / 28.0 % of scored
  players. The ceiling is 38.8 / 41.7 %.
- **Fresh games are rare in play.** 0.75 / 0.87 % of scored players played a new fresh game at all.
- **TH catalogue jump.** TH's 7 clusters listed 487–957 fresh titles each as of 26 Oct.
  - Most are a bulk catalogue addition: 923 titles dated 22 Oct on 96g1, for example.
  - The fresh-game bound in TH was still only 0.21 pt HR@10 that week, so fresh by catalogue date is not fresh to players.

## 4 · Netflix

Verdicts name the issue an item feeds or why it is not used. "Abstract only" means nothing beyond the abstract was readable.

### 4.1 Foundation and generative models

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|G1|[Foundation Model for Personalized Recommendation](https://netflixtechblog.com/foundation-model-for-personalized-recommendation-1a0bd8e02d39) (21 Mar 2025)|One autoregressive model over member interactions. Interactions are merged into tokens and plays are weighted. It has a multi-token objective and an age-gated mix of metadata and ID embeddings for new titles|Supports 02 (multi-token objective) and 05 (metadata/ID mix, ID dropout)|
|G2|[Integrating Netflix's Foundation Model into Personalization applications](https://netflixtechblog.medium.com/integrating-netflixs-foundation-model-into-personalization-applications-cf176b5860eb) (17 Nov 2025)|Three ways applications use the model: embeddings as features, a subgraph inside the application model, or fine-tuning|Supports 02: if a sequence model is built, feed its embeddings to the LightGBM ranker first|
|G3|[Towards Generalizable and Efficient Large-Scale Generative Recommenders](https://netflixtechblog.com/towards-generalizable-and-efficient-large-scale-generative-recommenders-a7db648aa257) (blog 1 Jan 2026; [paper](https://arxiv.org/abs/2605.23312))|Scaling laws, multi-token prediction over a time-decayed set of future items, and OOV masking for cold start. With 48 h cached serving, multi-token prediction gives "+22.1%, +27.8%, and +27.9% relative MRR for Tasks A, B, and C"|Issue 02: our lists are also cached and judged over a horizon|
|G4|[Sliding Window Training](https://arxiv.org/abs/2409.14517) (RecSys '24)|Sample a different history window each epoch, so the model sees long histories while serving a short one|Not proposed: snapshots hold 60 days. A cheap variant is more label weeks in the 11 Nov re-run of the unified ranker|
|G5|[Orthogonal Low Rank Embedding Stabilization](https://arxiv.org/abs/2508.07574) (Aug 2025; RecSys '25)|Rotates each retrain's embeddings onto a fixed basis so that downstream features keep their meaning|Not needed: ALS and EASE features are rebuilt inside each build|
|G6|[FM-Intent](https://netflixtechblog.com/fm-intent-predicting-user-session-intent-with-hierarchical-multi-task-learning-94c75e18f4b8) (21 May 2025; [IntentRec](https://arxiv.org/abs/2408.05353))|Predicts session intent first, including "discovering new content versus continuing previously started content", and feeds it to the item head: "7.4% in next-item prediction accuracy compared to the best baseline (TransAct)"|Issue 04|
|G7|[Post-Training Generative Recommenders with Advantage-Weighted Supervised Finetuning](https://netflixtechblog.com/post-training-generative-recommenders-with-advantage-weighted-supervised-finetuning-61a538d717a9) (24 Oct 2025)|Reweights supervised loss by an advantage instead of running RL, when logging propensities are unknown|Supports 03|
|G8|[Exponential Reward Weighting for Fine-Tuning Generative Recommenders](https://arxiv.org/abs/2608.00816) (Aug 2026; companion [2603.10279](https://arxiv.org/abs/2603.10279))|Weights each logged interaction by exp(r/λ). On StreamCo vs linear reward weighting: HR@10 +98.07 %; PPO −14.66 %; best at λ≈0.5–1.0|Issue 03|
|G9|[GenRec: Towards LLM-Native Recommendation at Netflix](https://netflixtechblog.com/genrec-towards-llm-native-recommendation-at-netflix-f20be6f643e3) (30 Jul 2026; [paper](https://arxiv.org/abs/2608.10257))|An LLM ranker over verbalised histories with a catalogue-aware ranking head|Not proposed: GPU-scale, and it would send player histories off the VM (ADR 0001)|
|G10|[Personalized LLM Recommendation with Semantic IDs](https://arxiv.org/abs/2610.15864) (Oct 2026)|Semantic-ID decoding in an LLM: beam search vs multi-token heads|Not proposed: GPU-scale LLM fine-tuning|
|G11|[LLM Reasoning for Cold-Start Item Recommendation](https://arxiv.org/abs/2511.18261) (WWW '26)|A large LLM re-ranks the production top 40 for titles newer than its training data|Not proposed: GPU-scale, player histories off the VM, and cold start fails stage 0 (05)|
|G12|[Netflix Artwork Personalization via LLM Post-training](https://arxiv.org/abs/2601.02764) (Jan 2026)|An LLM picks per-member artwork from captioned images|Not applicable: no per-game artwork choice|
|G13|[MAPS: Netflix's Multimodal Asset Personalization at Scale](https://netflixtechblog.com/maps-netflixs-multimodal-asset-personalization-at-scale-32f96320785e) (28 Aug 2026)|Concatenates a CLIP image embedding with the learned ID embedding. "V1 and V2 were both flat and non-significant, and only V3 won". IPS on an exploration slice; a linear probe gates embedding versions|Issue 05 (wontfix after stage 0); its IPS-on-exploration pattern feeds 06|
|G14|[The Lifecycle of LLM-as-a-Judge](https://netflixtechblog.com/the-lifecycle-of-llm-as-a-judge-building-aligning-and-monitoring-at-scale-c95bd8283508) (Sep 2026; [paper](https://arxiv.org/abs/2608.18300))|Building, aligning and monitoring an LLM judge for generated explanations|Not applicable: we generate no text|
|G15|[Scaling LLM Post-Training at Netflix](https://netflixtechblog.com/scaling-llm-post-training-at-netflix-0046f8790194) (13 Feb 2026)|GPU infrastructure for SFT, DPO and RL|Not applicable|
|G16|[Collaborative Retrieval for LLM-based Conversational Recommender Systems](https://arxiv.org/abs/2502.14137) (WWW '25)|Grounds a conversational LLM with collaborative-filtering retrieval|Not applicable: no conversational surface|
|G17|[Large Language Models as Zero-Shot Conversational Recommenders](https://arxiv.org/abs/2308.10053) (Aug 2023)|Probes LLMs as conversational recommenders|Not applicable|
|G18|[Reindex-Then-Adapt](https://arxiv.org/abs/2405.12119) (May 2024)|Single-token item ids for LLM conversational recommendation|Not applicable|
|G19|[LLM-based Conversational Recommendation Agents with Collaborative Verbalized Experience](https://aclanthology.org/2025.findings-emnlp.119/) (EMNLP 2025 Findings)|Retrieved reasoning traces for conversational agents|Not applicable|
|G20|[Rank-GRPO](https://arxiv.org/abs/2510.20150) (Oct 2025)|RL with per-rank credit for LLM conversational recommenders|Not applicable|
|G21|[Mult-DPO](https://arxiv.org/abs/2606.10078) (Jun 2026)|A set-wise preference optimisation objective for recommenders|Not applicable: aimed at LLM alignment|

### 4.2 Ranking, rewards and the value of recommendations

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|C1|[Recommending for Long-Term Member Satisfaction at Netflix](https://netflixtechblog.com/recommending-for-long-term-member-satisfaction-at-netflix-ac15cada49ef) (29 Aug 2024)|Proxy rewards for long-term satisfaction, with delayed feedback predicted by a separate model|Issue 03|
|C2|Reward innovation for long-term member satisfaction ([RecSys '23](https://recsys.acm.org/recsys23/accepted-contributions), abstract only)|Treats the reward as a product lever, tested separately from the model|Supports 03|
|C3|[Lessons Learnt From Consolidating ML Models](https://netflixtechblog.medium.com/lessons-learnt-from-consolidating-ml-models-in-a-large-scale-recommendation-system-870c5ea5eb4a) (24 Aug 2023)|One multi-task model with a task-type feature instead of many models|Not proposed: a maintenance gain, not HR@10. Revisit if build time near the 07:00 check binds|
|C4|[UniCoRn](https://arxiv.org/abs/2408.10394) (RecSys '24)|One model for search and recommendations|Not applicable: no search surface|
|C5|[Does Weighting Improve Matrix Factorization for Recommender Systems?](https://arxiv.org/abs/2510.10440) (WWW '25)|"training with unweighted data can perform comparably to, and sometimes outperform, training with weighted data, especially for large models"|Issue 01 (iALS α sweep)|
|C6|[Is Cosine-Similarity of Embeddings Really About Similarity?](https://arxiv.org/abs/2403.05440) (WWW '24 Companion)|Cosine on regularised factor embeddings can be arbitrary|Supports 05: use cosine only on embeddings trained for it|
|C7|[Optimizing Recommendation Systems with JDK's Vector API](https://netflixtechblog.com/optimizing-recommendation-systems-with-jdks-vector-api-30d2830401ec) (3 Mar 2026)|A serendipity feature, 1 − max similarity to history, computed as one matmul|Supports 05 (novelty feature)|
|C8|[Synergistic Signals](https://arxiv.org/abs/2312.04071) (Dec 2023, abstract only)|A GNN over co-engagement and semantic links for new and unpopular titles|Not proposed: our metadata is thin|
|C9|Cold Starting a New Content Type: Netflix Live ([RecSys '25](https://recsys.acm.org/recsys25/accepted-contributions), abstract only)|Cold start for a whole new content type, tested online|Supports 05|
|C11|Navigating the Feedback Loop in Recommender Systems ([RecSys '23](https://recsys.acm.org/recsys23/accepted-contributions), abstract only)|Offline simulation as a surrogate for feedback-loop bias|Supports 07|
|C12|[Thinking Fast & Slow for a Personalized Notification System](https://netflixtechblog.com/thinking-fast-slow-for-a-personalized-notification-system-4d89b26525cd) (19 Jun 2026)|A weekly pacing policy plus per-message choice, with a message cost|Not applicable: we send no notifications|
|C13|[Causal Machine Learning for Creative Insights](https://netflixtechblog.com/causal-machine-learning-for-creative-insights-4b0ce22a8a96) (2023)|Double ML on artwork attributes|Not proposed: needs impressions|
|C14|[Beyond Raw Engagement: A Counterfactual Observability Framework](https://arxiv.org/abs/2609.22747) (Sep 2026, abstract only)|Report model performance as incremental over a counterfactual|Supports 07|
|C15|[Measuring the Impact of Personalized Recommendations](https://netflixtechblog.com/measuring-the-impact-of-personalized-recommendations-4c26be3a4d96) (blog 14 Oct 2026; [paper](https://arxiv.org/abs/2511.07280))|A choice model identified with randomised nudges. Reverting to random, popularity or MF "would reduce engagement by 16%, 12%, and 4%"; the targeting effect is "nearly 7 times larger" than exposure|Issue 07|
|C16|[Recommendation Quality and the Concentration of Consumption](https://arxiv.org/abs/2608.21274) (Aug 2026, abstract only)|A better recommender moved consumption from the most popular titles toward moderately popular ones|Issue 08 (popularity-tier metric)|

### 4.3 Experimentation

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|C17|[Sequential A/B Testing Keeps the World Streaming Netflix Part 1: Continuous Data](https://netflixtechblog.com/sequential-a-b-testing-keeps-the-world-streaming-netflix-part-1-continuous-data-cba6c7ed49df) (13 Feb 2024)|Anytime-valid tests on quantiles. Under peeking, "66 out of 100 A/A simulations falsely rejected the null hypothesis" (figure caption; the body says 70 %)|Issue 08|
|C18|[Sequential Testing Keeps the World Streaming Netflix Part 2: Counting Processes](https://netflixtechblog.com/sequential-testing-keeps-the-world-streaming-netflix-part-2-counting-processes-da6805341642) (18 Mar 2024)|A sequential p-value from per-arm counts and assignment probabilities|Issue 08|
|C19|[Anytime-Valid Linear Models and Regression Adjusted Causal Inference](https://arxiv.org/abs/2210.08589) (Oct 2022)|CUPED-like adjustment that stays valid under peeking|Issue 08|
|C20|[Evaluating the Surrogate Index Using 200 A/B Tests at Netflix](https://arxiv.org/abs/2311.11922) (Nov 2023)|Short-term surrogates for long-term ship decisions|Not proposed: no long-term outcome has been chosen|
|C21|[Learning Better Proxy Metrics From Past Experiments](https://netflixtechblog.com/improve-your-next-experiment-by-learning-better-proxy-metrics-from-past-experiments-64c786c2a3ac) (26 Aug 2024)|Proxy weights learned across many past experiments|Not applicable: we have none yet|
|C22|[Return-Aware Experimentation](https://netflixtechblog.medium.com/return-aware-experimentation-3dd93c94b67a) (30 Jul 2025; [paper](https://arxiv.org/abs/2502.08763))|Decision rules scored on held-out units across past tests|Not applicable: we have no test portfolio|
|C23|[Optimizing Returns from Experimentation Programs](https://arxiv.org/abs/2412.05508) (Dec 2024)|Test size and thresholds set for cumulative return|Not proposed yet: relevant once several challengers queue|
|C24|[Round 2: A Survey of Causal Inference Applications at Netflix](https://netflixtechblog.com/round-2-a-survey-of-causal-inference-applications-at-netflix-fd78328ee0bb) (6 Jun 2024)|Synthetic-control family for game- and country-level changes, chosen by pre-period fit and checked by backdating|Issue 08 (rollout analysis)|
|C25|[Large Scale Longitudinal Experiments](https://arxiv.org/abs/2410.09952) (Oct 2024)|Compressed panel regressions for repeated measures|Not proposed: CUPED is already in the ticket|
|C26|[Treatment Effect Modification by Latent Classes](https://arxiv.org/abs/2610.10851) (Oct 2026, abstract only)|Effects of a recommender differ by latent state (heavy, less active, rewatch)|Supports 04|
|C27|[Simulation-Based Inference for Adaptive Experiments](https://arxiv.org/abs/2506.02881) (Jun 2025, abstract only)|Valid inference after bandit allocation|Supports 06|
|C28|[Netflix Original Research: MIT CODE 2023](https://netflixtechblog.com/netflix-original-research-mit-code-2023-9340b879176a) (27 Nov 2023)|Talk summaries: surrogates and one weighted overall evaluation criterion|Already ours: the POC pre-registers one primary metric|

## 5 · Shopify

### 5.1 Generative recommender, sequence models and retrieval

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|L1|[The generative recommender behind Shopify's commerce engine](https://shopify.engineering/generative-recommendations) (25 Feb 2026)|An HSTU retriever trained with "a boosting-inspired approach that increases training pressure on the parts of the space where the ensemble is weak". "Shop orders increased by 0.94% relative"|Issue 01 (the yardstick); also the reference design for 02|
|L2|[T-RoPE: Time-Aware Rotary Position Embedding for Sequential Recommendation](https://arxiv.org/abs/2609.30576) (Sep 2026)|Timestamps instead of positions in the rotary encoding. Amazon Books HR@10 7.65 vs 6.89 for the best baseline; Shop app conversion "+0.33%, p=0.037"|Issue 02|
|L11|[Foundation Models for Agentic and Counterfactual Decision Support](https://genai-ecommerce.github.io/) (RecSys '26 workshop keynote, abstract only)|A merchant-side sequence model with semantic IDs|Not applicable: models merchants|
|S1|[Optimizing product recommendations for millions of merchants](https://recsys.acm.org/recsys22/session-9/) (RecSys '22, abstract only)|Best strategy per segment from offline evaluation, then "adjust to the current environment using multi-armed bandits"|Issue 06|
|S3|[Foundational Generative Recommendations for E-Commerce](https://neurips.cc/virtual/2025/128667) (NeurIPS 2025 Expo, abstract only)|The same system as L1: contrastive learning with hard negatives and multi-scale time signals|Supports 02|
|S4|[Revisiting Generative vs. Dense Retrieval: A Static Value Prior Reverses the Gap](https://arxiv.org/abs/2610.19065) (CIKM '26)|A popularity/quality prior blended into dense retrieval explains much of generative retrieval's apparent lead; generative retrieval found almost no cold targets|Already ours: the ranker has popularity features|

### 5.2 Catalogue understanding and LLM/VLM

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|L3|[How Shopify improved consumer search intent with real-time ML](https://shopify.engineering/how-shopify-improved-consumer-search-intent-with-real-time-ml) (18 Oct 2024)|A streaming pipeline for text and image embeddings|Not needed: a nightly batch covers a few thousand games|
|L4|[Leveraging multimodal LLMs for Shopify's global catalogue](https://shopify.engineering/leveraging-multimodal-llms) (16 Jul 2025)|A fine-tuned VLM extracts attributes; LLM annotators plus an arbitrator make the labels|Supports 05 (optional step 3)|
|L5|[Evolution of Product Classification at Shopify](https://shopify.engineering/evolution-product-classification) (8 May 2025)|Two-stage VLM calls: category first, then that category's attributes|Supports 05 (optional step 3)|
|L6|[Beyond classification: AI agents evolving Shopify's product taxonomy](https://shopify.engineering/product-taxonomy-at-scale) (9 Oct 2025)|LLM agents propose taxonomy changes, gated by LLM judges|Not applicable: small, stable game schema|
|L7|[Clustering billions of products for agentic commerce with Catalog API](https://shopify.engineering/catalog-clustering) (17 Jun 2026)|Rules first ("Only a small percentage of shops actually require LLM-based clustering"), then nearest-neighbour batches, then LLM propose and critique|Supports 05; not needed: our title key is deterministic|
|L8|[Cross-store product clustering across millions of stores](https://shopify.engineering/catalog-clustering-part-ii) (20 Oct 2026)|A cascade of pair scorers; "L1 is a GBDT classifier that uses inexpensive pair features" and runs on CPU; LLM labels train the matchers|Supports 05; not needed: deterministic key|
|L10|[Augmented commerce: Machine learning at Shopify](https://shopify.engineering/machine-learning-at-shopify) (4 Jul 2025)|Overview: fine-tuned open text embeddings for search and recommendations, HSTU experiments|Supports 05 (an open text-embedding option)|
|L12|[SimPersona](https://arxiv.org/abs/2605.14205) (May 2026, abstract read)|Discrete buyer personas learned from clickstreams for LLM shopping agents|Not proposed: GPU LLM agents, not validated against real A/B tests|
|L15|[Shopify/product-taxonomy](https://github.com/Shopify/product-taxonomy) (version 2026-10)|An open, versioned category → attribute schema|Supports 05 (template for an attribute schema)|

### 5.3 Platforms and experimentation

|#|Item|What it is|Verdict for S5|
|---|---|---|---|
|L9|[Building world-class product search at Shopify](https://shopify.engineering/world-class-product-search) (12 Nov 2025)|GBDT rankers gated offline, then by A/B; purchase popularity over clicks|Already ours|
|L13|[ShopGym](https://shopify.engineering/shopgym) (1 Oct 2026; [paper](https://arxiv.org/abs/2605.16116))|Reproducible sandboxes for shopping agents|Not applicable|
|L14|[2,000 robots walk into a shop...](https://shopify.engineering/simgym) (27 Feb 2026)|LLM-simulated shoppers to pre-test storefront changes|Not proposed: GPU-heavy and not validated against real A/B results|
|S7|[Tangle](https://shopify.engineering/tangle) (5 Dec 2025)|An experiment-pipeline platform with content-hash caching|Not proposed: a Docker pipeline stack for runs that take minutes|
|S10|[Unlocking Real-time Predictions with Shopify's ML Platform](https://shopify.engineering/shopifys-machine-learning-platform-real-time-predictions) (10 Mar 2023)|Online inference and a feature store on Kubernetes|Not applicable: we serve batch lists|
|S11|[Monte Carlo Simulations: Separating Signal from Noise in Sampled Success Metrics](https://shopify.engineering/monte-carlo-simulations-sampled-success-metrics) (3 Jan 2023)|Simulate a metric to size a test|Already ours: the X9 MDE and CUPED sizing (`notes/2026-11-05-v2-spec-review.md`)|
|S12|[The Magic of Merlin](https://shopify.engineering/merlin-shopify-machine-learning-platform) (6 Apr 2022)|A Ray-based ML platform|Not applicable: one VM|

## 6 · POC and rollout inputs (not applied; for decision)

Issue 08 has three proposals. None has been applied to `drafts/`.
1. **Anytime-valid tests for the daily guardrail looks** (C17–C19):
   - opens and fallback counts with the Part 2 count test;
   - `listApiMs` p95 with the Part 1 quantile test;
   - opens per player with anytime-valid CUPED.
2. **A new secondary metric** (C16): the share of opens and rounds by the live Popular tier (ranks 1–10, 11–50, 51+).
3. **Rollout analysis** (C24): synthetic control or synthetic difference-in-differences per market, with the market's
   other brands as donors, checked by backdating.

## 7 · Could not verify, and gaps

**Caveats on the verified claims:**
- **V1 (G3):** the numbers come from the arXiv paper, not the blog (the blog has them only in figures). They are for
  "the best five-token window". The model sizes differ between the blog and the paper.
- **V7 (L2):** the reader assumed the first baseline column of the table is SASRec, because the column headers did not
  come through. The +11.0 % is against the best baseline, 6.89.
- **V8 (C15):** the blog text was read from a syndicated mirror, so the arXiv paper is the citation.
- **V10 (C17):** the "66 out of 100" figure caption and the body's "70%" disagree.

**Abstract only, or not fully read:** C2, C8, C9, C11, C14, C16, C26, C27, L11, L12, S1, S3.
- C2 and C9: the ACM full texts returned 403.
- C9: the method is unread.
- S1: the talk's segment definitions, bandit type and numbers are unread.

**Venues and dates seen only on author pages:** G10, G12 and IntentRec (G6). C13's publication date is inconsistent in
the blog feed.

**No first-party work found:**
- Netflix, 2023 on: Continue Watching ranking, EASE or EDLAE follow-ups, interleaving, long-term holdouts.
- Netflix: LLM-simulated users.
- Shopify: almost no classical recommender or experimentation work after 2022, no complementary-products write-up, and
  no Shopify paper at RecSys 2023–2025.

**Not read:**
- the MediaFM blog;
- Shopify's ICLR 2025 and NeurIPS 2025 talk videos;
- the Liquid AI partnership claims (Liquid AI's page, not Shopify's);
- the PRS workshop talks, whose pages were unreachable.
