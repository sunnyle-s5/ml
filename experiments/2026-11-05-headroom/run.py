#!/usr/bin/env python3
"""headroom: how many HR@10 points could any better model still add to the default, and which brand suits an online POC?

Rebuilds the default list from a frozen backtest snapshot (read-only) and two oracle variants that peek at the test week:
- "oracle new slot": the default with the player's most-played NEW test-week game (not in the 60-day hist) inserted right
  after the continue slots. Its HR@10 is the best any new-slot model could reach; its new-game HR is the ceiling
  (share of scored players who play >= 1 new game in the test week).
- "oracle continue slot": the default with the player's most recent own game that is replayed in the test week moved to the
  first continue slot. Its HR@10 is the best any continue-slot rule could reach (new slots unchanged).
"rebuilt default" must match the stored default exactly. If it doesn't, the harness is wrong: fix that before reading
any other number. For the newest frozen week it also scores the default and `live (as stored)` per brand (POC sizing).

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-headroom/run.py mx96g1 2026-10-26     # one cluster-week, quick check
    bin/py experiments/2026-11-05-headroom/run.py all                    # every scored cluster, newest 2 weeks, then summarize
    bin/py experiments/2026-11-05-headroom/run.py summarize              # out/summary.md from the per-job CSVs in out/
"""
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import sys
import time

import pandas as pd

from mlkit import (DEFAULT_MODEL, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SHARED, attach,
                   connect, guard, load, print_scores, save_csv, score, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
LIVE_MODEL = "live (as stored)"
ORACLE_NEW, ORACLE_CONT, REBUILT = "oracle new slot", "oracle continue slot", "rebuilt default"
POC_MIN_PLAYERS = 40_000        # smallest brand with at least this many scored players a week is the POC pick


def dedupe(xs):
    return list(dict.fromkeys(xs))


def build(snap):
    """DataFrame (model, brand, member, game, rk): the rebuilt default and the two oracle variants, top 10 each."""
    hist, recs, truth = snap["hist"], snap["recs"], snap["truth"]
    # hist arrives sorted: own games newest first (build_recs.py: days since last play, then rounds desc)
    own = hist.groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    new = recs[recs.model == RANKER_NEW].groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    # truth arrives sorted by rounds desc: element 0 is the player's most-played test-week game
    tru = truth.groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    rows = []
    for key, rnew in new.items():
        b, m = key
        played = own.get(key, [])
        seen = set(played)
        n_cont = 5 if len(played) >= 3 else 3
        cont = played[:n_cont]
        fill = [g for g in rnew if g not in seen]
        tgames = tru.get(key, [])
        tnew = [g for g in tgames if g not in seen]
        tset = set(tgames)
        told = [g for g in played if g in tset]
        cont2 = dedupe(told[:1] + played)[:n_cont]
        for name, lst in ((REBUILT, cont + fill), (ORACLE_NEW, cont + tnew[:1] + fill), (ORACLE_CONT, cont2 + fill)):
            rows += [(name, b, m, g, k + 1) for k, g in enumerate(dedupe(lst)[:10])]
    return pd.DataFrame(rows, columns=["model", "brand", "member", "game", "rk"])


# Same scoring rule as pull/recs_eval.py:9-25, limited to the default and the live brand list, grouped per brand.
BRAND_SQL = f"""
WITH scored AS (SELECT DISTINCT brand, member FROM snap.recs WHERE model = '{SCORED_MODEL}'),
w AS (SELECT brand, member FROM scored JOIN (SELECT DISTINCT brand, member FROM snap.truth) USING (brand, member)),
shown AS (
    SELECT r.model, r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
     WHERE r.model = '{DEFAULT_MODEL}' AND r.rk <= 10
    UNION ALL
    SELECT l.model, w.brand, w.member, l.game FROM w JOIN snap.lists l ON l.brand = w.brand AND l.rk <= 10
     WHERE l.model = '{LIVE_MODEL}'),
per AS (
    SELECT s.model, s.brand, s.member,
           max((t.game IS NOT NULL)::INT) AS hit,
           max((t.game IS NOT NULL AND h.game IS NULL)::INT) AS new_hit
      FROM shown s
      LEFT JOIN snap.truth t ON t.brand = s.brand AND t.member = s.member AND t.game = s.game
      LEFT JOIN snap.hist h ON h.brand = s.brand AND h.member = s.member AND h.game = s.game
     GROUP BY 1, 2, 3)
SELECT brand, model, count(*) AS players, avg(hit) AS hr, avg(new_hit) AS new_hr FROM per GROUP BY 1, 2 ORDER BY 1, 2"""


def per_brand(c, asof):
    labels = json.load(open(f"{SHARED}/ui/brands.json"))
    con = attach(connect(), c, asof)
    res = con.execute(BRAND_SQL).fetchall()
    con.close()
    rows = [dict(cluster=c, market=MARKET_OF[c], asof=asof, brand=b, label=labels.get(b, "?"), model=m,
                 players=n, hr=round(h, 5), new_hr=round(hn, 5)) for b, m, n, h, hn in res]
    save_csv(rows, f"{OUT}/brands_{c}_{asof}.csv")
    print(f"   per brand: {sum(r['model'] == DEFAULT_MODEL for r in rows)} brands → out/brands_{c}_{asof}.csv")


def run(c, asof):
    t0 = time.time()
    snap = load(c, asof)
    rows = score(c, asof, build(snap), stored=(DEFAULT_MODEL, RANKER_NEW, SCORED_MODEL))
    del snap
    print_scores(c, asof, rows)
    ref = next(r for r in rows if r["model"] == DEFAULT_MODEL)
    reb = next((r for r in rows if r["model"] == REBUILT), None)
    if reb and (abs(reb["hr"] - ref["hr"]) > 0.001 or reb["players"] != ref["players"]):
        print(f"   !! rebuilt default {reb['hr']:.2%} != stored {ref['hr']:.2%}: check build() before trusting variants")
    for r in rows:
        r.update(cluster=c, asof=asof)
    save_csv(rows, f"{OUT}/{c}_{asof}.csv")
    if asof == week_asofs(1)[0]:
        per_brand(c, asof)
    print(f"   ({time.time() - t0:.0f} s)")
    return rows


def _week(asof):
    d = dt.date.fromisoformat(asof)
    a, b = d + dt.timedelta(days=1), d + dt.timedelta(days=7)
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def _pt(x):
    return f"{x * 100:+.1f}"


def _pct(x):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1%}"


