#!/usr/bin/env python3
"""v2-coldstart (X3): the test-week players who have no personal list. What should they see?

Cold player = plays in the test week but has no row in the snapshot's hist (no play in the 30 days before the as-of
date), so the POC serves them the brand list. Split: newcomer (no play at all in the market cache, ~120 days) vs
returning player (played before). Scored like pull/step13_coldstart.py "HR@10 rest": players with >= 2 distinct test
games; the first test game (earliest hour, ties by game id) is removed from every list; a hit = one of the OTHER test
games in the top 10. Lists:
  L1 brand list        the brand's live (as stored) list, rk <= 50 (normalised 30/70 (pct-rank) where a brand has none)
  L2 after first game  snapshot coldstart (newcomers' first game -> next games, training data only), then L1
  L3 own older games   returning players only: their 5 most recent earlier games, then L1
Also L1 "HR@10 all": every cold player, target = all test games, first game kept.
Check: the cold count must be within 0.5 % of (truth players without hist) in the snapshot.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v2-coldstart/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-05-v2-coldstart/run.py all
    bin/py experiments/2026-11-05-v2-coldstart/run.py summarize
"""
import datetime as dt
import glob
import os
import re
import sys
import time
from collections import defaultdict

import duckdb
import pandas as pd

from mlkit import (MARKET_OF, MARKETS, SCORED_CLUSTERS, attach, attach_market, connect, ep, guard, plays_sql, save_csv,
                   week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
LIVE, PCT = "live (as stored)", "normalised 30/70 (pct-rank)"
K, R5_PT, R5_CLUSTER = 10, 2.0, "bdk1"


def top(xs, drop, k=K):
    return [g for g in dict.fromkeys(xs) if g != drop][:k]


def run(c, asof):
    t0 = time.time()
    a = dt.date.fromisoformat(asof)
    tr1, te1 = a + dt.timedelta(days=1), a + dt.timedelta(days=8)
    base = dict(cluster=c, asof=asof, market=MARKET_OF[c])
    con = attach(connect(), c, asof)
    try:
        attach_market(con, c)
    except duckdb.IOException:
        print(f"SKIP {c} {asof}: market cache locked")
        save_csv([dict(base, valid=0, note="market cache locked")], f"{OUT}/{c}_{asof}.csv")
        return
    q = plays_sql(con, c)
    con.execute(f"""CREATE TEMP TABLE tw AS SELECT brand, member, game, min(ts) AS t0, sum(rounds) AS rounds FROM {q} p
                     WHERE epoch(ts) >= {ep(tr1, c)} AND epoch(ts) < {ep(te1, c)} GROUP BY 1, 2, 3""")
    con.execute("CREATE TEMP TABLE hp AS SELECT DISTINCT brand, member FROM snap.hist")
    con.execute("CREATE TEMP TABLE cold AS SELECT DISTINCT t.brand, t.member FROM tw t ANTI JOIN hp USING (brand, member)")
    n_test = con.execute("SELECT count(*) FROM (SELECT DISTINCT brand, member FROM tw)").fetchone()[0]
    n_cold = con.execute("SELECT count(*) FROM cold").fetchone()[0]
    expect = con.execute("SELECT count(*) FROM (SELECT DISTINCT brand, member FROM snap.truth) t ANTI JOIN hp USING (brand, member)").fetchone()[0]
    notes = []
    if abs(n_cold - expect) > 0.005 * max(expect, 1):
        notes.append(f"cold {n_cold}/{expect}")
        print(f"   !! cold count {c} {asof}: {n_cold:,} rebuilt vs {expect:,} in the snapshot")
    con.execute(f"""CREATE TEMP TABLE before AS
        SELECT p.brand, p.member, p.game, max(p.ts) AS last_ts, sum(p.rounds) AS rounds FROM {q} p JOIN cold USING (brand, member)
         WHERE epoch(p.ts) < {ep(tr1, c)} GROUP BY 1, 2, 3""")
    returning = {(b, m) for b, m in con.execute("SELECT DISTINCT brand, member FROM before").fetchall()}
    tests = defaultdict(list)
    for b, m, g in con.execute("""SELECT t.brand, t.member, t.game FROM tw t JOIN cold USING (brand, member)
                                   ORDER BY t.brand, t.member, t.t0, t.game""").fetchall():
        tests[(b, m)].append(g)
    older = defaultdict(list)
    for b, m, g in con.execute("""SELECT brand, member, game FROM (SELECT *, row_number() OVER (PARTITION BY brand, member
                                    ORDER BY last_ts DESC, rounds DESC, game) AS r FROM before) WHERE r <= 6
                                   ORDER BY brand, member, r""").fetchall():
        older[(b, m)].append(g)
    brand_list, src = {}, defaultdict(int)
    for model in (LIVE, PCT):
        for b, g in con.execute("SELECT brand, game FROM snap.lists WHERE model = ? AND rk <= 50 ORDER BY brand, rk", [model]).fetchall():
            if b not in brand_list or brand_list[b][0] == model:
                brand_list.setdefault(b, (model, []))[1].append(g)
    after = defaultdict(list)
    for b, g1, g in con.execute("SELECT brand, first_game, game FROM snap.coldstart ORDER BY brand, first_game, rk").fetchall():
        after[(b, g1)].append(g)
    con.close()

    h = defaultdict(int)
    for (b, m), games in tests.items():
        model, l1 = brand_list.get(b, (None, []))
        src[model or "none"] += 1
        h["l1_all"] += bool(set(top(l1, None)) & set(games))
        if len(games) < 2:
            continue
        g1, rest = games[0], set(games[1:])
        h["multi"] += 1
        h["l1_rest"] += bool(set(top(l1, g1)) & rest)
        h["l2_rest"] += bool(set(top(after.get((b, g1), []) + l1, g1)) & rest)
        h["l2_cov"] += (b, g1) in after
        if (b, m) in returning:
            h["ret_multi"] += 1
            h["l1_rest_ret"] += bool(set(top(l1, g1)) & rest)
            h["l3_rest_ret"] += bool(set(top([g for g in older[(b, m)] if g != g1][:5] + l1, g1)) & rest)
    multi, ret_multi = max(h["multi"], 1), max(h["ret_multi"], 1)
    row = dict(base, test_players=n_test, cold=n_cold, cold_share=round(n_cold / max(n_test, 1), 5),
               newcomers=n_cold - len(returning), returning=len(returning), multi=h["multi"], returning_multi=h["ret_multi"],
               l1_rest=round(h["l1_rest"] / multi, 5), l2_rest=round(h["l2_rest"] / multi, 5),
               l1_rest_ret=round(h["l1_rest_ret"] / ret_multi, 5), l3_rest_ret=round(h["l3_rest_ret"] / ret_multi, 5),
               l1_all=round(h["l1_all"] / max(n_cold, 1), 5), l2_coverage=round(h["l2_cov"] / multi, 5),
               l1_source="; ".join(f"{k}: {v:,}" for k, v in sorted(src.items())), valid=int(not notes), note="; ".join(notes))
    save_csv([row], f"{OUT}/{c}_{asof}.csv")
    print(f"\n{c} ({MARKET_OF[c]}) asof {asof}: {n_cold:,} cold of {n_test:,} test-week players ({row['cold_share']:.0%}); "
          f"newcomers {row['newcomers']:,}, returning {row['returning']:,}; scored (>= 2 games) {h['multi']:,}")
    print(f"   HR@10 rest  L1 brand list {row['l1_rest']:.1%} | L2 after first game {row['l2_rest']:.1%} "
          f"(first game has a coldstart row: {row['l2_coverage']:.0%})"
          f"   returning: L1 {row['l1_rest_ret']:.1%} | L3 own older games {row['l3_rest_ret']:.1%}   L1 all {row['l1_all']:.1%}")
    print(f"   L1 source per cold player: {row['l1_source']}   ({time.time() - t0:.0f} s)")


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
        return dict(clusters=len(g), test=int(g.test_players.sum()), cold=int(g.cold.sum()), share=g.cold.sum() / g.test_players.sum(),
                    newc=int(g.newcomers.sum()), ret=int(g.returning.sum()), multi=int(g.multi.sum()),
                    l1=w("l1_rest", "multi"), l2=w("l2_rest", "multi"), l1r=w("l1_rest_ret", "returning_multi"),
                    l3r=w("l3_rest_ret", "returning_multi"), l1all=w("l1_all", "cold"), cov=w("l2_coverage", "multi"))

    out = ["# Cold-start summary (X3)", "",
           f"- Excluded: {', '.join(f'{r.cluster} {r.asof} ({r.note})' for r in bad.itertuples()) or 'none'}.",
           "- HR@10 rest = players with ≥ 2 distinct test games; first test game removed from every list; player-weighted.", "",
           "| Week | Market | Clusters | Test-week players | Cold | Cold share | Newcomers | Returning | Scored (≥ 2 games) | "
           "L1 brand list | L2 after first game | Δ L2 (pt) | L2 coverage | Returning: L1 | L3 own older | Δ L3 (pt) | L1 HR@10 all |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    deltas = {}
    for asof in sorted(df["asof"].unique()):
        wk = df[df["asof"] == asof]
        groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
        for m, g in groups:
            s = agg(g)
            out.append(f"| {_week(asof)} | {m} | {s['clusters']} | {s['test']:,} | {s['cold']:,} | {s['share']:.0%} | {s['newc']:,} | "
                       f"{s['ret']:,} | {s['multi']:,} | {s['l1']:.1%} | {s['l2']:.1%} | {(s['l2'] - s['l1']) * 100:+.1f} | {s['cov']:.0%} | "
                       f"{s['l1r']:.1%} | {s['l3r']:.1%} | {(s['l3r'] - s['l1r']) * 100:+.1f} | {s['l1all']:.1%} |")
        for scope, g in (("all", wk), (R5_CLUSTER, wk[wk.cluster == R5_CLUSTER])):
            if len(g):
                s = agg(g)
                deltas[(scope, asof)] = ((s["l2"] - s["l1"]) * 100, (s["l3r"] - s["l1r"]) * 100)
    weeks = sorted(df["asof"].unique())
    need = [(s, a) for s in ("all", R5_CLUSTER) for a in weeks]
    fire = {i: len(weeks) == 2 and all(k in deltas and deltas[k][i] >= R5_PT for k in need) for i in (0, 1)}
    txt = "; ".join(f"{s} {_week(a)}: L2 {deltas[(s, a)][0]:+.1f}, L3 {deltas[(s, a)][1]:+.1f}" for s, a in need if (s, a) in deltas)
    verdict = ("fires for " + " and ".join(n for i, n in ((0, "L2"), (1, "L3")) if fire[i])) if any(fire.values()) else "does not fire"
    out += ["", f"**R5:** Δ vs L1 (pt): {txt} → {verdict} (needs ≥ {R5_PT} pt everywhere)."]
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
        if (1, 45) <= (now.hour, now.minute) < (7, 0):
            sys.exit(f"stop: {now:%H:%M} +07 is too close to the 02:00 nightly window to start {c} {w}")
        run(c, w)
    if args == ["all"]:
        summarize()
