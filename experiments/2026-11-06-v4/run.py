#!/usr/bin/env python3
"""v4: the v3 unified own + new ranker plus the Netflix/Shopify findings that can be applied offline now, compared
with v1, v2 and v3 on the same frozen week (issues/recsys-research/, notes/2026-11-06-netflix-shopify-recsys.md).

What v4 adds to v3 (experiments/2026-11-05-v3-unified/; candidates = own 20 recent + ranker new 10 + popular 10 + live 20):
  issue 01  two new candidate sources, 10 new games each, and their scores as features:
            rp3    RP3beta-style co-play from the 60-day history (beta RP3_BETA, NEIGH neighbours per game)
            trans  next-game transitions from the player's most recent game (60-day plays, market cache)
  issue 04  intent features (FM-Intent): p_new7 (own games first played in the window's last 7 days), p_new7_rshare
            (their share of the player's last-7-day rounds), p_try_share (own games played on one day only), first_days
  issue 03  v4a: the same model trained with adoption weights exp(r / LAMBDA) on positives, r = (label-week play days - 1) / 6
Variants on the test week, next to the stored default (v1):
  v1: default (rebuilt)        3/5 own recent games + ranker new (must equal the stored default)
  v2: own + live (no ML)       3/5 own recent games + the live Popular list (pct-rank where a brand has none) minus played
  v3: unified top 10 / v3: learned continue (3/5)   the v3 model, re-trained here (must equal v3's CSVs)
  v4: top 10 / v4: 3/5 split   the v4 model; the split keeps 3/5 own slots (own by p) and fills new slots by p
  v4a: top 10 / v4a: 3/5 split the adoption-weighted v4 model
Each test week is scored with models trained on the frozen week before it. Metrics: HR@10, new-game HR, adopted-game HR
(a new game played on >= 2 market days of the test week, X2 SQL), beyond5 HR.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-06-v4/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-06-v4/run.py all
    bin/py experiments/2026-11-06-v4/run.py summarize
"""
import csv
import datetime as dt
import gc
import glob
import os
import re
import sys
import time

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.metrics import roc_auc_score

