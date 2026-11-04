"""mlkit: small helpers for experiments in /home/sunny/ml. Reads the shared pipeline's data, never writes to it.

    from mlkit import guard, snap_path, load, score, save_csv, CLUSTERS

- guard()            refuse to run during the nightly window (02:00–07:00 +07) or when disk is low
- snap_path(c, asof) absolute path of a shared backtest snapshot (recs_<c>_<asof>.duckdb)
- load(c, asof)      hist / truth / stored recs of one snapshot as pandas DataFrames (opened READ-ONLY)
- score(c, asof, mine, stored=[...])  HR@10 · new · both, the same SQL as pull/recs_eval.py and the rank UI Overview
- save_csv(rows, path) write result rows under your experiment's out/ folder

All paths are absolute on purpose: the shared scripts use "~/ml/...", which from the sunny account means /home/sunny/ml.
"""
import csv
import datetime as dt
import os
import shutil
import sys

import duckdb

SHARED = "/home/ubuntu/ml"                      # the live pipeline: READ ONLY
SHARED_DATA = f"{SHARED}/data"
SHARED_LOGS = f"{SHARED}/logs"
HOME = "/home/sunny/ml"                         # this workspace
BKK = dt.timezone(dt.timedelta(hours=7))
NIGHTLY = (2, 7)                                # 02:00–07:00 +07: nightly pulls, refresh, weekly backtest
MIN_FREE_GB = 10

MARKETS = {                                     # copied from pull/common.py (4 Nov 2026)
    "MX": ["mx96g1", "mxk1"],
    "BD": ["bd96g1", "bdk1"],
    "PH": ["phk1", "phk2", "phblg1", "ph96g1"],
    "TH": ["kzg1", "kzg2", "blg1", "96g1", "wdb1", "96g2", "thblg2"],
    "PK": ["pkkz1", "pk96g1"],
    "BR": ["brlkz1"],
    "PE": ["pekz1"],
    "CO": ["cokz1"],
    "EG": ["egkz1"],                            # too few active players: not scored in backtests
}
CLUSTERS = [c for cs in MARKETS.values() for c in cs]
SCORED_CLUSTERS = [c for c in CLUSTERS if c != "egkz1"]
MARKET_OF = {c: m for m, cs in MARKETS.items() for c in cs}

DEFAULT_MODEL = "hybrid (recent continue + ranker new)"   # the default list since 3 Nov 2026
SCORED_MODEL = "popular 30/70 minus played"               # defines who is scored (warm players with a list)
RANKER_NEW = "ranker (new games only)"

# Same rule as pull/recs_eval.py: scored = players with a SCORED_MODEL list who played in the test week;
# hit = any of the top 10 played; new = a hit on a game not in the 60-day hist; both = an old and a new hit.
EVAL_SQL = """
WITH scored AS (SELECT DISTINCT brand, member FROM snap.recs WHERE model = '{scored}'),
w AS (SELECT brand, member FROM scored JOIN (SELECT DISTINCT brand, member FROM snap.truth) USING (brand, member)),
allrecs AS ({union}),
shown AS (SELECT r.model, r.brand, r.member, r.game FROM allrecs r JOIN w USING (brand, member) WHERE r.rk <= 10),
per AS (
    SELECT s.model, s.brand, s.member,
           max((t.game IS NOT NULL)::INT) AS hit,
           max((t.game IS NOT NULL AND h.game IS NULL)::INT) AS new_hit,
           max((t.game IS NOT NULL AND h.game IS NOT NULL)::INT) AS old_hit
      FROM shown s
      LEFT JOIN snap.truth t ON t.brand = s.brand AND t.member = s.member AND t.game = s.game
      LEFT JOIN snap.hist h ON h.brand = s.brand AND h.member = s.member AND h.game = s.game
     GROUP BY 1, 2, 3)
SELECT model, count(*) AS players, avg(hit) AS hr, avg(new_hit) AS new_hr, avg(new_hit * old_hit) AS both_hr
  FROM per GROUP BY 1 ORDER BY hr DESC"""


def guard(min_free_gb=MIN_FREE_GB):
    """Stop during the nightly window or on low disk. Override the window with ML_FORCE=1 (ask first)."""
    now = dt.datetime.now(BKK)
    if NIGHTLY[0] <= now.hour < NIGHTLY[1] and os.environ.get("ML_FORCE") != "1":
        sys.exit(f"guard: {now:%H:%M} +07 is inside the nightly window {NIGHTLY[0]:02d}:00–{NIGHTLY[1]:02d}:00. Try after 07:00.")
    free = shutil.disk_usage("/").free / 1e9
    if free < min_free_gb:
        sys.exit(f"guard: only {free:.1f} GB free on / (need {min_free_gb}). Clean scratch/ or old out/ first.")


