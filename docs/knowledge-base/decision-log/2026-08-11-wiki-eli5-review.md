# Wiki ELI5 review

- **Date:** 2026-08-11
- **Decision:** Keep `wiki/` as a game-first, math-light explanation and
  explicitly distinguish the default executable from the recommended fair-play
  research configuration.
- **Rationale:** The prior pages described Searcher3 and the strategic neural
  network as if they were always active. Current baseline documentation says
  Searcher2 and heuristic out-of-combat policy are the executable defaults;
  Searcher3 and the strategic gate stack are opt-in. The wiki should teach the
  game-facing idea first and label measurements by configuration rather than
  presenting a single universal AI behavior.
- **Alternatives considered:** Rewrite the wiki as a technical reference. Not
  chosen because `docs/knowledge-base/` already owns that role; the wiki's
  audience is someone who knows *Slay the Spire* but not the math.
- **Evidence:** `wiki/index.md`, `wiki/how-combat-works.md`,
  `wiki/run-decisions.md`, and `wiki/putting-it-together.md` now explain the
  player-facing mental model and opt-in boundaries. The configuration and
  measurements are checked against
  `docs/knowledge-base/evaluation/current-baselines.md` and
  `docs/knowledge-base/research/combat-search/searcher3.md`.
- **Status:** Complete; future benchmark changes should update the wiki only
  when the current-baselines page supports the new wording.
