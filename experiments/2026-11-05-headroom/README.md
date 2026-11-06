# headroom

Started: 2026-11-05 · Status: done

## Question
How many HR@10 points could *any* better model still add to the default `hybrid (recent continue + ranker new)`, and in which slots?
Which brand is big enough for a one-brand online POC? This decides whether to keep doing offline model work (e.g. Step 16 EASE,
SASRec) or to put the effort into getting the list online.

## Setup
- 20 scored clusters × as-of 2026-10-19 and 2026-10-26 (test weeks 20–26 Oct and 27 Oct–2 Nov). Frozen snapshots, opened read-only.
- Check: "rebuilt default" = stored default on **40/40** cluster-weeks (players, HR@10 and new-game HR identical).
- Two oracle variants that peek at the test week:
  - **oracle new slot:** the default, with the player's most-played *new* test-week game (not in the 60-day hist) inserted right
    after the continue slots. It is the best any new-slot model could do. Its new-game HR is the ceiling: the share of scored players
    who play ≥ 1 new game that week. It matches the ceiling in `sasrec/ease_*_2026-10-26.out` exactly (mxk1 47.9 %, mx96g1 51.8 %).
  - **oracle continue slot:** the default, with the most recent own game the player replays moved to the first continue slot.
    It is the best any continue-slot rule could do (new slots unchanged).
- Per brand (newest week): default vs `live (as stored)`, same scoring as `pull/recs_eval.py`. Brand totals match the cluster
  totals (mxk1 86,197 players / 86.6 %; phk1 158,337 / 93.5 %).
- Run: `bin/py experiments/2026-11-05-headroom/run.py all`, 9 min, slowest cluster-week 52 s. **Peak RSS 14 GB** (bdk1): run it
  outside busy hours, and don't run it in parallel with anything else.

## Result (player-weighted, all 20 clusters; per market in `out/summary.md`)
| Variant | HR@10 vs default | new-game HR vs default | cluster-weeks better |
|---|---|---|---|
| default (stored) | 92.4 % / 92.1 % (20–26 Oct / 27 Oct–2 Nov) | 17.6 % / 19.4 % | — |
| oracle new slot (perfect new-game model) | +6.2 / +6.6 pt (clusters +4.6 to +15.7) | +21.2 / +22.3 pt (ceiling 38.8 % / 41.7 %) | 40/40 |
| oracle continue slot (perfect continue rule) | +2.1 / +2.1 pt (clusters +0.8 to +4.9) | 0 | 40/40 |

- The oracles reach 98.6 % / 94.2–94.5 % HR@10. The default already has ~92 % of scored players covered; what is left is mostly new games.
- Ranker (new games only) new-game HR is 21.7 % / 23.7 %, against the 38.8 % / 41.7 % ceiling: the ranker finds about half of
  the players who try something new.
- MX has the most headroom in new slots (+9.9 / +12.0 pt), BD and PH the least (+5.2–5.9 pt).

POC brand (table B): only one brand has ≥ 40,000 scored players a week, **ADDA7 (bdk1, BD)**: 64,040 players, default 93.8 % vs
live 78.9 % (+14.9 pt), MDE 1.1 pt. No brand qualifies as an alternate under the rule. The next largest are BDPOP (bdk1, 32,551,
MDE 1.6 pt) and, outside BD, MXWOW (mxk1, 20,263, gap +22.2 pt, MDE 2.0 pt). All of them are an order of magnitude above their MDE.
178 brands were scored; 4 have no live list.

## Decision / next
- A perfect continue rule adds at most **2.1 pt** HR@10: stop tuning the continue slots.
- A perfect new-game model adds at most **6.2–6.6 pt** HR@10 and **~22 pt** new-game HR. A realistic model gets a fraction of that:
  Step 16 EASE gained +0.0–0.1 pt HR@10 and +0.0–0.6 pt new-game HR. Offline model work has a small ceiling on HR@10. Its room is
  in discovery (new-game HR), where the offline metric undercounts the value anyway.
- So the next gain comes from getting the list online (A/B on ADDA7). The online gap vs the live list (offline +15–41 pt by market)
  is far larger than anything left offline.
