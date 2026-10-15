# Frozen learned-prior root replay screen

## Question and boundary

Does the frozen `SilverPriorNetV1` T2 prior improve low-budget Silver root
search over uniform PUCT and ordinary root UCT, with an L-target oracle prior
as a diagnostic? This is a development mechanism screen. VALIDATION data was
already used to select T2, so this does not establish fresh generalization,
gameplay quality, or deployment readiness.

No model was retrained, no temperature was changed, and no other checkpoint was
evaluated. Preparation opened only the 64 preselected VALIDATION L shards.
Replay completed and was sealed before judging opened the corresponding 64
VALIDATION J raw records. No LOCKED_TEST root, label, count, or raw artifact was
used. The learned prior is `softmax(logits)` directly; the oracle is
`softmax(L values / 1.179975000005129)`.

## Frozen inputs and run

- Baseline: `293c0704f0921688a6dc7066800b3bfcb1801bc5`.
- Checkpoint: `SilverPriorNetV1`, arm T2, initialization seed `20260922`,
  target temperature `1.179975000005129`.
- Checkpoint SHA-256:
  `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`.
- Corpus release/binding/selection/vocabulary SHA-256 values are pinned in
  [config.json](config.json).
- Population: 64 preselected VALIDATION-J roots and 64 unique source seeds;
  no replacements.
- Four arms: ordinary UCT; uniform PUCT; learned-prior PUCT; L-target-oracle
  PUCT.
- Each arm used native Silver action order, a fresh tree, 32 simulations/root,
  and four replicates/root. The existing root PUCT constant is 2.5; internal
  nodes, chance handling, rollouts, and evaluator stayed unchanged.
- Each `(root, replicate)` reused the same deterministic search seed in all
  four arms. The completed replay contains exactly 1,024 rows.
- Search seeds were checked against every L teacher identity during replay and
  every J teacher identity during judging; there were no collisions.
- The analyzer averaged replicates within each root/arm and used 10,000 paired
  bootstrap replicates over the 64 source seeds. Runtime is diagnostic only.

## Result

Classification: **`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`**.

| Arm | Mean J regret | Median J regret | J-best selection | Mean replay time |
| --- | ---: | ---: | ---: | ---: |
| `A_UCT` | 1.32065 | 0.52223 | 50.78% | 1,327.9 µs |
| `U_UNIFORM` | 1.41371 | 0.77052 | 49.22% | 1,307.1 µs |
| `M_LEARNED` | 1.37981 | 0.71951 | 48.44% | 1,304.5 µs |
| `O_ORACLE_L` | 1.14595 | 0.44524 | 51.95% | 1,290.5 µs |

Paired regret contrasts (negative favors the left arm):

- `M_LEARNED - U_UNIFORM`: `-0.03390`, 95% CI `[-0.11794, 0.03651]`;
  improved/worsened/tied roots `7/4/53`.
- `M_LEARNED - A_UCT`: `+0.05916`, 95% CI `[-0.28676, 0.37000]`;
  improved/worsened/tied roots `17/19/28`.
- `O_ORACLE_L - U_UNIFORM`: `-0.26776`, 95% CI `[-0.56135, -0.07144]`;
  improved/worsened/tied roots `17/2/45`.

The oracle interval confirms usable root-PUCT headroom on these roots. The
learned prior does not pass the learned-versus-uniform criterion and does not
beat ordinary UCT. Stop the native-inference deployment line here; do not port
the network based on this screen. No live Silver behavior, default search, or
gameplay was changed.

## Evidence and hashes

- [config.json](config.json): frozen run contract and input provenance.
- [prior-summary.json](prior-summary.json): preparation-only prior diagnostics.
- [replay-analysis.json](replay-analysis.json): full arm, contrast, and
  per-root analysis.
- `prepared/roots.jsonl` SHA-256:
  `c9b26024b92b4a44136e0b365940b818a52accedfe030adbedbe50b0bbcec111`.
- `prepared/priors.jsonl` SHA-256:
  `67ad785b6160e2264884ce4c142d0b4f3c701d9ab76651cad7e272566db8899d`.
- `replay.jsonl` SHA-256:
  `1f55730f0b04a67a463852cae6ddfe37eadaa0918064cb586dc9b840302934fa`.
- Replay executable SHA-256:
  `ecabfb8e470927616e0576923ea4aaf99e87240e147b9d160e947cd576c09d64`.
- `prior-summary.json` SHA-256:
  `7515ac78c476ba5dcab86591f9ee77502193efb45264b61eb25acb4abd51f210`.
- `replay-analysis.json` SHA-256:
  `acd0be299057cb93786329a5a54194704e0fe78a36701a00e64737b6628334b8`.

Implementation source hashes and exact commands are recorded in [config.json](config.json).
