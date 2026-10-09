# Learned encoder Silver root prior (ledger §403)

- Rules: [PREREG.md](PREREG.md) (stage 1 committed at 1a0ac660 before
  training; stage 2 at 8b3bd752 before any 5x data existed).
- Code: `tools/silver_encoder_prior.py` (tokenizer, packed store, transformer,
  fit gate), `tools/silver_prior_v2.py` (v2 recipe; lean loader for 6x).
- Stage 1 (original corpus, 165,134 roots): `train-encoder.json`,
  `fit-encoder.json` (Gate 1 fail); exploratory learning curve
  `train-encoder-reg{0.33,0.67,1}.json`.
- Stage 2 (6x: original + 785,629 roots from
  `/mnt/project-files/silver-synthetic-prior/corpus5x-450376c8/`, 238 units):
  `train-encoder-6x.json`, `train-v2-6x.json`, `fit-encoder-6x.json`
  (Gate 1' fail). 242 training roots with > 128 tokens or > 64 actions were
  skipped (memory); evaluation covers every root.
- Exploratory replay (not a gate; Gate 2 did not run because Gate 1' failed):
  `weight-v2-6x.json` (v2-6x weight picked on validation roots at 1k = 400),
  `replay-6x-exploratory.json` (§400 test roots, 8,188 runs per arm, 0
  dropped; encoder arm at w = 400 without its own weight pick).
- Models: `/mnt/project-files/silver-synthetic-prior/encoder-20261008/`.
