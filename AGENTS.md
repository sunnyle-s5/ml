# AGENTS.md: sunny's ML workspace on the ML VM (S5VM-24)

Instructions for any coding agent (and for me) working in `/home/sunny/ml`. Read this file before doing anything.
The project: per-brand and per-player game lists for the casino sites, measured by HR@10 on frozen backtest weeks.
Background: the onboarding note from the manager, the Notion read-out https://app.notion.com/p/3e548905ea7781dea90fd48332c22198,
and `notes/2026-11-04-findings.md`.

## 1 · Hard rules (manager's rules. Don't break them, even if a task seems to need it)

1. **Never write under `/home/ubuntu/ml`** (`pull/`, `ui/`, `data/`, `logs/`, `sasrec/`) **or `/etc/ml`**. No edits, no new
   files, no `git init`, no `__pycache__`. That is the live pipeline, and it is not in git. Changes to it go to Yann as a patch or
   message. You may read it.
2. **Open shared DuckDB files read-only**: `duckdb.connect(p, read_only=True)` or `ATTACH '…' (READ_ONLY)`. Never rewrite a
   `recs_*.duckdb`. The rank UI and the S3 upload read them.
3. **No S3 writes. No replica DB queries.** Don't run `nightly.sh`, `pull_*.py`, `backfill_*.sh`, `snapshot_store.py`,
   `export_lists.py` or anything else that pulls or uploads. The replicas have a 30 s timeout and a strict load budget.
4. **Nightly window 02:00–07:00 +07**: run nothing that reads `~ubuntu/ml/data`. `lib/mlkit.guard()` enforces this.
5. **Disk**: keep ≥ 10 GB free on `/` (`df -h /`). Snapshots are 10 MB–1 GB each. Never copy them here; attach them in place.
6. **Nothing outward without the user's explicit OK**: no Slack posts, Notion edits, PostHog changes, GitHub pushes or emails.
   Write drafts in `drafts/` instead.
7. **Timers and services**: don't start, stop, enable or edit systemd units. Reading `systemctl status/show` is fine.
8. **Secrets**: never copy `/etc/ml/*.env`, `ui/CREDENTIALS.txt` or any token into this folder, a commit, or a message.

## 2 · This folder

```
AGENTS.md            this file (CLAUDE.md imports it)
bin/py               run Python: shared venv + lib/ on the path, no __pycache__, nice 10
bin/status           read-only check: nightly window, disk, timers, service exits, today's pipeline errors
bin/new-exp <name>   new experiment from the template → experiments/YYYY-MM-DD-<name>/
bin/sync-pipeline    refresh pipeline/ from the live code (read-only on source), show git status, no commit
lib/mlkit.py         guard(), snap_path(), load(), score() (same SQL as recs_eval.py), save_csv(), CLUSTERS/MARKETS
experiments/         one dated folder per idea: run.py + README.md (question · setup · result · decision) + out/
  _template/         copied by bin/new-exp
  2026-11-04-slot-split/   done: keep the 3/5 split (see its README)
notes/               dated findings (what is true, with numbers and sources)
drafts/              messages/specs waiting for the user to send (Slack, Notion, spec for FE/Product)
pipeline/            git repo: a read-only COPY of pull/ ui/ sasrec/*.py + systemd units. Not deployed
scratch/             throwaway, gitignored, safe to delete
```

## 3 · The shared system (read-only map)

| What | Where |
|---|---|
| Pipeline code | `/home/ubuntu/ml/pull/`: `build_recs.py` builds every list, `recs_eval.py` scores, `market.py`/`common.py` clusters + time zones |
| Snapshots | `/home/ubuntu/ml/data/recs_<cluster>[_<asof>].duckdb`, tables `recs lists hist truth coldstart games meta` |
| Market caches | `/home/ubuntu/ml/data/{ml(MX),th,ph,bd,pk,br,pe,co,eg}.duckdb`: `plays_*`, `rank_*` (live ranking), `game_*` |
| Logs | `/home/ubuntu/ml/logs/`: `pull.jsonl` (all pulls), `backtest-<asof>*.out`, `day-check.out`, `<market>.out` |
| Rank UI | https://rank.ml-ux.sfive.tech (Streamlit in Docker) |
| Venv | `/home/ubuntu/ml/.venv` (Python 3.12: duckdb, polars, pandas, implicit, lightgbm, torch CPU) |

