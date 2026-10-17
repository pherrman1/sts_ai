# Current A0 CTM children: Ritual VALIDATION diagnostic

This is a bounded investigation of #369's A0 Writhing Mass + Ritual Dagger
gap. It measures preserved VALIDATION rows with the actual deployed model
payloads. It performs no fitting, collection, TEST scoring, capability edit,
native export or deployment. The A0 support refusal remains in force.

## Question and interpretation

Does the ordinary child of the current A0 stack assign the observed Ritual
increment substantially different probability after upstream HP/potion
sampling than under the observed teacher conditions? Competing explanations
include upstream exposure mismatch, conditional event-head error and sparse
intersection coverage. The diagnostic can distinguish a conditional score
from a composed score; it cannot establish gameplay quality or qualification.

The baseline binds the current fast artifact
`combat_transition_deepsets_pathb_r2_lizard.native` SHA-256
`c6d56bbc959f4d5de8fe1dd57f58a922112cd8323bcbac9711e0aecda93f5a3c`
and standard fallback
`combat_transition_near_full_escape_pathb_r2.native` SHA-256
`b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf`.
Their Ritual heads differ: fast uses `06709aed…`; standard uses `95e07d97…`.
The older sparse head `f8358328…` is only a warm start. Its falling 12-epoch
loss does not justify extending training of the actual deployed heads.

Tensor custody is recorded in
[`custody.json`](custody.json), SHA-256
`f5959d359a761f9dfb3c0eaac563e37b582b50067f37c5bc3052b7cb47403801`.
The reviewed tool pins this receipt as well as both whole artifact hashes.

Initial held Entropic Brew selects standard; every other initial inventory
selects fast, matching native dispatch. Generated Brew never changes that
initial choice. Each artifact supplies its own normalization, four encoders,
maxHP head, escape-conditioned HP head, escape probability, potion trajectory
decoder and Ritual head. Historical cached encoder vectors and trace
posterior weights are not reused. Public-input/native parity checks of the
artifact loader must pass before this experiment runs.

This first diagnostic omits composed active-Lizard correction. Explicitly
exclude and count public active Tail (data 1) without Mark of the Bloom;
retain the Mark of the Bloom boundary and apply the remaining ordinary
public input/domain checks. The intended Writhing/Ritual exclusion is lifted
only inside the offline research predicate. No runtime support changes.

## Data custody and isolation

The archive remains unchanged at
`/home/philippherrmann/Documents/sts/wt-ctm-retrain/build/ctm-retrain-a69f8862`.
Use its `prom` data bindings and `pins-12.json` SHA-256
`c5fc22b3592675bc3b34854d5da59f7755560394e009977d01d5e435a10465db`.
Pins12 identifies the historical preparation only; model tensors come directly
from the two current identity-pinned native artifacts.

| Input under `prom/` | SHA-256 |
|---|---|
| `full-union-downstream-v1/cache.npz` | `fe4aec50843c151a33e603190358636c9ad74d78948f520a0b58c9efe3c81fa0` |
| `full-union-downstream-v1/affected_rows.jsonl` | `4f6d6d5b06fa44534f51de8214dd740f48653f606a283d9ba7d9b76546e164fc` |
| `potion-trajectory-v2/cache.npz` | `1171a925195c61437e12988e1822fe39b792371c93e72329b1e88a7a699ab598` |

Metadata `ids/split/source` may be decoded for all rows to verify source
disjointness and index alignment. Outcome/public mechanism flags are decoded
for VALIDATION only, identifying **143 intersection victories from 68
sources** before public exclusions. All label fields for other rows are
streamed as raw NPY row bytes and discarded before any numerical decoding.
The JSONL index is its first field: inspect that ASCII prefix, then decode
only the selected 143 JSON records. Nonselected labels are never JSON-decoded.
Whole-file hashes read opaque bytes only for custody.

Only selected VALIDATION pre/post labels and public predictor inputs enter
the sanitized artifact. Do not invoke old `load`, `prepare`, `diagnose`,
`q.load`, `q.upstream`, `_load_prepared`, raw corpus readers, or TEST snapshots.
Do not read a TEST score array, retune on the old failed aggregate, or reassign
splits. Reconstruct selected observed potion generation bodies from their
saved label history; model inputs remain the public predictor input alone.

