#!/usr/bin/env python3
"""v3-cold-day1: what should a cold player see on the one day they have no personal list?

Cold player = plays in the test week but has no row in the snapshot's hist (no play in the 30 days before the as-of
date). The daily build gives them a personal list the day after their first play, so the fallback list only matters
on that first day. Day-one HR@10 = share of the group who, on their first local day of play in the test week, play at
least one of the list's 10 games. Lists:
  L1 brand list       the brand's live Popular list, top 10 (normalised 30/70 (pct-rank) where a brand has none)
  L4 newcomer list    per brand: the 10 games most played on their first day by the brand's newcomers of the last 28
                      days before the test week (first play in the market cache inside that window); L1 if < 50 such players
  L3 own older games  returning players only: their 5 most recent earlier games, then L1 games not already listed
Groups: all cold (L1, L4), newcomers (L1, L4), returning (L1, L3, L4). Also the weekly L1 HR@10 on all cold players,
checked against experiments/2026-11-05-v2-coldstart (same cold count, same weekly L1 HR).

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v3-cold-day1/run.py bdk1 2026-10-26
    bin/py experiments/2026-11-05-v3-cold-day1/run.py all
    bin/py experiments/2026-11-05-v3-cold-day1/run.py summarize
"""
import csv
import datetime as dt
import glob
import os
import re
import sys
import time

import duckdb
import pandas as pd