def summarize():
    pat = re.compile(r"^([a-z0-9]+)_(\d{4}-\d{2}-\d{2})\.csv$")
    recs = []
    for p in sorted(glob.glob(f"{OUT}/*.csv")):
        mt = pat.match(os.path.basename(p))
        if mt and mt.group(1) in SCORED_CLUSTERS:
            recs += list(csv.DictReader(open(p)))
    if not recs:
        sys.exit("summarize: no per-job CSVs in out/")
    df = pd.DataFrame(recs).astype({"players": int, "hr": float, "new_hr": float, "both_hr": float})
    wide = df.pivot_table(index=["cluster", "asof"], columns="model", values=["players", "hr", "new_hr"], aggfunc="first")
    cw = wide.index.tolist()

    # checks: rebuilt == stored (exact, at the 5 decimals score() keeps), oracles >= default
    exact = [k for k in cw if all(wide.loc[k, (v, REBUILT)] == wide.loc[k, (v, DEFAULT_MODEL)] for v in ("players", "hr", "new_hr"))]
    bad = [(k, o) for k in cw for o in (ORACLE_NEW, ORACLE_CONT) if wide.loc[k, ("hr", o)] < wide.loc[k, ("hr", DEFAULT_MODEL)] - 1e-9]
    if bad:
        sys.exit(f"summarize: oracle HR below the default on {bad}: build() is wrong")

    t = pd.DataFrame({
        "cluster": [k[0] for k in cw], "asof": [k[1] for k in cw],
        "market": [MARKET_OF[k[0]] for k in cw],
        "n": [int(wide.loc[k, ("players", DEFAULT_MODEL)]) for k in cw],
        "hr": [wide.loc[k, ("hr", DEFAULT_MODEL)] for k in cw],
        "hr_on": [wide.loc[k, ("hr", ORACLE_NEW)] for k in cw],
        "hr_oc": [wide.loc[k, ("hr", ORACLE_CONT)] for k in cw],
        "new": [wide.loc[k, ("new_hr", DEFAULT_MODEL)] for k in cw],
        "ceil": [wide.loc[k, ("new_hr", ORACLE_NEW)] for k in cw],
        "rk_new": [wide.loc[k, ("new_hr", RANKER_NEW)] for k in cw],
        "pop_new": [wide.loc[k, ("new_hr", SCORED_MODEL)] for k in cw],
    })
    t["d_on"], t["d_oc"] = t.hr_on - t.hr, t.hr_oc - t.hr

    def wavg(g, col):
        return (g[col] * g.n).sum() / g.n.sum()

    out = [f"# Headroom summary ({len(cw)} cluster-weeks)", "",
           f"- Rebuilt default = stored default (players, HR@10, new-game HR) on {len(exact)}/{len(cw)} cluster-weeks.",
           f"- Oracle HR@10 ≥ default HR@10 on {len(cw)}/{len(cw)} cluster-weeks (checked).",
           "- Player-weighted. Δ = oracle − default, in pt; the range is over the clusters in the row.",
           "- Ceiling = new-game HR of the oracle new slot = share of scored players who play ≥ 1 new game in the test week.", "",
           "## A · Headroom per market and week", "",
           "| Week | Market | Clusters | Scored players | Default HR@10 | Oracle new slot | Δ (range) | Oracle continue slot | Δ (range) "
           "| Default new-game HR | New-game ceiling | Ranker (new only) new HR | Popular 30/70 minus played new HR |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for asof in sorted(t["asof"].unique()):
        tw = t[t["asof"] == asof]
        groups = [(m, tw[tw.market == m]) for m in MARKETS if (tw.market == m).any()] + [("**all**", tw)]
        for m, g in groups:
            out.append(f"| {_week(asof)} | {m} | {len(g)} | {g.n.sum():,} | {_pct(wavg(g, 'hr'))} "
                       f"| {_pct(wavg(g, 'hr_on'))} | {_pt(wavg(g, 'd_on'))} ({_pt(g.d_on.min())} to {_pt(g.d_on.max())}) "
                       f"| {_pct(wavg(g, 'hr_oc'))} | {_pt(wavg(g, 'd_oc'))} ({_pt(g.d_oc.min())} to {_pt(g.d_oc.max())}) "
                       f"| {_pct(wavg(g, 'new'))} | {_pct(wavg(g, 'ceil'))} | {_pct(wavg(g, 'rk_new'))} | {_pct(wavg(g, 'pop_new'))} |")

    # B · POC candidates per brand, newest week with brand files
    bfiles = sorted(glob.glob(f"{OUT}/brands_*.csv"))
    if bfiles:
        b = pd.concat([pd.read_csv(p) for p in bfiles], ignore_index=True)
        newest = b["asof"].max()
        b = b[b["asof"] == newest]
        d = b[b.model == DEFAULT_MODEL].set_index(["cluster", "brand"])
        lv = b[b.model == LIVE_MODEL].set_index(["cluster", "brand"])
        d = d.assign(live=lv.hr.reindex(d.index)).reset_index().sort_values("players", ascending=False)
        d["gap"] = d.hr - d.live
        d["mde"] = 280 / d.players ** 0.5
        ok = d[d.live.notna()].sort_values("players")
        big = ok[ok.players >= POC_MIN_PLAYERS]
        picks = big.head(3) if len(big) else ok.tail(1)
        role = {picks.index[0]: "**recommended**"} | {i: "alternate" for i in picks.index[1:]}
        show = d.loc[d.index.isin(d.head(10).index) | d.index.isin(picks.index)]
        out += ["", f"## B · POC candidates per brand, test week {_week(newest)} (as of {newest})", "",
                f"Rule: the recommended brand is the smallest with ≥ {POC_MIN_PLAYERS:,} scored players a week and a live list; "
                "the alternates are the next two larger. MDE = 280/√n pt: the smallest HR difference a 50/50 split of n players "
                "detects (p = 0.5, α = 0.05 two-sided, 80 % power). Shown: the 10 largest brands plus the picks. "
                f"{len(d)} brands scored in total; {int(d.live.isna().sum())} without a live list.", "",
                "| Pick | Brand | Cluster | Market | Scored players | Default HR@10 | Live HR@10 | Gap (pt) | MDE (pt) |",
                "|---|---|---|---|---|---|---|---|---|"]
        for i, r in show.iterrows():
            gap = "–" if math.isnan(r.gap) else _pt(r.gap)
            out.append(f"| {role.get(i, '')} | {r['label']} | {r.cluster} | {r.market} | {r.players:,} | {_pct(r.hr)} "
                       f"| {_pct(r.live)} | {gap} | {r.mde:.2f} |")
    with open(f"{OUT}/summary.md", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    a = sys.argv[1:]
    if a == ["summarize"]:
        summarize()
        sys.exit()
    if a == ["all"]:
        jobs = [(c, w) for w in week_asofs(2) for c in SCORED_CLUSTERS]
    elif len(a) >= 2 and len(a) % 2 == 0:
        jobs = list(zip(a[::2], a[1::2]))
    else:
        sys.exit(__doc__)
    allrows = []
    for c, w in jobs:
        guard()                                  # stops at 02:00 +07 even mid-run
        allrows += run(c, w)
    save_csv(allrows, f"{OUT}/all.csv")
    if a == ["all"]:
        summarize()
