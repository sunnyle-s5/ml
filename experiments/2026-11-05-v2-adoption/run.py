#!/usr/bin/env python3
"""v2-adoption (X2): of the new-game hits, how many are adopted rather than tried once?

The v2 spec's NGA-7 counts a new game only when the player comes back to it. Offline analogue, per scored player:
- hr        any of the list's top 10 played in the test week
- new_hr    ... a game not in the player's 60-day hist (= the backtest's new-game HR)
- adopt_hr  ... a new game played on >= 2 distinct market-local days of the test week (all rounds; no real/bonus flag)
Test-week days come from the market cache (plays_*), because snapshot truth has no days. Two checks per job:
the rebuilt truth must cover the snapshot's truth (rows >= 99.5 %, rounds within 0.5 %), and the rebuilt default
hr / new_hr must equal mlkit.score() within 0.1 pt. A job that fails either is excluded from the summary.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v2-adoption/run.py mx96g1 2026-10-26
    bin/py experiments/2026-11-05-v2-adoption/run.py all
    bin/py experiments/2026-11-05-v2-adoption/run.py summarize
"""
import datetime as dt
import glob
import os
import re
import sys
import time

import duckdb
import pandas as pd

from mlkit import (DEFAULT_MODEL, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SCORED_SET, attach,
                   attach_market, connect, day_sql, ep, guard, plays_sql, save_csv, score, week_asofs)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
MODELS = (DEFAULT_MODEL, RANKER_NEW, SCORED_MODEL)


