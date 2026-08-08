# 2026-08-08 — Live Pi observability for the AI cycle and interactive subagents

Date: 2026-08-08
Session/task: Add live observability to both Pi surfaces without touching
agent prompts, model routing, retry policy, verification policy, escalation
behavior, seed limits, or final-response parsing: (1) interactive subagent
live activity in `.pi/extensions/subagent/index.ts`, and (2) concise
lifecycle status streaming in `tools/ai_cycle.py::PiBackend`.

## Decision

- `.pi/extensions/subagent/index.ts` is now an **STS-local fork** of Pi's
  reference subagent extension, based on upstream commit
  `c185d412382581860a489b4959737bad1d119492` (byte-identical at fork time;
  the base commit and the local changes are documented in the `STS-LOCAL
  FORK` header comment; `agents.ts` stays upstream). `PROTECTED_WORKFLOW_PATHS`
  already covered the file, so the implementer restore path is unchanged.
- The fork adds transient `LiveActivity` state per subagent run (turn count,
  waiting/thinking/responding/running-a-tool status, current tool + concise
  args, up to 5 recent completed tool calls, usage-so-far, model) driven by
  Pi's JSON lifecycle events (`turn_start`, `message_update`,
  `tool_execution_start/end`, `agent_end`). The collapsed renderer shows it
  while an agent runs; the expanded renderer additionally exposes it. No
  reasoning/thinking or partial text is ever rendered or stored — a thinking
  delta only moves the status label.
- `message_update`-driven UI refreshes are throttled to ~150 ms
  (`LIVE_THROTTLE_MS`); tool start/end and `message_end` updates are
  immediate. `message_end` remains the authoritative source for completed
  messages, usage, stop reason, and final output; the completed-result
  renderers are byte-unchanged.
- `tools/ai_cycle.py::PiBackend` now prints a model-bearing banner
  (`====== ARCHITECT · DeepSeek V4 Pro ======` via new
  `PI_MODEL_DISPLAY_NAME`, display-only) and streams lifecycle status lines
  (`[role] model thinking...`, `[role] tool: read <path>:<range>`, `[role]
  tool done`, `[role] model responding...`) from
  `pi_live_status_line`/`pi_format_tool_call`. Thinking/text deltas never
  print content; the thinking/responding transition prints once per
  response; tool start/end print unconditionally (parallel tool batches all
  surface). The full raw JSONL stream still goes verbatim to the session
  log, so human terminal output is concise while forensic logs stay
  complete.
- `scripts/install_pi_subagent.sh` now fetches to a temp dir and **refuses**
  to overwrite a divergent local `index.ts` (the fork) unless
  `STS_FORCE_PI_SUBAGENT=1`; `scripts/check_pi_setup.sh` detects the
  `STS-LOCAL FORK` marker and reports the fork base instead of claiming
  byte-identity.

## Rationale

- Observability-only seam: both changes read the existing Pi JSON event
  protocol and add rendering/printing; no orchestration semantics moved and
  no prompt/routing/retry/escalation/seed logic changed. The Pi fork marker
  makes the divergence explicit and machine-checkable so a future vendor
  refresh cannot silently downgrade or misreport the extension.
- Lifecycle-only terminal output: the status line printer gates on state
  transitions, so token-frequency deltas collapse to one line per response
  (matches the long-standing "human output concise, session logs complete"
  convention for OpenCode transcripts).
- Throttle at the emit point (150 ms) rather than sampling deltas: simplest
  correct approach for a token-frequency stream, and tool/`message_end`
  events bypass it naturally because they call the unthrottled emitter.

## Alternatives considered

- Patch only the terminal banner (`→ tool` lines) and skip the subagent
  extension — rejected: the task explicitly requires interactive subagent
  observability, and the vendored extension is the interactive surface.
- Maintain a separate local copy of the whole extension directory —
  rejected: a single forked `index.ts` with a documented base commit is
  easier to re-merge upstream changes into; `agents.ts` stays upstream.
- Print a line per `message_update` delta — rejected: would spam the
  terminal at token frequency; the state-gated transition printer emits at
  most one line per response and per tool call.

## Evidence

- `.pi/extensions/subagent/index.ts`: `LiveActivity`, `CompletedToolCall`,
  `renderLiveActivity`, `isRunningResult`, `LIVE_THROTTLE_MS`,
  `RECENT_TOOL_CAP`, `STS-LOCAL FORK` header.
- `tools/ai_cycle.py`: `pi_live_status_line`, `pi_format_tool_call`,
  `PI_MODEL_DISPLAY_NAME`, PiBackend banner + streaming loop.
- `tools/test_ai_cycle.py`: `PiLiveStreamingTests` (11 tests: lifecycle
  status, tool start-before-done order, success/failed tool end,
  once-per-response transitions, malformed lines interleaved with live
  events, banner display names, tool-line formatting unit cases, bash
  truncation, unknown-tool truncation); full suite: 84 tests pass with
  `python3 -m unittest tools.test_ai_cycle` (fake `subprocess.Popen`, no
  API calls, no seed sweeps).
- `scripts/install_pi_subagent.sh`, `scripts/check_pi_setup.sh`; Pi JSON
  event shapes verified against the pinned Pi source at
  `/home/philippherrmann/Documents/pi-source` (`types.ts`, `agent-loop.ts`,
  `json-event.ts`, `print-mode.ts`).

## Status and follow-up

- Implemented; tests green; `git diff --check` clean. Observability only —
  the same live-verification and default-flip follow-ups from
  `2026-08-08-pi-backend-integration.md` still apply.
- Open: upstream changes to the reference subagent extension must be
  re-merged into the fork by hand (the install script now refuses silent
  overwrites; the decision log entry and the `STS-LOCAL FORK` header record
  the base commit for the re-merge).
