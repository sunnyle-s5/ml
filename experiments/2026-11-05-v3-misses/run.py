#!/usr/bin/env python3
"""v3-misses: where do the default list's misses go, and which v3 idea could recover them?

A miss = a scored player who plays none of the default list's top 10 in the test week. For every miss we look at the
games they did play and flag (non-exclusive): an own game ranked 6-10 / 11-20 / 21+ by recency (any_own = all of them),
a ranker pick that was ranked but not shown (rk 1-10 of `ranker (new games only)`, not own), a lapsed game (played in the
market cache before the 60-day hist window), a series-mate (same provider and same name stem as an own game: the
cheapest stand-in for "LLM-enriched content"), a live Popular top-50 game, a game from a provider the player already
plays, any new game. Each miss also gets ONE exclusive bucket, first match in this order:
own_replay -> ranker_unshown -> lapsed -> series -> live50 -> other_new.
Values are shares of misses and pt of scored players (= the most HR@10 that lever could recover).
Check: any_own (pt) must equal the headroom experiment's oracle-continue gain for the same cluster-week.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v3-misses/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-05-v3-misses/run.py all
    bin/py experiments/2026-11-05-v3-misses/run.py summarize
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

from mlkit import (DEFAULT_MODEL, HOME, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_SET, attach, attach_market,
                   connect, ep, guard, plays_sql, save_csv, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
HEADROOM = f"{HOME}/experiments/2026-11-05-headroom/out"
LIVE = "live (as stored)"
EDITION = {"deluxe", "megaways", "xmas", "christmas", "halloween", "edition", "remastered", "plus", "extra", "ii", "iii", "iv"}
FLAGS = ["own6_10", "own11_20", "own21", "any_own", "ranker_unshown", "lapsed", "series", "live50", "sameprov", "any_new"]
BUCKETS = ["own_replay", "ranker_unshown", "lapsed", "series", "live50", "other_new"]
LLM_BAR_PT = 1.0


def stem(name):
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " ")).split()
            if not t.isdigit() and t not in EDITION]
    return " ".join(toks) or (name or "").lower()


def oracle_gain(c, asof):
    p = f"{HEADROOM}/{c}_{asof}.csv"
    if not os.path.exists(p):
        return None
    hr = {r["model"]: float(r["hr"]) for r in csv.DictReader(open(p))}
    return (hr["oracle continue slot"] - hr[DEFAULT_MODEL]) * 100


def run(c, asof):
    t0 = time.time()
    a = dt.date.fromisoformat(asof)
    tr0 = a - dt.timedelta(days=59)
    con = attach(connect(), c, asof)
    try:
        attach_market(con, c)
    except duckdb.IOException:
        print(f"SKIP {c} {asof}: market cache locked")
        return
    q = plays_sql(con, c)
    gs = pd.DataFrame([(b, g, p, stem(n)) for b, g, n, p in con.execute("SELECT brand, game, name, provider FROM snap.games").fetchall()],
                      columns=["brand", "game", "provider", "stem"]).drop_duplicates(["brand", "game"])
    con.register("gstem", gs)
    con.execute(f"CREATE TEMP TABLE w AS {SCORED_SET}")
    con.execute("""CREATE TEMP TABLE own AS SELECT h.brand, h.member, h.game,
        row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS rr
        FROM snap.hist h JOIN w USING (brand, member)""")
    con.execute(f"""CREATE TEMP TABLE dl AS SELECT r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
                     WHERE r.model = '{DEFAULT_MODEL}' AND r.rk <= 10""")
    con.execute(f"""CREATE TEMP TABLE rk AS SELECT r.brand, r.member, r.game, r.rk FROM snap.recs r JOIN w USING (brand, member)
                     WHERE r.model = '{RANKER_NEW}'""")
    con.execute("CREATE TEMP TABLE tr AS SELECT t.brand, t.member, t.game FROM snap.truth t JOIN w USING (brand, member)")
    con.execute("CREATE TEMP TABLE hits AS SELECT DISTINCT brand, member FROM dl JOIN tr USING (brand, member, game)")
    con.execute("CREATE TEMP TABLE miss AS SELECT * FROM w ANTI JOIN hits USING (brand, member)")
    con.execute(f"""CREATE TEMP TABLE lap AS SELECT DISTINCT p.brand, p.member, p.game FROM {q} p JOIN miss USING (brand, member)
                     WHERE epoch(p.ts) < {ep(tr0, c)}""")
    cmin = con.execute(f"SELECT min(ts) FROM {q} p").fetchone()[0]
    con.execute("""CREATE TEMP TABLE ownprov AS SELECT DISTINCT o.brand, o.member, s.provider, s.stem
                     FROM own o JOIN gstem s USING (brand, game)""")
    con.execute(f"""CREATE TEMP TABLE pl AS
    WITH mt AS (SELECT t.brand, t.member, t.game, o.rr, (l.game IS NOT NULL) AS lapsed, (k.game IS NOT NULL) AS in_rk,
                       s.provider, s.stem, (lv.game IS NOT NULL) AS live50
                  FROM tr t JOIN miss USING (brand, member)
                  LEFT JOIN own o USING (brand, member, game) LEFT JOIN lap l USING (brand, member, game)
                  LEFT JOIN rk k USING (brand, member, game) LEFT JOIN gstem s USING (brand, game)
                  LEFT JOIN (SELECT brand, game FROM snap.lists WHERE model = '{LIVE}' AND rk <= 50) lv USING (brand, game)),
    f AS (SELECT mt.*,
                 EXISTS (SELECT 1 FROM ownprov op WHERE op.brand = mt.brand AND op.member = mt.member
                          AND op.stem = mt.stem AND op.provider = mt.provider) AS stem_hit,
                 EXISTS (SELECT 1 FROM ownprov op WHERE op.brand = mt.brand AND op.member = mt.member
                          AND op.provider = mt.provider) AS prov_hit
            FROM mt)
    SELECT brand, member,
           max(coalesce(rr BETWEEN 6 AND 10, false)::INT) AS own6_10,
           max(coalesce(rr BETWEEN 11 AND 20, false)::INT) AS own11_20,
           max(coalesce(rr > 20, false)::INT) AS own21,
           max((rr IS NOT NULL)::INT) AS any_own,
           max((rr IS NULL AND in_rk)::INT) AS ranker_unshown,
           max((rr IS NULL AND lapsed)::INT) AS lapsed,
           max((rr IS NULL AND NOT lapsed AND stem_hit)::INT) AS series,
           max((rr IS NULL AND live50)::INT) AS live50,
           max((rr IS NULL AND prov_hit)::INT) AS sameprov,
           max((rr IS NULL)::INT) AS any_new
      FROM f GROUP BY 1, 2""")
    n_w = con.execute("SELECT count(*) FROM w").fetchone()[0]
    n_m = con.execute("SELECT count(*) FROM miss").fetchone()[0]
    fl = dict(zip(FLAGS, con.execute("SELECT " + ", ".join(f"sum({f})" for f in FLAGS) + " FROM pl").fetchone()))
    case = ("CASE WHEN any_own = 1 THEN 'own_replay' WHEN ranker_unshown = 1 THEN 'ranker_unshown' WHEN lapsed = 1 THEN 'lapsed' "
            "WHEN series = 1 THEN 'series' WHEN live50 = 1 THEN 'live50' ELSE 'other_new' END")
    bk = dict(con.execute(f"SELECT {case} AS b, count(*) FROM pl GROUP BY 1").fetchall())
    con.close()
    row = dict(cluster=c, asof=asof, market=MARKET_OF[c], scored=n_w, misses=n_m, miss_share=round(n_m / n_w, 5),
               cache_min_ts=str(cmin)[:10])
    for f in FLAGS:
        row[f"{f}_of_misses"] = round((fl[f] or 0) / max(n_m, 1), 5)
        row[f"{f}_pt"] = round((fl[f] or 0) / n_w * 100, 4)
    for b in BUCKETS:
        row[f"b_{b}_of_misses"] = round(bk.get(b, 0) / max(n_m, 1), 5)
        row[f"b_{b}_pt"] = round(bk.get(b, 0) / n_w * 100, 4)
    og = oracle_gain(c, asof)
    row["oracle_continue_pt"] = None if og is None else round(og, 4)
    if og is not None and abs(og - row["any_own_pt"]) > 0.05:
        print(f"   !! oracle check {c} {asof}: any_own {row['any_own_pt']:.2f} pt vs oracle continue {og:.2f} pt")
    save_csv([row], f"{OUT}/{c}_{asof}.csv")
    print(f"\n{c} ({MARKET_OF[c]}) asof {asof}: {n_w:,} scored, {n_m:,} misses ({n_m / n_w:.1%}); cache from {row['cache_min_ts']}")
    print("   flags (pt of scored): " + ", ".join(f"{f} {row[f + '_pt']:.2f}" for f in FLAGS))
    print("   buckets (pt):         " + ", ".join(f"{b} {row['b_' + b + '_pt']:.2f}" for b in BUCKETS)
          + f"   oracle continue {row['oracle_continue_pt']}   ({time.time() - t0:.0f} s)")


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
    cols = ["misses"] + [f"{f}_pt" for f in ("any_own", "own6_10", "ranker_unshown", "lapsed", "series", "live50", "sameprov")]
    out = [f"# Miss anatomy ({len(df)} cluster-weeks)", "",
           "- pt = share of scored players; each column is the most HR@10 that lever could recover (flags overlap).",
           "- Misses = scored players with no top-10 hit on the stored default list.", "",
           "| Week | Market | Scored | Misses | Own replay (any) | … own rank 6–10 | Ranker 6–10 unshown | Lapsed | Series-mate | "
           "Live top 50 | Same provider |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    bucket_rows = ["", "## Exclusive buckets (first match: own replay → ranker unshown → lapsed → series → live 50 → other new), pt",
                   "", "| Week | Market | " + " | ".join(BUCKETS) + " |", "|---|---|" + "---|" * len(BUCKETS)]
    for asof in sorted(df["asof"].unique()):
        wk = df[df["asof"] == asof]
        groups = [(m, wk[wk.market == m]) for m in MARKETS if (wk.market == m).any()] + [("**all**", wk)]
        for m, g in groups:
            n = g.scored.sum()
            wv = lambda col: (g[col] * g.scored).sum() / n  # noqa: E731
            out.append(f"| {_week(asof)} | {m} | {int(n):,} | {g.misses.sum() / n:.1%} | " +
                       " | ".join(f"{wv(c_):.2f}" for c_ in cols[1:]) + " |")
            bucket_rows.append(f"| {_week(asof)} | {m} | " + " | ".join(f"{wv('b_' + b + '_pt'):.2f}" for b in BUCKETS) + " |")
    n = df.scored.sum()
    pooled = (df.series_pt * df.scored).sum() / n
    worst = df.loc[df.series_pt.idxmax()]
    out += bucket_rows
    out += ["", f"**Series bound:** pooled {pooled:.2f} pt (max cluster-week {worst.series_pt:.2f} pt, {worst.cluster} {worst['asof']}).",
            f"**LLM content enrichment:** {'worth a test next round' if pooled >= LLM_BAR_PT else 'not worth it for HR@10'} "
            f"(bar: pooled series bound ≥ {LLM_BAR_PT:.1f} pt)."]
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
