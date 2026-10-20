# AZ loop generation 0 data (never merge)

32 worker tars from campaign `docs/experiments/evidence/az_gen0_20261019`. RUN_COMMIT 76a31cd8, main 0abc831a,
binary decd91ea. 1,664 paired A20 seeds, 111140712-111142375, all verified with verify_campaign.py.
Ledger §TBD (PR #730).

Each tar holds out/<seed>/:
- on-SEED.jsonl.gz: heartoutcomegen policy rows. Gumbel targets go here; never use the `value` field as a target.
- on-SEED.ctm.jsonl.gz: real-combat CTM rows.
- off-SEED.*: search-off bestbench arm.

Train value heads with tools/heart1/distill.py --extra-inputs, Wing Boots flag 1, STS_ACTIVE_POWER_FEATURES=1.