def connect(threads=4, memory="8GB"):
    """An in-memory DuckDB with polite limits (the VM is shared with the nightly jobs)."""
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}; SET memory_limit = '{memory}'")
    return con


def snap_path(c, asof):
    p = f"{SHARED_DATA}/recs_{c}_{asof}.duckdb"
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} not on disk (older weeks live in S3, see pull/snapshot_store.py). "
                                f"Do not fetch into {SHARED_DATA}; ask Yann.")
    return p


def attach(con, c, asof, alias="snap"):
    con.execute(f"ATTACH '{snap_path(c, asof)}' AS {alias} (READ_ONLY)")
    return con


SCORED_SET = f"""SELECT brand, member FROM (SELECT DISTINCT brand, member FROM snap.recs WHERE model = '{SCORED_MODEL}')
                  JOIN (SELECT DISTINCT brand, member FROM snap.truth) USING (brand, member)"""


def load(c, asof, tables=("hist", "truth"), models=(RANKER_NEW,), scored_only=True):
    """Snapshot tables as DataFrames, sorted, for the players score() will score (scored_only=False: everyone).
    'recs' holds only `models`. Big clusters (bdk1, phk1, kzg1) are millions of rows, so ask only for what build() needs."""
    con = attach(connect(), c, asof)
    con.execute(f"CREATE TEMP TABLE w AS {SCORED_SET if scored_only else 'SELECT DISTINCT brand, member FROM snap.hist'}")
    order = {"hist": "brand, member, last_ts DESC, rounds DESC, game", "truth": "brand, member, rounds DESC, game"}
    out = {t: con.execute(f"SELECT x.* FROM snap.{t} x JOIN w USING (brand, member) ORDER BY {order.get(t, 'ALL')}").fetchdf()
           for t in tables}
    if models:
        ms = ", ".join(f"'{m}'" for m in models)
        out["recs"] = con.execute(f"SELECT r.model, r.brand, r.member, r.game, r.rk FROM snap.recs r JOIN w USING (brand, member) "
                                  f"WHERE r.model IN ({ms}) ORDER BY r.model, r.brand, r.member, r.rk").fetchdf()
    out["meta"] = dict(con.execute("SELECT k, v FROM snap.meta").fetchall())
    con.close()
    return out


def score(c, asof, mine=None, stored=(DEFAULT_MODEL,)):
    """Score your lists (DataFrame with model, brand, member, game, rk) next to stored models of the snapshot.
    Returns [{model, players, hr, new_hr, both_hr}], best HR first."""
    con = attach(connect(), c, asof)
    parts = []
    if stored:
        ms = ", ".join(f"'{m}'" for m in stored)
        parts.append(f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model IN ({ms})")
    if mine is not None and len(mine):
        con.register("_mine", mine[["model", "brand", "member", "game", "rk"]])
        parts.append("SELECT model, brand, member, game, rk FROM _mine")
    rows = con.execute(EVAL_SQL.format(scored=SCORED_MODEL, union=" UNION ALL ".join(parts))).fetchall()
    con.close()
    return [dict(model=m, players=n, hr=round(h, 5), new_hr=round(hn, 5), both_hr=round(hb, 5)) for m, n, h, hn, hb in rows]


def print_scores(c, asof, rows):
    d = dt.date.fromisoformat(asof)
    print(f"\n{c} ({MARKET_OF.get(c, '?')}) asof {asof}  test {d + dt.timedelta(days=1)}..{d + dt.timedelta(days=7)}")
    for r in rows:
        print(f"   {r['model']:44s} {r['players']:9,d}  HR@10 {r['hr']:6.1%}  new {r['new_hr']:6.1%}  both {r['both_hr']:6.1%}")


def save_csv(rows, path):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def week_asofs(n=2, last=None):
    """The newest n weekly as-of Mondays that have a snapshot on disk for mx96g1 (newest last)."""
    import glob
    ds = sorted(p.rsplit("_", 1)[1][:10] for p in glob.glob(f"{SHARED_DATA}/recs_mx96g1_2026-*.duckdb"))
    if last:
        ds = [d for d in ds if d <= last]
    return ds[-n:]
