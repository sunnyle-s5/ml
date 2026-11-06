#!/usr/bin/env python3
"""v3-unified: rank the player's own games and new candidates together, for HR@10.

Today's default fixes the split: 3 or 5 continue slots (own games, newest first), then the ranker's new games.
The v3 guide's "retrieve -> rank" pattern applied to the whole list: one LightGBM model scores every candidate
(the player's 20 most recent own games, the ranker's top 10 new, the stored popular-minus-played top 10, the brand's
live Popular top 20 minus played) for "played in the next week". Trained on one frozen week, tested on the next.
Variants on the test week, next to the stored default:
  rebuilt default                  own rr <= 3/5, then ranker new (must equal the stored default)
  rule: 8 continue / 10 continue   the same with 8 / 10 own games for players with >= 3 own games
  unified: learned continue (3/5)  the 3/5 own games with the highest p, then ranker new
  unified: top 10                  the 10 candidates with the highest p
beyond5_hr = a top-10 hit on a game that is not one of the player's 5 most recent own games (site's last_played row).

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v3-unified/run.py mx96g1 2026-10-26    # test week; trains on the week before it
    bin/py experiments/2026-11-05-v3-unified/run.py all                  # every consecutive pair of frozen weeks
    bin/py experiments/2026-11-05-v3-unified/run.py summarize
"""
import csv
import datetime as dt
import gc
import glob
import os
import re
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.metrics import roc_auc_score

