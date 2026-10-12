# ADR-0029: Live OOC MCTS uses the public X2-B as its default win model

Date: 2026-10-12
Status: accepted

## Context

With `STS_OOC_MCTS=1`, the process win model `g_winNet` serves three uses:
- it values the native MCTS leaf, which rollout3 evaluates at the map after the third simulated combat;
- it scores rest and upgrade in the native fallback;
- it supplies `vStateWin`.

Until now that model was always B0 `models/v_win_trees.txt` unless
`STS_WIN_NET` named another file. B0 reads the hidden `nextEliteId` and
`nextFight0..2` fields (§371, §438), and it was trained in July 2026 on a much
weaker policy.

§444 exported a public X2-B, `models/candidates/v_win_x2b_public_trees.txt`.
It follows the X2-B recipe without the four hidden fields, and its held-out
NLL is 0.4236 vs 0.4226 for X2-B.

§449 compared the two models as `STS_WIN_NET` inside rollout3 `combo` on 128
fresh paired seeds, with `STS_OOC_PUBLIC_FUTURES=8` in both arms:
- wins: 114/128 for X2-B vs 111/128 for B0;
- difference: +2.3 pp [−5.5, +10.2], NOT_SHOWN;
- CPU: the same.

On 2026-10-12 Philipp chose to make the public X2-B the default for OOC MCTS
("yes use it as default for ooc mcts").

## Decision

- When `STS_WIN_NET` is unset and `STS_OOC_MCTS=1`, the native OOC loader
  takes `g_winNet` from `models/candidates/v_win_x2b_public_trees.txt`. It
  prints `[OOC MCTS default win model: <path>]`.
- When `STS_WIN_NET` is unset and OOC MCTS is off, nothing changes: B0 stays
  the win model for the default stack, generators, label bootstraps and every
  other mode. `models/v_win_trees.txt` itself is unchanged (#397).
- `STS_WIN_NET=1` restores B0 under OOC MCTS, and any explicit path still
  takes precedence.
- The floor model (`v_rich_trees.txt`) for card, shop and remove is
  unchanged.
- The live advisor (`one_combat_advisor`) is out of scope. It takes its
  win model from `STS_LIVE_OOC_WIN_MODEL` and does not change.
- OOC MCTS itself stays off by default (ADR-0027 and §384 still apply). No
  default leaf, prior or simulation count changes.

## Consequences

- An OOC MCTS run with `STS_WIN_NET` unset now plays like the §449 `x2bpub`
  arm. Earlier OOC MCTS results (§422–§450) were made with B0 and need
  `STS_WIN_NET=1` to reproduce.
- X2-B was trained on MAP rows only, so in the native fallback (about 2.5% of
  decisions under `combo`) its rest and upgrade values are off-distribution.
  This is an inference that has not been measured separately.
- The default `screengbm` leaf anchors on the original X2-B
  (`v_win_x2b_trees.txt`). It does not read `g_winNet` for its anchor and is
  unaffected.

## Evidence

Ledger §444 and §449, evidence packet
`docs/experiments/evidence/ooc_x2b_vwin_449_20261012/`, test
`tools/test_vwin_override.py`.
