# Pre-registration: Silver rollout root table vs the ADR-0040 card table at 10k simulations (A20, fight level)

Status: authorized by Philipp (2026-10-17 19:59Z, thread "Distilled playout card picker": "can you compare on 10k
simulations?"; 20:03Z decision card: "8 workers" for 128 seeds). Launch waits for an independent review PASS.
Ledger entry §521.

## Question

§519 found the per-root table descriptively better at 2,500 simulations (+2.69 [+0.61, +4.80], not pre-registered)
but not CPU-matched against greedy at 2,650. Does the root table help at the production budget of 10k simulations,
at equal CPU?

## Intervention and design

Identical to §519 ([PREREG](../silver_rollout_root_table_20261017/PREREG.md); option `STS_SILVER_ROLLOUT_ROOT_TABLE`,
gen-6 E `ca9bd7f2…` as table model and tree prior, student C `eff2f74f…` source runs, keys flag off, harness, score,
pairing, bootstrap and exclusions unchanged; `run.sh`, `env.sh`, `analyze.py` here are copies with only the budgets,
seeds and paths changed). Only `STS_CTMSILVER_SWEEP_SIMS=10000,10700` differs. Arms: `greedy10000`,
`roottable10000`, `greedy10700`, `roottable10700`, R = 2.

- Seeds: sources **111190500–111190627** (128); reviewer smokes 111190700–111190799. No author smoke seeds.
- Size: 8 cloud workers (`worker.sh`, `BRIEF-worker.md`), 16 sources each on 4 cores (4 shards of 4). Estimated
  about 26 core-hours. Uploads to `/mnt/project-files/silver-rollout-root-table-10k/wWW.tar`.
- Code commit `42e54fac` (main with #612 merged; `CODE` in `run.sh`/`worker.sh`), binary sha256 `bb117ec2…`
  (`BINARY_SHA256`, linux-gcc-release).

## Outcome, analysis, decision rule

- **Primary (CPU-matched):** `roottable10000 − greedy10700` fight score. §519 measured the root table at 1.066x CPU
  per fight at equal simulations (5.1% per simulation plus 1.4% more decisions per fight); the table build is a per-
  root cost and shrinks relative to 10k searches, so greedy gets 7% more simulations.
  - lower bound > 0 → `ROOTTABLE_HELPS`: next step is an A20 whole-run test with the student C out-of-combat stack
    (separate authorization).
  - upper bound < 0 → `ROOTTABLE_HURTS`: stop.
  - otherwise `NOT_SHOWN`: stop; the option stays research-only and off.
- CPU match as §519: the label stands only if the point estimate of the `roottable10000` / `greedy10700` CPU-per-fight
  ratio is ≤ 1.00; otherwise `NOT_CPU_MATCHED` and no promotion.
- Descriptive: CPU ratios, `roottable10000 − greedy10000`, `roottable10700 − greedy10700`, `greedy10700 −
  greedy10000`, per room class, Act-4 subset, win rate, HP lost, rollout length.

## Known limitations

- As §519 (greedy student C sources, keys collected by student C despite the flag, prior trained on A0 hand cards).
- Power: §519's CI half-width was about 2 fight-score points on 1,426 fights; §476 found prior and budget effects
  shrink at 10k, so a smaller true effect may stay NOT_SHOWN.
