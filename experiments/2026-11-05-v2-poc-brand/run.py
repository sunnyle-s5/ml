#!/usr/bin/env python3
"""v2-poc-brand (X8 + X9) on the POC brand ADDA7 (bdk1, BD, market day UTC+6).

X8, play-based RG markers (the two of the v2 spec's six that plays alone support; no payments data on the VM),
over the 7 local days ending on each as-of date:
  night   >= 50 % of the week's rounds in local hours 00-05, with >= 500 rounds
  long    >= 3 local days with >= 8 distinct local hours played
Prevalence among all active ADDA7 players and among that week's scored players, plus the "newly flagged" base rate
(not flagged in the 19 Oct window, active and flagged in the 26 Oct window).
X9, variance for the POC metrics: players active in the week from T = 2026-10-20; post = 14 days from T, pre = the
28 days before T. Per metric: CV, pre/post correlation, CUPED factor 1 - rho^2, MDE (relative, alpha 0.05, 80 %) for
a 50/50 split and for one pairwise comparison of a 17/17/33/33 split, and the non-inferiority size
n_req = (2 * 2.487 * CV_adj / margin)^2 (margins: active days 1 %, bet 3 %). bet and ggr are winsorised at P0.5/P99.5.

Usage (from /home/sunny/ml):
    bin/py experiments/2026-11-05-v2-poc-brand/run.py
"""
import datetime as dt
import math
import os
import sys

import duckdb

from mlkit import SCORED_SET, attach, attach_market, connect, day_sql, ep, guard, hour_sql, plays_sql, save_csv

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
C, BRAND, LABEL = "bdk1", "4c0fc28c-5ee5-49ec-abb8-777b2b1295f5", "ADDA7"
WEEKS = ("2026-10-19", "2026-10-26")
T = dt.date(2026, 10, 20)
MARGINS = {"active_days": 0.01, "bet": 0.03}
Z2, ZNI = 2.8, 2.487            # two-sided 0.05 + 80 % power; one-sided 0.05 + 80 % power


def market(con=None, snap_asof=None):
    con = attach(connect(), C, snap_asof) if snap_asof else connect()
    try:
        attach_market(con, C)
    except duckdb.IOException:
        sys.exit(f"SKIP {C}: market cache locked; retry in 10 minutes, then run Step 5 on MXWOW (mxk1) instead")
    return con