from mlkit import (DEFAULT_MODEL, HOME, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SCORED_SET, attach,
                   connect, ep, guard, save_csv, score_sql, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
SLOT_SPLIT = f"{HOME}/experiments/2026-11-04-slot-split/out"
LIVE, PCT = "live (as stored)", "normalised 30/70 (pct-rank)"
TRAIN_CAP = 50_000
TYPES = ["SLOT", "FISHING", "ARCADE", "LIVE", "CRASH", "SPORTS", "NO CATEGORY", "OTHER"]
ADDA7, ADDA7_CLUSTER = "4c0fc28c-5ee5-49ec-abb8-777b2b1295f5", "bdk1"
REBUILT, RULE8, RULE10 = "rebuilt default", "rule: 8 continue", "rule: 10 continue"
U_CONT, U_TOP = "unified: learned continue (3/5)", "unified: top 10"
VARIANTS = [REBUILT, RULE8, RULE10, U_CONT, U_TOP]
BAR_PT, BAR_CLUSTERS, RULE_MARGIN_PT = 0.5, 15, 0.2
FEATS = ["is_own", "rec_days", "rec_rank", "play_days", "rounds_log", "round_share", "bet_share", "days_ratio",
         "rk_ranker", "rk_pop", "rk_live", "g_pop_rank", "g_player_share", "g_recent_share", "g_repeat_share", "g_type",
         "p_type_share", "p_prov_share", "p_games", "p_rounds_log", "p_days_max", "p_rec_days"]
PARAMS = dict(objective="binary", metric=["binary_logloss", "auc"], learning_rate=0.05, num_leaves=63, min_data_in_leaf=200,
              feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, num_threads=4, seed=7,
              deterministic=True, force_col_wise=True, verbose=-1)


def build(con, c, asof, cap=None):
    """Candidate table `cf` (one row per player x candidate game, with features and label) on a connection that has the
    snapshot attached as `snap`. Returns live_source (which brand list stands in for the live list)."""
    a = dt.date.fromisoformat(asof)
    t_end = ep(a + dt.timedelta(days=1), c)
    sample = f"ORDER BY hash(brand || ':' || member) LIMIT {cap}" if cap else ""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pw AS
        SELECT brand, member, row_number() OVER (ORDER BY brand, member) - 1 AS pid, (hash(member) % 10 = 0) AS hold
          FROM (SELECT * FROM ({SCORED_SET}) s {sample})""")
    tcase = ("CASE WHEN t IN ('SLOT', 'SLOTS') THEN 'SLOT' WHEN t IS NULL THEN 'NO CATEGORY' "
             f"WHEN t IN ({', '.join(repr(x) for x in TYPES[1:7])}) THEN t ELSE 'OTHER' END")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE gt AS SELECT brand, game, {tcase} AS type, provider
        FROM (SELECT brand, game, any_value(type) AS t, any_value(provider) AS provider FROM snap.games GROUP BY 1, 2)""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE gf AS
        WITH bp AS (SELECT brand, count(DISTINCT member) AS n FROM snap.hist GROUP BY 1),
             g AS (SELECT brand, game, count(DISTINCT member) AS g_players,
                          avg((epoch(last_ts) >= {ep(a - dt.timedelta(days=6), c)})::INT) AS g_recent_share,
                          avg((play_days >= 2)::INT) AS g_repeat_share FROM snap.hist GROUP BY 1, 2)
        SELECT g.*, g.g_players / bp.n AS g_player_share,
               row_number() OVER (PARTITION BY g.brand ORDER BY g.g_players DESC, g.game) AS g_pop_rank
          FROM g JOIN bp USING (brand)""")
    con.execute("""CREATE OR REPLACE TEMP TABLE own AS
        SELECT h.brand, h.member, h.game, h.rounds, h.bet, h.play_days, h.last_ts,
               row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS rr
          FROM snap.hist h JOIN pw USING (brand, member)""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pf AS
        SELECT brand, member, count(*) AS p_games, sum(rounds) AS p_rounds, sum(bet) AS p_bet, max(play_days) AS p_days_max,
               min(({t_end} - epoch(last_ts)) / 86400.0) AS p_rec_days FROM own GROUP BY 1, 2""")
    con.execute("""CREATE OR REPLACE TEMP TABLE ptype AS
        SELECT o.brand, o.member, g.type, sum(o.rounds) / NULLIF(any_value(p.p_rounds), 0) AS share
          FROM own o JOIN gt g ON g.brand = o.brand AND g.game = o.game JOIN pf p ON p.brand = o.brand AND p.member = o.member
         GROUP BY 1, 2, 3""")
    con.execute("""CREATE OR REPLACE TEMP TABLE pprov AS
        SELECT o.brand, o.member, g.provider, sum(o.rounds) / NULLIF(any_value(p.p_rounds), 0) AS share
          FROM own o JOIN gt g ON g.brand = o.brand AND g.game = o.game JOIN pf p ON p.brand = o.brand AND p.member = o.member
         GROUP BY 1, 2, 3""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE lv AS
        WITH hb AS (SELECT DISTINCT brand FROM snap.lists WHERE model = '{LIVE}')
        SELECT brand, game, rk, 'live' AS src FROM snap.lists WHERE model = '{LIVE}' AND rk <= 50
        UNION ALL SELECT brand, game, rk, 'pct-rank' FROM snap.lists
         WHERE model = '{PCT}' AND rk <= 50 AND brand NOT IN (SELECT brand FROM hb)""")
    src = dict(con.execute("SELECT src, count(DISTINCT brand) FROM lv GROUP BY 1").fetchall())
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cand AS
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
    tcode = "CASE gt.type " + " ".join(f"WHEN '{t}' THEN {i}" for i, t in enumerate(TYPES)) + f" ELSE {len(TYPES) - 1} END"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cf AS
        SELECT row_number() OVER (ORDER BY c.brand, c.member, c.game) - 1 AS cid, pw.pid, pw.hold, c.brand, c.member, c.game,
               c.is_own, c.rr, c.rk_ranker, c.rk_pop, lv.rk AS rk_live, pf.p_games, (t.game IS NOT NULL)::INT AS label,
               ({t_end} - epoch(o.last_ts)) / 86400.0 AS rec_days, o.play_days, ln(1 + o.rounds) AS rounds_log,
               o.rounds / NULLIF(pf.p_rounds, 0) AS round_share, o.bet / NULLIF(pf.p_bet, 0) AS bet_share,
               o.play_days / NULLIF(pf.p_days_max, 0) AS days_ratio, gf.g_pop_rank, gf.g_player_share, gf.g_recent_share,
               gf.g_repeat_share, {tcode} AS g_type, coalesce(pt.share, 0) AS p_type_share, coalesce(pp.share, 0) AS p_prov_share,
               ln(1 + pf.p_rounds) AS p_rounds_log, pf.p_days_max, pf.p_rec_days
          FROM cand c
          JOIN pw ON pw.brand = c.brand AND pw.member = c.member
          JOIN pf ON pf.brand = c.brand AND pf.member = c.member
          LEFT JOIN own o ON o.brand = c.brand AND o.member = c.member AND o.game = c.game
          LEFT JOIN lv ON lv.brand = c.brand AND lv.game = c.game
          LEFT JOIN gf ON gf.brand = c.brand AND gf.game = c.game
          LEFT JOIN gt ON gt.brand = c.brand AND gt.game = c.game
          LEFT JOIN ptype pt ON pt.brand = c.brand AND pt.member = c.member AND pt.type = gt.type
          LEFT JOIN pprov pp ON pp.brand = c.brand AND pp.member = c.member AND pp.provider = gt.provider
          LEFT JOIN snap.truth t ON t.brand = c.brand AND t.member = c.member AND t.game = c.game""")
    return "; ".join(f"{k}: {v} brands" for k, v in sorted(src.items()))


def fetch(con):
    col = {"rec_rank": "rr"}
    sel = ", ".join(f"coalesce(CAST({col.get(f, f)} AS FLOAT), CAST('NaN' AS FLOAT)) AS {f}" for f in FEATS)
    d = con.execute(f"SELECT cid, hold::INT AS hold, label, {sel} FROM cf ORDER BY cid").fetchnumpy()
    X = np.column_stack([np.asarray(d[f], dtype=np.float32) for f in FEATS])
    return np.asarray(d["cid"], dtype=np.int64), np.asarray(d["hold"], dtype=bool), np.asarray(d["label"], dtype=np.int8), X


def train(c, asof):
    con = attach(connect(), c, asof)
    build(con, c, asof, cap=TRAIN_CAP)
    n_players = con.execute("SELECT count(*) FROM pw").fetchone()[0]
    _, hold, y, X = fetch(con)
    con.close()
    meta = dict(train_players=n_players, train_rows=len(y), train_pos=int(y.sum()))
    if y.sum() < 500:
        print(f"   SKIP model {c}: {int(y.sum())} positives")
        return None, dict(meta, trees=0, hold_auc=None)
    gi = FEATS.index("g_type")
    dtr = lgb.Dataset(X[~hold], y[~hold], feature_name=FEATS, categorical_feature=[gi], free_raw_data=False)
    dva = lgb.Dataset(X[hold], y[hold], reference=dtr)
    bst = lgb.train(PARAMS, dtr, num_boost_round=2000, valid_sets=[dva],
                    callbacks=[lgb.early_stopping(50, first_metric_only=True, verbose=False)])
    os.makedirs(OUT, exist_ok=True)
    bst.save_model(f"{OUT}/model_{c}_{asof}.txt")
    imp = bst.feature_importance(importance_type="gain")
    save_csv([dict(feature=f, gain=round(float(g), 2), share=round(float(g / max(imp.sum(), 1e-9)), 5)) for f, g in zip(FEATS, imp)],
             f"{OUT}/importance_{c}_{asof}.csv")
    return bst, dict(meta, trees=bst.best_iteration, hold_auc=round(bst.best_score["valid_0"]["auc"], 5))


LISTS_SQL = f"""
CREATE OR REPLACE TEMP TABLE vlists AS
WITH x AS (SELECT cf.brand, cf.member, cf.game, cf.is_own, cf.rr, cf.rk_ranker, pr.p,
                  CASE WHEN cf.p_games >= 3 THEN 5 ELSE 3 END AS n5, CASE WHEN cf.p_games >= 3 THEN 8 ELSE 3 END AS n8,
                  CASE WHEN cf.p_games >= 3 THEN 10 ELSE 3 END AS n10,
                  CASE WHEN cf.is_own = 1 THEN row_number() OVER (PARTITION BY cf.brand, cf.member, cf.is_own ORDER BY pr.p DESC, cf.rr) END AS orank
             FROM cf JOIN pred pr USING (cid)),