def run(c, asof):
    t0 = time.time()
    a = dt.date.fromisoformat(asof)
    tr1, te1 = a + dt.timedelta(days=1), a + dt.timedelta(days=8)
    con = attach(connect(), c, asof)
    try:
        attach_market(con, c)
    except duckdb.IOException:
        print(f"SKIP {c} {asof}: market cache locked")
        save_csv([dict(cluster=c, asof=asof, market=MARKET_OF[c], model="", players=0, hr=0, new_hr=0, adopt_hr=0,
                       try_ceiling=0, adopt_ceiling=0, valid=0, note="market cache locked")], f"{OUT}/{c}_{asof}.csv")
        return
    q = plays_sql(con, c)
    con.execute(f"CREATE TEMP TABLE w AS {SCORED_SET}")
    con.execute(f"""CREATE TEMP TABLE tdays AS
        SELECT p.brand, p.member, p.game, count(DISTINCT {day_sql(c, tr1, 'p.ts')}) AS days, sum(p.rounds) AS rounds
          FROM {q} p JOIN w USING (brand, member)
         WHERE epoch(p.ts) >= {ep(tr1, c)} AND epoch(p.ts) < {ep(te1, c)}
         GROUP BY 1, 2, 3""")
    n_t, n_m, r_t = con.execute("""SELECT count(*), count(d.game), sum(t.rounds) FROM snap.truth t JOIN w USING (brand, member)
                                   LEFT JOIN tdays d USING (brand, member, game)""").fetchone()
    r_d = con.execute("SELECT sum(rounds) FROM tdays").fetchone()[0] or 0
    notes = []
    if n_t == 0 or n_m / n_t < 0.995 or abs(r_d - r_t) / max(r_t, 1) > 0.005:
        notes.append(f"truth rebuild rows {n_m}/{n_t} rounds {r_d}/{r_t}")
        print(f"   !! truth rebuild {c} {asof}: rows {n_m:,}/{n_t:,} rounds {r_d:,}/{r_t:,}")
    ms = ", ".join(f"'{m}'" for m in MODELS)
    res = con.execute(f"""
        WITH shown AS (SELECT r.model, r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
                        WHERE r.rk <= 10 AND r.model IN ({ms})),
        per AS (SELECT s.model, s.brand, s.member,
                       max((d.game IS NOT NULL)::INT) AS hit,
                       max((d.game IS NOT NULL AND h.game IS NULL)::INT) AS new_hit,
                       max((d.game IS NOT NULL AND h.game IS NULL AND d.days >= 2)::INT) AS adopt_hit
                  FROM shown s LEFT JOIN tdays d USING (brand, member, game) LEFT JOIN snap.hist h USING (brand, member, game)
                 GROUP BY 1, 2, 3)
        SELECT model, count(*), avg(hit), avg(new_hit), avg(adopt_hit) FROM per GROUP BY 1""").fetchall()
    n_w, tried, adopted = con.execute("""
        WITH pn AS (SELECT d.brand, d.member, max((h.game IS NULL)::INT) AS tried, max((h.game IS NULL AND d.days >= 2)::INT) AS adopted
                      FROM tdays d LEFT JOIN snap.hist h USING (brand, member, game) GROUP BY 1, 2)
        SELECT (SELECT count(*) FROM w), coalesce(sum(tried), 0), coalesce(sum(adopted), 0) FROM pn""").fetchone()
    con.close()
    ref = {r["model"]: r for r in score(c, asof, stored=(DEFAULT_MODEL,))}[DEFAULT_MODEL]
    mine = {m: (n, h, hn, ha) for m, n, h, hn, ha in res}
    _, _, h, hn, _ = (DEFAULT_MODEL, *mine[DEFAULT_MODEL])
    if abs(h - ref["hr"]) > 0.001 or abs(hn - ref["new_hr"]) > 0.001:
        notes.append(f"default hr {h:.4f}/{ref['hr']:.4f} new {hn:.4f}/{ref['new_hr']:.4f}")
        print(f"   !! default vs mlkit.score {c} {asof}: hr {h:.2%} / {ref['hr']:.2%}, new {hn:.2%} / {ref['new_hr']:.2%}")
    rows = [dict(cluster=c, asof=asof, market=MARKET_OF[c], model=m, players=n, hr=round(h, 5), new_hr=round(hn, 5),
                 adopt_hr=round(ha, 5), try_ceiling=round(tried / n_w, 5), adopt_ceiling=round(adopted / n_w, 5),
                 valid=int(not notes), note="; ".join(notes)) for m, (n, h, hn, ha) in mine.items()]
    save_csv(rows, f"{OUT}/{c}_{asof}.csv")
    print(f"\n{c} ({MARKET_OF[c]}) asof {asof}: {n_w:,} scored players, try ceiling {tried / n_w:.1%}, adopt ceiling {adopted / n_w:.1%}")
    for r in rows:
        ratio = r["adopt_hr"] / r["new_hr"] if r["new_hr"] else 0
        print(f"   {r['model']:44s} HR@10 {r['hr']:6.1%}  new {r['new_hr']:6.1%}  adopted {r['adopt_hr']:6.1%}  ({ratio:.0%} of new hits)")
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
    df["note"] = df["note"].fillna("")
    bad = df[df.valid == 0].drop_duplicates(["cluster", "asof"])
    df = df[df.valid == 1]
    wide = df.pivot_table(index=["cluster", "asof", "market"], columns="model",
                          values=["players", "hr", "new_hr", "adopt_hr", "try_ceiling", "adopt_ceiling"], aggfunc="first")
    out = [f"# Adoption summary ({len(wide)} valid cluster-weeks)", "",
           f"- Excluded: {', '.join(f'{r.cluster} {r.asof} ({r.note})' for r in bad.itertuples()) or 'none'}.",
           "- Player-weighted. adopted = a new-game hit played on ≥ 2 distinct local days of the test week; "
           "share = adopted ÷ new-game HR. Ceilings: share of scored players who try / adopt ≥ 1 new game.", "",
           "| Week | Market | Clusters | Scored players | Default HR@10 | Default new-game HR | Default adopted | Share | "
           "Ranker new HR | Ranker adopted | Share | Popular new HR | Popular adopted | Share | Try ceiling | Adopt ceiling | "
           "Ranker − popular: new / adopted (pt) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for asof in sorted(wide.index.get_level_values("asof").unique()):
        wk = wide.xs(asof, level="asof")
        groups = [(m, wk[wk.index.get_level_values("market") == m]) for m in MARKETS
                  if (wk.index.get_level_values("market") == m).any()] + [("**all**", wk)]
        for m, g in groups:
            n = g[("players", DEFAULT_MODEL)]
            wv = lambda col, mod: (g[(col, mod)] * n).sum() / n.sum()  # noqa: E731
            cells = []
            for mod in MODELS:
                nh, ah = wv("new_hr", mod), wv("adopt_hr", mod)
                cells += ([f"{wv('hr', mod):.1%}"] if mod == DEFAULT_MODEL else []) + [f"{nh:.1%}", f"{ah:.1%}", f"{ah / nh:.0%}"]
            gap = (f"{(wv('new_hr', RANKER_NEW) - wv('new_hr', SCORED_MODEL)) * 100:+.1f} / "
                   f"{(wv('adopt_hr', RANKER_NEW) - wv('adopt_hr', SCORED_MODEL)) * 100:+.1f}")
            out.append(f"| {_week(asof)} | {m} | {len(g)} | {int(n.sum()):,} | " + " | ".join(cells) +
                       f" | {wv('try_ceiling', DEFAULT_MODEL):.1%} | {wv('adopt_ceiling', DEFAULT_MODEL):.1%} | {gap} |")
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
        run(c, w)
    if args == ["all"]:
        summarize()
