# Model options: Step 16 (EASE), headroom, what to try next, SaaS (5 Nov 2026, read-only, sunny)

Answers Yann's question 2: is there a better model than the one being tried, or a SaaS that shortens the learning?
Repo paths are under `/home/ubuntu/ml/` unless they start with `experiments/`, `notes/` or `drafts/` (this folder).
Web sources were read on 4–5 Nov 2026.

## 1 · Step 16: EASE inside the ranker (shipped 4 Nov)

**What it is.**
- EASE (Steck 2019, https://arxiv.org/abs/1905.03375) is a closed-form item-to-item model.
- `fit_ease` (`pull/step14_ltr.py:65-74`) fits one per brand on a binary player × game matrix over the 60-day window, with
  λ = 200 (`pull/build_recs.py:90`). λ was swept only on the standalone list, where 200 gave the best new-game HR on mx96g1
  (`sasrec/ease_mx96g1_2026-10-26.out`).
- It adds the top 30 unplayed EASE games to the ranker's candidate pool (100 popular + 30 ALS + 30 EASE, `pull/build_recs.py:212-213`)
  and 3 features (`ease`, `ease_rank`, `is_ease_cand`; 29 → 32).
- The continue slots (own recent games) are untouched, so only the "new" slots of the default can change.

**Status.**
- Shipped by `sasrec/port_ease.py` ("Yann: 'Ship it'") on 4 Nov ~23:40 +07.
- `--ease-cands 30` is now the default (`pull/build_recs.py:89`), so every build from 5 Nov uses it. Off switch: `--ease-cands 0`.
- The model name is unchanged (`hybrid (recent continue + ranker new)`). Only the `meta` keys `ranker_ease_cands` and
  `ranker_ease_lam` show that EASE was on.

**Measured.** As of 2026-10-26 (test week 27 Oct–2 Nov), the frozen snapshot vs the same week rebuilt with EASE
(`sasrec/s14ease_<c>_2026-10-26.eval.out`, lines 3–9):

| Cluster | Scored players | Default HR@10 | Default new-game HR | Ranker (new games only) HR | Ranker trees |
|---|---|---|---|---|---|
| mxk1 | 86,197 | 86.6 → 86.7 % | 17.9 → 18.4 % | 23.2 → 23.7 % | 139 → 132 |
| kzg1 | 146,256 | 92.1 → 92.2 % | 17.5 → 18.1 % | 22.0 → 22.5 % | 107 → 165 |
| phk1 | 158,337 | 93.5 → 93.5 % | 19.4 → 19.7 % | 23.8 → 24.2 % | 160 → 69 |
| pkkz1 | 20,327 | 90.6 → 90.6 % | 13.9 → 13.9 % | 16.5 → 16.5 % | 204 → 116 |
| bdk1 | 285,405 | 93.4 → 93.4 % | 21.4 → 21.6 % | 24.7 → 24.9 % | 156 → 340 |

Standalone EASE in the new slots (instead of the ranker) is worse. On the 10 clusters with an eval, the default with EASE new
slots loses 0.3 to 1.2 pt HR@10 on all 10 and 0.0 to 2.1 pt new-game HR. The EASE new-only list beats the ranker's only on
brlkz1 (27.0 vs 26.8 %) (`sasrec/ease_all_2026-10-26.log`; bdk1: `sasrec/ease_bdk1_2026-10-26.eval.out`).

**Verdict: keep it on, but don't count it as a gain yet.** It costs little and shows no loss. HR@10 moves +0.0 to +0.1 pt and
new-game HR +0.0 to +0.6 pt. Caveats:
1. **One week, 5 clusters.** mx96g1 has build logs but no eval, and 14 clusters are unmeasured.
2. **Part of the delta may come from the early-stopping split, not from EASE.** The ranker is deterministic on the same data:
   `force_col_wise=True, deterministic=True` has been pinned since 27 Sep (`pull/step14_ltr.py:381-386`), and
   `sasrec/prod_off_mx96g1.out` reproduced the frozen mx96g1 build exactly. But the 10 % early-stopping holdout is a random draw
   over players (`step14_ltr.py:377`), and it changes when the candidate pool changes. Tree counts moved a lot (table above).
   A gain counts once it holds on 20 clusters × 2 weeks.
3. **Series break.** The weekly backtest as of 2 Nov (built Wed 11 Nov 06:00 +07) is the first week with EASE on, under the
   same model name. The Notion read-out should flag it.
4. **Build time.** Builds took 0–31 % longer (bdk1 1,078 → 1,412 s, `logs/pull.jsonl` vs `sasrec/s14ease_bdk1_2026-10-26.build.out`).
   The 04:30 refresh ended ~06:15 +07 on 4 Nov (`logs/recs-refresh.out`). If every cluster slowed by 31 %, it would end ~06:48 +07
   (1 h 45 min × 1.31 ≈ 2 h 18 min; arithmetic, not measured). That leaves little margin before the 07:00 day-check.

## 2 · Headroom: how much can any better model still add?

Source: `experiments/2026-11-05-headroom/` (README, `out/summary.md`), 20 clusters × 2 weeks. The rebuilt default matches the
stored default on 40/40 cluster-weeks. Two oracles peek at the test week: a perfect new-slot model (one new game the player will
play) and a perfect continue rule (one own game the player will replay). Player-weighted over all 20 clusters:

| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Default HR@10 | 92.4 % | 92.1 % |
| Perfect new-slot model | 98.6 % (+6.2 pt; clusters +5.0 to +11.9) | 98.6 % (+6.6 pt; +4.6 to +15.7) |
| Perfect continue rule | 94.5 % (+2.1 pt; +0.8 to +4.9) | 94.2 % (+2.1 pt; +0.9 to +4.8) |
| Default new-game HR | 17.6 % | 19.4 % |
| New-game ceiling (plays ≥ 1 new game) | 38.8 % | 41.7 % |
| Ranker (new games only), new-game HR | 21.7 % | 23.7 % |

- **Continue slots are done.** A perfect rule adds at most ~2 pt HR@10.
- **New slots carry the room.** A perfect model adds at most 6–7 pt HR@10 (MX most, +9.9 / +12.0 pt; BD and PH least, +5–6 pt)
  and ~22 pt new-game HR. Step 16 got +0.0–0.1 pt and +0.0–0.6 pt of that.
- The ranker's own 10-game new list reaches 23.7 % new-game HR, above the default's 19.4 % (27 Oct–2 Nov). Part of the
  discovery limit is simply that the default gives new games only 5–7 slots, which is the slot-split trade-off in
  `experiments/2026-11-04-slot-split/`.
- So more offline model work can move HR@10 only a little. Its value is discovery, which is exactly what offline HR@10
  undercounts (§3.1).

## 3 · What to try next, ranked

1. **No model swap before the online POC.** The offline gains still available are bounded by §2. The bigger unknown is how
   offline HR@10 translates online: "offline, a list only gets credit for games players found anyway … the real value needs a
   live A/B" (`ui/app.py:1332-1333`, `:1548`). The site's `last_played` row already shows the player's own games
   (`drafts/spec-game-list-impression-and-ab.md`).
2. **Raise new-game candidate recall.**
   - The popular-100 + ALS-10 pool measured in `sasrec/ease_*_2026-10-26.out` reaches 22–40 % of scored players with a new
     test-week game; adding EASE-30 gives 24–42 %. The ceiling is 29–52 % (11 clusters).
   - Add tuned iALS and RP3beta / item co-play as extra candidate sources (pool + score + rank features), the same pattern as
     `--ease-cands`.
   - Evidence that tuned simple models hold up: well-tuned iALS (Rendle et al., https://arxiv.org/abs/2110.14037); simple
     neighbour/graph methods beat most neural top-N methods (Dacrema et al. 2019, https://arxiv.org/abs/1907.06902); RP3beta
     (Paudel et al. 2016, https://dl.acm.org/doi/abs/10.1145/2955101).
3. **After the POC: learn from logged impressions and clicks.** Use shown-but-not-opened negatives and position bias, and add
   1–2 exploration slots for new games. This needs the impression event from the ticket.

**Not recommended:**
- **Retesting SASRec, BERT4Rec or gSASRec.** The 31 Oct SASRec run already used full-softmax cross-entropy
  (`sasrec/sasrec_backtest.py:155`), the setup under which SASRec does best (Klenitskiy & Vasilev 2023,
  https://arxiv.org/abs/2309.07602). It still lost to or tied the recent-games default on mx96g1 and mxk1 × 2 weeks
  (`sasrec/mx96g1_2026-10-1*.out`, `sasrec/mxk1_2026-10-1*.out`, `sasrec/ablation_all.out`).
- **Azure AI Personalizer.** Retiring 25 Aug 2026, with no new resources since 20 Sep 2023
  (https://learn.microsoft.com/en-us/previous-versions/azure/ai-services/personalizer/what-is-personalizer).

## 4 · SaaS

**Verdict.** No SaaS removes the real bottleneck: serving a per-player list on the site and logging which list was shown.
Every option below still needs the BE/FE work in the ticket.
- **Amazon Personalize** (batch) fits the same S3 file contract, so it can be a challenger arm once the A/B path exists.
- **ZingBrain / VAIX** are the "buy" option: they carry the lobby integration and the A/B themselves. Ask them for pricing only if
  Yann prefers buying to building.
- **Any vendor** needs a legal/compliance review before player data leaves: Recombee's personal-data clause, Shaped §4.2,
  Personalize regions.

**Generic recommendation services**

| Option | What | Input | Output | Built-in A/B | Price (public) | Terms that matter | Source |
|---|---|---|---|---|---|---|---|
| Amazon Personalize | user-personalization v2 (Transformer) and legacy recipes | S3 bulk import (≥ 1,000 interactions, ≥ 25 users with ≥ 2) | **batch job: S3 in, S3 out**; or real-time campaign | no (Evidently ended 16 Oct 2025) | v2: $0.15 / 1K recommendation requests, $0.002 / 1K interactions trained, $0.05 / GB; legacy batch $0.067 / 1K (first 20 M/month), $0.058 (next 180 M), + $0.24 / training hour | AUP: no gambling clause. No South America or Middle East region (closest: us-east-1, ap-south-1, ap-southeast-1) | https://aws.amazon.com/personalize/pricing/ · https://docs.aws.amazon.com/personalize/latest/dg/limits.html · https://docs.aws.amazon.com/general/latest/gr/personalize.html · https://aws.amazon.com/aup/ |
| Google AI Commerce Search (ex Recommendations AI) | retail recommendations over a product catalogue | catalogue + user events | `predict` API only | A/B section in the docs (not read) | $0.27 / 1K predictions (first 20 M/month) | Cloud AUP: no gambling clause; service terms not read | https://cloud.google.com/products/retail/pricing |
| Recombee | recommendation API with scenarios | API / batch calls | API (batch via Keboola CSV) | yes, per scenario | Standard from $99/mo, Pro from $1,699/mo, Premium from $4,499/mo | ToS (2021): "agrees not to use the Services for processing of personal data" | https://www.recombee.com/pricing · https://www.recombee.com/terms-of-use |
| Shaped | managed ranking (ALS, EASE, SASRec, gSASRec, BERT4Rec, LightGBM, …) | connectors; S3 on Standard | rank API | no | ~$500/mo (third-party figure) | ToS §4.2: perpetual, irrevocable licence to customer data | https://docs.shaped.ai/docs/v2/support/faq · https://www.shaped.ai/terms-of-service |
| Algolia Recommend | item-to-item, trending, looking-similar | events + product index | API, 30 results per model | listed | overage price not found | AUP: no gambling clause | https://algolia.com/doc/guides/algolia-recommend/overview |
| Bloomreach | CDP + product recommendations | events + catalogue | API / on-site | not verified | quote only | AUP: no gambling match | https://www.bloomreach.com/en/legal/acceptable-use-policy-current |
| Azure AI Personalizer | contextual bandit, ≤ ~50 actions per call | — | — | — | — | retiring 25 Aug 2026: excluded | (link in §3) |

**Personalize cost, recommendations only** (my arithmetic from the pricing page; training and ingest extra; 30 days a month,
4.33 weeks a month; players with a list from the 3 Nov build, `logs/recs-refresh.out`, `logs/nightly.out`):

| Scope | Players | Refresh | Requests / month | v2 ($0.15 / 1K) | Legacy batch (tiered) |
|---|---|---|---|---|---|
| Full scale | 3.79 M | daily | 113.7 M | ≈ $17,100 | ≈ $6,780 |
| Full scale | 3.79 M | weekly | 16.4 M | ≈ $2,460 | ≈ $1,100 |
| POC, phk1 | 396,480 | daily | 11.9 M | ≈ $1,780 | ≈ $800 |
| POC, phk1 | 396,480 | weekly | 1.72 M | ≈ $260 | ≈ $115 |

A batch request is one user's list: "returns 10 items per user, however the company is only charged for the 1 million
requests" (pricing page, example 3).

**iGaming vendors** (no public prices; all uplift figures are vendor claims)

| Vendor | What | Output | A/B | Source |
|---|---|---|---|---|
| ZingBrain AI | personalised casino lobby, cold start, game promotion tools | API drives lobby sections | yes; Hondubet 50/50 case, existing players +5 % GGR, +25 % unique games | https://www.zingbrain.ai/case-study/hondubet |
| VAIX (Sportradar) | game recommendations, lobby ordering, similar games | REST API or widget, "ready in 5 days from receipt of data" | dashboards; built-in A/B not stated | https://vaix.ai/product/casino-personalization/ |
| BetConstruct AI Lobby | factorisation machine, "prioritise the top 10 games for each player" | via sales | not stated | https://www.betconstruct.com/products/ai-lobby-personalization |
| OneBitTech Venix | recommendations for games, markets, offers | API on the OBT platform | not stated | https://www.onebittech.com/en/venix |
| Optimove, Smartico, Fast Track, Xtremepush | CRM tools, not lobby recommenders (Smartico doesn't reorder a third-party lobby; Xtremepush has no game recommender) | CRM channels | campaign-level | https://help.smartico.ai/welcome/products/ai-models/favorite-product-game-game-type-and-game-provider.md · https://docs.xtremepush.com/docs/ml-models.md |

**The A/B layer is already in place.** PostHog multivariate flags bucket by person (hash of `flag_key + distinct_id`) and carry
per-variant JSON payloads. Experiments accept a custom exposure event, report a Bayesian chance to win, and alarm on sample-ratio
mismatch (https://posthog.com/docs/experiments/running-experiments-without-feature-flags,
https://posthog.com/docs/feature-flags/local-evaluation, https://posthog.com/docs/experiments/exposures).

## 5 · Could not verify

- Shaped's price (its pricing page returned 404; the $500/mo is a third-party figure). Optimove (~$48K/yr) and Bloomreach
  ($60K+/yr) prices are also third-party.
- Bloomreach's MSA, Google's service-specific terms, Algolia's ToS and Recombee's current order-form terms were not read for
  gambling clauses. Recombee's "no personal data" clause needs a legal read for pseudonymous player ids.
- Google: whether it has any batch output, and its fit for casino games.
- AWS: country or regulatory restrictions on Personalize were not checked.
- None of the iGaming vendors' coverage of MX, TH, PH, BD, PK, BR, PE, CO or EG was confirmed. Their uplift figures are their own.
- RP3beta: only a secondary citation was read. LightGBM LambdaRank as a re-ranker: no recsys paper was read.
- PostHog: payload size limit and hash algorithm not checked. Assigning variants ourselves and sending server-side exposure
  events is an inference from the docs, not tested.
