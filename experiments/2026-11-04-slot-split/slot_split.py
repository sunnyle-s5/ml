#!/usr/bin/env python3
"""Slot-split ablation for the default list "hybrid (recent continue + ranker new)" (sunny, 4 Nov 2026).

The 3/5 split of continue vs new slots (H5, step 12) was tuned when the continue slots came from ALS. Since 3 Nov the
continue slots are the player's own games newest first. This rebuilds that list with other splits, from a snapshot
opened READ-ONLY, and scores it with the same rule as recs_eval.py / ablation.py (scored players = those with a
'popular 30/70 minus played' list who played in the test week; new = hit on a game not in the 60-day hist).

Nothing is written next to the snapshot. Output: one CSV per run under out/ next to this script.
Usage: slot_split.py <cluster> <asof> [<cluster> <asof> ...]
"""
import csv
import datetime as dt
import os
import sys

import duckdb

SNAP = "/home/ubuntu/ml/data/recs_{c}_{asof}.duckdb"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# continue-slot count per player, as SQL over np = games in 60-day hist, n7 = games played in the last 7 days of hist
VARIANTS = {
    "default 3/5 (np>=3 -> 5)": "CASE WHEN np >= 3 THEN 5 ELSE 3 END",
    "heavy 2": "CASE WHEN np >= 3 THEN 2 ELSE 3 END",
    "heavy 3": "CASE WHEN np >= 3 THEN 3 ELSE 3 END",
    "heavy 4": "CASE WHEN np >= 3 THEN 4 ELSE 3 END",
    "heavy 6": "CASE WHEN np >= 3 THEN 6 ELSE 3 END",
    "heavy 7": "CASE WHEN np >= 3 THEN 7 ELSE 3 END",
    "heavy 8": "CASE WHEN np >= 3 THEN 8 ELSE 3 END",
    "light 1 (np<3 -> 1)": "CASE WHEN np >= 3 THEN 5 ELSE 1 END",
    "adaptive n7, 2..7": "greatest(2, least(7, n7))",
    "adaptive n7, 1..7": "greatest(1, least(7, n7))",
    "adaptive n7, 2..5": "greatest(2, least(5, n7))",
    "adaptive n7+1, 2..7": "greatest(2, least(7, n7 + 1))",
}

SQL = """
WITH scored AS (SELECT DISTINCT brand, member FROM snap.recs WHERE model = 'popular 30/70 minus played'),
w AS (SELECT brand, member FROM scored JOIN (SELECT DISTINCT brand, member FROM snap.truth) USING (brand, member)),
ref AS (SELECT max(last_ts) AS t FROM snap.hist),
h AS (
    SELECT h.brand, h.member, h.game, h.last_ts,
           row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS hrank
      FROM snap.hist h JOIN w USING (brand, member)),
pp AS (
    SELECT brand, member, count(*) AS np,
           count(*) FILTER (WHERE last_ts > (SELECT t FROM ref) - INTERVAL 7 DAY) AS n7
      FROM h GROUP BY 1, 2),
nw AS (SELECT r.brand, r.member, r.game, r.rk AS nrank FROM snap.recs r JOIN w USING (brand, member)
        WHERE r.model = 'ranker (new games only)'),
v AS (SELECT * FROM (VALUES {values}) t(variant, ord)),
k AS (SELECT v.variant, v.ord, w.brand, w.member, coalesce(pp.np, 0) AS np, coalesce(pp.n7, 0) AS n7
        FROM w LEFT JOIN pp USING (brand, member) CROSS JOIN v),
kk AS (SELECT *, {kexpr} AS kc FROM k),
lst AS (
    SELECT kk.variant, kk.ord, kk.brand, kk.member, h.game, TRUE AS cont
      FROM kk JOIN h ON h.brand = kk.brand AND h.member = kk.member AND h.hrank <= kk.kc
    UNION ALL
    SELECT kk.variant, kk.ord, kk.brand, kk.member, nw.game, FALSE AS cont
      FROM kk JOIN nw ON nw.brand = kk.brand AND nw.member = kk.member AND nw.nrank <= 10 - least(kk.kc, kk.np)),
per AS (
    SELECT l.variant, l.ord, l.brand, l.member,
           max((t.game IS NOT NULL)::INT) AS hit,
           max((t.game IS NOT NULL AND hh.game IS NULL)::INT) AS new_hit,
           max((t.game IS NOT NULL AND l.cont)::INT) AS cont_hit,
           count(*) FILTER (WHERE NOT l.cont) AS n_new, count(*) AS n_shown
      FROM lst l
      LEFT JOIN snap.truth t ON t.brand = l.brand AND t.member = l.member AND t.game = l.game
      LEFT JOIN snap.hist hh ON hh.brand = l.brand AND hh.member = l.member AND hh.game = l.game
     GROUP BY 1, 2, 3, 4)
SELECT variant, count(*) AS players, avg(hit) AS hr, avg(new_hit) AS new_hr, avg(cont_hit) AS cont_hr,
       avg(n_new) AS new_slots, avg(n_shown) AS shown
  FROM per GROUP BY variant, ord ORDER BY ord"""

