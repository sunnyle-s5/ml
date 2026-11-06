# Review of "Building an In-House LLM-Based Casino Game Recommender (2026)" as v3, for HR@10 (5 Nov 2026, sunny)

**Scope.** Maximising HR@10. Responsible-gambling material is left for another session. The reference architecture was checked against what we already run and against measurements on our data: 20 clusters, frozen weeks as of 19 and 26 Oct, read-only. No LLM was called, and nothing was sent out.

## 1 · Bottom line

- **Worth shipping (provisional): a learned list that ranks the player's own games and new games together.**
  - Its form is the guide's "retrieve → rank" pattern applied to the whole list.
  - Effect: +1.13 pt HR@10 over the default (92.05 → 93.18 %), above the default on 20/20 clusters, and +0.40 pt over simply giving own games 8 slots. On ADDA7: 93.77 → 94.46 %.
  - It comes from learning *which* own games a player returns to.
  - A version that keeps today's 3/5 slots and only picks the own games better gives +0.77 pt, with no loss of new-game HR.
  - Source: `experiments/2026-11-05-v3-unified/`.
- **Also worth it: cold players' first day.** Returning cold players should see their own older games first: day-one HR@10 +12.7 to +17.8 pt. The newcomer list does not clear the bar. Source: `experiments/2026-11-05-v3-cold-day1/`.
- **Not worth it for HR@10:**
  - LLM catalogue enrichment: the content signal it could add would recover at most 0.20 pt of HR@10 (misses it could reach, as a share of all scored players).
  - Persona summaries, LLM teacher and distilled rankers, semantic IDs, HSTU, OneRec.
  - Exploration and diversity re-ranking.
  - Details in §2 and §5.

## 2 · Verdicts on the v3 ideas

| v3 idea | Verdict for HR@10 | Evidence |
|---|---|---|
| A. LLM-enriched game metadata and embeddings | **Not worth it** | Our catalogue has names, a provider and a lobby category only; no rules text, RTP or descriptions (`snap.games`). The closest content signal we can measure, a sequel or edition of an own game (same provider and name stem), could recover at most 0.20 pt of HR@10 pooled (share of scored players), and 0.95 pt at most in any cluster-week (`experiments/2026-11-05-v3-misses/out/summary.md`). The bar was 1.0 pt. |
| B. LLM persona / intent summaries | **No route to HR@10** | The guide places them in CRM and explanations. |
| C. Retrieve → rank with a GBDT ranker | **Adopt, extended to own games** | Already ours for the new slots (step-14 LightGBM). Extending it to own games: +1.13 pt (§3). |
| D. LLM reranker as offline teacher | **Skipped** | It adds no signal beyond play data, and player histories would have to leave the VM. The guide itself says LLM "relevance" judges semantic fit, not what players play. |
| E. Distilled small ranker | **Not applicable** | Needs a teacher (D). |
| F/G. Semantic IDs, generative retrieval, HSTU / OneRec | **Not worth it** | The guide's own evidence comes from billion-interaction, million-item platforms, and our catalogue is a few thousand games per brand. SASRec, the simplest sequential model, already lost to the recency default (`notes/2026-11-05-model-options.md`). |
| H. Conversational / chat recommender | **Not HR@10** | It's a separate surface. |
| Real-time / in-session features | **Not tested** | Lists are already rebuilt daily. Refreshing own games within the day would repeat the site's `last_played` row. |
| Weighted positives (session ≥ 2 min, return within 7 days) | **Moves the target away from HR@10** | Useful only if the goal changes to adoption (`experiments/2026-11-05-v2-adoption/`). |
| Stake bands as a feature | **Already in the ranker** | `p_bpr_log`, `stake_gap` (`pull/step14_ltr.py:57-60`). |
| Context (time of day, device) | **Not applicable** | The metric is weekly, and the VM has no device data. |
| Cold-start routing / segment popularity | **Partly** | Own older games for returning cold players: fires. A newcomer list: does not (§3). |
| Exploration slots, MMR, provider diversity | **Lowers HR@10 by construction** | They trade hits for discovery. |
| Off-policy evaluation | **After the POC** | Needs logged impressions and propensities. |

## 3 · Results

### Miss anatomy (`experiments/2026-11-05-v3-misses/out/summary.md`, 40/40 cluster-weeks, oracle check passed)

