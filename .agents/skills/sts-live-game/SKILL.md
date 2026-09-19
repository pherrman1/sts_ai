---
name: sts-live-game
description: Control and verify a live Slay the Spire run through the configured slay_the_spire MCP server, including real-game smoke tests and sts-model-inspector CTM/Silver observations. Do not activate for simulator-only work or ordinary code changes without live-game interaction.
---

# Live Slay the Spire workflow

Use this skill when the task involves playing or navigating the real game,
reproducing a live combat/game state, testing `sts-model-inspector`, checking
CTM/Silver output in the real game, or performing a real-game smoke test.

## Control boundary

- Check that the `slay_the_spire` MCP tools are available before attempting a
  live run.
- If they are unavailable, diagnose MCPTheSpire/game availability and stop
  with the concrete blocker. Do not fall back to mouse or native GUI
  automation for game control.
- Use MCPTheSpire for all game control. The inspector is read-only and must not
  be given control responsibilities.
- Call `get_screen_state` before acting. Use `get_available_commands` when the
  current screen or legal action is unclear.
- Start, continue, or abandon runs through the MCP tools as appropriate.

## Inspector observation contract

For inspector/model tasks, read:

```text
~/.cache/sts-model-inspector/latest.json
```

Treat the file as an asynchronous snapshot, not as a command channel. Before
trusting `response.advisor`:

1. Confirm the file is present and valid JSON.
2. Confirm `response.ready == true`.
3. Confirm the response identity matches the observation identity:
   `session`, `sequence`, and `observationHash`. When present, the embedded
   advisor object's identity must match them as well.
4. Compare the observation with the current MCP-visible game state before
   making a correctness claim.

If the game advances, wait for a new observation and re-check all identities.
Never carry a selected action, ranking, forecast, or evaluator status from a
previous sequence into the current state. A later-turn evaluator may be
explicitly `UNSUPPORTED`; that is not permission to reuse an earlier result.

## Recommended smoke-test loop

1. Establish the MCP/game state with `get_screen_state`.
2. Start or continue the requested deterministic run, resolving menus and
   rewards through MCP choices.
3. At the target combat, capture MCP state and the latest JSON observation
   before acting.
4. Wait for a matching ready advisor response when the task requires CTM or
   Silver. Record the evaluator status, selected action, rankings, and the
   matching identity.
5. Perform the requested MCP action, then verify that sequence/hash advance and
   that old advisor data is not presented as current.
6. Re-read MCP state and latest JSON after the transition. Report exact
   agreements and any unsupported evaluator scope.

For integration correctness, distinguish a matching live observation from a
merely plausible game state. If the file is missing, malformed, stale, or
identity-mismatched, report that result as not verified and do not infer the
advisor's current recommendation.
