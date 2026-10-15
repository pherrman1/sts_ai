# A20 Heart rollout-distillation pilot (2026-10-16)

Version3. Status: prospective; implementation/source/binary freeze and independent review required before generation.
Source baseline: main79404f1b, after separate Heart PR562 and Opus evidence PR561.

Hypothesis: a small public-input network can compress the expected three-combat
rollout leaf target while retaining within-parent decision ranking. A residual
network and ranking-aware loss may improve decisions more than scalar MSE.
The target remains a CTM/V4/X2-B surrogate, not an observed Heart-win probability.
No AlphaZero/self-play reinforcement-learning loop or joint prior/CTM tuning.

Inventory: §490 / merged PR561 provides 64-label targets and selected checkpoints,
with correlation0.645 at epoch20 versus X2-B0.596. Epoch selection used the
validation set; no untouched TEST or gameplay evidence exists. Its raw tars are
still unavailable locally. The frozen published X2-B-input CPU checkpoint is
an additional out-of-domain diagnostic baseline on the new TEST (in particular
its screen clamp maps BATTLE9 to SHOP8 and ignores the new extensions); it does not affect model
selection or change the primary X2-B comparison. §489 / merged PR560 provides 64 A20 keys-off Act3 source runs,
repeated sibling rollouts, and modest CPU value-net validation evidence. Its raw
tars remain in Claude cloud project storage and are unavailable locally; tracked
aggregate metrics cannot train a new student. The different keys/horizon also
precludes treating that cohort as A20 Heart data. §471 has only four early MAP
inputs. Existing screen-leaf tools and candidate-public-leaf-v1 capture are reused.
No historical TEST dataset will be opened or pooled. Recheck PR560 before training.

Version1 at7622669e failed its support canaries with zero cohort collection,
training or TEST opening. Preserved PROTOCOL-v1-invalid-canary.md and
canary-v1-result.json record that result. In particular, the126 rows marked
terminal_or_battle were UNDECIDED BATTLE boundaries, not exact terminal values.
Version2 repairs observation support rather than relaxing the80% complete-row
gate: capture-only extensions describe the CURRENT publicly visible encounter
at a pre-BattleContext boundary, and Match and Keep attempts/slot states. Unseen
board identities are masked; visible or remembered identities are retained.
No trained heart1 choice behavior changes. New canary seeds exclude both old
canaries; the64 cohort sources remain unused and fixed. This new representation
is reviewed/frozen before a new generation attempt.

Version2 passed both canaries (355/355 and678/678 rows, action parity), then
was explicitly stopped at the user's change of tree prior after11 completed
sources, before fitting or TEST. Preserve its bundle and scope-v2-stop.json;
never pool its partial V4-prior corpus. Version3 follows the user's clarification:
Arm C ONLY as tree prior, unchanged V4 rollout chain. New source seeds and
canaries below are disjoint from the interrupted run. This prior change defines
a new source distribution with the same V4 rollout target policy; it is not a test of V4 versus Arm C gameplay.

Arm C custody: published §488 d64 trim checkpoint from git68fe88be, checkpoint
SHA25653739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020,
native eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509.
The existing exporter with --n-heads4 --trim-map reproduces that native hash.
Freeze this consumed artifact and require its actual64/4/256/2/trim1 load marker,
prior=heart1, leaf_policy=v4, zero prior-leaf steps and>=90% student prior scoring
on every unit: scored/(scored+fallback) among attempted model-prior nodes,
excluding singleton/unqualified uniform-prior nodes (configuration/support
counters only, no TEST target parsing).
V4 remains the existing fallback for prior states Arm C cannot encode.

Source: separate Heart-objective PR must be merged first. Then a separate
research branch adds only default-off sibling-capture public input and measured
teacher CPU, plus offline fitting/analysis. Freeze reviewed SHA, binary SHA256,
all consumed model SHA256s, exact environment, tools and this protocol in a
machine-readable manifest before canary/data generation. Preserve all raw output.

Regime: native project-fair Silver; 10000 exact real-combat simulations,
reuse allocated cap32768, adaptive/learned stopping off. A20 Ironclad,
STS_COLLECT_KEYS=1 STS_STOP_AFTER_ACT=0. V4 rollout chain, distilled heart1 Arm C tree prior, native
leaf and automatic calibrated A20 CTM stack. OOC source search512 sims,
rollout3 (LEAF_COMBATS=3), same widening/PUCT settings as §489. This is a lower-cost
source distribution, not a qualification of the historical4096 search budget.

Capture: every4th searched decision, max64 leaves/root, depth<=1; 64 fresh
rollout3 labels per retained leaf, no rollout5. Public heart1 record only (schema heart1-public-record-v2);
seed, RNG, action ID, parent ID, outcomes, endpoints, errors and costs are
metadata/targets, never network inputs. X2-B is an explicit baseline/scalar
residual input. The existing candidate-public schema and new heart1 record remain
parity-unqualified for this new use: offline
results cannot themselves authorize native deployment or public-input parity.

Canary: seed110159994 capture off/on for decision/action byte parity (timing
excluded); seed110159995 capture on for coverage and support diagnostics.
At most600s/unit. Fail closed on crashes, identity mismatch, changed actions,
no complete sibling groups or >20% label/input rejection; preserve failures.
If canary is invalid, stop before the cohort and repair/review a new protocol.

