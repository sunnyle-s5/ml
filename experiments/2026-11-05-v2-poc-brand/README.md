# v2-poc-brand (X8 + X9)

Started: 2026-11-05 · Status: done

## Question
For the POC brand ADDA7 (bdk1, BD):
- **X8:** how many players would the v2 spec's play-based responsible-gambling markers flag, and what is the base rate of the "newly flagged after exposure" guardrail?
- **X9:** how noisy are the POC's secondary metrics and guardrails? How much would CUPED help, and which guardrails can be gated at this size?

## Setup
- **Data.** Market cache `bd.duckdb` (`plays_bdk1`, hourly rows; all round statuses), brand `4c0fc28c-5ee5-49ec-abb8-777b2b1295f5`. Local day = UTC+6.
- **X8 markers.** Of the v2 spec's six markers, only these two can be computed: the VM has no payments data.
  - Night play: ≥ 50 % of a 7-day window's rounds in local hours 00–05, with ≥ 500 rounds.
  - Long sessions: ≥ 3 days with ≥ 8 distinct local hours.
  - Windows: the 7 days ending 19 Oct and the 7 days ending 26 Oct.
- **X9 population.** Players active 20–26 Oct (n = 78,099). Post window: 14 days from 20 Oct. Pre window: 28 days before. `bet` and `ggr` (bet − earn) are winsorised at P0.5/P99.5.
- **X9 formulas.**
  - MDE = 2.8 · 2 · CV_adj / √n (relative, two-sided α 0.05, 80 % power, 50/50 split).
  - Non-inferiority size: n_req = (2 · 2.487 · CV_adj / margin)², with margins −1 % for active days and −3 % for bet.
- **Checks.** The spot-checked player (long sessions) had 14, 13, 20, 22 and 16 distinct hours on 5 of 7 days. Every flagged count is ≤ the active count. Every CUPED factor is in [0, 1].

## Result (`out/summary.md`)

**X8 flags:**

| Window | All active | Flagged (either) | Scored players | Flagged (either) |
|---|---|---|---|---|
| 13–19 Oct | 79,171 | 3,133 (3.96 %) | 47,743 | 2,720 (5.70 %) |
| 20–26 Oct | 78,099 | 2,727 (3.49 %) | 47,482 | 2,389 (5.03 %) |

Almost all flags come from night play (2,494 of 2,727 in the 20–26 Oct window). Newly flagged base rate: 2.86 %. The guardrail's MDE is 0.33 pt absolute.

**X9:**

| Metric | CV | ρ pre/post | CUPED factor | MDE 50/50 | n needed for non-inferiority | Gate? |
|---|---|---|---|---|---|---|
| active days | 0.83 | 0.66 | 0.56 | 1.2 % | 94,851 at −1 % | no (n = 78,099) |
| rounds | 4.26 | 0.70 | 0.51 | 6.1 % | – | – |
| bet | 4.65 | 0.65 | 0.58 | 7.1 % | 342,808 at −3 % | no |
| ggr (realized) | 6.20 | 0.29 | 0.91 | 11.9 % | – | – |
| distinct games | 1.65 | 0.59 | 0.65 | 2.7 % | – | – |

## Decision / next
- **Safer mode** (R2): leave out of the personal file the ~3.5 % of active ADDA7 players (~5 % of scored players) that the two markers flag. "Newly flagged after exposure" (base 2.9 %, MDE 0.33 pt) is a guardrail.
- **Guardrails.** ADDA7 alone cannot gate active days (−1 %) or bet (−3 %) as non-inferiority guardrails. Both are "monitored, not gated" (R6).
- **CUPED** roughly halves the variance of active days, rounds and bet (factor 0.51–0.58), so turn it on. It barely helps realized GGR (0.91), which is luck-dominated, as the spec says.
