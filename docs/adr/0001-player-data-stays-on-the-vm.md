---
status: accepted
---

# Player data stays on the VM; catalogue data reaches an external LLM only with an explicit OK

Player data (ids, plays, rounds, bets, wins, histories, lists) never leaves the ML VM, so any LLM or embedding model that
sees it runs locally from open weights. Public catalogue content (game names, providers, provider game codes, thumbnail
URLs) may be sent to an external LLM/VLM API, but only with sunny's explicit OK for each run (AGENTS.md §1 rule 6).
Decided 6 Nov 2026 while choosing experiments from Netflix and Shopify research (notes/2026-11-06-netflix-shopify-recsys.md).

## Considered Options

- Local models only: tagging thousands of thumbnails with a good vision-language model on the 8-core CPU VM is expected to
  be too slow.
- No LLM components at all (the 5 Nov v3 review's stance): it would also block the catalogue-only steps of the re-opened
  cold-start experiment, which touch no player data.