from mlkit import (DEFAULT_MODEL, HOME, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SCORED_SET, attach,
                   attach_market, connect, day_sql, ep, guard, plays_sql, save_csv, score_sql, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
V3_OUT = f"{HOME}/experiments/2026-11-05-v3-unified/out"
V2_OUT = f"{HOME}/experiments/2026-11-05-v2-arms/out"
X2 = f"{HOME}/experiments/2026-11-05-v2-adoption/out"
LIVE, PCT = "live (as stored)", "normalised 30/70 (pct-rank)"
TRAIN_CAP = 50_000                      # same as v3
COPLAY_SAMPLE = 100_000                 # players per cluster for the co-play graph
RP3_BETA, NEIGH, N_SRC = 0.5, 20, 10
LAMBDA = 0.5
TYPES = ["SLOT", "FISHING", "ARCADE", "LIVE", "CRASH", "SPORTS", "NO CATEGORY", "OTHER"]
ADDA7, ADDA7_CLUSTER = "4c0fc28c-5ee5-49ec-abb8-777b2b1295f5", "bdk1"
FEATS3 = ["is_own", "rec_days", "rec_rank", "play_days", "rounds_log", "round_share", "bet_share", "days_ratio",
          "rk_ranker", "rk_pop", "rk_live", "g_pop_rank", "g_player_share", "g_recent_share", "g_repeat_share", "g_type",
          "p_type_share", "p_prov_share", "p_games", "p_rounds_log", "p_days_max", "p_rec_days"]
NEW_FEATS = ["rk_rp3", "rp3_score", "rk_tr", "tr_score", "first_days", "p_new7", "p_new7_rshare", "p_try_share"]
FEATS4 = FEATS3 + NEW_FEATS
PARAMS = dict(objective="binary", metric=["binary_logloss", "auc"], learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
              feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, num_threads=4, seed=7,
              deterministic=True, force_col_wise=True, verbose=-1)
REBUILT, V2 = "v1: default (rebuilt)", "v2: own + live (no ML)"
V3_TOP, V3_CONT = "v3: unified top 10", "v3: learned continue (3/5)"
V4_TOP, V4_SPLIT = "v4: top 10", "v4: 3/5 split"
V4A_TOP, V4A_SPLIT = "v4a: top 10 (adoption-weighted)", "v4a: 3/5 split (adoption-weighted)"
VARIANTS = [REBUILT, V2, V3_TOP, V3_CONT, V4_TOP, V4_SPLIT, V4A_TOP, V4A_SPLIT]
V3_NAMES = {V3_TOP: "unified: top 10", V3_CONT: "unified: learned continue (3/5)"}
BAR_HR, BAR_ADOPT, BAR_CLUSTERS, GUARD_HR = 0.5, 0.3, 15, -0.2


def build(con, c, asof, cap=None):
    """Candidate table `cf` on a connection with the snapshot attached as `snap`: v3's candidates and features verbatim
    (in_v3 = 1) plus the rp3 / transition candidates (in_v3 = 0) and the v4 features. Also `tdays` (label-week play days of
    the sampled players) and `pw`, `own`, `lv`. Returns (live_source, notes)."""
    a = dt.date.fromisoformat(asof)
    t_end = ep(a + dt.timedelta(days=1), c)
    w0, w7 = ep(a - dt.timedelta(days=59), c), ep(a - dt.timedelta(days=6), c)
    tr1, te1 = a + dt.timedelta(days=1), a + dt.timedelta(days=8)
    sample = f"ORDER BY hash(brand || ':' || member) LIMIT {cap}" if cap else ""
    # ---- v3 build(), verbatim ----
    con.execute(f"""CREATE OR REPLACE TABLE pw AS
        SELECT brand, member, row_number() OVER (ORDER BY brand, member) - 1 AS pid, (hash(member) % 10 = 0) AS hold
          FROM (SELECT * FROM ({SCORED_SET}) s {sample})""")
    tcase = ("CASE WHEN t IN ('SLOT', 'SLOTS') THEN 'SLOT' WHEN t IS NULL THEN 'NO CATEGORY' "
             f"WHEN t IN ({', '.join(repr(x) for x in TYPES[1:7])}) THEN t ELSE 'OTHER' END")
    con.execute(f"""CREATE OR REPLACE TABLE gt AS SELECT brand, game, {tcase} AS type, provider
        FROM (SELECT brand, game, any_value(type) AS t, any_value(provider) AS provider FROM snap.games GROUP BY 1, 2)""")
    con.execute(f"""CREATE OR REPLACE TABLE gf AS
        WITH bp AS (SELECT brand, count(DISTINCT member) AS n FROM snap.hist GROUP BY 1),
             g AS (SELECT brand, game, count(DISTINCT member) AS g_players,
                          avg((epoch(last_ts) >= {ep(a - dt.timedelta(days=6), c)})::INT) AS g_recent_share,
                          avg((play_days >= 2)::INT) AS g_repeat_share FROM snap.hist GROUP BY 1, 2)
        SELECT g.*, g.g_players / bp.n AS g_player_share,
               row_number() OVER (PARTITION BY g.brand ORDER BY g.g_players DESC, g.game) AS g_pop_rank
          FROM g JOIN bp USING (brand)""")
    con.execute("""CREATE OR REPLACE TABLE own AS
        SELECT h.brand, h.member, h.game, h.rounds, h.bet, h.play_days, h.last_ts,
               row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS rr
          FROM snap.hist h JOIN pw USING (brand, member)""")
    con.execute(f"""CREATE OR REPLACE TABLE pf AS
        SELECT brand, member, count(*) AS p_games, sum(rounds) AS p_rounds, sum(bet) AS p_bet, max(play_days) AS p_days_max,
               min(({t_end} - epoch(last_ts)) / 86400.0) AS p_rec_days FROM own GROUP BY 1, 2""")
    con.execute("""CREATE OR REPLACE TABLE ptype AS
        SELECT o.brand, o.member, g.type, sum(o.rounds) / NULLIF(any_value(p.p_rounds), 0) AS share
          FROM own o JOIN gt g ON g.brand = o.brand AND g.game = o.game JOIN pf p ON p.brand = o.brand AND p.member = o.member
         GROUP BY 1, 2, 3""")
    con.execute("""CREATE OR REPLACE TABLE pprov AS
        SELECT o.brand, o.member, g.provider, sum(o.rounds) / NULLIF(any_value(p.p_rounds), 0) AS share
          FROM own o JOIN gt g ON g.brand = o.brand AND g.game = o.game JOIN pf p ON p.brand = o.brand AND p.member = o.member
         GROUP BY 1, 2, 3""")
    con.execute(f"""CREATE OR REPLACE TABLE lv AS
        WITH hb AS (SELECT DISTINCT brand FROM snap.lists WHERE model = '{LIVE}')
        SELECT brand, game, rk, 'live' AS src FROM snap.lists WHERE model = '{LIVE}' AND rk <= 50
        UNION ALL SELECT brand, game, rk, 'pct-rank' FROM snap.lists
         WHERE model = '{PCT}' AND rk <= 50 AND brand NOT IN (SELECT brand FROM hb)""")
    src = dict(con.execute("SELECT src, count(DISTINCT brand) FROM lv GROUP BY 1").fetchall())
    con.execute(f"""CREATE OR REPLACE TABLE cand3 AS
        WITH nw AS (
            SELECT r.brand, r.member, r.game, r.rk AS rk_ranker, NULL::BIGINT AS rk_pop FROM snap.recs r JOIN pw USING (brand, member)
             WHERE r.model = '{RANKER_NEW}'
            UNION ALL SELECT r.brand, r.member, r.game, NULL, r.rk FROM snap.recs r JOIN pw USING (brand, member)
             WHERE r.model = '{SCORED_MODEL}'
            UNION ALL SELECT pw.brand, pw.member, lv.game, NULL, NULL FROM pw JOIN lv USING (brand) WHERE lv.rk <= 20),
        nw2 AS (SELECT brand, member, game, min(rk_ranker) AS rk_ranker, min(rk_pop) AS rk_pop FROM nw
                 GROUP BY 1, 2, 3)
        SELECT brand, member, game, 1 AS is_own, rr, NULL::BIGINT AS rk_ranker, NULL::BIGINT AS rk_pop FROM own WHERE rr <= 20
        UNION ALL SELECT n.brand, n.member, n.game, 0, NULL, n.rk_ranker, n.rk_pop FROM nw2 n ANTI JOIN own o USING (brand, member, game)""")

    # ---- market cache: 60-day plays, label-week days ----
    notes = []
    attach_market(con, c)
    q = plays_sql(con, c)
    con.execute(f"""CREATE OR REPLACE TABLE pl AS
        SELECT p.brand, p.member, p.game, epoch(p.ts) AS t, p.rounds FROM {q} p
         WHERE epoch(p.ts) >= {w0} AND epoch(p.ts) < {t_end}""")
    con.execute(f"""CREATE OR REPLACE TABLE tdays AS
        SELECT p.brand, p.member, p.game, count(DISTINCT {day_sql(c, tr1, 'p.ts')}) AS days, sum(p.rounds) AS rounds
          FROM {q} p JOIN pw USING (brand, member)
         WHERE epoch(p.ts) >= {ep(tr1, c)} AND epoch(p.ts) < {ep(te1, c)}
         GROUP BY 1, 2, 3""")
    n_t, n_m, r_t = con.execute("""SELECT count(*), count(d.game), sum(t.rounds) FROM snap.truth t JOIN pw USING (brand, member)
                                   LEFT JOIN tdays d USING (brand, member, game)""").fetchone()
    r_d = con.execute("SELECT sum(rounds) FROM tdays").fetchone()[0] or 0
    if n_t == 0 or n_m / n_t < 0.995 or abs(r_d - r_t) / max(r_t, 1) > 0.005:
        notes.append(f"truth rebuild {asof} rows {n_m}/{n_t} rounds {r_d}/{r_t}")
        print(f"   !! truth rebuild {c} {asof}: rows {n_m:,}/{n_t:,} rounds {r_d:,}/{r_t:,}")

    # ---- issue 04: intent features ----
    con.execute(f"""CREATE OR REPLACE TABLE fpl AS
        SELECT pl.brand, pl.member, pl.game, min(pl.t) AS first_t, coalesce(sum(pl.rounds) FILTER (WHERE pl.t >= {w7}), 0) AS r7
          FROM pl JOIN pw USING (brand, member) GROUP BY 1, 2, 3""")
    con.execute(f"""CREATE OR REPLACE TABLE pint AS
        WITH a AS (SELECT brand, member, count(*) FILTER (WHERE first_t >= {w7}) AS p_new7,
                          sum(r7) FILTER (WHERE first_t >= {w7}) / NULLIF(sum(r7), 0) AS p_new7_rshare
                     FROM fpl GROUP BY 1, 2),
             b AS (SELECT brand, member, avg((play_days = 1)::INT) AS p_try_share FROM own GROUP BY 1, 2)
        SELECT b.brand, b.member, coalesce(a.p_new7, 0) AS p_new7, coalesce(a.p_new7_rshare, 0) AS p_new7_rshare, b.p_try_share
          FROM b LEFT JOIN a ON a.brand = b.brand AND a.member = b.member""")

    # ---- issue 01: rp3 co-play source ----
    con.execute(f"""CREATE OR REPLACE TABLE hs AS
        WITH sp AS (SELECT brand, member FROM (SELECT DISTINCT brand, member FROM snap.hist)
                     ORDER BY hash(brand || ':' || member), brand, member LIMIT {COPLAY_SAMPLE}),
             h AS (SELECT h.brand, h.member, h.game,
                          row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS r
                     FROM snap.hist h JOIN sp USING (brand, member))
        SELECT brand, member, game FROM h WHERE r <= 20""")
    con.execute(f"""CREATE OR REPLACE TABLE w3 AS
        WITH du AS (SELECT brand, member, count(*) AS n FROM hs GROUP BY 1, 2),
             dg AS (SELECT brand, game, count(*) AS n FROM hs GROUP BY 1, 2),
             pr AS (SELECT a.brand, a.game AS gi, b.game AS gj, sum(1.0 / du.n) AS s
                      FROM hs a JOIN hs b ON a.brand = b.brand AND a.member = b.member AND a.game <> b.game
                      JOIN du ON du.brand = a.brand AND du.member = a.member GROUP BY 1, 2, 3),
             wt AS (SELECT pr.brand, pr.gi, pr.gj, round(pr.s / di.n / pow(dj.n, {RP3_BETA}), 9) AS wv
                      FROM pr JOIN dg di ON di.brand = pr.brand AND di.game = pr.gi JOIN dg dj ON dj.brand = pr.brand AND dj.game = pr.gj)
        SELECT brand, gi, gj, wv FROM (
            SELECT *, row_number() OVER (PARTITION BY brand, gi ORDER BY wv DESC, gj) AS r FROM wt) WHERE r <= {NEIGH}""")
    con.execute("""CREATE OR REPLACE TABLE sp3 AS
        SELECT o.brand, o.member, w3.gj AS game, round(sum(w3.wv), 7) AS rp3_score
          FROM own o JOIN w3 ON w3.brand = o.brand AND w3.gi = o.game WHERE o.rr <= 10 GROUP BY 1, 2, 3""")
    con.execute(f"""CREATE OR REPLACE TABLE rp3c AS
        SELECT brand, member, game, rk_rp3 FROM (
            SELECT s.brand, s.member, s.game,
                   row_number() OVER (PARTITION BY s.brand, s.member ORDER BY s.rp3_score DESC, s.game) AS rk_rp3
              FROM sp3 s
             WHERE NOT EXISTS (SELECT 1 FROM own o WHERE o.brand = s.brand AND o.member = s.member AND o.game = s.game)
               AND EXISTS (SELECT 1 FROM gt WHERE gt.brand = s.brand AND gt.game = s.game))
         WHERE rk_rp3 <= {N_SRC}""")

    # ---- issue 01: next-game transitions ----
    con.execute(f"""CREATE OR REPLACE TABLE tt AS
        WITH s AS (SELECT brand, member, game, lag(game) OVER (PARTITION BY brand, member ORDER BY t, game) AS prev FROM pl),
             e AS (SELECT brand, prev AS gi, game AS gj, count(DISTINCT member) AS n FROM s
                    WHERE prev IS NOT NULL AND prev <> game GROUP BY 1, 2, 3),
             od AS (SELECT brand, gi, sum(n) AS m FROM e GROUP BY 1, 2)
        SELECT brand, gi, gj, tv FROM (
            SELECT e.brand, e.gi, e.gj, round(e.n / od.m, 9) AS tv,
                   row_number() OVER (PARTITION BY e.brand, e.gi ORDER BY e.n DESC, e.gj) AS r
              FROM e JOIN od ON od.brand = e.brand AND od.gi = e.gi) WHERE r <= {NEIGH}""")
    con.execute("CREATE OR REPLACE TABLE lastg AS SELECT brand, member, game AS g1 FROM own WHERE rr = 1")
    con.execute(f"""CREATE OR REPLACE TABLE trc AS
        SELECT brand, member, game, rk_tr FROM (
            SELECT l.brand, l.member, tt.gj AS game,
                   row_number() OVER (PARTITION BY l.brand, l.member ORDER BY tt.tv DESC, tt.gj) AS rk_tr
              FROM lastg l JOIN tt ON tt.brand = l.brand AND tt.gi = l.g1
             WHERE NOT EXISTS (SELECT 1 FROM own o WHERE o.brand = l.brand AND o.member = l.member AND o.game = tt.gj)
               AND EXISTS (SELECT 1 FROM gt WHERE gt.brand = l.brand AND gt.game = tt.gj))
         WHERE rk_tr <= {N_SRC}""")

    # ---- candidates and features ----
    con.execute("""CREATE OR REPLACE TABLE cand AS
        SELECT *, 1 AS in_v3 FROM cand3
        UNION ALL
        SELECT x.brand, x.member, x.game, 0, NULL, NULL, NULL, 0
          FROM (SELECT brand, member, game FROM rp3c UNION SELECT brand, member, game FROM trc) x
          ANTI JOIN cand3 c3 USING (brand, member, game)""")
    # keep only the co-play scores the candidates need (sp3 is up to ~200 rows per player) and free the 60-day plays
    con.execute("""CREATE OR REPLACE TABLE sp3c AS
        SELECT s.* FROM sp3 s SEMI JOIN cand c ON c.brand = s.brand AND c.member = s.member AND c.game = s.game""")
    con.execute("DROP TABLE sp3; DROP TABLE pl; DROP TABLE hs")
    tcode = "CASE gt.type " + " ".join(f"WHEN '{t}' THEN {i}" for i, t in enumerate(TYPES)) + f" ELSE {len(TYPES) - 1} END"
    # built in player chunks (bdk1's 20 M candidate rows ran out of memory in one 20-way join), numbered afterwards
    n_cand = con.execute("SELECT count(*) FROM cand").fetchone()[0]
    k_chunks = max(1, -(-n_cand // 3_000_000))
    con.execute("DROP TABLE IF EXISTS cf_raw")
    for k in range(k_chunks):
        con.execute(f"""{'CREATE TABLE cf_raw AS' if k == 0 else 'INSERT INTO cf_raw'}
        SELECT pw.pid, pw.hold, c.brand, c.member, c.game,
               c.is_own, c.rr, c.rk_ranker, c.rk_pop, lv.rk AS rk_live, pf.p_games, (t.game IS NOT NULL)::INT AS label,
               ({t_end} - epoch(o.last_ts)) / 86400.0 AS rec_days, o.play_days, ln(1 + o.rounds) AS rounds_log,
               o.rounds / NULLIF(pf.p_rounds, 0) AS round_share, o.bet / NULLIF(pf.p_bet, 0) AS bet_share,
               o.play_days / NULLIF(pf.p_days_max, 0) AS days_ratio, gf.g_pop_rank, gf.g_player_share, gf.g_recent_share,
               gf.g_repeat_share, {tcode} AS g_type, coalesce(pt.share, 0) AS p_type_share, coalesce(pp.share, 0) AS p_prov_share,
               ln(1 + pf.p_rounds) AS p_rounds_log, pf.p_days_max, pf.p_rec_days,
               rc.rk_rp3, coalesce(s3.rp3_score, 0) AS rp3_score, tc.rk_tr, coalesce(tt.tv, 0) AS tr_score,
               ({t_end} - f.first_t) / 86400.0 AS first_days, pi.p_new7, pi.p_new7_rshare, pi.p_try_share,
               coalesce(td.days, 0) AS label_days, c.in_v3
          FROM cand c
          JOIN pw ON pw.brand = c.brand AND pw.member = c.member
          JOIN pf ON pf.brand = c.brand AND pf.member = c.member
          LEFT JOIN own o ON o.brand = c.brand AND o.member = c.member AND o.game = c.game
          LEFT JOIN lv ON lv.brand = c.brand AND lv.game = c.game
          LEFT JOIN gf ON gf.brand = c.brand AND gf.game = c.game
          LEFT JOIN gt ON gt.brand = c.brand AND gt.game = c.game
          LEFT JOIN ptype pt ON pt.brand = c.brand AND pt.member = c.member AND pt.type = gt.type
          LEFT JOIN pprov pp ON pp.brand = c.brand AND pp.member = c.member AND pp.provider = gt.provider
          LEFT JOIN snap.truth t ON t.brand = c.brand AND t.member = c.member AND t.game = c.game
          LEFT JOIN rp3c rc ON rc.brand = c.brand AND rc.member = c.member AND rc.game = c.game
          LEFT JOIN sp3c s3 ON s3.brand = c.brand AND s3.member = c.member AND s3.game = c.game
          LEFT JOIN trc tc ON tc.brand = c.brand AND tc.member = c.member AND tc.game = c.game
          LEFT JOIN lastg lg ON lg.brand = c.brand AND lg.member = c.member
          LEFT JOIN tt ON tt.brand = c.brand AND tt.gi = lg.g1 AND tt.gj = c.game
          LEFT JOIN fpl f ON f.brand = c.brand AND f.member = c.member AND f.game = c.game
          LEFT JOIN pint pi ON pi.brand = c.brand AND pi.member = c.member
          LEFT JOIN tdays td ON td.brand = c.brand AND td.member = c.member AND td.game = c.game
         WHERE hash(c.member) % {k_chunks} = {k}""")
    con.execute("""CREATE OR REPLACE TABLE cf AS
        SELECT row_number() OVER (ORDER BY brand, member, game) - 1 AS cid, * FROM cf_raw""")
    con.execute("DROP TABLE cf_raw")
    return "; ".join(f"{k}: {v} brands" for k, v in sorted(src.items())), notes


def fetch(con):
    col = {"rec_rank": "rr"}
    sel = ", ".join(f"coalesce(CAST({col.get(f, f)} AS FLOAT), CAST('NaN' AS FLOAT)) AS {f}" for f in FEATS4)
    d = con.execute(f"SELECT cid, hold::INT AS hold, label, label_days, in_v3, {sel} FROM cf ORDER BY cid").fetchnumpy()
    X = np.column_stack([np.asarray(d[f], dtype=np.float32) for f in FEATS4])
    return (np.asarray(d["cid"], dtype=np.int64), np.asarray(d["hold"], dtype=bool), np.asarray(d["label"], dtype=np.int8),
            np.asarray(d["label_days"], dtype=np.float32), np.asarray(d["in_v3"], dtype=bool), X)


def fit(X, y, hold, feats, w=None):
    gi = feats.index("g_type")
    dtr = lgb.Dataset(X[~hold], y[~hold], weight=None if w is None else w[~hold], feature_name=feats,
                      categorical_feature=[gi], free_raw_data=False)
    dva = lgb.Dataset(X[hold], y[hold], weight=None if w is None else w[hold], reference=dtr)
    return lgb.train(PARAMS, dtr, num_boost_round=2000, valid_sets=[dva],
                     callbacks=[lgb.early_stopping(50, first_metric_only=True, verbose=False)])


def work_con(c, asof):
    """Snapshot attached read-only as `snap`; the work tables go to a scratch DuckDB file (USE work), so DuckDB can evict
    them to disk instead of failing at the 8 GB cap (bdk1's candidate table did). The file is removed by close_work()."""
    path = f"{HOME}/scratch/duck_tmp/v4_{c}_{asof}_{os.getpid()}.duckdb"
    close_work(None, path)
    con = attach(connect(), c, asof)
    con.execute(f"ATTACH '{path}' AS work; USE work; SET preserve_insertion_order = false")
    return con, path


def close_work(con, path):
    if con is not None:
        con.close()
    for p in (path, path + ".wal"):
        if os.path.exists(p):
            os.remove(p)


def train(c, asof):
    con, path = work_con(c, asof)
    _, notes = build(con, c, asof, cap=TRAIN_CAP)
    n_players = con.execute("SELECT count(*) FROM pw").fetchone()[0]
    _, hold, y, days, in3, X = fetch(con)
    close_work(con, path)
    i3 = [FEATS4.index(f) for f in FEATS3]
    meta = dict(train_players=n_players, train_rows_v3=int(in3.sum()), train_rows=len(y), train_pos=int(y.sum()),
                train_pos_v3=int(y[in3].sum()))
    if y[in3].sum() < 500:
        print(f"   SKIP models {c}: {int(y[in3].sum())} positives")
        return None, meta, notes
    w = np.where(y == 1, np.exp((np.clip(days, 1, 7) - 1) / 6.0 / LAMBDA), 1.0).astype(np.float32)
    m3 = fit(X[in3][:, i3], y[in3], hold[in3], FEATS3)
    m4 = fit(X, y, hold, FEATS4)
    m4a = fit(X, y, hold, FEATS4, w)
    os.makedirs(OUT, exist_ok=True)
    for name, m, feats in (("v4", m4, FEATS4), ("v4a", m4a, FEATS4)):
        imp = m.feature_importance(importance_type="gain")
        save_csv([dict(model=name, feature=f, gain=round(float(g), 2), share=round(float(g / max(imp.sum(), 1e-9)), 5))
                  for f, g in zip(feats, imp)], f"{OUT}/importance_{name}_{c}_{asof}.csv")
    meta.update(trees_v3=m3.best_iteration, trees_v4=m4.best_iteration, trees_v4a=m4a.best_iteration,
                hold_auc_v3=round(m3.best_score["valid_0"]["auc"], 5), hold_auc_v4=round(m4.best_score["valid_0"]["auc"], 5))
    return (m3, m4, m4a), meta, notes


LISTS_SQL = f"""
CREATE OR REPLACE TABLE vlists AS
WITH x AS (SELECT cf.brand, cf.member, cf.game, cf.is_own, cf.rr, cf.rk_ranker, cf.in_v3, pr.p3, pr.p4, pr.p4a,
                  CASE WHEN cf.p_games >= 3 THEN 5 ELSE 3 END AS n5,
                  CASE WHEN cf.is_own = 1 THEN row_number() OVER (PARTITION BY cf.brand, cf.member, cf.is_own ORDER BY pr.p3 DESC, cf.rr) END AS o3,
                  CASE WHEN cf.is_own = 1 THEN row_number() OVER (PARTITION BY cf.brand, cf.member, cf.is_own ORDER BY pr.p4 DESC, cf.rr) END AS o4,
                  CASE WHEN cf.is_own = 1 THEN row_number() OVER (PARTITION BY cf.brand, cf.member, cf.is_own ORDER BY pr.p4a DESC, cf.rr) END AS o4a
             FROM cf JOIN pred pr USING (cid)),
v AS (
  SELECT '{REBUILT}' AS model, brand, member, game,
         row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, rr, rk_ranker) AS rk
    FROM x WHERE (is_own = 1 AND rr <= n5) OR rk_ranker IS NOT NULL
  UNION ALL
  SELECT '{V3_CONT}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, o3, rk_ranker)
    FROM x WHERE in_v3 = 1 AND ((is_own = 1 AND o3 <= n5) OR rk_ranker IS NOT NULL)
  UNION ALL
  SELECT '{V3_TOP}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY p3 DESC, is_own DESC, rr, rk_ranker, game)
    FROM x WHERE in_v3 = 1
  UNION ALL
  SELECT '{V4_TOP}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY p4 DESC, is_own DESC, rr, rk_ranker, game)
    FROM x
  UNION ALL
  SELECT '{V4_SPLIT}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, o4, p4 DESC, game)
    FROM x WHERE (is_own = 1 AND o4 <= n5) OR is_own = 0
  UNION ALL
  SELECT '{V4A_TOP}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY p4a DESC, is_own DESC, rr, rk_ranker, game)
    FROM x
  UNION ALL
  SELECT '{V4A_SPLIT}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, o4a, p4a DESC, game)
    FROM x WHERE (is_own = 1 AND o4a <= n5) OR is_own = 0)
SELECT * FROM v WHERE rk <= 10
UNION ALL
SELECT '{V2}', brand, member, game, rk FROM (
    SELECT brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY k, ord) AS rk FROM (
        SELECT o.brand, o.member, o.game, 0 AS k, o.rr AS ord FROM own o JOIN pf USING (brand, member)
         WHERE o.rr <= CASE WHEN pf.p_games >= 3 THEN 5 ELSE 3 END
        UNION ALL
        SELECT pw.brand, pw.member, lv.game, 1, lv.rk FROM pw JOIN lv USING (brand)
         WHERE NOT EXISTS (SELECT 1 FROM own o WHERE o.brand = pw.brand AND o.member = pw.member AND o.game = lv.game)))
 WHERE rk <= 10"""


def metrics(con, union, brand=None):
    """HR@10 / new / both (mlkit rule) plus adopted-game HR and beyond5 HR per model, on the scored players."""
    bf = f"WHERE brand = '{brand}'" if brand else ""
    u = f"SELECT * FROM ({union}) {bf}"
    rows = {r["model"]: r for r in score_sql(con, u)}
    extra = con.execute(f"""
        WITH allrecs AS ({u}), sc AS ({SCORED_SET}),
        own5 AS (SELECT brand, member, game FROM own WHERE rr <= 5),
        shown AS (SELECT r.model, r.brand, r.member, r.game FROM allrecs r JOIN sc USING (brand, member) WHERE r.rk <= 10),
        per AS (SELECT s.model, s.brand, s.member,
                       max((d.game IS NOT NULL AND h.game IS NULL AND d.days >= 2)::INT) AS adopt,
                       max((t.game IS NOT NULL AND o5.game IS NULL)::INT) AS b5
                  FROM shown s
                  LEFT JOIN tdays d ON d.brand = s.brand AND d.member = s.member AND d.game = s.game
                  LEFT JOIN snap.hist h ON h.brand = s.brand AND h.member = s.member AND h.game = s.game
                  LEFT JOIN snap.truth t ON t.brand = s.brand AND t.member = s.member AND t.game = s.game
                  LEFT JOIN own5 o5 ON o5.brand = s.brand AND o5.member = s.member AND o5.game = s.game GROUP BY 1, 2, 3)
        SELECT model, avg(adopt), avg(b5) FROM per GROUP BY 1""").fetchall()
    for m, ad, b5 in extra:
        rows[m].update(adopt_hr=round(ad, 5), beyond5_hr=round(b5, 5))
    return rows


def check_v3(c, test, rows, notes):
    p = f"{V3_OUT}/{c}_{test}.csv"
    if not os.path.exists(p):
        print(f"   (no v3 CSV for {c} {test}: v3 reproduction not checked)")
        return None
    with open(p) as f:
        ref = {r["model"]: r for r in csv.DictReader(f)}
    for mine, theirs in V3_NAMES.items():
        r = ref.get(theirs)
        if r is None or abs(rows[mine]["hr"] - float(r["hr"])) > 1e-5 or abs(rows[mine]["new_hr"] - float(r["new_hr"])) > 1e-5:
            got = (rows[mine]["hr"], rows[mine]["new_hr"])
            notes.append(f"v3 repro {mine} {got} vs {(r['hr'], r['new_hr']) if r else None}")
            print(f"   !! v3 reproduction {c} {test} {mine}: {got} vs v3 CSV {(r['hr'], r['new_hr']) if r else None}")
    return int(ref["unified: top 10"]["train_rows"]) if "unified: top 10" in ref else None


def run(c, test, train_asof):
    t0 = time.time()
    models, meta, notes = train(c, train_asof)
    gc.collect()
    con, path = work_con(c, test)
    live_source, n2 = build(con, c, test)
    notes += n2
    cid, _, y, _, in3, X = fetch(con)
    i3 = [FEATS4.index(f) for f in FEATS3]
    if models is not None:
        m3, m4, m4a = models
        p3 = np.full(len(y), np.nan)
        p3[in3] = m3.predict(X[in3][:, i3], num_iteration=m3.best_iteration)
        p4 = m4.predict(X, num_iteration=m4.best_iteration)
        p4a = m4a.predict(X, num_iteration=m4a.best_iteration)
        meta["test_auc_v3"] = round(float(roc_auc_score(y[in3], p3[in3])), 5) if 0 < y[in3].sum() < in3.sum() else None
        meta["test_auc_v4"] = round(float(roc_auc_score(y, p4)), 5) if 0 < y.sum() < len(y) else None
    else:       # too small to train: every model falls back to the recency order (v3 does the same)
        base = -con.execute("SELECT coalesce(rr, 100 + rk_ranker, 1000) AS s FROM cf ORDER BY cid").fetchnumpy()["s"].astype(np.float64)
        p3, p4, p4a = np.where(in3, base, np.nan), base, base
    del X
    con.register("pred", pa.table({"cid": cid, "p3": p3, "p4": p4, "p4a": p4a}))
    con.execute(LISTS_SQL)
    union = (f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model = '{DEFAULT_MODEL}' "
             "UNION ALL SELECT model, brand, member, game, rk FROM vlists")
    rows = metrics(con, union)
    # incremental recall of the new sources: scored players with a new test-week game among them and not among v3's
    inc = con.execute("""
        WITH nt AS (SELECT t.brand, t.member, t.game FROM snap.truth t JOIN pw USING (brand, member)
                     ANTI JOIN snap.hist h USING (brand, member, game)),
             ad AS (SELECT d.brand, d.member, d.game FROM tdays d ANTI JOIN snap.hist h USING (brand, member, game) WHERE d.days >= 2),
             c3 AS (SELECT brand, member, game FROM cf WHERE in_v3 = 1 AND is_own = 0),
             c4 AS (SELECT brand, member, game FROM cf WHERE in_v3 = 0),
             r3 AS (SELECT DISTINCT brand, member FROM nt JOIN c3 USING (brand, member, game)),
             r4 AS (SELECT DISTINCT brand, member FROM nt JOIN c4 USING (brand, member, game)),
             a3 AS (SELECT DISTINCT brand, member FROM ad JOIN c3 USING (brand, member, game)),
             a4 AS (SELECT DISTINCT brand, member FROM ad JOIN c4 USING (brand, member, game))
        SELECT avg((r3.member IS NOT NULL)::INT), avg((r4.member IS NOT NULL AND r3.member IS NULL)::INT),
               avg((a3.member IS NOT NULL)::INT), avg((a4.member IS NOT NULL AND a3.member IS NULL)::INT)
          FROM pw
          LEFT JOIN r3 ON r3.brand = pw.brand AND r3.member = pw.member
          LEFT JOIN r4 ON r4.brand = pw.brand AND r4.member = pw.member
          LEFT JOIN a3 ON a3.brand = pw.brand AND a3.member = pw.member
          LEFT JOIN a4 ON a4.brand = pw.brand AND a4.member = pw.member""").fetchone()
    meta.update(recall_new_v3=round(inc[0], 5), inc_new_v4=round(inc[1], 5), recall_adopt_v3=round(inc[2], 5),
                inc_adopt_v4=round(inc[3], 5))
    brows = metrics(con, union, ADDA7) if c == ADDA7_CLUSTER else None
    close_work(con, path)
    # ---- checks ----
    ref, reb = rows[DEFAULT_MODEL], rows[REBUILT]
    if (reb["players"], reb["hr"], reb["new_hr"]) != (ref["players"], ref["hr"], ref["new_hr"]):
        notes.append("rebuilt default != stored")
        print(f"   !! rebuilt default {c} {test}: {reb['hr']:.5f}/{reb['new_hr']:.5f} vs stored {ref['hr']:.5f}/{ref['new_hr']:.5f}")
    v3_rows = check_v3(c, test, rows, notes)
    if v3_rows is not None and v3_rows != meta["train_rows_v3"]:
        notes.append(f"v3 train rows {meta['train_rows_v3']} vs {v3_rows}")
        print(f"   !! v3 train rows {c}: {meta['train_rows_v3']:,} vs v3's {v3_rows:,}")
    p = f"{X2}/{c}_{test}.csv"
    if os.path.exists(p):
        with open(p) as f:
            x2 = next((r for r in csv.DictReader(f) if r["model"] == DEFAULT_MODEL), None)
        if x2 is None or abs(ref["adopt_hr"] - float(x2["adopt_hr"])) > 1.01e-5:
            notes.append("adopt != X2")
            print(f"   !! adopted-game HR {c} {test}: {ref['adopt_hr']} vs X2 {x2 and x2['adopt_hr']}")
    p = f"{V2_OUT}/{c}_{test}.csv"
    if os.path.exists(p) and "pct-rank" not in live_source:
        with open(p) as f:
            v2 = next((r for r in csv.DictReader(f) if r["model"] == "own + live"), None)
        if v2 is not None and (int(v2["players"]) != rows[V2]["players"] or abs(float(v2["hr"]) - rows[V2]["hr"]) > 1e-5):
            notes.append("v2 != v2-arms")
            print(f"   !! v2 own + live {c} {test}: {rows[V2]['hr']} vs v2-arms {v2['hr']}")
    out = []
    for m, r in rows.items():
        out.append(dict(r, cluster=c, asof=test, market=MARKET_OF[c], valid=int(not notes), note="; ".join(notes),
                        live_source=live_source, **meta))
    save_csv(out, f"{OUT}/{c}_{test}.csv")
    if brows:
        save_csv([dict(r, brand="ADDA7", cluster=c, asof=test) for r in brows.values()], f"{OUT}/brand_adda7_{test}.csv")
    print(f"\n{c} ({MARKET_OF[c]}) train {train_asof} -> test {test}: v3 rows {meta['train_rows_v3']:,}, v4 rows "
          f"{meta['train_rows']:,}; trees v3/v4/v4a {meta.get('trees_v3')}/{meta.get('trees_v4')}/{meta.get('trees_v4a')}; "
          f"new-source incremental recall {meta['inc_new_v4']:.2%} (adopted {meta['inc_adopt_v4']:.2%})")
    base = ref["hr"]
    for m in [DEFAULT_MODEL] + VARIANTS:
        r = rows[m]
        print(f"   {m:38s} {r['players']:9,d}  HR@10 {r['hr']:6.2%} ({(r['hr'] - base) * 100:+.2f})  new {r['new_hr']:6.1%}  "
              f"adopted {r['adopt_hr']:5.2%}  beyond5 {r['beyond5_hr']:5.1%}")
    print(f"   ({time.time() - t0:.0f} s){'   INVALID: ' + '; '.join(notes) if notes else ''}")


def _week(asof):
    d = dt.date.fromisoformat(asof)
    a, b = d + dt.timedelta(days=1), d + dt.timedelta(days=7)
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def summarize():
    pat = re.compile(r"^([a-z0-9]+)_(\d{4}-\d{2}-\d{2})\.csv$")
    files = [p for p in sorted(glob.glob(f"{OUT}/*.csv")) if (m := pat.match(os.path.basename(p))) and m.group(1) in SCORED_CLUSTERS]
    if not files:
        sys.exit("summarize: no per-job CSVs in out/")
    df = pd.concat([pd.read_csv(p, dtype={"asof": str}) for p in files], ignore_index=True)
    bad = df[df.valid != 1].drop_duplicates(["cluster", "asof"])
    df = df[df.valid == 1]
    models = [DEFAULT_MODEL] + VARIANTS
    show = {DEFAULT_MODEL: "v1: default (stored)"}
    out = ["# v1 → v4 comparison", "",
           f"- Valid cluster-weeks: {df[['cluster', 'asof']].drop_duplicates().shape[0]}. Excluded: "
           f"{', '.join(f'{r.cluster} {r.asof} ({r.note})' for r in bad.itertuples()) or 'none'}.",
           "- Player-weighted over scored players. Δ in pt. Each test week is scored with models trained on the frozen week before it.",
           f"- Bars vs v1: HR@10 track Δ ≥ +{BAR_HR} pt, ≥ {BAR_CLUSTERS}/20 clusters above v1, new-game HR not lower; "
           f"discovery track adopted-game HR Δ ≥ +{BAR_ADOPT} pt, ≥ {BAR_CLUSTERS}/20 clusters above v1, HR@10 Δ ≥ {GUARD_HR} pt.", ""]

    def wv(g, m, col):
        x = g[g.model == m]
        return (x[col] * x.players).sum() / x.players.sum()

    for asof in sorted(df["asof"].unique()):
        wk = df[df["asof"] == asof]
        n_cl = wk.cluster.nunique()
        piv = {col: wk.pivot_table(index="cluster", columns="model", values=col) for col in ("hr", "adopt_hr", "new_hr")}
        b = {col: wv(wk, DEFAULT_MODEL, col) for col in ("hr", "new_hr", "adopt_hr")}
        v3 = {col: wv(wk, V3_TOP, col) for col in ("hr", "new_hr", "adopt_hr")}
        out += [f"## Test week {_week(asof)} (as of {asof}, {n_cl} clusters, {int(wk[wk.model == DEFAULT_MODEL].players.sum()):,} scored players)", "",
                "|Variant|HR@10|Δ vs v1|vs v3 top 10|Clusters > v1|New-game HR|Adopted-game HR|Δ adopted vs v1|Clusters > v1 (adopted)|beyond5 HR|HR@10 track|Discovery track|",
                "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for m in models:
            hr, nh, ah = wv(wk, m, "hr"), wv(wk, m, "new_hr"), wv(wk, m, "adopt_hr")
            if m == DEFAULT_MODEL:
                above = above_a = "–"
                t1 = t2 = "–"
            else:
                na, naa = int((piv["hr"][m] > piv["hr"][DEFAULT_MODEL]).sum()), int((piv["adopt_hr"][m] > piv["adopt_hr"][DEFAULT_MODEL]).sum())
                above, above_a = f"{na}/{n_cl}", f"{naa}/{n_cl}"
                t1 = "pass" if (hr - b["hr"]) * 100 >= BAR_HR and na >= BAR_CLUSTERS and nh >= b["new_hr"] else "fail"
                t2 = "pass" if (ah - b["adopt_hr"]) * 100 >= BAR_ADOPT and naa >= BAR_CLUSTERS and (hr - b["hr"]) * 100 >= GUARD_HR else "fail"
            out.append(f"|{show.get(m, m)}|{hr:.2%}|{(hr - b['hr']) * 100:+.2f}|{(hr - v3['hr']) * 100:+.2f}|{above}|{nh:.1%}|{ah:.2%}|"
                       f"{(ah - b['adopt_hr']) * 100:+.2f}|{above_a}|{wv(wk, m, 'beyond5_hr'):.1%}|{t1}|{t2}|")
        # v4 vs its v3 counterpart, cluster by cluster
        pairs = [(V4_TOP, V3_TOP), (V4A_TOP, V3_TOP), (V4_SPLIT, V3_CONT), (V4A_SPLIT, V3_CONT)]
        out += ["", "|v4 variant vs its v3 counterpart|Δ HR@10|Clusters better|Δ new-game HR|Δ adopted-game HR|Clusters better (adopted)|",
                "|---|---|---|---|---|---|"]
        for m4, m3 in pairs:
            out.append(f"|{m4} vs {m3}|{(wv(wk, m4, 'hr') - wv(wk, m3, 'hr')) * 100:+.2f}|"
                       f"{int((piv['hr'][m4] > piv['hr'][m3]).sum())}/{n_cl}|{(wv(wk, m4, 'new_hr') - wv(wk, m3, 'new_hr')) * 100:+.2f}|"
                       f"{(wv(wk, m4, 'adopt_hr') - wv(wk, m3, 'adopt_hr')) * 100:+.2f}|"
                       f"{int((piv['adopt_hr'][m4] > piv['adopt_hr'][m3]).sum())}/{n_cl}|")
        cols = [DEFAULT_MODEL, V2, V3_TOP, V3_CONT, V4_TOP, V4_SPLIT, V4A_TOP, V4A_SPLIT]
        out += ["", "**HR@10 by market**", "", "|Market|Players|" + "|".join(show.get(m, m) for m in cols) + "|",
                "|---|---|" + "---|" * len(cols)]
        for mk in list(MARKETS) + ["all"]:
            g = wk if mk == "all" else wk[wk.market == mk]
            if not len(g):
                continue
            out.append(f"|{'**all**' if mk == 'all' else mk}|{int(g[g.model == DEFAULT_MODEL].players.sum()):,}|"
                       + "|".join(f"{wv(g, m, 'hr'):.2%}" for m in cols) + "|")
        out += ["", "**Adopted-game HR by market**", "", "|Market|" + "|".join(show.get(m, m) for m in cols) + "|",
                "|---|" + "---|" * len(cols)]
        for mk in list(MARKETS) + ["all"]:
            g = wk if mk == "all" else wk[wk.market == mk]
            if len(g):
                out.append(f"|{'**all**' if mk == 'all' else mk}|" + "|".join(f"{wv(g, m, 'adopt_hr'):.2%}" for m in cols) + "|")
        d0 = wk[wk.model == DEFAULT_MODEL]
        n = d0.players
        out += ["", f"**New candidate sources (rp3 + transitions):** v3's new candidates hold a new test-week game for "
                f"{(d0.recall_new_v3 * n).sum() / n.sum():.1%} of scored players; the new sources add "
                f"{(d0.inc_new_v4 * n).sum() / n.sum() * 100:.2f} pt (clusters {d0.inc_new_v4.min() * 100:.2f}–{d0.inc_new_v4.max() * 100:.2f}). "
                f"For adopted games: {(d0.recall_adopt_v3 * n).sum() / n.sum():.1%} and +{(d0.inc_adopt_v4 * n).sum() / n.sum() * 100:.2f} pt.", ""]
    bfiles = sorted(glob.glob(f"{OUT}/brand_adda7_*.csv"))
    if bfiles:
        bb = pd.concat([pd.read_csv(p, dtype={"asof": str}) for p in bfiles], ignore_index=True)
        out += ["## POC brand ADDA7 (bdk1)", "", "|Test week|Variant|HR@10|New-game HR|Adopted-game HR|", "|---|---|---|---|---|"]
        for asof in sorted(bb["asof"].unique()):
            g = bb[bb["asof"] == asof].set_index("model")
            out += [f"|{_week(asof)}|{show.get(m, m)}|{g.loc[m, 'hr']:.2%}|{g.loc[m, 'new_hr']:.1%}|{g.loc[m, 'adopt_hr']:.2%}|"
                    for m in models if m in g.index]
        out.append("")
    ifiles = sorted(glob.glob(f"{OUT}/importance_v4_*.csv"))
    if ifiles:
        imp = pd.concat([pd.read_csv(p) for p in ifiles]).groupby("feature").share.mean().sort_values(ascending=False)
        out += ["## v4 features (mean gain share over clusters)", "", "|Feature|Gain share|New in v4|", "|---|---|---|"]
        out += [f"|{f}|{s:.1%}|{'yes' if f in NEW_FEATS else ''}|" for f, s in imp.head(12).items()]
        out += [f"", f"New v4 features together: {imp[[f for f in NEW_FEATS if f in imp.index]].sum():.1%} of gain.", ""]
    m = df[df.model == DEFAULT_MODEL]
    out.append(f"Model fit: trees v3 {int(m.trees_v3.min())}–{int(m.trees_v3.max())}, v4 {int(m.trees_v4.min())}–{int(m.trees_v4.max())}, "
               f"v4a {int(m.trees_v4a.min())}–{int(m.trees_v4a.max())}; test AUC v3 {m.test_auc_v3.min():.3f}–{m.test_auc_v3.max():.3f}, "
               f"v4 {m.test_auc_v4.min():.3f}–{m.test_auc_v4.max():.3f}.")
    with open(f"{OUT}/summary.md", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    if args == ["summarize"]:
        summarize()
        sys.exit()
    weeks = week_asofs(3)
    prev = {weeks[i + 1]: weeks[i] for i in range(len(weeks) - 1)}
    if args == ["all"]:
        jobs = [(c, w) for w in weeks[1:] for c in SCORED_CLUSTERS]
    elif len(args) >= 2 and len(args) % 2 == 0:
        jobs = list(zip(args[::2], args[1::2]))
    else:
        sys.exit(__doc__)
    for c, w in jobs:
        if w not in prev:
            sys.exit(f"no train week before {w}")
        guard()
        now = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))
        if (1, 40) <= (now.hour, now.minute) < (7, 0):
            sys.exit(f"stop: {now:%H:%M} +07 is too close to the 02:00 nightly window to start {c} {w}")
        try:
            run(c, w, prev[w])
        except duckdb.IOException as e:
            print(f"SKIP {c} {w}: {e}")
        gc.collect()
    if args == ["all"]:
        summarize()
