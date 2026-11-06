# Game lists

Per-brand and per-player game lists for the casino sites, and how we judge them by what players play next.

## Language

### Business

**Brand**:
One casino site with its own players and catalogue.
_Avoid_: account, site, operator

**Player**:
A person playing on one brand (the same person on two brands is two players).
_Avoid_: member, user, customer

**Cluster**:
A group of brands that share one source database and are built and judged together.
_Avoid_: shard, server

**Market**:
The country a cluster serves, which sets its local day.
_Avoid_: region

### Site

**Lobby tab**:
A game category the lobby shows as its own tab (slots, live, arcade, fishing, crash, …); each game belongs to one.
_Avoid_: category page, vertical

**Surface**:
A place on the site where a player can open a game, such as the main list, last played, search or a promo banner.
_Avoid_: placement, widget

**Popular list**:
The brand-wide game order the site computes from recent player counts and bets, with manual pins and exclusions; today's control.
_Avoid_: 30/70 formula, live ranking, auto-ranked

### Lists

**Personal list**:
The 10 games ML picks for one player, continue slots first and new games after.
_Avoid_: hybrid, recs, for-you list

**Continue slots**:
The first 3 to 5 positions of a personal list, holding the player's most recently played games.
_Avoid_: your games, R block, recent block

**New game**:
A game the player has not played in the 60 days before the as-of date.
_Avoid_: unplayed game, new release

**Adopted game**:
A new game the player plays on at least two different local days within a week.
_Avoid_: hit, conversion

**Lapsed game**:
A new game the player had played before the 60 days that precede the as-of date.
_Avoid_: old favourite, returning game

### Evaluation

**HR@10**:
The share of scored players who play at least one of a list's first 10 games in the week after the as-of date.
_Avoid_: hit rate, accuracy

**New-game HR**:
The share of scored players who play at least one new game among a list's first 10 in that week.
_Avoid_: discovery rate

**Day-one HR@10**:
The share of cold players who, on their first day of play in the test week, play at least one of the first 10 games of the list they would see.
_Avoid_: cold HR, first-session HR

**Miss**:
A scored player who plays none of a list's first 10 games in the week after the as-of date.
_Avoid_: failure, zero hit

**Scored player**:
A player who had a personal list on the as-of date and played in the following week.
_Avoid_: warm player, test player

**Cold player**:
A player who plays in the week after the as-of date without having played in the 30 days before it, and so has no personal list.
_Avoid_: new player

**Newcomer**:
A cold player with no earlier play in our data.
_Avoid_: new registrant, new depositor

**Returning player**:
A cold player who played before, but not in the 30 days before the as-of date.
_Avoid_: lapsed, churned

**Snapshot**:
A frozen copy of every list, and of the plays behind them, for one cluster and one as-of date.
_Avoid_: dump, backup

**As-of date**:
The last market day of data a list is built from; the week after it is the test week.
_Avoid_: asof, cutoff, build date
