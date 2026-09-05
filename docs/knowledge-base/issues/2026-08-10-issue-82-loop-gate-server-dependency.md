# Issue 82: Value/policy gates needlessly depend on server startup

- **Status:** closed (2026-08-10, `selfplay/loop.sh::needs_server`; native-OOC gate batches no longer start v_server; see decision-log `2026-08-10-issue-82-fix.md`)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `selfplay/loop.sh`

## Symptom

Value and policy gate batches call `start_server` even though those arms are
native-OOC (`STS_NATIVE_OOC=1` in the meta arm). A server failure fails
native arms unnecessarily.

## Evidence

- `selfplay/loop.sh`: value/policy gate blocks call `start_server`.
- Meta arm sets `STS_NATIVE_OOC=1` per AGENTS.md.

## Candidate fix directions

Skip `start_server` for native-OOC gate evaluations, or make the server
dependency conditional.

## Relevant code

- `selfplay/loop.sh`
