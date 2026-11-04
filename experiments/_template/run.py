#!/usr/bin/env python3
"""__NAME__: one-line hypothesis here.

Rebuilds a list variant from a frozen backtest snapshot (read-only) and scores it next to the stored default.
The first variant, "rebuilt default", must match the stored default exactly. If it doesn't, the harness is wrong:
fix that before reading any other number.

Usage (from /home/sunny/ml):
    bin/py experiments/__DIR__/run.py mx96g1 2026-10-26          # one cluster-week, quick check
    bin/py experiments/__DIR__/run.py all                         # every scored cluster, newest 2 weeks
"""
import os
import sys

import pandas as pd

from mlkit import DEFAULT_MODEL, RANKER_NEW, SCORED_CLUSTERS, guard, load, print_scores, save_csv, score, week_asofs

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def build(snap):
    """Return a DataFrame (model, brand, member, game, rk) with your list variants. Example: rebuild the default."""
    hist, recs = snap["hist"], snap["recs"]
    # hist arrives sorted: own games newest first (build_recs.py: days since last play, then rounds desc)
    own = hist.groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    new = recs[recs.model == RANKER_NEW].groupby(["brand", "member"], sort=False)["game"].agg(list).to_dict()
    rows = []
    for key, rnew in new.items():
        b, m = key
        played = own.get(key, [])
        n_cont = 5 if len(played) >= 3 else 3
        for name, cont in [("rebuilt default", played[:n_cont])]:      # add your variants here
            lst = list(dict.fromkeys(cont + [g for g in rnew if g not in set(played)]))[:10]
            rows += [(name, b, m, g, k + 1) for k, g in enumerate(lst)]
    return pd.DataFrame(rows, columns=["model", "brand", "member", "game", "rk"])


def run(c, asof):
    snap = load(c, asof)
    rows = score(c, asof, build(snap), stored=(DEFAULT_MODEL,))
    print_scores(c, asof, rows)
    ref = next(r for r in rows if r["model"] == DEFAULT_MODEL)
    reb = next((r for r in rows if r["model"] == "rebuilt default"), None)
    if reb and (abs(reb["hr"] - ref["hr"]) > 0.001 or reb["players"] != ref["players"]):
        print(f"   !! rebuilt default {reb['hr']:.2%} != stored {ref['hr']:.2%}: check build() before trusting variants")
    for r in rows:
        r.update(cluster=c, asof=asof)
    save_csv(rows, f"{OUT}/{c}_{asof}.csv")
    return rows


if __name__ == "__main__":
    guard()
    a = sys.argv[1:]
    if a == ["all"]:
        jobs = [(c, w) for w in week_asofs(2) for c in SCORED_CLUSTERS]
    elif len(a) >= 2 and len(a) % 2 == 0:
        jobs = list(zip(a[::2], a[1::2]))
    else:
        sys.exit(__doc__)
    allrows = [r for c, w in jobs for r in run(c, w)]
    save_csv(allrows, f"{OUT}/all.csv")
