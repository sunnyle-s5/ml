# DRAFT · Personal game list: impression event + A/B test

Status: draft for Yann / Product / FE, sunny, 4 Nov 2026. Nothing has been built or changed.

## What exists today (PostHog, checked 4 Nov)

- `evt:home_game_list_shown` is a **page-speed event**: `listRenderedMs`, `listShownMs`, `listApiMs`, … plus
  `accountId`, `brand`, `category`, `authStatus`. It has **no game ids, no positions, and nothing saying which list was shown**.
  So it can't tell us what a player saw.
- `act:game_open_triggered` already carries `gameId`, `gamePosition`, `gameRank`, `openSource`
  (`main_list`, `last_played`, `provider`, `surprise_me`, `search`, `promo_banner`), `openSourceCategory`, `accountId`.
  Clicks are attributed to a surface. They are not attributed to a list version.
- Reminder: `accountId` in PostHog is the **brand**, not the player. The player is the person / `$user_id`.

So the onboarding note's "needs evt:game_list_shown" is right. The fix is small: add list identity to the
existing events instead of adding a new pipeline.

## 1 · Impression: what the FE sends once per render of a game list

Either extend `evt:home_game_list_shown` or add `evt:game_list_shown` with:

| property | example | why |
|---|---|---|
| `listSurface` | `main_list`, `for_you` | same values as `openSource`, so clicks join to impressions |
| `listId` | `for_you:2026-11-05:phk1` | which built list (model + build date + cluster) |
| `listVariant` | `control` / `personal` | the A/B arm actually served (not only the flag value) |
| `gameIds` | `["…","…",…]` (top 10, in order) | needed for HR@10 on what was *shown*, not what we built |
| `listSize` | `10` | |
| `fallbackReason` | `null`, `no_history`, `api_timeout` | players who should have had a personal list but got the brand list |

Keep the existing timing properties. The event should fire only when the list is actually on screen
(`wasHidden = false`), like today.

## 2 · Click: add two properties to `act:game_open_triggered`

`listId` and `listVariant` (same values as the impression). `gamePosition` already exists.

## 3 · A/B test

- **Unit:** player (person), not brand. 50/50 inside each brand, sticky per player (PostHog feature flag).
- **Arms:** control = today's brand Popular list. Treatment = "hybrid (recent continue + ranker new)", top 10, and players
  without history fall back to the brand list (flagged with `fallbackReason = no_history`).
- **Surface:** one surface only. Options: the home `main_list`, or a new "For you" row. Product decides. A new row
  doesn't take away a list players already rely on.
- **Primary metric:** play-through HR@10 = share of exposed players who open ≥1 game from the list's top 10 within 7 days
  (`act:game_open_triggered` with matching `listId`). Same definition as the offline HR@10, so we can compare.
- **Secondary:** new-game HR@10 (opened a game not played in the 60 days before exposure), rounds and bet per exposed player
  (from the replica pulls, joined by player id), and the guardrail: total game opens per player don't drop.
- **Sizing:** offline gap on warm players is about +20 to +30 pt HR@10 (default 86–93 % vs live 58–78 %). Even if the online gap
  is a tenth of that, one week on one large cluster (phk1 ~158k scored players a week) is far more than enough. Start with
  one cluster per market, 1 week, then widen.
- **Serving:** lists are already built daily at 04:30 +07 into `recs_<cluster>.duckdb`. The missing piece is an API or file
  the FE can read per player (S3 per brand + player → top 10). Same blocker family as the PostHog S3 read key (Harvey).

## Open questions for Product / FE

1. Which surface: `main_list`, or a new "For you" row?
2. Can the FE read a per-player list (API vs a static file per brand)?
3. Who owns the feature flag, and is 50/50 per brand acceptable?