v AS (
  SELECT '{REBUILT}' AS model, brand, member, game,
         row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, rr, rk_ranker) AS rk
    FROM x WHERE (is_own = 1 AND rr <= n5) OR rk_ranker IS NOT NULL
  UNION ALL
  SELECT '{RULE8}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, rr, rk_ranker)
    FROM x WHERE (is_own = 1 AND rr <= n8) OR rk_ranker IS NOT NULL
  UNION ALL
  SELECT '{RULE10}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, rr, rk_ranker)
    FROM x WHERE (is_own = 1 AND rr <= n10) OR rk_ranker IS NOT NULL
  UNION ALL
  SELECT '{U_CONT}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, orank, rk_ranker)
    FROM x WHERE (is_own = 1 AND orank <= n5) OR rk_ranker IS NOT NULL
  UNION ALL
  SELECT '{U_TOP}', brand, member, game, row_number() OVER (PARTITION BY brand, member ORDER BY p DESC, is_own DESC, rr, rk_ranker, game)
    FROM x)
SELECT * FROM v WHERE rk <= 10"""


def beyond5(con, union):
    return dict(con.execute(f"""
        WITH allrecs AS ({union}), sc AS ({SCORED_SET}),
        own5 AS (SELECT brand, member, game FROM own WHERE rr <= 5),
        shown AS (SELECT r.model, r.brand, r.member, r.game FROM allrecs r JOIN sc USING (brand, member) WHERE r.rk <= 10),
        per AS (SELECT s.model, s.brand, s.member, max((t.game IS NOT NULL AND o5.game IS NULL)::INT) AS b5
                  FROM shown s LEFT JOIN snap.truth t ON t.brand = s.brand AND t.member = s.member AND t.game = s.game
                  LEFT JOIN own5 o5 ON o5.brand = s.brand AND o5.member = s.member AND o5.game = s.game GROUP BY 1, 2, 3)
        SELECT model, avg(b5) FROM per GROUP BY 1""").fetchall())


def heavy8(c, asof):
    p = f"{SLOT_SPLIT}/slot_split_{c}_{asof}.csv"
    if not os.path.exists(p):
        return None
    return next((float(r["hr"]) for r in csv.DictReader(open(p)) if r["variant"] == "heavy 8"), None)


def run(c, test, train_asof):
    t0 = time.time()
    bst, meta = train(c, train_asof)
    gc.collect()
    con = attach(connect(), c, test)
    live_source = build(con, c, test)
    cid, _, y, X = fetch(con)
    if bst is not None:
        p = bst.predict(X, num_iteration=bst.best_iteration)
        test_auc = round(float(roc_auc_score(y, p)), 5) if 0 < y.sum() < len(y) else None
    else:
        p = -con.execute("SELECT coalesce(rr, 100 + rk_ranker, 1000) AS s FROM cf ORDER BY cid").fetchnumpy()["s"].astype(np.float64)
        test_auc = None
    del X
    con.register("pred", pa.table({"cid": cid, "p": np.asarray(p, dtype=np.float64)}))
    con.execute(LISTS_SQL)
    if bst is None:
        con.execute(f"DELETE FROM vlists WHERE model IN ('{U_CONT}', '{U_TOP}')")
        for name in (U_CONT, U_TOP):
            con.execute(f"INSERT INTO vlists SELECT '{name}', brand, member, game, rk FROM vlists WHERE model = '{REBUILT}'")
    stored = f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model = '{DEFAULT_MODEL}'"
    union = f"{stored} UNION ALL SELECT model, brand, member, game, rk FROM vlists"
    rows = score_sql(con, union)
    b5 = beyond5(con, union)
    extra = dict(meta, test_auc=test_auc, live_source=live_source)
    for r in rows:
        r.update(cluster=c, asof=test, market=MARKET_OF[c], beyond5_hr=round(b5.get(r["model"], 0.0), 5), **extra)
    save_csv(rows, f"{OUT}/{c}_{test}.csv")
    if c == ADDA7_CLUSTER:
        bu = (f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model = '{DEFAULT_MODEL}' AND brand = '{ADDA7}' "
              f"UNION ALL SELECT model, brand, member, game, rk FROM vlists WHERE brand = '{ADDA7}'")
        brows = score_sql(con, bu)
        bb5 = beyond5(con, bu)
        for r in brows:
            r.update(brand="ADDA7", cluster=c, asof=test, beyond5_hr=round(bb5.get(r["model"], 0.0), 5))
        save_csv(brows, f"{OUT}/brand_adda7_{test}.csv")
    con.close()
    ref = next(r for r in rows if r["model"] == DEFAULT_MODEL)
    reb = next(r for r in rows if r["model"] == REBUILT)
    if (reb["players"], reb["hr"], reb["new_hr"]) != (ref["players"], ref["hr"], ref["new_hr"]):
        print(f"   !! rebuilt default {c} {test}: {reb['hr']:.5f}/{reb['new_hr']:.5f} vs stored {ref['hr']:.5f}/{ref['new_hr']:.5f}")
    h8 = heavy8(c, test)
    r8 = next(r for r in rows if r["model"] == RULE8)
    if h8 is not None and abs(r8["hr"] - h8) > 0.0002:
        print(f"   !! heavy 8 {c} {test}: {r8['hr']:.5f} vs slot-split {h8:.5f}")
    print(f"\n{c} ({MARKET_OF[c]}) train {train_asof} -> test {test}: train {meta['train_players']:,} players, {meta['train_rows']:,} rows, "
          f"{meta['train_pos']:,} positives, {meta['trees']} trees, holdout AUC {meta['hold_auc']}, test AUC {test_auc}")
    for r in sorted(rows, key=lambda r: -r["hr"]):
        print(f"   {r['model']:36s} {r['players']:9,d}  HR@10 {r['hr']:6.2%} ({(r['hr'] - ref['hr']) * 100:+.2f})  "
              f"new {r['new_hr']:6.1%}  beyond5 {r['beyond5_hr']:6.1%}")
    print(f"   ({time.time() - t0:.0f} s)")


def _week(asof):
    d = dt.date.fromisoformat(asof)
    a, b = d + dt.timedelta(days=1), d + dt.timedelta(days=7)
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def summarize():
    pat = re.compile(r"^([a-z0-9]+)_(\d{4}-\d{2}-\d{2})\.csv$")
    files = [p for p in sorted(glob.glob(f"{OUT}/*.csv")) if (m := pat.match(os.path.basename(p))) and m.group(1) in SCORED_CLUSTERS]
    if not files:
        sys.exit("summarize: no per-job CSVs in out/")
    df = pd.concat([pd.read_csv(p) for p in files], ignore_index=True)
    models = [DEFAULT_MODEL] + VARIANTS

    def wv(g, m, col):
        x = g[g.model == m]
        return (x[col] * x.players).sum() / x.players.sum()

    out = ["# Unified own + new ranker (v3)", "",
           "- Player-weighted. Δ = vs the stored default, pt. beyond5 = a top-10 hit on a game outside the player's 5 most recent own games.",
           "- Each test week is scored with a model trained on the frozen week before it.", ""]
    bar_lines = []
    for asof in sorted(df["asof"].unique()):
        wk = df[df["asof"] == asof]
        n_cl = wk.cluster.nunique()
        out += [f"## Test week {_week(asof)} (as of {asof}, {n_cl} clusters)", "",
                "| Market | Players | " + " | ".join(f"{m} HR@10 (Δ)" for m in models) + " |",
                "|---|---|" + "---|" * len(models)]
        groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
        for mk, g in groups:
            base = wv(g, DEFAULT_MODEL, "hr")
            cells = [f"{wv(g, m, 'hr'):.2%} ({(wv(g, m, 'hr') - base) * 100:+.2f})" for m in models]
            out.append(f"| {mk} | {int(g[g.model == DEFAULT_MODEL].players.sum()):,} | " + " | ".join(cells) + " |")
        base = wv(wk, DEFAULT_MODEL, "hr")
        piv = wk.pivot_table(index="cluster", columns="model", values="hr")
        above = {m: int((piv[m] > piv[DEFAULT_MODEL]).sum()) for m in VARIANTS}
        out += ["", "| Variant | HR@10 | Δ (pt) | Clusters above default | New-game HR | beyond5 HR |", "|---|---|---|---|---|---|"]
        for m in models:
            out.append(f"| {m} | {wv(wk, m, 'hr'):.2%} | {(wv(wk, m, 'hr') - base) * 100:+.2f} | "
                       f"{'–' if m == DEFAULT_MODEL else f'{above[m]}/{n_cl}'} | {wv(wk, m, 'new_hr'):.1%} | {wv(wk, m, 'beyond5_hr'):.1%} |")
        delta = {m: (wv(wk, m, "hr") - base) * 100 for m in VARIANTS if m != REBUILT}
        passing = [m for m in delta if delta[m] >= BAR_PT and above[m] >= BAR_CLUSTERS]
        best = max(passing, key=lambda m: delta[m]) if passing else None
        rec = best or "none"
        if best in (U_CONT, U_TOP) and RULE8 in passing and delta[best] - delta[RULE8] < RULE_MARGIN_PT:
            rec = RULE8
        bm = best or max(delta, key=delta.get)
        bar_lines.append(f"**Ship bar, {_week(asof)}:** {bm} Δ {delta[bm]:+.2f} pt, {above[bm]}/{n_cl} clusters → "
                         f"{'passes' if best else 'fails'}; vs rule 8: {delta[bm] - delta[RULE8]:+.2f} pt → recommend {rec}.")
        out.append("")
    nweeks = df["asof"].nunique()
    out += bar_lines + [f"({'provisional: one forward week' if nweeks < 2 else f'{nweeks} forward weeks'}; "
                        f"bar = Δ ≥ {BAR_PT} pt pooled and ≥ {BAR_CLUSTERS} clusters above the default; "
                        f"the 8-slot rule wins if a unified variant beats it by < {RULE_MARGIN_PT} pt.)"]
    bfiles = sorted(glob.glob(f"{OUT}/brand_adda7_*.csv"))
    if bfiles:
        b = pd.concat([pd.read_csv(p) for p in bfiles], ignore_index=True)
        out += ["", "## POC brand ADDA7 (bdk1)", "", "| Test week | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
        for asof in sorted(b["asof"].unique()):
            g = b[b["asof"] == asof].set_index("model")
            out.append(f"| {_week(asof)} | " + " | ".join(f"{g.loc[m, 'hr']:.2%}" for m in models) + " |")
    ifiles = sorted(glob.glob(f"{OUT}/importance_*.csv"))
    if ifiles:
        imp = pd.concat([pd.read_csv(p) for p in ifiles]).groupby("feature").share.mean().sort_values(ascending=False).head(10)
        out += ["", "## Top 10 features (mean gain share over clusters)", "", "| Feature | Gain share |", "|---|---|"]
        out += [f"| {f} | {s:.1%} |" for f, s in imp.items()]
    meta = df[df.model == DEFAULT_MODEL][["cluster", "asof", "trees", "hold_auc", "test_auc", "train_pos"]]
    out += ["", f"Model fit: trees {int(meta.trees.min())}–{int(meta.trees.max())}, holdout AUC {meta.hold_auc.min():.3f}–"
                f"{meta.hold_auc.max():.3f}, test AUC {meta.test_auc.min():.3f}–{meta.test_auc.max():.3f}."]
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
        run(c, w, prev[w])
        gc.collect()
    if args == ["all"]:
        summarize()