pt of scored players, all 20 clusters. A miss = a scored player who plays none of the default list's top 10. The levers overlap.

| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Misses | 7.6 % | 7.9 % |
| Own game outside the list (… ranked 6–10) | 2.14 (1.46) | 2.11 (1.44) |
| Ranker pick ranked but not shown | 0.96 | 1.00 |
| Lapsed game | 0.47 | 0.50 |
| Sequel / edition of an own game | 0.20 | 0.20 |
| Live Popular top 50 | 2.98 | 3.43 |

### Unified own + new ranker (`experiments/2026-11-05-v3-unified/out/summary.md`)

Trained on 20–26 Oct, tested on 27 Oct–2 Nov. All 20 clusters pass the rebuilt-default and heavy-8 checks.

| Variant | HR@10 | Δ | Clusters above default | New-game HR |
|---|---|---|---|---|
| Stored default | 92.05 % | — | — | 19.4 % |
| Rule: 8 continue slots | 92.78 % | +0.73 | 20/20 | 16.1 % |
| Rule: 10 continue slots | 92.84 % | +0.79 | 20/20 | 12.6 % |
| Unified: learned continue (3/5) | 92.83 % | +0.77 | 20/20 | 19.4 % |
| **Unified: top 10** | **93.18 %** | **+1.13** | **20/20** | 14.0 % |

- The gain is positive in every market: from +0.38 pt (CO) to +1.70 pt (MX).
- The top features are all own-game history: days ratio, play days, days since last play, recency rank. Together they are 80 % of gain.

### Cold players' day-one list (`experiments/2026-11-05-v3-cold-day1/out/summary.md`, 40/40 cluster-weeks, v2 checks passed)

| Day-one HR@10 | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| All cold: live list vs newcomer list | 64.2 % vs 67.4 % | 62.9 % vs 64.9 % |
| Returning: live list vs own older games | 58.4 % vs 76.2 % | 61.7 % vs 74.4 % |
| bdk1: newcomer − live / own older − live (pt) | +9.2 / +12.7 | +1.4 / +9.8 |

## 4 · Recommendations (not applied; for decision)

1. **Unified top 10 as the treatment list** (provisional).
   - It passes the bar: ≥ 0.5 pt pooled and ≥ 15/20 clusters; it wins by +1.13 pt on 20/20 and beats the 8-slot rule by more than 0.2 pt.
   - Re-test after Wed 11 Nov 07:00 +07: run `bin/py experiments/2026-11-05-v3-unified/run.py all`. It then also trains on 27 Oct–2 Nov and tests on the 2 Nov week. Update this note.
   - That 2 Nov snapshot is the first built with step-16 EASE on (`meta.ranker_ease_cands` = 30; the 19 and 26 Oct snapshots have none). A shift in the stored default or in the ranker-rank features that week is a pipeline change, not model drift.
   - Caveat: the gain is mostly own-game replays. New-game HR falls 19.4 → 14.0 %, and the site's last_played row may already show some of those games. The cold-player L3 gain is replays of own older games in the same way.
   - If Product wants to keep discovery: "learned continue (3/5)" gives +0.77 pt at unchanged new-game HR.
   - Production: one extra LightGBM per cluster in `build_recs.py`, trained on the previous week. This is a patch for Yann.
2. **Returning cold players: own older games, then the live list.** Day-one +12.7 / +17.8 pt pooled; on bdk1 +12.7 / +9.8. This agrees with v2's weekly rule R5.
3. **Newcomers: keep the live list.** The newcomer list misses the 2.0 pt bar on bdk1 (+1.4) in the 27 Oct–2 Nov week.
4. **Not adopted:** all LLM components for the lobby.

## 5 · Not worth trying here, and why

- **LLM content enrichment.** Bounded at 0.20 pt of HR@10 (misses reachable, as a share of scored players) on our names-only catalogue. Revisit only if the site can export rules or paytable text, or if new games make up a large share of plays.
- **Generative recommenders (TIGER, HSTU, OneRec), persona LLMs, LLM teachers.** Their published wins need data and catalogue scale we don't have. Our sequential baseline (SASRec) already lost.
- **Lapsed-game candidates** (0.47–0.50 pt), **sequel matching** (0.20 pt) and **diversity re-ranking** (negative by construction).