DEFAULT_SQL = """
WITH scored AS (SELECT DISTINCT brand, member FROM snap.recs WHERE model = 'popular 30/70 minus played'),
w AS (SELECT brand, member FROM scored JOIN (SELECT DISTINCT brand, member FROM snap.truth) USING (brand, member)),
shown AS (SELECT r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
           WHERE r.model = 'hybrid (recent continue + ranker new)' AND r.rk <= 10),
per AS (SELECT s.brand, s.member, max((t.game IS NOT NULL)::INT) AS hit,
               max((t.game IS NOT NULL AND h.game IS NULL)::INT) AS new_hit
          FROM shown s LEFT JOIN snap.truth t USING (brand, member, game)
          LEFT JOIN snap.hist h USING (brand, member, game) GROUP BY 1, 2)
SELECT count(*), avg(hit), avg(new_hit) FROM per"""


def run(c, asof):
    path = SNAP.format(c=c, asof=asof)
    con = duckdb.connect()
    con.execute("SET threads = 4; SET memory_limit = '8GB'")
    con.execute(f"ATTACH '{path}' AS snap (READ_ONLY)")
    values = ", ".join(f"('{n}', {i})" for i, n in enumerate(VARIANTS))
    kexpr = "CASE variant " + " ".join(f"WHEN '{n}' THEN {e}" for n, e in VARIANTS.items()) + " END"
    rows = con.execute(SQL.format(values=values, kexpr=kexpr)).fetchall()
    ref = con.execute(DEFAULT_SQL).fetchone()  # the stored default list, as the snapshot holds it
    con.close()
    d = dt.date.fromisoformat(asof)
    print(f"\n{c} asof {asof} (test {d + dt.timedelta(days=1)}..{d + dt.timedelta(days=7)})"
          f"   stored default: {ref[0]:,} players HR@10 {ref[1]:.1%} new {ref[2]:.1%}")
    out = []
    for variant, n, hr, nhr, chr_, ns, sh in rows:
        print(f"   {variant:26s} {n:9,d}  HR@10 {hr:6.1%}  new {nhr:6.1%}  cont {chr_:6.1%}  new slots {ns:4.1f}  shown {sh:4.1f}")
        out.append(dict(cluster=c, asof=asof, variant=variant, players=n, hr=round(hr, 5), new_hr=round(nhr, 5),
                        cont_hr=round(chr_, 5), new_slots=round(ns, 3), shown=round(sh, 3),
                        stored_default_hr=round(ref[1], 5), stored_default_new=round(ref[2], 5)))
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/slot_split_{c}_{asof}.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    for i in range(0, len(a), 2):
        run(a[i], a[i + 1])
