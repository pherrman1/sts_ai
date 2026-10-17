# §497 recovered Heart-outcome corpus: import and seal audit

**TRAIN_VALIDATION_READY; independent implementation and result reviews PASS.**
The delivered data pass the unchanged readiness gate for future value-head
training. No model was fitted and no TEST archive was opened. This is data
qualification, not a model-quality, speed, gameplay or RL verdict.

## Exact import

Transport branch `claude/heart-outcome-data`, pinned commit
`e3b649ced5a392f78e9412787a84d458cffd60a1`, remains **never merge**. The primary
local main was fast-forwarded to `b35c179ebedfa33935198dc784004a52f58eef8b`.
The importer was independently reviewed and frozen at
`747f47e935c5c35c41dd5599f0905dd7a270806a` before the full outcome audit.
Later documentation commits do not replace that reviewed tool identity.

All 379 regular transport files were inventoried, including SHA256SUMS itself;
all 378 checksum entries passed, before and after the audit. DELIVERY-INDEX.json
is byte-identical to main's copy, SHA256
`e3621c3873dc0155edd651f787802412560b632ee6cca3f32b6e4ed2be746026`.

Per the current user's explicit handoff, accepted data come from 41 original
`wWW` deliveries and 8 replacement halves `rWW-0`/`rWW-1` for lost workers
7,8,27,34. This covers all 1,800 unique planned sources without overlap.
The four original partial archives remain superseded and opaque. No source
was selected or discarded based on its outcome. All 49 accepted worker receipts
attest complete runs and zero nonzero source return codes.

## TRAIN/VALIDATION results

| Split | Complete sources | Heart kills | Other completed outcomes | Supported / observed states |
| --- | ---: | ---: | ---: | ---: |
| TRAIN |1,080|126|954|171,442 /171,442|
| VALIDATION |360|47|313|56,704 /56,704|
| Total development data |1,440|173|1,267|228,146 /228,146|

The original gate requires TRAIN ≥20 wins/20 losses and VALIDATION ≥5 wins/5
losses. Every gate passes without adaptation. TRAIN and VALIDATION remain
source-disjoint; the total above does not authorize pooling them for fitting.
Each future source-balanced fit should use inverse within-source supported-state count,
so long successful trajectories do not receive extra independent-game weight.

All 1,440 TRAIN/VALIDATION sources were checked for complete healthy outcome
framing, source/binary/policy/environment identity, exact seven-file receipt
hash binding, full public-record schema, ordered actual-driver trace alignment,
and fixed guarded invocation. Public HP/maxHP/gold comparisons use the frozen
producer's caps 200/200/1800. Seed/RNG/outcome/label provenance stays outside
model inputs. All sources scored with original Arm C at 100% prior and rollout
coverage, expected 64/4/256/2/trim1 shape, zero fallbacks and zero legacy prior
leaves. Missing or invalid runs were never relabeled as losses.

Independent metadata review also found no TRAIN/VALIDATION timing anomaly:
maximum source duration 1,296.575s; recorded started-file times 17:50:40–20:58:40Z
and receipt-file times 17:56:10–21:10:36Z are inside the original global window
17:43:29–23:43:29Z on the collection date. TEST inner clocks remain unparsed.

## TEST custody and limitations

The 49 `SEALED-test.tar.gz` files, representing 360 assigned sources, and 4
superseded partial archives were hashed as opaque bytes only. No tar parser,
member listing, extraction, state/label/log read or outcome count was performed
on any of these 53 sealed objects. TEST completion is attested by the producer's
worker receipts and archive hashes; independent framing/schema/clock claims
apply only to the 1,440 TRAIN/VALIDATION sources. No fit or TEST-opening latch
exists in this import root.

Recorded deviations remain part of this corpus's provenance:

- Recovery uses the user-directed replacement deliveries, not an unchanged
  execution of the original no-retry protocol.
- The cross-container export check was one-way. The receipt's field names do
  not turn it into an actual roundtrip; the reviewer timestamp string alone
  does not establish final approval chronology.
- Worker 11 used a different CPU. Fixed simulation counts and identical binary
  hashes do not independently prove cross-CPU byte-identical decisions. The
  earlier ledger statement that only wall time differs was too strong.
- Public-record/native parity remains unqualified; observation coverage is
  sampled real driver boundaries, not every primitive action. Outcomes describe
  the fixed Arm C prior+rollout, CTM/X2-B-guided search and exact 10k Silver
  behavior policy, not optimal Heart-win probabilities.

No prior §491–496 verdict is changed. No native value-head integration or
production-default change was made. A separate reviewed frozen fitting protocol
should use TRAIN for fitting and VALIDATION for selection before any one-shot
TEST protocol is considered.

## Reproduction and evidence

```bash
# From the reviewed repository checkout; TARGET and OUT must be fresh absolute paths.
git fetch origin claude/heart-outcome-data
mkdir TARGET
git archive e3b649ced5a392f78e9412787a84d458cffd60a1 heart-outcome-collection | tar -x -C TARGET
(cd TARGET/heart-outcome-collection && sha256sum -c SHA256SUMS)
python3 tools/heart_outcome_import.py TARGET/heart-outcome-collection OUT
```

Focused CTest 2/2 passed (collector 15 and importer 12 Python cases). Independent
importer 12/12 passed in 0.070 s after fixing the capped-observation comparison.
Repository health and diff checks passed. No C++ source changed; no new native
build, full core/smoke run or authoritative CI pass is claimed.

Original result [import-audit.json](import-audit.json) SHA256:
`aafe46933b03b153fc3b3032f0afa3f860663b15e9d96e015f3af06688328d33`.
Separate [independent result review](import-reviewed.json) SHA256:
`e07fce84e152dc4d0bf10c6c8ae833c37ff0d7ed8d49b41ac18fea71b59e01be`.
The validated 1,440-source manifest SHA256 is
`1d2c6b03f95ca4750eb9869627f590d11fafeb69f04c43077d927d524117f5c6`.
[Transport/check receipt](transport-receipt.json) binds the raw logs and manifest.
[Protocol](PROTOCOL.md) records the fixed selection, gates and custody boundary.

All raw files and the source manifest remain under
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-import-20261016-v1`.
No raw corpus, state rows or data archives are copied into this PR/main.
