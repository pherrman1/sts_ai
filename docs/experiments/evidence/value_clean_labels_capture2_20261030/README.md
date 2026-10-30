# Clean value labels, capture 2 (2026-10-30)

Philipp chose "Mehr Spiele capturen (~1.000)" (card, 16:52Z 10-30) and set 16 workers (typed, 16:53Z).

Why: stage 5 (../value_clean_labels_stage4_20261030) failed its gate with both feature sets. The labels come from
only 288 captured games (~200 in TRAIN); with the full encoder the per-act GBMs overfit to individual games, and the
level calibration used real states of games the model had seen. TEST of stage 4 is read twice and burned.

What: the remaining 992 run-1 base seeds (111384032-111385023, all USED by run 1; no new seeds) replayed once with
the act-end record capture, exactly as stage 4 (run_unit.sh verbatim, K = 0, same code 6af96563, binary 44188a46).
Play is unchanged by the capture (observer only), so every replay reproduces its run-1 base game and outcome.

Cost: stage 4 measured ~0.75 lane-h per unit (256 units, 12:05-13:15Z on 176 lanes) -> ~740 lane-h,
~11-12 h on 16 workers x 4 lanes. Share ~4 GB. (The card's "350 lane-h / 2 h on 44" was my underestimate.)

Analysis (stage 5b) is written and committed before this data is read: fresh TEST = capture-2 seeds with seed % 4 == 3;
TRAIN/VALIDATION = the other capture-2 seeds plus the stage-4 and pilot games (their TEST seeds excluded from the
gate); level calibration only on real run-1 states of games that are not used to fit that act's model.
