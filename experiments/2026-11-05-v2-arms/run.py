#!/usr/bin/env python3
"""v2-arms (X1): how much of the personal list's gain over the live Popular list comes from pinning own games alone?

The v2 spec's heuristic arm = the player's own games first, then popularity, no ML. Two views:
- mixed top 10 (main_list as one list): "own + live" = the default's 3/5 continue slots + the site's own live Popular
  list minus played games (an arm the site could serve without our file); "own + popular" = the same with our stored
  `popular 30/70 minus played` fill; vs the stored default and `live (as stored)`. "rebuilt default" must equal the
  stored default (harness check). For ADDA7 (bdk1) the same lists are also scored on that brand alone (R1 is decided there).
- SLOT tab (main_list as the selected lobby tab's grid): SLOT games only, scored on players who play a SLOT game in
  the test week. "SLOT: personal" = own SLOT games + ranker SLOT picks + brand pct-rank SLOT fill; "SLOT: own +
  popular" = own SLOT games + the fill; "SLOT: live proxy" = the brand's live list, SLOT games only.
Share of gain = (HR_x - HR_live) / (HR_default - HR_live).

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v2-arms/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-05-v2-arms/run.py all
    bin/py experiments/2026-11-05-v2-arms/run.py summarize
"""
import datetime as dt
import glob
import os
import re
import sys
import time

import pandas as pd