from mlkit import (HOME, MARKET_OF, MARKETS, SCORED_CLUSTERS, attach, attach_market, connect, day_sql, ep, guard, plays_sql,
                   save_csv, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
V2 = f"{HOME}/experiments/2026-11-05-v2-coldstart/out"
LIVE, PCT = "live (as stored)", "normalised 30/70 (pct-rank)"
MIN_NEWCOMERS, BAR_PT, BAR_CLUSTER = 50, 2.0, "bdk1"
METRICS = ["d1_all_l1", "d1_all_l4", "d1_new_l1", "d1_new_l4", "d1_ret_l1", "d1_ret_l3", "d1_ret_l4", "wk_all_l1"]


def v2_ref(c, asof):
    p = f"{V2}/{c}_{asof}.csv"
    if not os.path.exists(p):
        return None
    r = next(csv.DictReader(open(p)))
    return int(r["cold"]), float(r["l1_all"])


def run(c, asof):
    t0 = time.time()
    a = dt.date.fromisoformat(asof)
    tr1, te1, nc0 = a + dt.timedelta(days=1), a + dt.timedelta(days=8), a - dt.timedelta(days=27)
    con = attach(connect(), c, asof)
    try:
        attach_market(con, c)
    except duckdb.IOException:
        print(f"SKIP {c} {asof}: market cache locked")
        return
    q = plays_sql(con, c)
    con.execute(f"""CREATE TEMP TABLE tday AS SELECT brand, member, game, {day_sql(c, tr1)} AS d FROM {q} p
                     WHERE epoch(ts) >= {ep(tr1, c)} AND epoch(ts) < {ep(te1, c)} GROUP BY ALL""")
    con.execute("CREATE TEMP TABLE hp AS SELECT DISTINCT brand, member FROM snap.hist")
    con.execute("""CREATE TEMP TABLE cold AS SELECT brand, member, min(d) AS d1 FROM tday GROUP BY 1, 2""")
    con.execute("DELETE FROM cold WHERE (brand, member) IN (SELECT (brand, member) FROM hp)")
    con.execute("CREATE TEMP TABLE t1 AS SELECT t.brand, t.member, t.game FROM tday t JOIN cold c ON c.brand = t.brand AND c.member = t.member AND t.d = c.d1")
    con.execute("CREATE TEMP TABLE tw AS SELECT DISTINCT t.brand, t.member, t.game FROM tday t JOIN cold USING (brand, member)")
    con.execute(f"""CREATE TEMP TABLE before AS SELECT p.brand, p.member, p.game, max(p.ts) AS last_ts, sum(p.rounds) AS rounds
                     FROM {q} p JOIN cold USING (brand, member) WHERE epoch(p.ts) < {ep(tr1, c)} GROUP BY 1, 2, 3""")
    con.execute("ALTER TABLE cold ADD COLUMN is_ret BOOLEAN")
    con.execute("UPDATE cold SET is_ret = (brand, member) IN (SELECT (brand, member) FROM before)")
    con.execute(f"""CREATE TEMP TABLE l1 AS
        WITH hb AS (SELECT DISTINCT brand FROM snap.lists WHERE model = '{LIVE}')
        SELECT brand, game, rk FROM snap.lists WHERE model = '{LIVE}' AND rk <= 10
        UNION ALL SELECT brand, game, rk FROM snap.lists WHERE model = '{PCT}' AND rk <= 10 AND brand NOT IN (SELECT brand FROM hb)""")
    d0 = ep(nc0, c)
    con.execute(f"""CREATE TEMP TABLE fp AS SELECT brand, member, min(ts) AS first_ts FROM {q} p
                     WHERE epoch(ts) < {ep(tr1, c)} GROUP BY 1, 2 HAVING epoch(min(ts)) >= {d0}""")
    con.execute(f"""CREATE TEMP TABLE l4raw AS
        SELECT p.brand, p.game, count(DISTINCT p.member) AS n FROM {q} p JOIN fp USING (brand, member)
         WHERE epoch(p.ts) < {ep(tr1, c)} AND floor((epoch(p.ts) - {d0}) / 86400) = floor((epoch(fp.first_ts) - {d0}) / 86400)
         GROUP BY 1, 2""")
    con.execute(f"""CREATE TEMP TABLE l4 AS
        WITH nb AS (SELECT brand, count(*) AS n FROM fp GROUP BY 1),
        ok AS (SELECT brand FROM nb WHERE n >= {MIN_NEWCOMERS}),
        top AS (SELECT brand, game, row_number() OVER (PARTITION BY brand ORDER BY n DESC, game) AS rk FROM l4raw
                 WHERE brand IN (SELECT brand FROM ok))
        SELECT brand, game, rk FROM top WHERE rk <= 10
        UNION ALL SELECT brand, game, rk FROM l1 WHERE brand NOT IN (SELECT brand FROM ok)""")
    n_fallback = con.execute(f"""SELECT count(DISTINCT brand) FROM cold WHERE brand NOT IN
                                  (SELECT brand FROM fp GROUP BY 1 HAVING count(*) >= {MIN_NEWCOMERS})""").fetchone()[0]
    con.execute("""CREATE TEMP TABLE l3 AS
        WITH o AS (SELECT b.brand, b.member, b.game, row_number() OVER (PARTITION BY b.brand, b.member ORDER BY b.last_ts DESC, b.rounds DESC, b.game) AS rn
                     FROM before b),
        o5 AS (SELECT brand, member, game, 0 AS k, rn AS pos FROM o WHERE rn <= 5),
        f AS (SELECT c.brand, c.member, l.game, 1 AS k, l.rk AS pos FROM cold c JOIN l1 l USING (brand) WHERE c.is_ret),
        u AS (SELECT * FROM o5 UNION ALL SELECT f.* FROM f ANTI JOIN o5 USING (brand, member, game))
        SELECT brand, member, game FROM (SELECT *, row_number() OVER (PARTITION BY brand, member ORDER BY k, pos) AS r FROM u) WHERE r <= 10""")
    hits = con.execute("""
        WITH h1 AS (SELECT DISTINCT t.brand, t.member FROM t1 t JOIN l1 USING (brand, game)),
             h4 AS (SELECT DISTINCT t.brand, t.member FROM t1 t JOIN l4 USING (brand, game)),
             h3 AS (SELECT DISTINCT t.brand, t.member FROM t1 t JOIN l3 USING (brand, member, game)),
             w1 AS (SELECT DISTINCT t.brand, t.member FROM tw t JOIN l1 USING (brand, game)),
             x AS (SELECT c.is_ret, (h1.member IS NOT NULL)::INT AS a1, (h4.member IS NOT NULL)::INT AS a4,
                          (h3.member IS NOT NULL)::INT AS a3, (w1.member IS NOT NULL)::INT AS wk1
                     FROM cold c LEFT JOIN h1 USING (brand, member) LEFT JOIN h4 USING (brand, member)
                     LEFT JOIN h3 USING (brand, member) LEFT JOIN w1 USING (brand, member))
        SELECT count(*), sum(is_ret::INT), avg(a1), avg(a4),
               avg(a1) FILTER (WHERE NOT is_ret), avg(a4) FILTER (WHERE NOT is_ret),
               avg(a1) FILTER (WHERE is_ret), avg(a3) FILTER (WHERE is_ret), avg(a4) FILTER (WHERE is_ret), avg(wk1)
          FROM x""").fetchone()
    n_test = con.execute("SELECT count(*) FROM (SELECT DISTINCT brand, member FROM tday)").fetchone()[0]
    n_fp = con.execute("SELECT count(*) FROM fp").fetchone()[0]
    con.close()
    n_cold, n_ret = hits[0], int(hits[1] or 0)
    row = dict(cluster=c, asof=asof, market=MARKET_OF[c], test_players=n_test, cold=n_cold, newcomers=n_cold - n_ret,
               returning=n_ret, recent_newcomers=n_fp, l4_fallback_brands=n_fallback)
    row.update({m: round(float(v or 0), 5) for m, v in zip(METRICS, hits[2:])})
    ref = v2_ref(c, asof)
    notes = []
    if ref and (abs(n_cold - ref[0]) > 0.005 * max(ref[0], 1) or abs(row["wk_all_l1"] - ref[1]) > 0.001):
        notes.append(f"v2 check cold {n_cold}/{ref[0]} weekly L1 {row['wk_all_l1']:.4f}/{ref[1]:.4f}")
        print(f"   !! v2 check {c} {asof}: cold {n_cold:,} vs {ref[0]:,}, weekly L1 {row['wk_all_l1']:.4f} vs {ref[1]:.4f}")
    row.update(valid=int(not notes), note="; ".join(notes))
    save_csv([row], f"{OUT}/{c}_{asof}.csv")
    print(f"\n{c} ({MARKET_OF[c]}) asof {asof}: {n_cold:,} cold of {n_test:,} ({n_cold / max(n_test, 1):.0%}); "
          f"newcomers {row['newcomers']:,}, returning {n_ret:,}; recent newcomers for L4 {n_fp:,} (fallback brands {n_fallback})")
    print(f"   day one, all cold: L1 {row['d1_all_l1']:.1%} | L4 {row['d1_all_l4']:.1%}   newcomers: L1 {row['d1_new_l1']:.1%} | "
          f"L4 {row['d1_new_l4']:.1%}   returning: L1 {row['d1_ret_l1']:.1%} | L3 {row['d1_ret_l3']:.1%} | L4 {row['d1_ret_l4']:.1%}   "
          f"weekly L1 {row['wk_all_l1']:.1%}   ({time.time() - t0:.0f} s)")


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
    df["note"] = df["note"].fillna("")
    bad, df = df[df.valid == 0], df[df.valid == 1]

    def agg(g):
        w = lambda col, n: (g[col] * g[n]).sum() / g[n].sum() if g[n].sum() else float("nan")  # noqa: E731
        return dict(test=int(g.test_players.sum()), cold=int(g.cold.sum()), new=int(g.newcomers.sum()), ret=int(g.returning.sum()),
                    a1=w("d1_all_l1", "cold"), a4=w("d1_all_l4", "cold"), n1=w("d1_new_l1", "newcomers"), n4=w("d1_new_l4", "newcomers"),
                    r1=w("d1_ret_l1", "returning"), r3=w("d1_ret_l3", "returning"), r4=w("d1_ret_l4", "returning"),
                    wk=w("wk_all_l1", "cold"))

    out = ["# Cold players' day-one list (v3)", "",
           f"- Excluded: {', '.join(f'{r.cluster} {r.asof} ({r.note})' for r in bad.itertuples()) or 'none'}.",
           "- Day-one HR@10 = share who play ≥ 1 of the list's 10 games on their first local day of play in the test week.", "",
           "| Week | Market | Cold | Newcomers | Returning | All cold: L1 | L4 | Δ | Newcomers: L1 | L4 | Returning: L1 | L3 | Δ L3 | L4 | Weekly L1 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    d = {}
    for asof in sorted(df["asof"].unique()):
        wk = df[df["asof"] == asof]
        groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
        for m, g in groups:
            s = agg(g)
            out.append(f"| {_week(asof)} | {m} | {s['cold']:,} | {s['new']:,} | {s['ret']:,} | {s['a1']:.1%} | {s['a4']:.1%} | "
                       f"{(s['a4'] - s['a1']) * 100:+.1f} | {s['n1']:.1%} | {s['n4']:.1%} | {s['r1']:.1%} | {s['r3']:.1%} | "
                       f"{(s['r3'] - s['r1']) * 100:+.1f} | {s['r4']:.1%} | {s['wk']:.1%} |")
        for scope, g in (("pooled", wk), (BAR_CLUSTER, wk[wk.cluster == BAR_CLUSTER])):
            if len(g):
                s = agg(g)
                d[(scope, asof)] = ((s["a4"] - s["a1"]) * 100, (s["r3"] - s["r1"]) * 100)
    weeks = sorted(df["asof"].unique())
    need = [(s, a) for s in ("pooled", BAR_CLUSTER) for a in weeks]
    fire = {i: len(weeks) == 2 and all(k in d and d[k][i] >= BAR_PT for k in need) for i in (0, 1)}
    names = [n for i, n in ((0, "L4"), (1, "L3")) if fire[i]]
    verdict = "both" if len(names) == 2 else (names[0] if names else "neither")
    txt = "; ".join(f"{s} {_week(a)}: L4 − L1 {d[(s, a)][0]:+.1f}, L3 − L1 {d[(s, a)][1]:+.1f}" for s, a in need if (s, a) in d)
    out += ["", f"**R-cold:** {txt} → fires for {verdict} (needs ≥ {BAR_PT} pt pooled and on {BAR_CLUSTER}, both weeks)."]
    with open(f"{OUT}/summary.md", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    if args == ["summarize"]:
        summarize()
        sys.exit()
    if args == ["all"]:
        jobs = [(c, w) for w in week_asofs(2) for c in SCORED_CLUSTERS]
    elif len(args) >= 2 and len(args) % 2 == 0:
        jobs = list(zip(args[::2], args[1::2]))
    else:
        sys.exit(__doc__)
    for c, w in jobs:
        guard()
        now = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))
        if (1, 40) <= (now.hour, now.minute) < (7, 0):
            sys.exit(f"stop: {now:%H:%M} +07 is too close to the 02:00 nightly window to start {c} {w}")
        run(c, w)
    if args == ["all"]:
        summarize()
