"""mlkit: small helpers for experiments in /home/sunny/ml. Reads the shared pipeline's data, never writes to it.

    from mlkit import guard, snap_path, load, score, save_csv, CLUSTERS

- guard()            refuse to run during the nightly window (02:00–07:00 +07) or when disk is low
- snap_path(c, asof) absolute path of a shared backtest snapshot (recs_<c>_<asof>.duckdb)
- load(c, asof)      hist / truth / stored recs of one snapshot as pandas DataFrames (opened READ-ONLY)
- score(c, asof, mine, stored=[...], lists=[...])  HR@10 · new · both, the same SQL as pull/recs_eval.py and the rank UI
                     Overview; `lists` adds brand lists from snap.lists (e.g. "live (as stored)")
- save_csv(rows, path) write result rows under your experiment's out/ folder
- attach_market(con, c) + plays_sql(con, c)  the market cache's plays (archive + live, READ-ONLY), for anything the
                     snapshot lacks (days, hours, earlier history); ep(day, c), day_sql(), hour_sql() use the market's day

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

# copied from pull/market.py (4 Nov 2026): fixed UTC offset of each market's product day, and the archive -> live cut
TZ_HOURS = {"MX": -6, "TH": 7, "BD": 6, "PH": 8, "PK": 5, "BR": -3, "PE": -5, "CO": -5, "EG": 2}
ARCHIVE_CUT = {"MX": "2026-08-16", "TH": "2026-08-17", "BD": "2026-08-18", "PH": "2026-08-18", "PK": "2026-08-19",
               "BR": "2026-08-20", "PE": "2026-08-20", "CO": "2026-08-20", "EG": "2026-08-20"}

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
    """An in-memory DuckDB with polite limits (the VM is shared with the nightly jobs). Spills go to scratch/duck_tmp."""
    tmp = f"{HOME}/scratch/duck_tmp"
    os.makedirs(tmp, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}; SET memory_limit = '{memory}'; SET temp_directory = '{tmp}'; "
                "SET enable_progress_bar = false")
    return con


def market_db(c):
    """The shared market cache holding plays_<c>, archive_<c>, rank_<c>, game_<c> (pull/market.py db_path)."""
    m = MARKET_OF[c]
    return f"{SHARED_DATA}/ml.duckdb" if m == "MX" else f"{SHARED_DATA}/{m.lower()}.duckdb"


def ep(day, c):
    """Epoch seconds of local midnight of `day` in the cluster's market (pull/market.py ep)."""
    tz = dt.timezone(dt.timedelta(hours=TZ_HOURS[MARKET_OF[c]]))
    return int(dt.datetime.combine(day, dt.time(0), tzinfo=tz).timestamp())


def attach_market(con, c, alias="mkt"):
    """Attach the market cache READ-ONLY. Raises duckdb.IOException while a writer holds it (mostly 02:00-07:00)."""
    con.execute(f"ATTACH '{market_db(c)}' AS {alias} (READ_ONLY)")
    return con


def plays_sql(con, c, alias="mkt"):
    """A parenthesised subquery over the cluster's plays (brand, member, game, ts, rounds, bet, earn): live plays from the
    archive cut on, archive before it (pull/market.py plays_expr). No status filter, like build_recs.py."""
    sel = ('SELECT "accountId" AS brand, "memberId" AS member, "gameId" AS game, ts, rounds, "betAmount" AS bet, '
           '"earnAmount" AS earn FROM {t} WHERE "memberId" IS NOT NULL AND "gameId" IS NOT NULL')
    have = {r[0] for r in con.execute(f"SELECT table_name FROM duckdb_tables() WHERE database_name = '{alias}'").fetchall()}
    if f"archive_{c}" in have:
        cut = f"TIMESTAMPTZ '{ARCHIVE_CUT[MARKET_OF[c]]} 00:00:00+00'"
        return (f"({sel.format(t=f'{alias}.plays_{c}')} AND ts >= {cut} "
                f"UNION ALL {sel.format(t=f'{alias}.archive_{c}')} AND ts < {cut})")
    return f"({sel.format(t=f'{alias}.plays_{c}')})"


def day_sql(c, day0, col="ts"):
    """SQL for the market-day index of `col` counted from local midnight of day0 (build_recs.py convention)."""
    return f"floor((epoch({col}) - {ep(day0, c)}) / 86400)"


def hour_sql(c, col="ts"):
    """SQL for the market-local hour 0-23 of `col`."""
    return f"CAST(floor(((epoch({col}) + {TZ_HOURS[MARKET_OF[c]] * 3600}) % 86400) / 3600) AS INTEGER)"


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


def score(c, asof, mine=None, stored=(DEFAULT_MODEL,), lists=()):
    """Score your lists (DataFrame with model, brand, member, game, rk) next to stored models of the snapshot, and next to
    brand lists from snap.lists (`lists`, e.g. ("live (as stored)",): every scored player gets the brand's list).
    Returns [{model, players, hr, new_hr, both_hr}], best HR first."""
    con = attach(connect(), c, asof)
    parts = []
    if stored:
        ms = ", ".join(f"'{m}'" for m in stored)
        parts.append(f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model IN ({ms})")
    if lists:
        ls = ", ".join(f"'{m}'" for m in lists)
        parts.append(f"SELECT l.model, w.brand, w.member, l.game, l.rk FROM w JOIN snap.lists l ON l.brand = w.brand "
                     f"WHERE l.model IN ({ls})")
    if mine is not None and len(mine):
        con.register("_mine", mine[["model", "brand", "member", "game", "rk"]])
        parts.append("SELECT model, brand, member, game, rk FROM _mine")
    rows = score_sql(con, " UNION ALL ".join(parts))
    con.close()
    return rows


def score_sql(con, union):
    """Score lists already in SQL (`union` = SELECT model, brand, member, game, rk ...) on a connection with the snapshot
    attached as `snap`. Same rule and output as score(); use it when the lists are too big for a DataFrame."""
    rows = con.execute(EVAL_SQL.format(scored=SCORED_MODEL, union=union)).fetchall()
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
