# 2026-08-02 — Karpathy coding guidelines merged into AGENTS.md

Date: 2026-08-02
Session/task: Incorporate Andrej Karpathy's LLM-coding-guidelines
(`multica-ai/andrej-karpathy-skills`) into this workspace's agent contract.

## Decision

- Install the guidelines as always-on instructions in
  `sts_lightspeed/AGENTS.md` only; do not create an opencode skill file.
- Merge the four principles into existing sections rather than appending a new
  section:
  - Think Before Coding → "Modification workflow" step 3 and the end of
    "Prohibited assumptions";
  - Simplicity First + Surgical Changes → "Modification workflow" step 4 and
    "Definition of done";
  - Goal-Driven Execution → "Modification workflow" step 6 (reproducing test
    first; `step → verify` loops).
- Add the caution-over-speed tradeoff note at the end of "Definition of done".
- Scope: this workspace only; no global opencode config changes.

## Rationale

The repository's AGENTS.md already encoded parts of the principles (smallest
scoped change, success criterion before coding, intentional-only diffs,
"Do not invent rationale"), so a separate skill or appended section would
duplicate the contract. Skills in opencode are loaded on demand by description;
behavioral guidelines that should shape every session belong in the always-on
instructions. The upstream file is plain, model-agnostic markdown
(`CLAUDE.md`), so it transfers to opencode with deepseek without the
Claude Code plugin machinery.

## Alternatives considered

- Register `skills/karpathy-guidelines/SKILL.md` as an opencode skill
  (`.opencode/skills/`) — rejected: skills are trigger-based and would not
  reliably shape every session.
- Append the upstream content verbatim as a new AGENTS.md section — rejected:
  duplicated existing language and added no precision.
- Install globally (`~/.config/opencode/AGENTS.md`) — rejected: user wants
  this workspace only; the guidelines are also partially project-specific
  here.

## Evidence

- `sts_lightspeed/AGENTS.md` — pre-existing "Modification workflow",
  "Definition of done", "Prohibited assumptions".
- Upstream `CLAUDE.md` at `multica-ai/andrej-karpathy-skills` (MIT) — four
  principles and tradeoff note.
- `docs/knowledge-base/decision-log/README.md` — session-log convention this
  entry follows.

## Status and follow-up

- Implemented: AGENTS.md merged; "Last verified" bumped to 2026-08-02.
- Open: none. If the guidelines are later wanted in other projects, install
  globally via `~/.config/opencode/AGENTS.md`.
