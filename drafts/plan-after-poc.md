# DRAFT · After the POC: decision gate, rollout, hardening, model iteration

Status: draft for Yann, sunny, 5 Nov 2026. Nothing has been sent or started. It assumes the POC in
`drafts/spec-game-list-impression-and-ab.md` (14-day 50/50 A/B on one brand's home `main_list`).

## 1 · Decision gate on day 15

The three outcomes are pre-registered in the ticket (§5):

| Outcome | Rule | What it triggers |
|---|---|---|
| **Ship** | primary metric chance-to-win ≥ 95 %, no guardrail breached | §2 rollout |
| **Iterate** | primary wins, but game opens per player are flat (the list moved clicks, not play) | test a "For you" row of new games next to the Popular list (§5), same A/B setup |
| **Stop and rethink** | anything else | compare online play-through with the offline replay of the same 14 days, and fix the offline metric before the next model test |

## 2 · Rollout (after Ship)

1. One brand per market for 2 weeks, same metrics and guardrails. The markets are MX, TH, PH, BD, PK, BR, PE and CO; EG has too few
   players and is never scored.
2. Then all brands.
3. Keep a permanent 10 % control holdout (Popular list) for long-run measurement and for every later model test.

## 3 · Production hardening, in parallel with the rollout

| Item | Why | Owner |
|---|---|---|
| Pipeline code into git and deployed from it | the live code in `/home/ubuntu/ml` is not under version control; a copy exists in `pipeline/` | Yann |
| Extend `ml-day-check` beyond rounds: catalogue (dims) freshness, recs-file freshness and coverage, export success | the 4 Nov catalogue failure (all 21 clusters) raised no alarm because the check only covers rounds | ML |
| Serving SLA and fallback-rate monitoring | a stale or missing file silently falls back to the brand list | BE + ML |
| Reproducibility: save the ranker model and seed per build; `list_id` identifies the build | the ranker is retrained in every build and not saved, so a served list can't be rebuilt later | ML |
| A schema-change contract with the site team | the `game."freeSpinEnabled"` drop broke the catalogue pull without warning | Yann + site team |
| Keep the refresh finished before 07:00 +07 | the 04:30 refresh ended ~06:15 on 4 Nov, and EASE (Step 16) makes builds 0–31 % slower | ML |

## 4 · Model iteration from online data

- One challenger at a time, as an A/B arm against the shipped list, inside the holdout design.
- Offline entry bar: beats the default on ≥ 15 of 20 clusters × 2 weeks without losing new-game HR.
- Order:
  1. more new-game candidate sources for the ranker (tuned iALS, RP3beta / item co-play), the same pattern as Step 16's EASE;
  2. 1–2 exploration slots for new games;
  3. a cold-start list for new players (the `coldstart` table already exists in every snapshot);
  4. Amazon Personalize (batch) as an external challenger, if Yann approves the cost (`notes/2026-11-05-model-options.md` §4).
- Once 4 weeks of logged impressions exist: retrain on impressions and clicks (shown-but-not-opened negatives, position bias).

## 5 · More surfaces

- A "For you" row of new games (needs a new FE component).
- CRM (push, email) if the company has a tool that can take per-player game lists.

## 6 · Responsible gambling and compliance

Before going beyond the POC brand: how self-excluded and cooling-off players are handled, and the market rules on
personalised game promotion in each market. Owners: Product + Compliance.

## 7 · Weekly reporting

Online play-through next to offline HR@10 for the same week (calibration), plus coverage and freshness of the served file.
It goes in as an extra row in the Notion read-out (drafted, not posted, like the current read-out drafts).

## 8 · Owners

| Area | Owner |
|---|---|
| Lists, export file, analysis, offline backtests, monitoring | ML (sunny, Yann) |
| Home list API, file ingest, fallback | BE |
| Impression and click events | FE |
| S3 access for the BE | DevOps (Harvey) |
| Brand, surface, guardrails, flag and experiment sign-off | Product |
| Responsible-gambling and market rules | Compliance |
