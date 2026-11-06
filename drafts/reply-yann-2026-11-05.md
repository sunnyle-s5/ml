Draft — NOT sent. Edit and send yourself.

---

Hi Yann, my take on the three next steps. Details are in the linked files; nothing has been built or sent.

*1. Model into production for an experiment.* We can't do it ourselves: the home list comes from the site's own API, and the ML VM has no write path to the site. The brand-wide order (the only no-code lever) is already as good as our best brand list (64.4 vs 64.9 %). The ask to the tech team is small: BE serves a daily per-player S3 file we build, FE adds list identity to two existing events, one PostHog flag, read access from Harvey. Proposed: 14-day 50/50 A/B on ADDA7's home `main_list` (bdk1, 64k scored players/week, offline 93.8 vs 78.9 % live). We do the file, the analysis and the monitoring. Ticket: `drafts/spec-game-list-impression-and-ab.md`. Question: do we have a CRM tool that can send per-player game lists? That would be a channel without site changes.

*2. Better model / SaaS.* Keep Step 16 EASE on: no loss and cheap. So far it's +0.0–0.1 pt HR@10 and +0.0–0.6 pt new-game HR, on 5 clusters × 1 week, so not a proven gain yet. I checked the headroom with an oracle (20 clusters × 2 weeks). A *perfect* new-game model would add only 6–7 pt HR@10, and a perfect continue rule ~2 pt. The room left is discovery (new-game HR 19 % vs a 42 % ceiling), and that is what offline HR@10 undercounts. So the next big step is the online test, not another model. After that: more candidate sources for the ranker (tuned iALS, RP3beta). SASRec is not worth a retest: it already used the recommended loss. SaaS doesn't remove the bottleneck (serving + events). Amazon Personalize batch would fit the same S3 file as a challenger arm, at ~$260–1,780/month in recommendation fees for one large cluster. ZingBrain/VAIX are the "buy" option (they bring the lobby integration + A/B), with no public prices. Note: `notes/2026-11-05-model-options.md`, numbers in `experiments/2026-11-05-headroom/`.

*3. After the POC.* Day-15 gate (ship / iterate with a "For you" new-games row / stop). Then one brand per market, then all brands, with a 10 % holdout. In parallel: code into git, a day-check that also covers the catalogue and the served file, saved ranker models, a responsible-gambling review. Then one challenger at a time online. Plan: `drafts/plan-after-poc.md`.

🔴 Blocker before any POC: the catalogue (dims) pull still fails on all clusters (`pull_dims.py` selects the dropped `"freeSpinEnabled"`), so no new games enter any list. Tonight's 02:00 run will fail again (see my earlier draft `drafts/slack-ux-pipeline-2026-11-04.md`).
