Draft for #ux-pipeline — NOT sent. Edit and post yourself.

---

Hi Yann, new on the VM. Three things from a read-only pass tonight, nothing changed:

🔴 *Dims pull is failing on all 21 clusters since 4 Nov 00:00 +07.* The replicas no longer have `game."freeSpinEnabled"`, so `pull_dims.py` stops with `UndefinedColumn`. Since then no game / provider / asset / category / `gameRankingScore` updates, and the newest ranking day in every cache is 2 Nov. `ml-day-check` only checks rounds, so it didn't alarm. Nothing downstream reads that column, so dropping it from GAME_SQL looks like a one-line fix. Want me to prep the patch in my folder for you to apply before tonight's 02:00 run?

🟡 *The mx96g1 30 Oct alarm should clear tomorrow.* The file landed in S3 at 13:49 +07 today, after the morning check.

🟡 *The `JSONDecodeError` every 30 min in th/br/bd/….out* comes from 7 bad lines in `logs/pull.jsonl` (29–30 Oct: 1 unescaped `\` in an explain line, 6 interleaved writes). Only the status summary crashes, the pulls are fine.

❓ *Question: the live Popular formula changed on 22–23 Oct* on every market. It's now about 100 × (0.7 · players share + 0.3 · bet share of the brand), and MX shows a fixed list from 14 Oct. That explains the jump in "live as stored" HR@10 (MX 35 → 64 %). The Sunday undercount is still there. Who shipped it, and do you have the exact spec? The onboarding note still describes the raw formula.

❓ `~/ml/sasrec/` also holds an EASE run (`ease_*_2026-10-26`) that isn't in the note or the read-out. Is it done, and what was the result?