def x8():
    rows, flagged = [], {}
    for asof in WEEKS:
        a = dt.date.fromisoformat(asof)
        d0, d1 = a - dt.timedelta(days=6), a + dt.timedelta(days=1)
        con = market(snap_asof=asof)
        q = plays_sql(con, C)
        con.execute(f"""CREATE TEMP TABLE x AS SELECT member, rounds, {hour_sql(C, 'ts')} AS hr, {day_sql(C, d0, 'ts')} AS d
                          FROM {q} p WHERE brand = '{BRAND}' AND epoch(ts) >= {ep(d0, C)} AND epoch(ts) < {ep(d1, C)}""")
        con.execute("""CREATE TEMP TABLE m AS
            WITH pd AS (SELECT member, d, count(DISTINCT hr) AS hours FROM x GROUP BY 1, 2),
                 pl AS (SELECT member, sum(rounds) AS rounds_7d, sum(CASE WHEN hr < 6 THEN rounds ELSE 0 END) AS night FROM x GROUP BY 1),
                 ld AS (SELECT member, count(*) FILTER (WHERE hours >= 8) AS long_days FROM pd GROUP BY 1)
            SELECT member, rounds_7d, night / NULLIF(rounds_7d, 0) AS night_share, long_days,
                   (night / NULLIF(rounds_7d, 0) >= 0.5 AND rounds_7d >= 500) AS m_night, long_days >= 3 AS m_long
              FROM pl JOIN ld USING (member)""")
        con.execute(f"CREATE TEMP TABLE sc AS SELECT member FROM ({SCORED_SET}) s WHERE brand = '{BRAND}'")
        for pop, where in (("all active", ""), ("scored", "WHERE member IN (SELECT member FROM sc)")):
            n, nn, nl, ne, nb = con.execute(f"""SELECT count(*), sum(m_night::INT), sum(m_long::INT),
                sum((m_night OR m_long)::INT), sum((m_night AND m_long)::INT) FROM m {where}""").fetchone()
            rows.append(dict(window_end=asof, population=pop, players=n, night=nn, long=nl, either=ne, both=nb,
                             night_share=round(nn / n, 5), long_share=round(nl / n, 5), either_share=round(ne / n, 5)))
        flagged[asof] = {m: f for m, f in con.execute("SELECT member, m_night OR m_long FROM m").fetchall()}
        if asof == WEEKS[-1]:
            spot = con.execute("SELECT member FROM m WHERE m_long ORDER BY rounds_7d DESC, member LIMIT 1").fetchone()
            if spot:
                hrs = con.execute("SELECT d, count(DISTINCT hr), sum(rounds) FROM x WHERE member = ? GROUP BY 1 ORDER BY 1", [spot[0]]).fetchall()
                print(f"   spot check (long sessions, member {spot[0][:8]}…): day, distinct hours, rounds = {hrs}")
        con.close()
    w1, w2 = flagged[WEEKS[0]], flagged[WEEKS[1]]
    base = [f for m, f in w2.items() if not w1.get(m, False)]
    both_active = [f for m, f in w2.items() if m in w1 and not w1[m]]
    p, p2 = sum(base) / len(base), sum(both_active) / len(both_active)
    save_csv(rows, f"{OUT}/x8_markers.csv")
    return rows, dict(newly_flagged=p, n_base=len(base), newly_flagged_both_active=p2, n_both_active=len(both_active))


def x9():
    con = market()
    q = plays_sql(con, C)
    first = con.execute(f"SELECT min(ts) FROM {q} p WHERE brand = '{BRAND}'").fetchone()[0]
    pre0 = T - dt.timedelta(days=28)
    pre_days = 28
    if first > dt.datetime.combine(pre0, dt.time(0), tzinfo=dt.timezone(dt.timedelta(hours=6))):
        pre0 = (first + dt.timedelta(hours=6)).date() + dt.timedelta(days=1)
        pre_days = (T - pre0).days
        print(f"   pre window shortened to {pre_days} days (cache starts {first})")
    post1 = T + dt.timedelta(days=14)
    con.execute(f"""CREATE TEMP TABLE x AS SELECT member, game, rounds, bet, bet - earn AS ggr, {day_sql(C, pre0, 'ts')} AS d,
                           epoch(ts) >= {ep(T, C)} AS post
                      FROM {q} p WHERE brand = '{BRAND}' AND epoch(ts) >= {ep(pre0, C)} AND epoch(ts) < {ep(post1, C)}""")
    con.execute(f"""CREATE TEMP TABLE pop AS SELECT DISTINCT member FROM x
                     WHERE post AND d < {(T - pre0).days + 7}""")
    con.execute("""CREATE TEMP TABLE pp AS
        WITH agg AS (SELECT member, post, count(DISTINCT d) AS active_days, sum(rounds) AS rounds, sum(bet) AS bet,
                            sum(ggr) AS ggr, count(DISTINCT game) AS games FROM x WHERE member IN (SELECT member FROM pop) GROUP BY 1, 2)
        SELECT p.member,
               coalesce(a.active_days, 0) AS active_days, coalesce(a.rounds, 0) AS rounds, coalesce(a.bet, 0) AS bet,
               coalesce(a.ggr, 0) AS ggr, coalesce(a.games, 0) AS games,
               coalesce(b.active_days, 0) AS pre_active_days, coalesce(b.rounds, 0) AS pre_rounds, coalesce(b.bet, 0) AS pre_bet,
               coalesce(b.ggr, 0) AS pre_ggr, coalesce(b.games, 0) AS pre_games
          FROM pop p LEFT JOIN agg a ON a.member = p.member AND a.post LEFT JOIN agg b ON b.member = p.member AND NOT b.post""")
    for col in ("bet", "ggr", "pre_bet", "pre_ggr"):
        lo, hi = con.execute(f"SELECT quantile_cont({col}, 0.005), quantile_cont({col}, 0.995) FROM pp").fetchone()
        con.execute(f"UPDATE pp SET {col} = least(greatest({col}, {lo}), {hi})")
    rows = []
    for metric in ("active_days", "rounds", "bet", "ggr", "games"):
        n, mean, sd, rho = con.execute(f"SELECT count(*), avg({metric}), stddev_samp({metric}), corr({metric}, pre_{metric}) FROM pp").fetchone()
        rho = rho or 0.0
        cv = sd / abs(mean) if mean else float("inf")
        f = 1 - rho ** 2
        cva = cv * math.sqrt(f)
        mde2 = Z2 * 2 * cva / math.sqrt(n)
        margin = MARGINS.get(metric)
        n_req = (2 * ZNI * cva / margin) ** 2 if margin else None
        rows.append(dict(metric=metric, n=n, mean=round(mean, 4), sd=round(sd, 4), cv=round(cv, 4), rho=round(rho, 4),
                         cuped_factor=round(f, 4), cv_adj=round(cva, 4), mde_2arm_rel=round(mde2, 5),
                         mde_4arm_pair_rel=round(mde2 / math.sqrt(0.67), 5), margin=margin,
                         n_req=None if n_req is None else int(math.ceil(n_req)), gated=None if n_req is None else int(n_req <= n),
                         pre_days=pre_days))
    con.close()
    save_csv(rows, f"{OUT}/x9_variance.csv")
    return rows


