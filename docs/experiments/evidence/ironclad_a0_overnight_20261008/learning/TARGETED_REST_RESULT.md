# One-state REST diagnostic

The fixed independent evaluation is **LOCAL_CONDITIONAL_INCONCLUSIVE**. Upgrading Offering won 23/32 sampled futures; the actual source action, REST, won 17/32. The paired gain was +0.1875, with the preregistered 10,000-resample paired 95% bootstrap interval [0.0, 0.375] (RNG 20261008). The lower bound equals zero, so this does not satisfy a strictly positive conditional signal criterion. There were eight Offering-only wins, two REST-only wins, fifteen shared wins, and seven shared losses. The two REST-only wins are observed counterexamples to a claim of sampled-future dominance.

The source was seed 610081015, Act 3 floor 44, native decision index 93, at 85/85 HP without Dream Catcher or Fusion Hammer. The strategy reviewer nominated Offering, Disarm, and Immolate upgrades using the public state before continuation outcomes were opened. The original action was known during that review; this was action-informed public-state review, not blinding to the chosen action. A zero-future replay matched all twelve comparable public packet fields and established native semantic keys. Its complete public-state identity was SHA256 `11a1ea6ea301c078ce522c00acd92b8f4cac9e39038d48677ea498117bc7f332`.

Selection and evaluation were separate. On selection k=0–15, REST won 10/16, Disarm 11/16, Immolate 11/16, and Offering 12/16. The highest selection mean selected Offering; exact ties would favor the actual baseline, then semantic key. The choice artifact was written and hashed before evaluation launched. Only independent k=16–47 entered the reported paired estimate. Selection and evaluation counts are not pooled.

Every evaluation branch passed the contract: 64/64 valid labels and complete post-action MAP joins; one valid source trajectory; exact preflight public-state, teacher, binary, action, and future-seed bindings; no recorded branch errors; output bytes and hashes intact. Startup logs confirmed public encounter mixture 8, Act-3 cutoff, and learned stopping. Evaluation used 18.317 source CPU seconds plus 360.56808 continuation CPU seconds and 379.24485 process-wall seconds. The 64 evaluation branches contained 281 fights. Selection previously used 16.2784 source plus 321.67519 branch CPU seconds and 338.27730 process-wall seconds. The preflight consumed 17.0424 wall seconds. No sample extension or policy change followed the result.

The experiment has one selected source decision, not 32 independent full runs. The interval concerns sampled futures conditional on that state and fixed sampler/teacher; it excludes source-selection uncertainty and uncertainty about the teacher. The preserved 631f teacher retains the optional Ruby Recall defect to reproduce the exact old discovery source. This result does not qualify a policy against the corrected reference, establish population Act-3 win-rate improvement, or justify deployment/training. It identifies a plausible action-ranking weakness for broader independent investigation while preserving an inconclusive statistical verdict.

## Reproduction and custody

The invocation receipts contain the exact guarded commands, controlled environment, input bindings, output paths, bytes, hashes, timestamps, and exit status. The fixed commands are also reconstructible through `run_targeted_rest.py --stage preflight|selection|evaluation` with the frozen protocol and stage-target hashes. The independently reviewed analyzers are `freeze_targeted_rest_selection.py` and `analyze_targeted_rest_evaluation.py`. They refuse to overwrite their result artifacts.

| Artifact | SHA256 |
|---|---|
| `strategy/targeted_rest_631f/protocol.json` | `8c703eeaca9bd35d1c69b2cd4bad4096732e0ad6fd86f883dcc42fc83c1ddcf7` |
| immutable `targeted-631f7f92/one_combat` | `0d78692026608575721d1e47bc78f4c1eed150d41c7a4b6edd5387c2e007ca48` |
| `targeted_rest_631f_selection_choice.json` | `c4f8f74597ca5c9b423a4ae40920ab76ca70cf2559965916bd0784712ee000a8` |
| `targeted_rest_631f_evaluation_target.json` | `9c97ebca79bf6f6fba111f7ecebcb8f3365df16bf4256294a3c9a186da9044c3` |
| raw `targeted_rest_631f/evaluation.receipt.json` | `ca75f616fd85d63720229e0f61f06a5d5d054d5169bec801061ca3c353981f46` |
| `targeted_rest_631f_evaluation_result.json` | `f075d65327dd180f1d99be639448a54c3a35873c194bdace93195ff85ad41fd7` |
| reviewed `run_targeted_rest.py` | `1058d955fc57e9b2deb9e7a5efcf2352e7901c7926e7f6ac9568ad616a2b68a9` |
| reviewed `analyze_targeted_rest_evaluation.py` | `87cb840ccd7b86e24ba6f08d6f15195c4e645a2b4b92e01826457e2e79d65408` |

The failed selection launcher hash typo is preserved separately in `targeted_rest_launcher_failure001.json`; it was rejected before any source/branch execution or output-prefix creation. No failed game attempt was discarded or relabeled.
