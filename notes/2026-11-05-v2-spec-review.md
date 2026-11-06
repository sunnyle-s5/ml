# Review of "Game Recommendation v2: Personalized Category & Provider Grids" (5 Nov 2026, sunny)

**What this is.** The v2 spec (dated 2026-10-01) was written for another stack: BigQuery, wallet CDC, Redis. Here it is read as a source of ideas, and where it conflicts with what we measured on our data, our data wins.
- **What was run.** Five offline experiments, all on the VM and read-only: X1, X2 and X3 on 20 clusters × 2 weeks (as-of 19 and 26 Oct); X8 and X9 on the POC brand ADDA7.
- **What changed.** Nothing is applied to the POC ticket yet, apart from its new open question 1 (§3 below). The recommended changes wait for a decision.
- **Paths.** Repo paths are under `/home/ubuntu/ml/` unless they start with `experiments/`, `notes/` or `drafts/`.

## 1 · Verdicts on the spec

| Spec idea (§) | Verdict | Evidence |
|---|---|---|
| Own games pinned first, then personalised (§2) | **Already ours** for a single mixed list: the continue slots. The grid form waits on ticket open question 1. | X1 measures the pin-only arm (§2). |
| NGA-7, adoption instead of a single try (§3.1) | **Adopt as an online secondary metric** (R4) | X2: only ~19 % of new-game hits are adopted. |
| The control is "0.3 × own play + 0.7 × total bets" (§0, change #3) | **Contradicted.** Our Popular list is brand-wide, led by player counts, and has manual pins and exclusions. It has no per-player term. | `rank_mxk1` (ml.duckdb, rows ≥ 25 Oct): `weightUniquePlayers` 7000, `weightBetAmount` 3000, `scoringWindowDays` 7, `maxPopularGames` 150; 108 pinned and 85,706 excluded rows. One list per brand (`pull/pull_dims.py:43-50`). |
| Wallet rounds as ground truth, not per-round PostHog events (#4, §13) | **Agree; already ours** | Rounds come from the replicas through S3 into DuckDB (`pull/pull_hourly_agg.py`, `pull/load_archive.py`). PostHog carries only impressions and clicks. |
| Popularity from engaged real-money players (#5, 03) | **Not applicable** | The Popular list is already 70 % player count. There is no real/bonus flag on rounds: `betAmount` ≈ `playAmount` on all but 0.0009 % of mx96g1 rows. |
| Offline protocol: temporal split, full catalogue (#6, §9) | **Already ours.** Grid metrics wait on open question 1. | Frozen weekly snapshots, full-catalogue top 10 (`pull/recs_eval.py`). X1 adds a first SLOT-tab view. |
| A/A, 3 arms, long-term holdout (#7, §10) | **Adopt** (R3, R1) | The 10 % holdout is already in `drafts/plan-after-poc.md` §2. |
| RG-lite as a launch gate (#8, §8) | **Partly possible.** 2 of 6 markers can be computed; adopt safer mode (R2). | X8. The deposit, failed-deposit and reversed-withdrawal markers need payments and account-status data, which the VM doesn't have (§4). |
| Item-item / EASE / ALS as the model (#9, §6) | **Already beyond it.** Item-kNN is not worth testing. | The LightGBM ranker already uses item-item features (`ii_sum`, `ii_mean`) and EASE (`pull/step14_ltr.py:57-62`). Standalone EASE lost to the ranker on 9/10 clusters (`notes/2026-11-05-model-options.md` §1). |
| Serving path, fallback ladder (#10, §7) | **The tech team's domain** | The ticket already has a file contract and `fallbackReason` values (`drafts/spec-game-list-impression-and-ab.md` §3–4). |
| Theoretical GGR as the revenue guardrail (#11, §3.3) | **Not computable** (no RTP on the VM). Bet per player is the proxy (R6); realized GGR is reported only. | X9: CUPED barely helps realized GGR (factor 0.91), as the spec predicts. |
| Session stability (§2.3) | **Met by construction** | Lists are rebuilt once a day. |
| Bonus UX (§2.6) | **Not applicable** | No bonus data on the VM. |
| Signals never to use (§2.7) | **Review needed** | The ranker uses stake-level features: `p_bpr_log` (the player's bet per round), `stake_gap` (player vs game bet per round) and `bet7_log` (`pull/step14_ltr.py:57-60, :203, :272`). It uses nothing on session results, balance or deposits. Compliance should confirm that stake matching is acceptable. |
| Sponsored and explore slots (§2.2) | **Later, online only** | Explore is already in `drafts/plan-after-poc.md` §4. |

## 2 · Results

### X1 · Own games + Popular fill, no ML (`experiments/2026-11-05-v2-arms/`)

Player-weighted (`experiments/2026-11-05-v2-arms/out/summary.md`). The rebuilt default equals the stored default on 40/40 cluster-weeks. "Own + live" = 3/5 own recent games, then the site's live Popular list minus played games: an arm the site could serve without our file.

| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| All clusters, HR@10: default / own + live / live | 92.4 % / 91.1 % / 66.4 % | 92.1 % / 91.1 % / 68.6 % |
| All clusters, share of gain of own + live | 95 % | 96 % |
| All clusters, new-game HR: default vs own + live | 17.5 % vs 14.4 % | 19.3 % vs 16.4 % |
| ADDA7, HR@10: default / own + live / live | 94.3 % / 92.6 % / 73.4 % | 93.8 % / 92.9 % / 78.9 % |
| ADDA7, share of gain of own + live | 92 % | 94 % |
| SLOT tab, all clusters: share of gain of own + popular | 94 % | 94 % |

- Pinning the player's own games carries 88–98 % of the offline HR@10 gain over live in every market-week, with no ML at all.
- What the ranker adds is discovery: about +3 pt new-game HR (only ~19 % of that is adopted, X2).
- The SLOT-tab view gives the same picture, so the result doesn't depend on open question 1.

### X2 · Adoption vs one-off tries (`experiments/2026-11-05-v2-adoption/`)

All 20 clusters, player-weighted (`experiments/2026-11-05-v2-adoption/out/summary.md`). 40/40 cluster-weeks passed both checks.

| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Default: new-game HR / adopted | 17.6 % / 3.3 % | 19.4 % / 3.6 % |
| Ranker (new only): new-game HR / adopted | 21.7 % / 4.2 % | 23.7 % / 4.6 % |
| Popular minus played: new-game HR / adopted | 18.2 % / 3.3 % | 20.0 % / 3.7 % |
| Scored players who try / adopt ≥ 1 new game | 38.8 % / 8.9 % | 41.7 % / 9.7 % |

- About four in five new-game hits are one-day tries, for every list and in every market.
- The ranker's lead over popular is +3.6 / +3.7 pt in new-game HR but only +0.9 pt in adopted.
- Offline new-game HR overstates the discovery value roughly five-fold.

### X3 · Cold players (`experiments/2026-11-05-v2-coldstart/`)

All 20 clusters, player-weighted (`experiments/2026-11-05-v2-coldstart/out/summary.md`). The cold counts match the snapshots on 40/40 cluster-weeks.

| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| Cold players / test-week players | 442,329 / 1,807,409 (24 %) | 552,323 / 1,935,988 (29 %) |
| … of which newcomers | 78 % | 80 % |
| HR@10 rest: brand list vs one-game cold start (L2) | 69.8 % vs 71.4 % | 69.1 % vs 69.0 % |
| Returning players: brand list vs own older games (L3) | 61.7 % vs 73.3 % | 63.9 % vs 73.1 % |

- A quarter to a third of each week's players have no personal list, and no backtest has scored them.
- The spec's one-game cold start is a wash. Its coverage is 84–98 %, so that is a real result, not a fallback artefact.
- Returning players do much better with their own older games: +9.2 to +11.5 pt.

### X8 · RG markers on ADDA7 (`experiments/2026-11-05-v2-poc-brand/`)

Players in a 7-day window flagged by night play (≥ 50 % of rounds 00–05 local, ≥ 500 rounds) or by long sessions (≥ 3 days with ≥ 8 active hours):

| Window | All active | Flagged | Scored players | Flagged |
|---|---|---|---|---|
| 13–19 Oct | 79,171 | 3,133 (3.96 %) | 47,743 | 2,720 (5.70 %) |
| 20–26 Oct | 78,099 | 2,727 (3.49 %) | 47,482 | 2,389 (5.03 %) |

- Nearly all flags come from night play: 2,494 of 2,727.
- Newly flagged in the 26 Oct window after not being flagged in the 19 Oct window: 2.86 %. A 50/50 test detects a change of 0.33 pt in that rate.

### X9 · Variance and CUPED on ADDA7 (`experiments/2026-11-05-v2-poc-brand/out/summary.md`)

n = 78,099 players active 20–26 Oct. Post window 14 days, pre window 28 days.

| Metric | CV | ρ pre/post | CUPED factor | MDE 50/50 | Non-inferiority: n needed |
|---|---|---|---|---|---|
| Active days | 0.83 | 0.66 | 0.56 | 1.2 % | 94,851 at −1 % |
| Bet (winsorised) | 4.65 | 0.65 | 0.58 | 7.1 % | 342,808 at −3 % |
| Realized GGR (winsorised) | 6.20 | 0.29 | 0.91 | 11.9 % | – |
| Distinct games | 1.65 | 0.59 | 0.65 | 2.7 % | – |

CUPED halves the variance of activity and bet. It barely helps realized GGR.

## 3 · Recommended POC changes (not applied; for decision)

| Rule | Fires? | Evidence | Change to the ticket if accepted |
|---|---|---|---|
| **R1** third arm, no ML | **Yes** | ADDA7 share of gain of own + live: 92 % (20–26 Oct), 94 % (27 Oct–2 Nov); needs ≥ 80 % in both (X1) | §1 and §5: add arm H = "own games (3/5 slots) + live Popular list minus played". ML also writes H to the daily file (`list_id` `own_live:<list_date>:<cluster>`), so the BE work is unchanged. Flag variants `control_a`, `control_b`, `own_live`, `personal`. |
| **R2** safer mode | **Always** | ADDA7: 3.5–4.0 % of active players and 5.0–5.7 % of scored players flagged; newly-flagged base 2.86 % (X8) | §3: flagged players get no personal or H rows, so they see the brand list in every arm, with a new `fallbackReason` value `safer_mode`. §5: new guardrail "newly flagged (night play / long sessions) during the test", one-sided. MDE ≈ 0.33 pt at 50/50, ≈ 0.41 pt per pair at 17/17/33/33 (X8, X9 n). ML recomputes the flags daily. |
| **R3** A/A in parallel | **Always** | (design) | §5: split 17/17/33/33 (control A1, control A2, H, B), since R1 fires. The primary pools A1 + A2 as control. A1 vs A2 on every metric is the pipeline check, plus PostHog's split-mismatch alarm. With 4 arms the per-pair MDE is ~1.2× the 50/50 one (X9: active days 1.2 % → 1.5 %). |
| **R4** adoption metric | **Always** | Offline only ~19 % of new-game hits are adopted; default adopted rate 3.3–3.6 %, ceiling 8.9–9.7 % (X2) | §5 secondary metric: "share of exposed players who first open a new game (not played in the 60 days before exposure) from `main_list` within 7 days, and play it on ≥ 2 distinct days within 7 days of that open". |
| **R5** cold-player fallback | **Yes, for L3 (returning players)**; no for L2 | L3 − L1 HR@10 rest: all clusters +11.5 / +9.2 pt, bdk1 +10.4 / +7.5. L2 − L1: all +1.6 / −0.1 (X3) | §3 coverage: in arms B and H, returning cold players (no play in the 30 days before the build, but earlier play in the cache) get their 5 most recent earlier games, then the brand list. Newcomers keep the brand list. §5: pre-register the stratum "had a personal list at exposure". On bdk1, 25–30 % of test-week players are cold; 22–25 % of those are returning. |
| **R6** guardrail gating | **Does not fire** for active days or bet | Non-inferiority needs n = 94,851 (active days, −1 %) and 342,808 (bet, −3 %) vs 78,099 weekly active on ADDA7 (X9, after CUPED) | §5: active days and bet per player are "monitored, not gated". Realized GGR is reported only. Turn on CUPED (variance factor 0.56–0.58). Re-check at launch: 14 days of exposure may reach more than one week's 78k players. |

Reading: offline, almost all of the gain comes from pinning own games, so the POC's real question becomes "does the ML add anything online on top of pinning?" Arm H answers it. If H ≈ B online, the cheapest product is a site-side "pin recent games" change.

## 4 · Questions for the tech team

1. Can the read account select payments and account status? `wallet`, `walletTx`, `fundingTx`, `member` and `account` were only probed by `pull/privcheck.py`, and no output was saved. Those tables are needed for the spec's other four RG markers and for self-exclusion.
2. Do rounds carry a real/bonus flag? `gameRoundRecord` has `betAmount` and `playAmount`, which differ on 0.0009 % of rows.
3. Is there a configured RTP per game and brand? It's needed for theoretical GGR.
4. What orders a lobby tab (`gameCategory.rank`)? It's needed to score grids against the current tab order (open question 1).

## 5 · Not worth testing here

- **Item-kNN as the personalised block:** the ranker already uses item-item features, and EASE (the same family) lost to it.
- **"Engaged real-money popularity":** the control is already player-led, and there's no real/bonus flag.
- **Theoretical GGR and real-money-only training:** no RTP, no balance type.
- **Explore, sponsored and session-stability rules:** they can only be measured online.
