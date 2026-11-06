# v2-arms (X1)

Started: 2026-11-05 · Status: done

## Question
The v2 spec's "heuristic arm" pins the player's own games first and fills with popularity, with no ML. How much of the personal list's gain over the live Popular list does that alone deliver? If it delivers most of the gain, the POC should test it as a separate arm: the site could build it without our file.

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26.
- **Mixed top 10** (`main_list` as one list), all on the same scored players:
  - "own + live": the default's 3/5 continue slots (own games, newest first), then the site's own `live (as stored)` Popular list minus played games.
  - "own + popular": the same with our `popular 30/70 minus played` list as the fill.
  - Both are compared against the stored default and `live (as stored)`.
  - ADDA7 (bdk1) is also scored on its own; R1 is decided there.
- **SLOT tab** (`main_list` as the selected lobby tab's grid): SLOT games only, on scored players who play a SLOT game in the test week.
  - "SLOT: personal": own SLOT games, then ranker SLOT picks, then the brand pct-rank SLOT fill.
  - "SLOT: own + popular": own SLOT games, then the fill.
  - "SLOT: live proxy": the brand's live list, SLOT games only.
  - pk96g1 labels the tab `SLOTS`; both labels are treated as SLOT.
- Share of gain = (HR_x − HR_live) ÷ (HR_default − HR_live). thblg2 has no live list and is left out of the shares.
- **Checks:**
  - "rebuilt default" = stored default on 40/40 cluster-weeks (`grep -c '!!' out/run_all.out` = 0).
  - Live HR@10 via `mlkit.score(lists=…)` matches `logs/backtest-2026-10-26.out`: bdk1 77.9 %, kzg1 62.4 %.
  - Brand-level ADDA7 totals match the headroom run: 64,040 players, 93.8 % vs 78.9 %.

## Result (player-weighted; full tables in `out/summary.md`)
| | 20–26 Oct | 27 Oct–2 Nov |
|---|---|---|
| All clusters: default / own + live / live, HR@10 | 92.4 % / 91.1 % / 66.4 % | 92.1 % / 91.1 % / 68.6 % |
| All clusters: share of gain, own + live (own + popular) | 95 % (95 %) | 96 % (94 %) |
| All clusters: new-game HR, default vs own + live | 17.5 % vs 14.4 % | 19.3 % vs 16.4 % |
| **ADDA7**: default / own + live / live, HR@10 | 94.3 % / 92.6 % / 73.4 % | 93.8 % / 92.9 % / 78.9 % |
| **ADDA7**: share of gain, own + live | **92 %** | **94 %** |
| SLOT tab, all clusters: personal / own + popular / live proxy | 92.4 % / 91.1 % / 72.1 % (share 94 %) | 92.1 % / 91.0 % / 72.9 % (share 94 %) |

- Pinning own games, with no ML at all, carries 88–98 % of the offline HR@10 gain in every market-week, and 92–94 % on ADDA7. The SLOT-tab view agrees.
- What the ranker adds is discovery: +2.9 to +3.1 pt new-game HR over the live fill (all clusters). X2 shows only about a fifth of those new-game hits are adopted.

## Decision / next
- **R1 fires:** add arm H, "own games (3/5) + the live Popular list minus played", to the POC. The A/B then measures what the ML adds on top of pinning, which offline puts at only ~1 pt HR@10 and ~3 pt new-game HR.
- For Product: if H is close to B online, a site-only change (pin recent games in `main_list`) gets most of the value without our pipeline. The site's existing `last_played` row already does part of it, which is why online total opens matter.
