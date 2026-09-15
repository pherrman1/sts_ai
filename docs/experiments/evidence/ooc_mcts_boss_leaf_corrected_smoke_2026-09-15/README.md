# Corrected all-boss OOC MCTS leaf mechanism and paired N8 smoke

Classification: **`CORRECTED_MECHANISM_PASS_PAIRED_N8_SMOKE`**.

The checkpoint-path bug is fixed and the intended treatment is demonstrably
active. With the tracked V2 combat model, identical map leaf states at HP
20/40/60 produced boss values 0.00409/0.00647/0.01371 versus native `v_win`
0.15437/0.19850/0.24000. On an identical 64-simulation MCTS root, every root
action Q changed by 0.095--0.101. The selected action happened to remain the
same in this one mechanism fixture.

Fresh paired seeds 12003064--12003071 then used Ironclad A0, fair RNG, keys
off, Act-3 stop, exactly 512 OOC MCTS simulations, V4 priors, and exact10k
Silver real combat. Native won 6/8 and the corrected all-ten-boss leaf won
4/8, a descriptive -25 percentage-point paired delta. All eight terminal rows
and all eight non-timing trace rows differ. This is a mechanism-confirming
smoke, not a powered quality estimate and not evidence for changing defaults.

The treatment is also expensive: mean elapsed time was about 83 seconds/run
for native versus 2,218 seconds/run for all-boss evaluation. A conditionally
planned extension began after the N8 behavior-change gate; its native arm and
three boss rows completed before the user requested recording and merge. Those
files are retained under `interrupted-extension/` and are excluded from every
reported N8 statistic.

`plan.json` was written before gameplay collection. `mechanism.json` records
the pre-game mechanism gate, `analyze.py` validates exact N8 membership and
binds raw hashes, and `results.json` is the machine-readable result.
