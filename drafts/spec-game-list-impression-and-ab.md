# DRAFT · Ticket: personal game list POC (A/B on one brand)

Status: draft for Yann → BE / FE / DevOps / Product, sunny, 5 Nov 2026. Nothing has been built or sent.
Updated 5 Nov to the release proposal in `notes/2026-11-05-summary-report.html` §4 (four arms, personal list v3,
returning-player fallback). Replaces the 4 Nov draft of this file (impression event + A/B), which had no serving path or owners.

## 1 · The ask

A 14-day A/B test with four arms on one brand's home `main_list`:

| Arm | Share | What the player sees |
|---|---|---|
| `control_a` | 17 % | today's Popular list |
| `control_b` | 17 % | today's Popular list (A/A check: must match `control_a`) |
| `own_live` (H) | 33 % | the player's 3–5 most recently played games, then today's Popular list minus games they played (no ML) |
| `personal` (B) | 33 % | **personal list v3**: ML ranks the player's own games and new games together, 10 in total |

Arms H and B are read from a daily S3 file that ML builds; ML also does the analysis.
From the tech team we need: BE serving of the file, two FE event changes, one PostHog flag, S3 read access, and Product
sign-off on the brand, the surface, the guardrails and the treatment variant (§5).

**Personal list v3, per player type:**
- **Players with a personal list** (played in the last 30 days): the unified ranker's top 10. One LightGBM model scores the
  player's 20 most recent own games together with new-game candidates (ranker new 10, popular 10, live Popular top 20),
  retrained daily on the previous week.
- **Returning players without one** (no play in the last 30 days, but earlier play): their 5 most recent earlier games, then
  the Popular list.
- **Newcomers** (no earlier play): the Popular list, as today.

**Why four arms.** B vs the two controls is the main test. B vs H shows whether the ML adds anything over simply pinning the
player's own games, which offline carries ~90 % of the gain (§2). If H ≈ B online, the cheapest product is a site-side change.

## 2 · Why this needs the tech team, and what ML does itself

- The home list comes from the site's own API (`listApiMs` in the impression event). The ML VM has no write path to the site,
  so nothing a player sees can change without BE work.
- The only lever that needs no site code is the brand-wide order, and it already matches our best brand list:
  `live (as stored)` 64.4 % vs `normalised 30/70 (max)` 64.9 % HR@10 (mx96g1, 20–26 Oct; `notes/2026-11-04-findings.md` §3).
  The gain is per player. Offline backtest, week 27 Oct–2 Nov (HR@10 = share of players who play ≥ 1 of the list's top 10 in
  the week after it was built; `notes/2026-11-05-summary-report.html` §1 and §3):

  | Market | Live Popular | Today's personal list (v1) | Personal list v3 | Scored players |
  |---|---|---|---|---|
  | MX | 61.7 % | 86.2 % | 87.9 % | 95,779 |
  | TH | 60.4 % | 91.9 % | 93.0 % | 617,760 |
  | PH | 77.8 % | 93.0 % | 94.5 % | 305,408 |
  | BD | 77.9 % | 93.4 % | 94.0 % | 321,266 |
  | PK | 58.3 % | 90.5 % | 91.8 % | 20,741 |
  | BR | 61.5 % | 88.8 % | 90.4 % | 8,967 |
  | PE | 50.5 % | 91.4 % | 92.0 % | 8,548 |
  | CO | 70.6 % | 91.6 % | 92.0 % | 5,196 |

  - v3 is above v1 on 20/20 clusters (+1.13 pt pooled). Its gain is mostly replays of the player's own games: new-game HR
    drops from 19.4 % to 14.0 %.
  - Returning players without a list play one of their own older games on their first day back much more often than a
    Popular game: day-one HR@10 74.4–76.2 % vs 58.4–61.7 % with the Popular list.
  - Caveat: offline, a list gets credit for games players would have found anyway (the site already has a `last_played` row).
    Only the A/B measures what the list adds.