from mlkit import (DEFAULT_MODEL, EVAL_SQL, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SCORED_SET,
                   attach, connect, guard, load, print_scores, save_csv, score, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
LIVE = "live (as stored)"
PCT = "normalised 30/70 (pct-rank)"
REBUILT, OWN_POP, OWN_LIVE = "rebuilt default", "own + popular", "own + live"
S_PERS, S_OWN, S_LIVE = "SLOT: personal", "SLOT: own + popular", "SLOT: live proxy"
SLOT_TYPE = "CASE WHEN any_value(type) IN ('SLOT', 'SLOTS') THEN 'SLOT' ELSE any_value(type) END"  # pk96g1 labels it SLOTS
R1_BRAND, R1_LABEL, R1_CLUSTER, R1_SHARE = "4c0fc28c-5ee5-49ec-abb8-777b2b1295f5", "ADDA7", "bdk1", 0.80


def dedupe(xs):
    return list(dict.fromkeys(xs))


def lists_by_player(recs, model):
    return recs[recs.model == model].groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()


def build_mixed(snap, live):
    """live: brand -> the site's live Popular list (rk order). "own + live" is the arm the site could serve without our
    file; "own + popular" uses our pct-rank popularity instead."""
    own = snap["hist"].groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    new, pop = lists_by_player(snap["recs"], RANKER_NEW), lists_by_player(snap["recs"], SCORED_MODEL)
    rows = []
    for key, rnew in new.items():
        b, m = key
        played = own.get(key, [])
        seen = set(played)
        n_cont = 5 if len(played) >= 3 else 3
        variants = [(REBUILT, played[:n_cont] + [g for g in rnew if g not in seen]),
                    (OWN_POP, played[:n_cont] + [g for g in pop.get(key, []) if g not in seen])]
        if b in live:
            variants.append((OWN_LIVE, played[:n_cont] + [g for g in live[b] if g not in seen]))
        for name, lst in variants:
            rows += [(name, b, m, g, k + 1) for k, g in enumerate(dedupe(lst)[:10])]
    return pd.DataFrame(rows, columns=["model", "brand", "member", "game", "rk"])


def score_brand(c, asof, mine):
    """Default, live and the variants for the POC brand only (same rule as mlkit.score)."""
    con = attach(connect(), c, asof)
    con.register("_mine", mine[mine.brand == R1_BRAND][["model", "brand", "member", "game", "rk"]])
    union = (f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model = '{DEFAULT_MODEL}' AND brand = '{R1_BRAND}' "
             f"UNION ALL SELECT l.model, w.brand, w.member, l.game, l.rk FROM w JOIN snap.lists l ON l.brand = w.brand "
             f"WHERE l.model = '{LIVE}' AND w.brand = '{R1_BRAND}' UNION ALL SELECT model, brand, member, game, rk FROM _mine")
    res = con.execute(EVAL_SQL.format(scored=SCORED_MODEL, union=union)).fetchall()
    con.close()
    rows = [dict(brand=R1_LABEL, cluster=c, asof=asof, model=m, players=n, hr=round(h, 5), new_hr=round(hn, 5))
            for m, n, h, hn, _ in res]
    save_csv(rows, f"{OUT}/brand_{R1_LABEL.lower()}_{asof}.csv")
    for r in rows:
        print(f"   {R1_LABEL}: {r['model']:40s} {r['players']:8,d}  HR@10 {r['hr']:6.1%}  new {r['new_hr']:6.1%}")
    return pd.DataFrame(rows, columns=["model", "brand", "member", "game", "rk"])


SLOT_SQL = f"""
WITH g AS (SELECT brand, game, {SLOT_TYPE} AS type FROM snap.games GROUP BY 1, 2),
tslot AS (SELECT t.brand, t.member, t.game FROM snap.truth t JOIN g USING (brand, game) WHERE g.type = 'SLOT'),
w AS (SELECT DISTINCT s.brand, s.member FROM ({SCORED_SET}) s JOIN tslot USING (brand, member)),
lv AS (SELECT l.brand, l.game, row_number() OVER (PARTITION BY l.brand ORDER BY l.rk) AS rk
         FROM snap.lists l JOIN g USING (brand, game) WHERE l.model = '{LIVE}' AND g.type = 'SLOT'),
allrecs AS (SELECT model, brand, member, game, rk FROM _slot
            UNION ALL SELECT '{S_LIVE}', w.brand, w.member, lv.game, lv.rk FROM w JOIN lv USING (brand)),
shown AS (SELECT r.model, r.brand, r.member, r.game FROM allrecs r JOIN w USING (brand, member) WHERE r.rk <= 10),
per AS (SELECT s.model, s.brand, s.member, max((t.game IS NOT NULL)::INT) AS hit,
               max((t.game IS NOT NULL AND h.game IS NULL)::INT) AS new_hit, count(*) AS n_shown
          FROM shown s LEFT JOIN tslot t USING (brand, member, game) LEFT JOIN snap.hist h USING (brand, member, game)
         GROUP BY 1, 2, 3)
SELECT model, count(*) AS players, avg(hit) AS hr, avg(new_hit) AS new_hr, sum((n_shown < 10)::INT) AS short_lists
  FROM per GROUP BY 1 ORDER BY hr DESC"""


def run_slot(c, asof):
    con = attach(connect(), c, asof)
    gtype = dict(((b, g), t) for b, g, t in con.execute(f"SELECT brand, game, {SLOT_TYPE} FROM snap.games GROUP BY 1, 2").fetchall())
    fill_rows = con.execute(f"SELECT brand, game FROM snap.lists WHERE model = '{PCT}' ORDER BY brand, rk").fetchall()
    con.close()
    fill = {}
    for b, g in fill_rows:
        if gtype.get((b, g)) == "SLOT":
            fill.setdefault(b, []).append(g)
    snap = load(c, asof, tables=("hist",), models=(RANKER_NEW,))
    own = snap["hist"].groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    new = lists_by_player(snap["recs"], RANKER_NEW)
    del snap
    rows = []
    for key, rnew in new.items():
        b, m = key
        played = own.get(key, [])
        seen = set(played)
        own_s = [g for g in played if gtype.get((b, g)) == "SLOT"]
        n_s = 5 if len(own_s) >= 3 else 3
        f = [g for g in fill.get(b, []) if g not in seen]
        r_s = [g for g in rnew if g not in seen and gtype.get((b, g)) == "SLOT"]
        for name, lst in ((S_PERS, own_s[:n_s] + r_s + f), (S_OWN, own_s[:n_s] + f)):
            rows += [(name, b, m, g, k + 1) for k, g in enumerate(dedupe(lst)[:10])]
    df = pd.DataFrame(rows, columns=["model", "brand", "member", "game", "rk"])
    del rows, own, new
    con = attach(connect(), c, asof)
    con.register("_slot", df)
    res = con.execute(SLOT_SQL).fetchall()
    con.close()
    out = [dict(cluster=c, asof=asof, market=MARKET_OF[c], model=m, players=n, hr=round(h, 5), new_hr=round(hn, 5),
                short_lists=int(s)) for m, n, h, hn, s in res]
    save_csv(out, f"{OUT}/slot_{c}_{asof}.csv")
    for r in out:
        print(f"   {r['model']:44s} {r['players']:9,d}  HR@10 {r['hr']:6.1%}  new {r['new_hr']:6.1%}  lists < 10 games: {r['short_lists']:,}")


def run(c, asof):
    t0 = time.time()
    con = attach(connect(), c, asof)
    live = {}
    for b, g in con.execute(f"SELECT brand, game FROM snap.lists WHERE model = '{LIVE}' ORDER BY brand, rk").fetchall():
        live.setdefault(b, []).append(g)
    con.close()
    snap = load(c, asof, models=(RANKER_NEW, SCORED_MODEL))
    mine = build_mixed(snap, live)
    del snap
    rows = score(c, asof, mine, stored=(DEFAULT_MODEL,), lists=(LIVE,))
    if c == R1_CLUSTER:
        score_brand(c, asof, mine)
    del mine
    print_scores(c, asof, rows)
    ref = next(r for r in rows if r["model"] == DEFAULT_MODEL)
    reb = next((r for r in rows if r["model"] == REBUILT), None)
    if reb and (abs(reb["hr"] - ref["hr"]) > 0.001 or reb["players"] != ref["players"]):
        print(f"   !! rebuilt default {reb['hr']:.2%} != stored {ref['hr']:.2%}: check build_mixed() before trusting variants")
    for r in rows:
        r.update(cluster=c, asof=asof, market=MARKET_OF[c])
    save_csv(rows, f"{OUT}/{c}_{asof}.csv")
    run_slot(c, asof)
    print(f"   ({time.time() - t0:.0f} s)")


def _week(asof):
    d = dt.date.fromisoformat(asof)
    a, b = d + dt.timedelta(days=1), d + dt.timedelta(days=7)
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def _load(prefix):
    pat = re.compile(rf"^{prefix}([a-z0-9]+)_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$")
    files = [p for p in sorted(glob.glob(f"{OUT}/*.csv")) if (m := pat.match(os.path.basename(p))) and m.group(1) in SCORED_CLUSTERS]
    return pd.concat([pd.read_csv(p) for p in files], ignore_index=True) if files else None


def _wavg(g, model, col):
    x = g[g.model == model]
    return (x[col] * x.players).sum() / x.players.sum() if len(x) and x.players.sum() else float("nan")


def _share(x, top, base):
    return (x - base) / (top - base) if top - base else float("nan")


def summarize():
    mixed, slot = _load(""), _load("slot_")
    if mixed is None:
        sys.exit("summarize: no per-job CSVs in out/")
    with_live = set(map(tuple, mixed[mixed.model == LIVE][["cluster", "asof"]].values))
    out = ["# Arms summary (X1)", "",
           "- Player-weighted; share of gain = (HR_x − HR_live) ÷ (HR_default − HR_live), over cluster-weeks that have a live list "
           f"({len(with_live)} of {mixed[['cluster', 'asof']].drop_duplicates().shape[0]}).", "",
           "## Mixed top 10", "",
           "| Week | Market | Default HR@10 (new) | Own + live (new) | Share | Own + popular (new) | Share | Live HR@10 (new) |",
           "|---|---|---|---|---|---|---|---|"]
    r1_cluster = {}
    for asof in sorted(mixed["asof"].unique()):
        wk = mixed[(mixed["asof"] == asof) & mixed.apply(lambda r: (r.cluster, r["asof"]) in with_live, axis=1)]
        groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
        for m, g in groups:
            d, ol, o, lv = (_wavg(g, x, "hr") for x in (DEFAULT_MODEL, OWN_LIVE, OWN_POP, LIVE))
            dn, oln, on, lvn = (_wavg(g, x, "new_hr") for x in (DEFAULT_MODEL, OWN_LIVE, OWN_POP, LIVE))
            out.append(f"| {_week(asof)} | {m} | {d:.1%} ({dn:.1%}) | {ol:.1%} ({oln:.1%}) | {_share(ol, d, lv):.0%} | "
                       f"{o:.1%} ({on:.1%}) | {_share(o, d, lv):.0%} | {lv:.1%} ({lvn:.1%}) |")
        g = wk[wk.cluster == R1_CLUSTER]
        if len(g):
            r1_cluster[asof] = _share(_wavg(g, OWN_LIVE, "hr"), _wavg(g, DEFAULT_MODEL, "hr"), _wavg(g, LIVE, "hr"))
    r1 = {}
    bfiles = sorted(glob.glob(f"{OUT}/brand_{R1_LABEL.lower()}_*.csv"))
    if bfiles:
        b = pd.concat([pd.read_csv(p) for p in bfiles], ignore_index=True)
        out += ["", f"## POC brand {R1_LABEL} ({R1_CLUSTER}), mixed top 10", "",
                "| Week | Players | Default HR@10 (new) | Own + live (new) | Share | Own + popular (new) | Share | Live HR@10 (new) |",
                "|---|---|---|---|---|---|---|---|"]
        for asof in sorted(b["asof"].unique()):
            g = b[b["asof"] == asof]
            v = {m: g[g.model == m].iloc[0] for m in (DEFAULT_MODEL, OWN_LIVE, OWN_POP, LIVE) if (g.model == m).any()}
            d, ol, o, lv = (v[m].hr for m in (DEFAULT_MODEL, OWN_LIVE, OWN_POP, LIVE))
            r1[asof] = _share(ol, d, lv)
            out.append(f"| {_week(asof)} | {int(v[DEFAULT_MODEL].players):,} | {d:.1%} ({v[DEFAULT_MODEL].new_hr:.1%}) | "
                       f"{ol:.1%} ({v[OWN_LIVE].new_hr:.1%}) | {r1[asof]:.0%} | {o:.1%} ({v[OWN_POP].new_hr:.1%}) | "
                       f"{_share(o, d, lv):.0%} | {lv:.1%} ({v[LIVE].new_hr:.1%}) |")
    if slot is not None:
        out += ["", "## SLOT tab (players who play a SLOT game in the test week)", "",
                "| Week | Market | Players | SLOT: personal (new) | SLOT: own + popular (new) | Share | SLOT: live proxy (new) | Lists < 10 games (personal / own + popular) |",
                "|---|---|---|---|---|---|---|---|"]
        for asof in sorted(slot["asof"].unique()):
            wk = slot[slot["asof"] == asof]
            wk = wk[wk.cluster.isin(wk[wk.model == S_LIVE].cluster)]
            groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
            for m, g in groups:
                p, o, lv = (_wavg(g, x, "hr") for x in (S_PERS, S_OWN, S_LIVE))
                pn, on, lvn = (_wavg(g, x, "new_hr") for x in (S_PERS, S_OWN, S_LIVE))
                n = int(g[g.model == S_PERS].players.sum())
                sp, so = int(g[g.model == S_PERS].short_lists.sum()), int(g[g.model == S_OWN].short_lists.sum())
                out.append(f"| {_week(asof)} | {m} | {n:,} | {p:.1%} ({pn:.1%}) | {o:.1%} ({on:.1%}) | {_share(o, p, lv):.0%} | "
                           f"{lv:.1%} ({lvn:.1%}) | {sp:,} / {so:,} |")
    shares = ", ".join(f"{_week(a)} = {s:.0%}" for a, s in sorted(r1.items()))
    fires = len(r1) == 2 and all(s >= R1_SHARE for s in r1.values())
    out += ["", f"**R1 on {R1_LABEL}:** share of gain of own + live (the arm the site can serve without our file): "
                f"{shares or 'no data'} → {'fires' if fires else 'does not fire'} (needs ≥ {R1_SHARE:.0%} in both weeks). "
                f"Cluster {R1_CLUSTER}: " + (", ".join(f"{_week(a)} = {s:.0%}" for a, s in sorted(r1_cluster.items())) or "no data") + "."]
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
