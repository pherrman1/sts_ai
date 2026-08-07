# 2026-08-07 — DeepSeek-only agent models

Date: 2026-08-07
Session/task: Switch the workflow's review agents from OpenAI models to DeepSeek.

## Decision

- architect and reviewer (Luna role): `deepseek/deepseek-v4-pro` with `reasoningEffort: high`.
- reviewer_sol (Sol role): `deepseek/deepseek-reasoner` with no explicit reasoning effort, so it runs at its native full-reasoning mode.
- implementer: unchanged `deepseek/deepseek-v4-flash`.

## Rationale

`opencode/gpt-5.6-luna` and `opencode/gpt-5.6-sol` do not resolve in this
setup (`Model not found`, `opencode models` lists them only as
`openai/gpt-5.6-*`); the user decided to use DeepSeek for everything for now.

## Alternatives considered

- `openai/gpt-5.6-luna` + `openai/gpt-5.6-sol` — rejected by the user's choice to move to DeepSeek.
- `reasoningEffort: "max"` on reviewer_sol — rejected because opencode's valid effort values are `minimal|low|medium|high`; the reasoner model already provides max-strength reasoning natively.

## Evidence

- `opencode.json` + `architect`, `reviewer`, `reviewer_sol` agent configuration.
- `opencode models` + resolution check of the three model IDs.
- `opencode debug config` + merged configuration output.

## Status and follow-up

- Implemented. Session `.ai/20260807-211018` can resume `--continue-rejected` with the DeepSeek Sol adjudicator.

## Superseded (same day)

- reviewer_sol changed from `deepseek/deepseek-reasoner` to `deepseek/deepseek-v4-pro` with `reasoningEffort: max`.
- reviewer changed from `deepseek/deepseek-v4-pro` to `deepseek/deepseek-v4-flash` with `reasoningEffort: high`.
- implementer now sets `reasoningEffort: high` on the unchanged `deepseek/deepseek-v4-flash`.
- Final mapping: architect `deepseek-v4-pro` high; implementer `deepseek-v4-flash` high; cheap reviewer `deepseek-v4-flash` high; escalation reviewer (Sol) `deepseek-v4-pro` max. "Flash 0731" refers to the `deepseek-v4-flash` model itself, not a separate dated id.
