# DRAFT · Proposed Notion read-out update (for Yann; not posted)

Leaves the VM-written "Weekly backtest tracking" section untouched. Proposes (A) a new section after step 17,
(B) two new rows for "What did not work", and (C) small fixes at the top.

## A · Step 18 · Continue slots from the player's own recent games (31 Oct – 4 Nov 2026), new section

Testing a sequence model (SASRec, 31 Oct) did not beat the ranker hybrid, but the ablation behind it showed where the loss was.
About 65 % of the ALS "continue" slots held games the player had **never played**, and those hit only 7–8 % of the time.
Filling the 3 or 5 continue slots with the player's own games, newest first, and keeping the ranker in the new slots
gives "hybrid (recent continue + ranker new)":

- 20–26 Oct (as of 19 Oct): ahead of "hybrid (als continue + ranker new)" on 20 of 20 clusters, +2.3 to +8.4 pt HR@10, new-game HR flat.
- 27 Oct–2 Nov (as of 26 Oct, verdict posted 4 Nov): 20 of 20 clusters, +2.3 to +8.5 pt HR@10, new-game HR −0.6 to +0.6 pt,
  1,383,665 scored players.
- **Default list since 3 Nov 2026.** Code: `build_recs.py` (step 15 comment), `~/ml/sasrec/ablation.py`, `recent_check.py`.

**Is the 3/5 split still right? (sunny, 4 Nov, 20 clusters × 2 weeks.)** Rebuilt from the frozen snapshots; the 3/5
default reproduces the stored list exactly on all 40 cluster-weeks. Changing the slots heavy players (3+ games) get is a pure trade:

| Continue slots, heavy players | HR@10 vs default | new-game HR vs default |
|---|---|---|
| 3 | −2.0 pt (−5.1 to −0.5) | +1.7 pt (+0.7 to +2.4) |
| 4 | −0.7 pt (−1.7 to −0.2) | +0.9 pt (+0.4 to +1.2) |
| **5 (default)** | — | — |
| 6 | +0.4 pt (+0.1 to +0.8) | −0.9 pt (−1.5 to −0.2) |
| 7 | +0.6 pt | −2.0 pt |

Player-weighted, both weeks agree within 0.05 pt. Every cluster-week moves the same way. Sizing the continue slots by
games played in the last 7 days, or giving light players 1 slot, loses more HR@10 per new-game point than a fixed split, so
neither is a candidate. **The 3/5 split stays.** Going from 5 to 4 is the cheapest discovery gain if Product wants one
(about 1 pt HR@10 for 1.3 pt of new-game hits). Code: `/home/sunny/ml/experiments/2026-11-04-slot-split/slot_split.py`.

## B · "What did not work", new rows

| Trap | Rule |
|---|---|
| A sequence model (SASRec) for the whole list | Did not beat hybrid + ranker (31 Oct). Most of the "continue" value is just recency. Keep the no-model rule |
| ALS for the continue slots | About 65 % of its continue picks were games the player never played (7–8 % hit rate). Continue slots = own games newest first |

## C · Top of page

- Headline and flowchart box "Hybrid: 3–5 ALS continue slots": change to "3–5 recent own games" (default since 3 Nov).
- Ask (27 Sep): the live Popular list switched to a share-of-total 30/70 on 22–23 Oct on every market (MX showed a
  fixed list from 14 Oct). The Sunday undercount is still in the inputs (MX: the ranking sees 87–92 % of the week's bet).
  Suggest a line: "Normalisation shipped 22 Oct (BE); Sunday fix open."
- Section 16: "TH snapshots are rebuilt by hand": now ml-recs-refresh, 04:30 +07, all markets.
- Weekly backtests are as of a **Monday** (the onboarding note says Sunday).
