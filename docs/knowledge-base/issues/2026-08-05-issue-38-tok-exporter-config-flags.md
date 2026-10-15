# Issue 38: export_strategic_tok ignores non-default checkpoint config flags

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `export_strategic_tok.py`

## Symptom

`export_strategic_tok.py` hardcodes the default topology (DIMS, W_ORDER, ent
input 37) and only reads `rung` from the checkpoint. Trainers can produce
checkpoints with `STRAT_TOK_TRANSFORMER=1`, `STRAT_TOK_QUANTILES=1` (per-screen
11-quantile heads), or `STRAT_TOK_CROSS=1` (ent input 37→69); exporting such a
checkpoint writes a misaligned/garbage native layout without error. The
checkpoint didn't even save these flags.

## Evidence

- `export_strategic_tok.py:21-38` (DIMS/W_ORDER), `:191-193` (only rung read).
- `train_strategic_tok.py:50-55,408` (flags), `:664-667` (flags not saved).
- `strategic_tok_net.py:66` (`nn.Linear(37 + 32 * ncross, ...)`).

## Why it matters

Silent wrong export for any non-default config; the parity check would still
pass because it rebuilds `Net()` with default flags.

## Candidate fix direction

Save `transformer`/`nquants`/`ncross`/`nprobes` in the checkpoint; exporter
reads them and fails loudly on any non-default config it cannot lay out.

## Relevant code

- `export_strategic_tok.py::main`
- `train_strategic_tok.py` (torch.save block)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: trainer saves the flags;
exporter `raise SystemExit`s with a clear message on non-default configs.
No experiment used a non-default config → nothing to rerun.