Cohort:64 source seeds110161000..110161063, disjoint by source run:
TRAIN110161000..039 (40), VALIDATION110161040..047 (8),
TEST110161048..063 (16). No replacement, extension, pooling or adaptive seed
selection. Collect TEST to separate files but do not load their contents for
training/selection; inspect only exit/hash/receipt metadata until frozen final
selection. Three single-threaded workers; max600s/source,4h cohort wall cap.
Local CPU/GPU only. Missing units make the pilot INCOMPLETE, with no efficacy
claim. Every trajectory command uses tools/seed_guard.sh.

Offline grid (frozen, no additional architectures): a count MLP, heart1-inspired
pooled typed tokens, and heart1/student-C-inspired attention tokens (dim64,
2 pre-norm transformer layers,4 heads, FF128, dropout0). Same public heart1
record in all arms: fixed observation, deck/upgrades, relics/public counters,
potions, offers/fixed actions, screen and forward map nodes/edges, plus
current public battle encounter and public memory-game state; no released
heart1 weights required. Tokens preserve map coordinates/outgoing links and
burning-elite identity. This is not an exact port of the trained heart1 network.
Count arm gets typed entity counts and attribute sums plus identical fixed
observation. Pool arm adds learned token means; attention arm adds a CLS token
with masked attention. Each uses two hidden head layers128, ReLU, and the same
X2-B logit residual plus within-parent centered MSE +0.1 absolute MSE. This
compares representations at a fixed fit protocol, not parameter-matched models.
Two initialization seeds0 and1 each (six fits); AdamW lr0.001 decay0.0001,
30 epochs, whole-parent group batches of at most512 leaves. Numeric token
attributes are clipped to[-8,8]. Fixed observation scales and token vocabularies
are fixed in heart_record_encoder.py; no normalization fits VALIDATION/TEST. Vocabulary fits TRAIN
only. Epoch/model/blend selection uses VALIDATION only: lowest per-source mean
per-action sibling regret quantized to1e-6, tie uses MSE then fewer parameters.
Fixed X2-B blends weights0.25,0.5,0.75,1.0 are selectable only on VALIDATION.
Freeze checkpoint, vocabulary, tool/dependency hashes and blend before TEST.
No tuning after TEST. Fit subprocess has a hard1200s wall cap including
preprocessing. Tensors stay on CPU and only batches transfer to GPU. Before
allocation, require<=2GiB estimated tensor CPU storage and conservative GPU
allocation<=min(4GiB,80% free VRAM); otherwise stop without batch/architecture
changes. No student-driven trajectories.

Metrics: per-source MSE, within-parent pair concordance and regret across distinct actions (average
all retained leaf predictions and targets per action before comparing) against
64-rollout mean, noise/sample/support coverage by act/screen/key state, inference
CPU latency batch1 and32 versus measured rollout CPU. Aggregate by source seed,
not treating correlated leaves as independent. Bootstrap source seeds with fixed
bootstrap seed20261016 (2000 resamples). Evaluate exact selected model/blend once
on TEST; record negative/inconclusive results unchanged.

Offline candidate criterion: at least500 complete multi-action sibling groups
in TRAIN,100 in VALIDATION,200 in TEST, with at least one multi-action group
from every declared source seed; >80%
valid rows; TEST pair concordance improves at least0.02 over X2-B and regret is
at least10% lower, with source-bootstrap lower bound of regret improvement>0.
Require>=4x measured Python compression including record encoding, vectorization,
student inference and the required X2-B call. Missing/nonfinite/nonpositive
teacher CPU evidence fails validation. Python speedup cannot establish native speedup.
Otherwise NOT_SHOWN/INSUFFICIENT as appropriate. Neither PASS nor MSE is a
playing-strength or default-promotion verdict. Only a passing candidate advances
to a separately frozen native-parity and matched-CPU gameplay experiment; this
pilot does not silently combine those claims. Document results in ledger and KB.

Custody and group validity: freeze a metadata-only corpus receipt/hash manifest
after generation and before fitting. Selection pins its hash. Verify frozen
Python/runtime dependency versions and representative binary/module hashes,
bundle/model/build-receipt/protocol/tool hashes, and TEST capture+receipt hashes
before creating test-opened.json. No TEST JSONL parse occurs before the latch.
A failed opened TEST is never retried. Every retained captured row in a parent
must have64 finite supported returns, valid public encoding, and valid costs;
otherwise drop that entire captured parent. This means complete retained
capture groups, not an exhaustive set of all legal actions/chance outcomes.
Canary and corpus use the identical validator. The runner verifies/builds the
reviewed source before copying the executable; build receipt and log hashes
connect the frozen binary with that source.

Domain diagnostic: report row counts, source coverage and MSE by original
heart1, battle-start and memory-game inputs; these do not affect selection.

Fixed hybrid diagnostic: after selection, compare a50/50 blend of the selected
prediction with its independent scheduled rollout3 return (`r0`) on TEST, beside
pure scheduled rollout3 and frozen Opus490. These diagnostics are not additional
model-selection choices, and a hybrid still pays for its rollout.
