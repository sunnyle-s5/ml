#!/usr/bin/env python3
"""research-bounds: stage-0 ceilings for the experiments proposed from the Netflix/Shopify research.

Each bound is an oracle ceiling, in pt of scored players, of what an issue in issues/recsys-research/ could add over the
stored default `hybrid (recent continue + ranker new)` on one frozen backtest week (definitions in README.md):
  b01_hr / b01_adopt  misses / not-adopted players with a new (adopted) test-week game outside U, the stored ranker-new,
                      ALS-new and popular-minus-played top 10s                                        -> issues 01, 02
  b03_adopt           not-adopted players who adopted a game inside C, the unified ranker's new candidates -> issue 03
  b04_hr / b04_adopt  per-player best of {rebuilt default, heavy 10, heavy 3}, minus the default          -> issue 04
  b05_hr / b05_adopt  misses / not-adopted players with a new (adopted) fresh game: a title first in the
                      cluster's catalogue in the 30 days up to the as-of date                         -> issue 05
Test-week play days come from the market cache with the X2 SQL (experiments/2026-11-05-v2-adoption/run.py).
Checks per job, each failure prints a "!!" line and marks the job invalid: truth rebuild; A rebuilt default == stored
default; B heavy 3 == slot-split's heavy 3; C default HR@10 over all scored players == stored; D adopted-game HR and
adopt ceiling == X2's CSVs.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-06-research-bounds/run.py mx96g1 2026-10-26     # one cluster-week (pairs may repeat)
    bin/py experiments/2026-11-06-research-bounds/run.py all                    # 20 clusters x WEEKS, then summarize
    bin/py experiments/2026-11-06-research-bounds/run.py summarize
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

from mlkit import (DEFAULT_MODEL, HOME, MARKET_OF, MARKETS, RANKER_NEW, SCORED_CLUSTERS, SCORED_MODEL, SCORED_SET, attach,
                   attach_market, connect, day_sql, ep, guard, plays_sql, save_csv, score_sql)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
WEEKS = ["2026-10-19", "2026-10-26"]   # pinned: X2's cross-check CSVs exist only for these weeks
ALS_NEW, LIVE, PCT = "als (new games only)", "live (as stored)", "normalised 30/70 (pct-rank)"
X2 = f"{HOME}/experiments/2026-11-05-v2-adoption/out"
SLOT_SPLIT = f"{HOME}/experiments/2026-11-04-slot-split/out"
BAR_HR, BAR_ADOPT = 0.005, 0.003
SPARSE_PLAYERS, FRESH_DAYS = 20, 30
MIN_VALID = 18                          # fewer valid clusters in a week -> the gate reads INCOMPLETE
REBUILT, HEAVY10, HEAVY3 = "rebuilt default", "heavy 10", "heavy 3"
METRICS = ["dflt_hr", "dflt_adopt", "ceil_new", "ceil_adopt", "u_new", "b01_hr", "b01_adopt", "b03_adopt", "b04_hr",
           "b04_adopt", "b05_hr", "b05_adopt", "fresh_new", "launch_new", "sparse_miss"]
BOUNDS = {"b01_hr": BAR_HR, "b01_adopt": BAR_ADOPT, "b03_adopt": BAR_ADOPT, "b04_hr": BAR_HR, "b04_adopt": BAR_ADOPT,
          "b05_hr": BAR_HR, "b05_adopt": BAR_ADOPT}
ISSUES = [("01 candidate sources", "b01_hr", "b01_adopt"),
          ("02 next-7-day sequence model (shares 01's bound)", "b01_hr", "b01_adopt"),
          ("03 adoption-weighted labels", None, "b03_adopt"),
          ("04 per-player split", "b04_hr", "b04_adopt"),
          ("05 fresh games", "b05_hr", "b05_adopt")]
LOG = None                              # set in __main__: out/run_all.out or out/run_<c>_<asof>.out


def log(s=""):
    print(s, flush=True)
    if LOG:
        with open(LOG, "a") as f:
            f.write(s + "\n")


def run(c, asof):
    t0 = time.time()
    a = dt.date.fromisoformat(asof)
    tr1, te1 = a + dt.timedelta(days=1), a + dt.timedelta(days=8)
    con = attach(connect(), c, asof)
    try:
        attach_market(con, c)
    except duckdb.IOException:
        log(f"SKIP {c} {asof}: market cache locked")
        save_csv([dict(cluster=c, asof=asof, market=MARKET_OF[c], players=0, valid=0, note="market cache locked")],
                 f"{OUT}/{c}_{asof}.csv")
        con.close()
        return

    # ---- test-week play days and the truth-rebuild check: X2 (v2-adoption run.py lines 46-59) ----
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
        log(f"   !! truth rebuild {c} {asof}: rows {n_m:,}/{n_t:,} rounds {r_d:,}/{r_t:,}")

    # ---- own games and three rebuilt lists (v3-unified build() / LISTS_SQL rules) ----
    con.execute("""CREATE TEMP TABLE own AS
        SELECT h.brand, h.member, h.game, h.rounds, h.last_ts,
               row_number() OVER (PARTITION BY h.brand, h.member ORDER BY h.last_ts DESC, h.rounds DESC, h.game) AS rr
          FROM snap.hist h JOIN w USING (brand, member)""")
    con.execute("CREATE TEMP TABLE pg AS SELECT brand, member, count(*) AS p_games FROM own GROUP BY 1, 2")
    con.execute(f"""CREATE TEMP TABLE x AS
        SELECT o.brand, o.member, o.game, 1 AS is_own, o.rr, NULL::BIGINT AS rk_ranker, pg.p_games
          FROM own o JOIN pg ON pg.brand = o.brand AND pg.member = o.member
         WHERE o.rr <= 10
        UNION ALL
        SELECT r.brand, r.member, r.game, 0, NULL::BIGINT, r.rk, coalesce(pg.p_games, 0)
          FROM snap.recs r JOIN w ON w.brand = r.brand AND w.member = r.member
          LEFT JOIN pg ON pg.brand = r.brand AND pg.member = r.member
         WHERE r.model = '{RANKER_NEW}'
           AND NOT EXISTS (SELECT 1 FROM own o WHERE o.brand = r.brand AND o.member = r.member AND o.game = r.game)""")
    n5, n10 = "CASE WHEN p_games >= 3 THEN 5 ELSE 3 END", "CASE WHEN p_games >= 3 THEN 10 ELSE 3 END"
    order = "row_number() OVER (PARTITION BY brand, member ORDER BY is_own DESC, rr, rk_ranker)"
    con.execute(f"""CREATE TEMP TABLE vl AS SELECT * FROM (
        SELECT '{REBUILT}' AS model, brand, member, game, {order} AS rk FROM x WHERE (is_own = 1 AND rr <= {n5}) OR is_own = 0
        UNION ALL
        SELECT '{HEAVY10}', brand, member, game, {order} FROM x WHERE (is_own = 1 AND rr <= {n10}) OR is_own = 0
        UNION ALL
        SELECT '{HEAVY3}', brand, member, game, {order} FROM x WHERE (is_own = 1 AND rr <= 3) OR is_own = 0
        ) WHERE rk <= 10""")

    # ---- checks A and B ----
    sc = {r["model"]: r for r in score_sql(con, f"SELECT model, brand, member, game, rk FROM snap.recs WHERE model = '{DEFAULT_MODEL}' "
                                                "UNION ALL SELECT model, brand, member, game, rk FROM vl")}
    ref, reb = sc[DEFAULT_MODEL], sc.get(REBUILT)
    if reb is None or (reb["players"], reb["hr"], reb["new_hr"]) != (ref["players"], ref["hr"], ref["new_hr"]):
        got = (reb["players"], reb["hr"], reb["new_hr"]) if reb else None
        notes.append(f"A rebuilt default {got} vs stored {(ref['players'], ref['hr'], ref['new_hr'])}")
        log(f"   !! A rebuilt default {c} {asof}: {got} vs stored {(ref['players'], ref['hr'], ref['new_hr'])}")
    p = f"{SLOT_SPLIT}/slot_split_{c}_{asof}.csv"
    if os.path.exists(p):
        with open(p) as f:
            h3 = next((float(r["hr"]) for r in csv.DictReader(f) if r["variant"] == HEAVY3), None)
        if h3 is None or HEAVY3 not in sc or abs(sc[HEAVY3]["hr"] - h3) > 0.0002:
            notes.append(f"B heavy 3 {sc.get(HEAVY3, {}).get('hr')} vs slot-split {h3}")
            log(f"   !! B heavy 3 {c} {asof}: {sc.get(HEAVY3, {}).get('hr')} vs slot-split {h3}")
    else:
        log(f"   (no {os.path.basename(p)}: check B skipped)")

    # ---- sets: new / adopted test-week games, candidate sets, fresh titles, sparse games ----
    con.execute("""CREATE TEMP TABLE nt AS
        WITH tw AS (SELECT t.brand, t.member, t.game FROM snap.truth t JOIN w USING (brand, member))
        SELECT tw.* FROM tw ANTI JOIN snap.hist h USING (brand, member, game)""")
    con.execute("""CREATE TEMP TABLE ad AS
        WITH d2 AS (SELECT brand, member, game FROM tdays WHERE days >= 2)
        SELECT d2.* FROM d2 ANTI JOIN snap.hist h USING (brand, member, game)""")
    con.execute(f"""CREATE TEMP TABLE uu AS
        WITH u0 AS (SELECT DISTINCT r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
                     WHERE r.model IN ('{RANKER_NEW}', '{ALS_NEW}', '{SCORED_MODEL}') AND r.rk <= 10)
        SELECT u0.* FROM u0 ANTI JOIN snap.hist h USING (brand, member, game)""")
    con.execute(f"""CREATE TEMP TABLE lv AS
        WITH hb AS (SELECT DISTINCT brand FROM snap.lists WHERE model = '{LIVE}')
        SELECT brand, game FROM snap.lists WHERE model = '{LIVE}' AND rk <= 20
        UNION ALL SELECT brand, game FROM snap.lists
         WHERE model = '{PCT}' AND rk <= 20 AND brand NOT IN (SELECT brand FROM hb)""")
    con.execute(f"""CREATE TEMP TABLE cc AS
        WITH c0 AS (SELECT r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
                     WHERE r.model IN ('{RANKER_NEW}', '{SCORED_MODEL}') AND r.rk <= 10
                    UNION SELECT w.brand, w.member, lv.game FROM w JOIN lv USING (brand))
        SELECT c0.* FROM c0 ANTI JOIN snap.hist h USING (brand, member, game)""")
    lo_ep, hi_ep = ep(a - dt.timedelta(days=FRESH_DAYS - 1), c), ep(a + dt.timedelta(days=1), c)
    con.execute(f"""CREATE TEMP TABLE gk AS
        SELECT DISTINCT id AS game,
               coalesce(json_extract_string(rawData, '$.productId') || ':' || json_extract_string(rawData, '$.code'),
                        'id:' || id) AS tkey,
               createdAt
          FROM mkt.game_{c} WHERE snapshot = (SELECT max(snapshot) FROM mkt.game_{c})""")
    con.execute("CREATE TEMP TABLE tk AS SELECT tkey, min(createdAt) AS first_at FROM gk GROUP BY 1")
    con.execute(f"""CREATE TEMP TABLE fresh AS SELECT DISTINCT gk.game FROM gk JOIN tk USING (tkey)
                    WHERE epoch(tk.first_at) >= {lo_ep} AND epoch(tk.first_at) < {hi_ep}""")
    con.execute(f"""CREATE TEMP TABLE launch AS SELECT DISTINCT gk.game FROM gk JOIN tk USING (tkey)
                    WHERE epoch(tk.first_at) >= {hi_ep}""")
    fresh_titles = con.execute(f"SELECT count(*) FROM tk WHERE epoch(first_at) >= {lo_ep} AND epoch(first_at) < {hi_ep}").fetchone()[0]
    keyless = con.execute("SELECT count(*) FROM gk WHERE tkey LIKE 'id:%'").fetchone()[0]
    if keyless:
        log(f"   ({keyless:,} catalogue ids without productId/code: keyed by id)")
    con.execute("CREATE TEMP TABLE bp AS SELECT brand, game, count(DISTINCT member) AS n FROM snap.hist GROUP BY 1, 2")

    # ---- per-player outcomes ----
    con.execute(f"""CREATE TEMP TABLE lo AS
        WITH l AS (SELECT r.model, r.brand, r.member, r.game FROM snap.recs r JOIN w USING (brand, member)
                    WHERE r.model = '{DEFAULT_MODEL}' AND r.rk <= 10
                   UNION ALL SELECT model, brand, member, game FROM vl WHERE model IN ('{HEAVY10}', '{HEAVY3}'))
        SELECT l.brand, l.member,
               max((t.game IS NOT NULL AND l.model = '{DEFAULT_MODEL}')::INT) AS hit_d,
               max((a.game IS NOT NULL AND l.model = '{DEFAULT_MODEL}')::INT) AS adopt_d,
               max((t.game IS NOT NULL AND l.model = '{HEAVY10}')::INT) AS hit_h10,
               max((a.game IS NOT NULL AND l.model = '{HEAVY10}')::INT) AS adopt_h10,
               max((t.game IS NOT NULL AND l.model = '{HEAVY3}')::INT) AS hit_h3,
               max((a.game IS NOT NULL AND l.model = '{HEAVY3}')::INT) AS adopt_h3
          FROM l
          LEFT JOIN snap.truth t ON t.brand = l.brand AND t.member = l.member AND t.game = l.game
          LEFT JOIN ad a ON a.brand = l.brand AND a.member = l.member AND a.game = l.game
         GROUP BY 1, 2""")
    con.execute(f"""CREATE TEMP TABLE gn AS
        SELECT n.brand, n.member,
               max((u.game IS NULL)::INT) AS new_out_u, max((u.game IS NOT NULL)::INT) AS new_in_u,
               max((f.game IS NOT NULL)::INT) AS new_fresh, max((la.game IS NOT NULL)::INT) AS new_launch,
               max((coalesce(b.n, 0) < {SPARSE_PLAYERS})::INT) AS new_sparse
          FROM nt n
          LEFT JOIN uu u ON u.brand = n.brand AND u.member = n.member AND u.game = n.game
          LEFT JOIN fresh f ON f.game = n.game
          LEFT JOIN launch la ON la.game = n.game
          LEFT JOIN bp b ON b.brand = n.brand AND b.game = n.game
         GROUP BY 1, 2""")
    con.execute("""CREATE TEMP TABLE ga AS
        SELECT d.brand, d.member,
               max((u.game IS NULL)::INT) AS adopt_out_u, max((k.game IS NOT NULL)::INT) AS adopt_in_c,
               max((f.game IS NOT NULL)::INT) AS adopt_fresh
          FROM ad d
          LEFT JOIN uu u ON u.brand = d.brand AND u.member = d.member AND u.game = d.game
          LEFT JOIN cc k ON k.brand = d.brand AND k.member = d.member AND k.game = d.game
          LEFT JOIN fresh f ON f.game = d.game
         GROUP BY 1, 2""")
    v = con.execute("""
        WITH pf AS (
            SELECT coalesce(lo.hit_d, 0) AS hit_d, coalesce(lo.adopt_d, 0) AS adopt_d,
                   coalesce(lo.hit_h10, 0) AS hit_h10, coalesce(lo.adopt_h10, 0) AS adopt_h10,
                   coalesce(lo.hit_h3, 0) AS hit_h3, coalesce(lo.adopt_h3, 0) AS adopt_h3,
                   coalesce(gn.new_out_u, 0) AS new_out_u, coalesce(gn.new_in_u, 0) AS new_in_u,
                   coalesce(gn.new_fresh, 0) AS new_fresh, coalesce(gn.new_launch, 0) AS new_launch,
                   coalesce(gn.new_sparse, 0) AS new_sparse,
                   coalesce(ga.adopt_out_u, 0) AS adopt_out_u, coalesce(ga.adopt_in_c, 0) AS adopt_in_c,
                   coalesce(ga.adopt_fresh, 0) AS adopt_fresh,
                   (gn.member IS NOT NULL)::INT AS new_any, (ga.member IS NOT NULL)::INT AS adopt_any
              FROM w
              LEFT JOIN lo ON lo.brand = w.brand AND lo.member = w.member
              LEFT JOIN gn ON gn.brand = w.brand AND gn.member = w.member
              LEFT JOIN ga ON ga.brand = w.brand AND ga.member = w.member)
        SELECT count(*), avg(hit_d), avg(adopt_d), avg(new_any), avg(adopt_any), avg(new_in_u),
               avg((1 - hit_d) * new_out_u), avg((1 - adopt_d) * adopt_out_u), avg((1 - adopt_d) * adopt_in_c),
               avg(greatest(hit_d, hit_h10, hit_h3)), avg(greatest(adopt_d, adopt_h10, adopt_h3)),
               avg((1 - hit_d) * new_fresh), avg((1 - adopt_d) * adopt_fresh), avg(new_fresh), avg(new_launch),
               avg((1 - hit_d) * new_sparse)
          FROM pf""").fetchone()
    con.close()
    n = v[0]
    m = dict(zip(["dflt_hr", "dflt_adopt", "ceil_new", "ceil_adopt", "u_new", "b01_hr", "b01_adopt", "b03_adopt",
                  "best_hr", "best_adopt", "b05_hr", "b05_adopt", "fresh_new", "launch_new", "sparse_miss"], v[1:]))
    m["b04_hr"], m["b04_adopt"] = m.pop("best_hr") - m["dflt_hr"], m.pop("best_adopt") - m["dflt_adopt"]
    m = {k: round(m[k], 5) for k in METRICS}

    # ---- checks C and D ----
    if abs(m["dflt_hr"] - ref["hr"]) > 1e-6:
        notes.append(f"C default hr {m['dflt_hr']} vs stored {ref['hr']}")
        log(f"   !! C default HR@10 over all scored players {c} {asof}: {m['dflt_hr']} vs stored {ref['hr']}")
    p = f"{X2}/{c}_{asof}.csv"
    if os.path.exists(p):
        with open(p) as f:
            x2 = next((r for r in csv.DictReader(f) if r["model"] == DEFAULT_MODEL), None)
        if (x2 is None or abs(m["dflt_adopt"] - float(x2["adopt_hr"])) > 1.01e-5
                or abs(m["ceil_adopt"] - float(x2["adopt_ceiling"])) > 1.01e-5):
            got = (x2["adopt_hr"], x2["adopt_ceiling"]) if x2 else None
            notes.append(f"D adopt {m['dflt_adopt']}/{m['ceil_adopt']} vs X2 {got}")
            log(f"   !! D adopted-game HR / adopt ceiling {c} {asof}: {m['dflt_adopt']} / {m['ceil_adopt']} vs X2 {got}")
    else:
        notes.append("D: no X2 CSV")
        log(f"   !! D {c} {asof}: no {p}")

    secs = round(time.time() - t0, 1)
    save_csv([dict(cluster=c, asof=asof, market=MARKET_OF[c], players=n, valid=int(not notes), note="; ".join(notes),
                   **m, fresh_titles=fresh_titles, seconds=secs)], f"{OUT}/{c}_{asof}.csv")
    pt = lambda k: f"{m[k] * 100:5.2f}"  # noqa: E731
    log(f"\n{c} ({MARKET_OF[c]}) asof {asof}: {n:,} scored players, {fresh_titles:,} fresh titles ({secs:.0f} s)")
    log(f"   default HR@10 {m['dflt_hr']:.2%}  adopted-game HR {m['dflt_adopt']:.2%}  ceilings: new {m['ceil_new']:.1%}, "
        f"adopt {m['ceil_adopt']:.1%}  U reaches {m['u_new']:.1%}  heavy 10 / heavy 3 HR@10 {sc[HEAVY10]['hr']:.2%} / {sc[HEAVY3]['hr']:.2%}")
    log(f"   bounds (pt): b01 {pt('b01_hr')} / {pt('b01_adopt')}   b03 adopt {pt('b03_adopt')}   b04 {pt('b04_hr')} / "
        f"{pt('b04_adopt')}   b05 {pt('b05_hr')} / {pt('b05_adopt')}")
    log(f"   fresh new {m['fresh_new']:.2%}  launch new {m['launch_new']:.2%}  sparse-game misses {pt('sparse_miss')} pt"
        + ("" if not notes else f"   INVALID: {'; '.join(notes)}"))


def _week(asof):
    d = dt.date.fromisoformat(asof)
    a, b = d + dt.timedelta(days=1), d + dt.timedelta(days=7)
    return f"{a.day} {a:%b}–{b.day} {b:%b}"


def summarize():
    pat = re.compile(r"^([a-z0-9]+)_(\d{4}-\d{2}-\d{2})\.csv$")
    files = [p for p in sorted(glob.glob(f"{OUT}/*.csv")) if (mm := pat.match(os.path.basename(p))) and mm.group(1) in SCORED_CLUSTERS]
    if not files:
        sys.exit("summarize: no per-job CSVs in out/")
    df = pd.concat([pd.read_csv(p, dtype={"asof": str}) for p in files], ignore_index=True)
    df["note"] = df["note"].fillna("")
    bad = df[df.valid != 1]
    ok = df[df.valid == 1]
    weeks = [w for w in WEEKS if w in set(df["asof"])]
    byw = {w: ok[ok["asof"] == w] for w in weeks}       # df.asof is a pandas method, so index the column by name
    n_ok = {w: len(byw[w]) for w in weeks}
    pooled = lambda g, k: (g[k] * g.players).sum() / g.players.sum() if len(g) and g.players.sum() else float("nan")  # noqa: E731
    f2 = lambda x: f"{x * 100:.2f}"  # noqa: E731

    def gate(k):
        if any(n_ok[w] < MIN_VALID for w in weeks) or len(weeks) < len(WEEKS):
            return "INCOMPLETE"
        return "PASS" if all(pooled(byw[w], k) >= BOUNDS[k] for w in weeks) else "FAIL"

    out = [f"# Stage-0 bounds ({len(ok)} valid cluster-weeks of {len(SCORED_CLUSTERS) * len(WEEKS)})", "",
           "All numbers in pt of scored players, player-weighted over valid clusters. Definitions and bars: README.md.", "",
           "## 1 · Valid jobs", ""]
    out += [f"- {_week(w)} (as-of {w}): {n_ok[w]}/{len(SCORED_CLUSTERS)} valid" for w in weeks]
    missing = [f"{c} {w}" for w in WEEKS for c in SCORED_CLUSTERS if not ((df.cluster == c) & (df["asof"] == w)).any()]
    out.append(f"- Skipped or invalid: {', '.join([f'{r.cluster} {r.asof} ({r.note})' for r in bad.itertuples()] + [f'{x} (not run)' for x in missing]) or 'none'}")
    out += ["", "## 2 · Pooled bounds", "",
            "|Bound|Bar|" + "|".join(_week(w) for w in weeks) + "|Cluster range|Clusters ≥ bar|Gate|",
            "|---|---|" + "---|" * len(weeks) + "---|---|---|"]
    for k, bar in BOUNDS.items():
        rng = "; ".join(f"{f2(byw[w][k].min())}–{f2(byw[w][k].max())}" for w in weeks)
        cnt = "; ".join(f"{int((byw[w][k] >= bar).sum())}/{n_ok[w]}" for w in weeks)
        out.append(f"|`{k}`|{f2(bar)}|" + "|".join(f2(pooled(byw[w], k)) for w in weeks) + f"|{rng}|{cnt}|{gate(k)}|")
    out += ["", "## 3 · Reference", "",
            "|Metric|" + "|".join(_week(w) for w in weeks) + "|", "|---|" + "---|" * len(weeks)]
    for k in ["dflt_hr", "dflt_adopt", "ceil_new", "ceil_adopt", "u_new", "fresh_new", "launch_new", "sparse_miss"]:
        out.append(f"|`{k}`|" + "|".join(f2(pooled(byw[w], k)) for w in weeks) + "|")
    out.append("|`fresh_titles` (sum over clusters)|" + "|".join(f"{int(byw[w].fresh_titles.sum()):,}" for w in weeks) + "|")
    out.append("|scored players|" + "|".join(f"{int(byw[w].players.sum()):,}" for w in weeks) + "|")
    out += ["", "## 4 · Per-issue gates", "", "|Issue|HR@10 gate|Discovery gate|Stage 1|", "|---|---|---|---|"]
    for name, kh, ka in ISSUES:
        gh, ga = (gate(kh) if kh else None), gate(ka)
        go = "INCOMPLETE" if "INCOMPLETE" in (gh, ga) else ("yes" if "PASS" in (gh, ga) else "no")
        out.append(f"|{name}|{f'`{kh}` {gh}' if kh else '—'}|`{ka}` {ga}|{go}|")
    out += ["", "## 5 · Per market", "",
            "|Week|Market|Clusters|Scored players|" + "|".join(f"`{k}`" for k in BOUNDS) + "|",
            "|---|---|---|---|" + "---|" * len(BOUNDS)]
    for w in weeks:
        g = byw[w]
        for mk in list(MARKETS) + ["all"]:
            gm = g if mk == "all" else g[g.market == mk]
            if not len(gm):
                continue
            out.append(f"|{_week(w)}|{'**all**' if mk == 'all' else mk}|{len(gm)}|{int(gm.players.sum()):,}|"
                       + "|".join(f2(pooled(gm, k)) for k in BOUNDS) + "|")
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
        jobs = [(c, w) for w in WEEKS for c in SCORED_CLUSTERS]
    elif len(args) >= 2 and len(args) % 2 == 0:
        jobs = list(zip(args[::2], args[1::2]))
        if bad_args := [c for c, _ in jobs if c not in SCORED_CLUSTERS]:
            sys.exit(f"not a scored cluster: {', '.join(bad_args)}")
    else:
        sys.exit(__doc__)
    os.makedirs(OUT, exist_ok=True)
    if args == ["all"]:
        LOG = f"{OUT}/run_all.out"
        open(LOG, "w").close()
    for c, w in jobs:
        guard()
        if args != ["all"]:
            LOG = f"{OUT}/run_{c}_{w}.out"
            open(LOG, "w").close()
        run(c, w)
    if args == ["all"]:
        summarize()
