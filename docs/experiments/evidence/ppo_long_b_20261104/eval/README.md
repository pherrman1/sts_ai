# LONG_B evaluation campaign (frozen 2026-11-05 after SERVE_DONE)

Plays LONG_B's checkpoints net-0070/0120/0170/0220 against heart1 on G1's 2,048 seeds (../PREREG.md, "Evaluation"),
with G1's runner, flags and analysis rules. GH is reused from G1 after a 32-seed sentinel replay
(`sentinel_expected.csv`: G1's GH Heart kill, final floor and decisions= for seeds 111520000-111520031, from G1's
unit tars).

Freeze (after SERVE_DONE): copy the four nets from the PC (~/ppo-longb/LONG_B/net-NNNN.bin, sha256 = loop.json's
next_sha256 of updates 70/120/170/220) to /mnt/project-files/ppo-long-b/nets/, fill the @SHA…@ placeholders in
run_unit.sh (16-hex prefixes) and campaign.manifest (full sha256), set workers, delta review, then launch.
The gate's cap is min(2,048, analysed seeds): with dropped seeds and G1's fixed cap 2,048 the gate would stay
PARTIAL (sprt_gate needs cap rows; G1 had no drops, so §752 is unaffected).
`python3 analyze.py --self-test` covers drops, an abort and a sentinel mismatch (CONTROL_INVALID).
Cost: 4 × 2,048 + 32 games × ~25 s ≈ 57 core-h.

Frozen 2026-11-05 ~18:45 CET: nets from the PC via store ref ppo-xfer/longb-nets (sha checked against the PC files
and loop.json), 40 workers (Philipp 18:38 CET "go eval 40 workers"), engine binary 78849fcf (code_commit bc33e470,
PREREG amendment 2026-11-05; the sentinel already reproduced G1's 32 GH games on it).