- ML does itself: the daily file, the flag definition (after Product's OK), the analysis queries, a daily freshness and
  coverage check during the test, and the read-out.
- A channel that needs no site change would be a CRM tool that can send per-player game lists (open question 5).

## What exists today (PostHog, checked 4 Nov)

- `evt:home_game_list_shown` is a **page-speed event**: `listRenderedMs`, `listShownMs`, `listApiMs`, … plus
  `accountId`, `brand`, `category`, `authStatus`. It has **no game ids, no positions, and nothing saying which list was shown**.
  So it can't tell us what a player saw.
- `act:game_open_triggered` already carries `gameId`, `gamePosition`, `gameRank`, `openSource`
  (`main_list`, `last_played`, `provider`, `surprise_me`, `search`, `promo_banner`), `openSourceCategory`, `accountId`.
  Clicks are attributed to a surface. They are not attributed to a list version.
- Reminder: `accountId` in PostHog is the **brand**, not the player. The player is the person / `$user_id`.

So the onboarding note's "needs evt:game_list_shown" is right. The fix is small: add list identity to the
existing events instead of adding a new pipeline.

## 3 · What ML delivers: the daily file

- Key: `s3://uxlab-ml-data-20260922042321746900000001/recs/<list_date>_<cluster>.parquet`, the same bucket and naming as
  the brand lists ML already exports to `lists/` (`pull/export_lists.py`). A new key every day. An S3 object appears whole,
  so the BE takes the newest `list_date` for its cluster. During the POC, ML writes only the POC cluster (bdk1).
- Written after each build: MX by ~02:30 +07, the other markets by ~06:30 +07 (bdk1 is a non-MX cluster). Data runs through
  the previous market day.
- One row per player, arm and position. Each player has two lists in the file: one for arm H and one for arm B.

  | Column | Type | Meaning |
  |---|---|---|
  | `list_date` | DATE | data through this market day |
  | `cluster` | VARCHAR | ML cluster, e.g. `bdk1` |
  | `market` | VARCHAR | `MX`, `TH`, `PH`, `BD`, `PK`, `BR`, `PE`, `CO` |
  | `account_id` | VARCHAR | the brand (= PostHog `accountId`) |
  | `member` | VARCHAR | the player id from the site DB |
  | `arm` | VARCHAR | `own_live` or `personal` (= the flag variant that serves this list) |
  | `rk` | INTEGER | 1–10, display order |
  | `game_id` | VARCHAR | = PostHog `gameId` |
  | `slot` | VARCHAR | `continue` (a game the player played before) or `new` |
  | `list_id` | VARCHAR | `<arm>:<list_date>:<cluster>`, e.g. `personal:2026-11-20:bdk1` |
  | `built` | TIMESTAMP | build time |

- Coverage:
  - every player active in the brand in the last 30 days: both lists, 10 rows each;
  - returning players (no play in the last 30 days, but earlier play in ML's ~120-day history): both lists, own older games
    first, then the Popular list;
  - newcomers have no rows; the BE serves them the Popular list (`fallbackReason = no_list`);
  - brands with < 20 games or < 50 active players are skipped.
- Size: about 2 × players × 10 rows. bdk1 had 841,487 active players on 3 Nov, so ≈ 17 M rows plus the returning players.
- Only games in ML's copy of the catalogue appear. That copy has been frozen since 2 Nov because the catalogue pull breaks on
  a dropped column (`game."freeSpinEnabled"`). It must be fixed before launch, or new games never enter the list.

## 4 · Checklist per owner

**BE**
- [ ] Daily ingest of the newest file for the POC cluster.
- [ ] For a player assigned `own_live` or `personal` with rows for that arm in a file ≤ 48 h old, the home list API returns
  those 10 games in `rk` order, plus `listId`.
- [ ] Otherwise (and always for `control_a` / `control_b`) it returns the brand list. For H and B players this carries
  `fallbackReason` ∈ {`no_list`, `stale_list`, `error`}.
- [ ] The response always carries `listVariant` (the assigned arm) and `listId`.
- [ ] No change outside the POC brand.

**FE**
- [ ] `evt:home_game_list_shown` gains these properties. Keep the timing properties. It fires only when the list is on screen
  (`wasHidden = false`), as today.

  | Property | Example | Why |
  |---|---|---|
  | `listSurface` | `main_list` | same values as `openSource`, so clicks join to impressions |
  | `listId` | `personal:2026-11-20:bdk1`, `own_live:2026-11-20:bdk1`, `popular:2026-11-20` | the list actually served |
  | `listVariant` | `control_a` / `control_b` / `own_live` / `personal` | the assigned arm (intent-to-treat: also set when the player got the fallback) |
  | `gameIds` | `["…", …]` (10, in shown order) | HR@10 on what was *shown*, not what we built |
  | `listSize` | `10` | |
  | `fallbackReason` | `null`, `no_list`, `stale_list`, `error` | assigned H or B but shown the brand list |
  | `$feature/personal-game-list` | same values as `listVariant` | lets PostHog Experiments read the exposure |

- [ ] `act:game_open_triggered` gains `listId` and `listVariant` when `openSource = main_list`.

**PostHog / Product**
- [ ] Multivariate flag `personal-game-list`: `control_a` 17 / `control_b` 17 / `own_live` 33 / `personal` 33, release
  condition `accountId` = the POC brand, person-level bucketing. The tech team chooses where it is evaluated (BE local
  evaluation, or the FE passes it to the API); the assigned variant must be on both events.
- [ ] A PostHog Experiment on the flag, with exposure = custom event `evt:home_game_list_shown` where `listSurface = main_list`.
  CUPED on (it roughly halves the variance of activity metrics on ADDA7).

**DevOps (Harvey)**
- [ ] Read-only access for the BE role to `s3://uxlab-ml-data-20260922042321746900000001/recs/*`.

**ML**
- [ ] A `build_recs.py` patch for Yann: the unified ranker and the returning-player list. Its offline harness is
  `experiments/2026-11-05-v3-unified/` and `experiments/2026-11-05-v3-cold-day1/`.
- [ ] `export_recs.py` (a patch for Yann) writing both lists, hooked next to the `export_lists.py` call in `build_market_recs.sh`.
- [ ] Saved HogQL queries for every metric below.
- [ ] A daily freshness and coverage check during the test.
- [ ] An offline replay of the same 14 days, to calibrate offline HR@10 against online play-through.

## 5 · Experiment design

- **Unit:** the player (person), sticky, split 17/17/33/33 inside the brand. Analysis by assigned arm.
- **Comparisons:** B vs `control_a` + `control_b` pooled (main test); B vs H (does the ML add anything over pinning?);
  H vs pooled control; `control_a` vs `control_b` (A/A: any difference on any metric means the pipeline is broken).
- **Surface:** `main_list` only. It's the least work: same component, new content. The alternative for Product is a new
  "For you" row: more FE work, but it doesn't touch the Popular list. `last_played` already shows the player's own games,
  which is why total opens is a key secondary metric.
- **Duration:** 14 days (two weekly cycles). No early stop except on a guardrail breach.
- **Primary:** share of exposed players who open ≥ 1 game from the first 10 positions of `main_list` within 7 days of
  first exposure. This is the online twin of HR@10.
- **Secondary:**
  - game opens per exposed player across all surfaces (is it incremental?);
  - new-game opens per exposed player: a game the player hadn't played in the 60 days before exposure (ML computes it);
  - adoption: share of exposed players who first open a new game from `main_list` within 7 days and play it on ≥ 2 distinct
    days within 7 days of that open (offline, only ~19 % of new-game hits are adopted);
  - share of opens by `openSource`: did `main_list` take clicks from `last_played` or `search`?;
  - rounds and bet per exposed player, from the pulled rounds (monitored, not gated: ADDA7 is too small to gate them);
  - pre-registered stratum: "had a personal list at exposure" (24–29 % of a week's players don't).
- **Guardrails** (proposed; Product signs off):
  - opens per player not down by more than 1 %;
  - `listApiMs` p95 up by no more than 100 ms;
  - fallback rate < 5 % of H and B impressions;
  - PostHog's sample-ratio-mismatch alarm, and no significant `control_a` vs `control_b` difference.
- **Decision rule** (pre-registered):
  - **ship B** if B beats pooled control on the primary metric with PostHog chance-to-win ≥ 95 % and no guardrail is breached;
  - if B also fails to beat H, the gain comes from pinning: **propose the site-side "own games first" change** instead of the
    ML list;
  - **iterate** if the primary wins but opens per player is flat (the list moved clicks, not play);
  - **stop and rethink** otherwise.
- **Treatment variant (Product decides):** the proposal is the unified top 10 (+1.13 pt HR@10 offline, new-game HR
  19.4 → 14.0 %). If discovery matters more, use "learned continue" instead: the same 3/5 own slots, with the model choosing
  which own games (+0.77 pt, new-game HR unchanged).
- **Sizing** (`experiments/2026-11-05-headroom/out/summary.md` table B; `experiments/2026-11-05-v3-unified/`; test week
  27 Oct–2 Nov):
  - **Proposed brand: ADDA7 (bdk1, BD).** It is the only brand with ≥ 40,000 scored players a week (64,040).
  - Offline HR@10 on ADDA7: Popular 78.9 % · H 92.9 % · today's personal list 93.8 % · personal list v3 94.5 %.
  - Detectable difference (α = 0.05, 80 % power): 1.1 pt at 50/50, ≈ 1.35 pt per pair with the four arms. That's enough for
    B vs control (offline gap +15.6 pt); B vs H (offline +1.6 pt) is near the limit, so read it as a direction, not a verdict.
  - If Product prefers another brand: BDPOP (bdk1, 32,551 players) or, outside BD, MXWOW (mxk1, 20,263 players), at a
    larger detectable difference. With four arms, consider 3 weeks there.

## 6 · Open questions

1. Is `main_list` one mixed list, or the grid of the selected lobby tab? The impression event `evt:home_game_list_shown`
   carries a `category`, and the lobby's tabs are the site's default game categories plus Popular. If it is one grid per
   tab: which tab does the POC change (we assume Popular), and should the file carry one list per tab?
2. Is `member` (our player id) the id the BE sees, and the PostHog distinct_id / `$user_id`?
3. Is `main_list` fetched per player, or cached per brand?
4. Brand and surface: our proposal (above) vs Product's choice.
5. Is there a CRM tool that can send per-player game lists?
6. Self-excluded or limited players: are they already filtered out of the home list, and must the personal list exclude them?
   (Responsible-gambling design is handled in a separate review.)
7. Who owns the flag and the experiment in PostHog?
8. Treatment variant: unified top 10 (more HR@10) or learned continue (keeps discovery)? See §5.

## 7 · Timeline and release conditions

Before launch:
1. **Second offline week, Wed 11 Nov:** ML re-runs the unified ranker on the 2 Nov week. It must again beat today's personal
   list by ≥ 0.5 pt pooled on ≥ 15 of 20 clusters. If it doesn't, arm B becomes today's personal list
   (`hybrid (recent continue + ranker new)`, plus the returning-player list). Nothing else in this ticket changes.
2. **Catalogue pull fixed** (`pull_dims.py`, the `freeSpinEnabled` column), so new games reach the lists.
3. **The `build_recs.py` and `export_recs.py` patches applied by Yann.**

ML's side is ready within 2 working days after the file format is agreed and the 11 Nov check is done. The tech team
estimates its own part. Decision on day 15 after launch (rules in §5).