## Frozen estimator

Use exactly **32** upstream draws, NumPy seed **20260920**, with each selected
artifact's FP32 component arithmetic. Preserve complete native potion
trajectories, recursive Brew generation, generated potion effects and escape
conditions. Use existing native `ritual_posts`, `conditions`, Ritual scorer,
and `sample_potions_batch` semantics.

Teacher Ritual target mass is the exact weighted sum over compatible potion
traces at observed ending HP/maxHP and observed eligible escape. Rebuild the
compatibility DAG and recompute its posterior using that row's current
artifact potion decoder. Its old standard-model posterior cannot substitute
for the fast decoder. Include teacher target mass zero as explicit evidence.

For each ancestral draw, sample maxHP; sample the artifact escape bit when an
initial Smoke Bomb makes it eligible; sample ending HP from the corresponding
escape-conditioned head; sample the full conditioned potion trajectory;
then evaluate the observed Ritual increment's exact probability on that
draw's native candidate support. Absent targets contribute zero, with no
smoothing, clipping, dropping or renormalization. The composed probability
is the mean of the 32 target masses. Compute NLL after averaging probabilities,
then exposure gap = composed NLL − conditional teacher NLL.

Observed Brew-generated Smoke escapes without initial Smoke are an explicit
diagnostic subgroup because the deployed escape bit cannot represent them.
Report their row counts and zero masses separately; do not silently remove
them or normalize a zero posterior. The ordinary subgroup is reported
separately, with the historical source-group bootstrap (1,000 repetitions,
seed 20260917). Preserve per-row target masses and indices for inspection.

The fixed route iteration and reduced population change RNG consumption from
old E2. This is a newly frozen VALIDATION estimator, not bitwise historical
replay or an independent holdout. No checkpoint or hyperparameter is selected.

## Decision and completion boundaries

The output classification is exactly
`CURRENT_CHILD_RITUAL_VALIDATION_DIAGNOSTIC`; it has no PASS/qualification
verdict. Report conditional NLL, composed NLL, mean exposure gap and source
bootstrap interval when finite; report zero conditional/composed masses
explicitly. Extended-real results remain in row evidence, with JSON null plus
explicit zero counts rather than a fabricated finite score. Report artifact
routes and every public exclusion, and keep the active-Tail limitation clear.

Do not infer a fix from general Ritual improvements or this diagnostic alone.
A later intervention, ancestral qualification and native support promotion
need their own reviewed design/evidence. No automatic extension or training
follows the result.

## Review, freeze, resource limits and execution

Review implementation and scientific scope independently, then commit the
reviewed source. `identity` binds the clean SHA and all repository Python tools,
tests and this protocol. An independent review JSON has `verdict: PASS` and
the exact `identity` object. `freeze` verifies custody, writes a new sanitized
VALIDATION cache/records, and freezes hashes of all inputs and the review.
`run` rechecks them and consumes an exclusive `evaluation-started.json` latch
before any inference. A failure leaves the latch/evidence and is not retried
automatically. An implementation or runtime failure can be diagnosed and
repaired under the active task, with affected checks, independent review and
a new source/input freeze in a separate evidence directory. Preserve the
failed attempt; do not repeat a successful evaluation or extend its draws.

Budget: one execution, **300 seconds** of bounded inference, four CPU threads,
one GPU with a PyTorch allocator ceiling of **1,900,000,000 bytes**, and peak
RSS below **8,000,000,000 bytes**. No game seeds are driven. Hashing and safe
extraction happen before the inference clock. An external 330-second process
timeout is an additional guard; the internal alarm remains 300 seconds.

```sh
python3 tools/ctm_ritual_validation.py identity
python3 tools/ctm_ritual_validation.py freeze --out "$OUT" --review "$REVIEW"
timeout --signal=TERM 330s python3 tools/ctm_ritual_validation.py run --out "$OUT" --review "$REVIEW"
```

Preserve source/review/freeze, sanitized inputs, one-use latch, raw commands,
stdout/stderr/exit status, version/resource metadata, `row-evidence.npz` and
`result.json`. Do not overwrite existing evidence. Record the exact outcome
and its limited scope in the ledger and maintained current-research page.

Knowledge impact: safe development-data extraction and a scoped diagnosis of
the current model gap; no qualified model/default/capability change.