Timers (+07): `ml-pull-nightly` 02:00 · `ml-recs-refresh` 04:30 · `ml-backtest-weekly` Wed 06:00 (builds a week, writes the Notion
row) · `ml-day-check` 07:00 (Slack alarm, rounds only) · `ml-backfill-<market>` always on, a pass every 30 min.
Slack channel for all of it: #ux-pipeline (`C0BT4102X7V`).

## 4 · How to test an idea

1. `bin/status`: check you're outside the window and there's enough disk.
2. `bin/new-exp <name>`, then edit `build()` in its `run.py`. It gets the snapshot's `hist` (60-day history), `truth` (the week after)
   and the stored ranker list, and returns `(model, brand, member, game, rk)` rows.
3. `bin/py experiments/<dir>/run.py mx96g1 <asof>` first (small, under a minute), then `… run.py all` (20 clusters × newest 2 weeks).
4. **Validation rule:** the "rebuilt default" row must equal the stored `hybrid (recent continue + ranker new)` to 0.0 pt on
   every cluster-week. If it doesn't, the harness is wrong. Fix that before reading any other number.
5. Report like the read-out: player-weighted per market, range over clusters, and how many cluster-weeks improve. Always give
   **both HR@10 and new-game HR**, since most changes trade one for the other. Fill in the experiment's README.

Scoring (same as `recs_eval.py` and the UI Overview): scored players = those with a `popular 30/70 minus played` list who play
in the test week. HR@10 = ≥1 of the top 10 played. New = a hit on a game not in the 60-day `hist`.

Reference: `recs_mx96g1_2026-10-19.duckdb` gives default 88.7 % · als-continue hybrid 84.2 % · live 64.4 % on 8,148 players.

## 5 · Traps

- **`~` means `/home/sunny` here.** Shared scripts use `~/ml/...`. Run as sunny, they read and write `/home/sunny/ml/...`.
  Use absolute `/home/ubuntu/ml/...` paths (mlkit does).
- Backtests are frozen **as of a Monday**: the week labelled "27 Oct–2 Nov" is as of 2026-10-26 (Tue–Mon).
- `asof` is a reserved word in DuckDB and HogQL. Use `list_date` or `asof_d` as a column name.
- PostHog `accountId` = the **brand**, not the player.
- The daily game report undercounts **Sundays** (only the first ~4 h). The live ranking still has this bug (4 Nov).
- DuckDB float sums vary with parallelism: **round + ORDER BY** before training, or two runs aren't comparable.
- egkz1 (EG) has too few players: it's never scored. PE's live list was a frozen 10-game list until 22 Oct.
- Opening a shared `.duckdb` read-only fails while a writer holds it (mostly during the nightly window). Wait; don't retry in a loop.
- Run Python with `bin/py` (`-P`: no script-dir imports) so a stray `json.py` in a data folder can't be imported.
- **Memory:** the VM has 30 GB shared with the nightly jobs. Loading a big cluster whole into pandas took 17 GB (bdk1).
  `mlkit.load()` keeps only scored players and the ranker list (bdk1: about 4 GB, 30 s). Run clusters one after another, not in parallel,
  and prefer DuckDB SQL for anything heavier (see `experiments/2026-11-04-slot-split/`).
- `ml-pull-nightly` exits 0 even when the dims step fails on every cluster. Check `bin/status` ("errors in pull.jsonl today"), not just exit codes.

## 6 · State as of 4 Nov 2026 (check before relying on it)

- Default personal list = `hybrid (recent continue + ranker new)` since 3 Nov. Confirmed on the 27 Oct–2 Nov week: 20/20 clusters,
  +2.3 to +8.5 pt HR@10 vs the ALS-continue hybrid.
- Live Popular list: share-of-total 30/70 since 22–23 Oct on every market (raw formula before). Sunday bug still in the inputs.
- **Broken since 4 Nov 00:00 +07:** `pull_dims.py` on all 21 clusters (`game."freeSpinEnabled"` dropped upstream), so no catalogue or
  live-ranking updates. Reported via `drafts/slack-ux-pipeline-2026-11-04.md` (check whether it's been sent and fixed).
- Nothing is player-facing yet. The A/B test needs list identity on `evt:home_game_list_shown` / `act:game_open_triggered`
  (`drafts/spec-game-list-impression-and-ab.md`).
- Open with others: PostHog S3 read key (Harvey, #devops), moving the code into git (Yann, `pipeline/`).