def main():
    guard()
    r8, nf = x8()
    guard()
    r9 = x9()
    n = r9[0]["n"]
    p = nf["newly_flagged"]
    mde_nf = Z2 * math.sqrt(2 * p * (1 - p) / (n / 2))
    out = [f"# POC brand {LABEL} ({C}, BD): RG markers (X8) and variance (X9)", "",
           "## X8 · Play-based RG markers (7 local days ending on the date)", "",
           "| Window ends | Population | Players | Night play | Long sessions | Either | Both |", "|---|---|---|---|---|---|---|"]
    for r in r8:
        out.append(f"| {r['window_end']} | {r['population']} | {r['players']:,} | {r['night']:,} ({r['night_share']:.2%}) | "
                   f"{r['long']:,} ({r['long_share']:.2%}) | {r['either']:,} ({r['either_share']:.2%}) | {r['both']:,} |")
    out += ["", f"Newly flagged base rate: {p:.2%} of {nf['n_base']:,} players active in the 26 Oct window and not flagged in the 19 Oct "
                f"window ({nf['newly_flagged_both_active']:.2%} of the {nf['n_both_active']:,} active in both). "
                f"Guardrail MDE (absolute, 50/50, n = {n:,}): {mde_nf * 100:.2f} pt.", "",
            f"## X9 · Variance and CUPED (players active 20–26 Oct; post 14 days, pre {r9[0]['pre_days']} days)", "",
            "| Metric | n | Mean | CV | ρ pre/post | CUPED factor | CV after CUPED | MDE 50/50 (rel) | MDE 17/17/33/33 pair (rel) | "
            "NI margin | n needed | Gate? |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in r9:
        gate = "–" if r["gated"] is None else ("yes" if r["gated"] else "no: monitor only")
        margin = "–" if r["margin"] is None else f"−{r['margin']:.0%}"
        n_req = "–" if r["n_req"] is None else f"{r['n_req']:,}"
        out.append(f"| {r['metric']} | {r['n']:,} | {r['mean']:,.2f} | {r['cv']:.2f} | {r['rho']:.2f} | {r['cuped_factor']:.2f} | "
                   f"{r['cv_adj']:.2f} | {r['mde_2arm_rel']:.1%} | {r['mde_4arm_pair_rel']:.1%} | {margin} | {n_req} | {gate} |")
    with open(f"{OUT}/summary.md", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
