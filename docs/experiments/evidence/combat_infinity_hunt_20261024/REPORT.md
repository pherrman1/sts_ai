# Targeted natural infinity hunt — retained-data census

**Current-policy natural positive signal: BLOCKED_BY_DATA.** Recent data contain
plausible public deck/relic ingredients, but no eligible recent enriched public
combat roots were available. The formats split the required information: recent
Heart/AZ records have full relic inventories but no in-combat public wire; recent
combat-root generation has the wire but omits complete run-relic provenance.
No new oracle world, collection, capture patch or model work was launched.

Starting #844 SHA: `7249709a16a19b8cc6d265a5b42c8d93e5a24872`. Existing branch and
app-managed worktree retained. Latest main was fetched/read only at
`413e85d69634b51419f3306e286f385f68c3a32c`; it was not merged. The relevant seven
producer/conversion files are byte-identical to this branch; exact hashes and
current campaign identities are in [schema-audit.json](schema-audit.json).

## Frozen screen and safeguards

[SCREEN.md](SCREEN.md) and [screen_rules.py](screen_rules.py) were committed at
`bef9bbc1e` before the census. No rules were tuned after the scan. The five broad
known-ingredient flags are cycle-card pairs with required Vulnerable support,
Sundial+draw, small/cheap Top, Headbutt+draw, and Corruption+Dark Embrace+Dead
Branch. The last two are intentionally broad ingredient flags, not demonstrated
infinities. Generic G requires a real combat active pool of1..8 cards plus a
specified draw/energy mechanism. Exact card lists, thresholds and selection
ordering are retained in the frozen document.

Only public deck/relic/combat information enters the screen. OOC compression is
**not assessable**; zero G counts in those internal counters must be read as N/A.
OOC Top cheapness is likewise not assessed because those records lack costs.
Combat Top uses public costForTurn. Current active powers are decoded from the
public status bits for the relevant ingredient checks. No hidden draw order,
oracle output, target/logit/z, run outcome, future decision or witness determines
an enrichment flag or selected root. Census code projects record deck/relic
fields only. Source TRAIN membership is a fixed partition, not outcome selection.
Only TRAIN tar files and AZ seed%8!=7 row files were opened. Sealed TEST/confirm
archives and validation data were not opened. No corpus verdict was changed.

Public candidates require proven no-Shard provenance before selection. Ordinary
oracle domain/quiet-boundary checks would still apply; a deck ingredient flag
alone is never eligibility. Selection is max32 roots, max4 per combat with the
frozen deterministic ordering. Four roots were selected; all are retrospective
reuses described below. Selected root IDs/hashes and the exact input hash were
committed at `1c9d14ffb` before the reuse analysis. No new oracle execution occurs.

## Source inventory and census

| Source inspected | Declared run IDs | Public records / roots screened | K flag records | K flag run IDs | G |
|---|---:|---:|---:|---:|---|
| A20 Heart round2 TRAIN,32 archives | 1,088 | 169,239 OOC | 58,709 | 588 | N/A |
| Recent AZ gen3 TRAIN rows | 896 | 150,383 OOC | 57,147 | 513 | N/A |
| AZ gen2 TRAIN rows | 1,904 | 329,804 OOC | 126,825 | 1,117 | N/A |
| A20 Heart round1 TRAIN,49 archives | 1,080 | 171,442 OOC | 61,838 | 624 | N/A |
| Older paired A0 Champ public capture | 1 | 72 combat roots | 72 | 1 | 0 |
| native8 public captures | 8 | 175 combat roots | 19 | 2 | 0 |
| Forced-action public archive | 16 | 32 combat roots | 6 | 3 | 0 |
| Prior-root archive | 64 | 64 combat roots | 19 | 19 | 0 |

Total: **4,968 OOC run IDs /820,868 public OOC records**, plus **343 combat-root
observations across89 declared seed IDs**. These are artifact/run identifiers,
not independent trials or a prevalence estimate. Counts across known-ingredient
subclasses overlap. There are116 enriched combat-root observations; only the72
paired Champ roots have complete no-Shard provenance. The older public sources
are small/partial archives and do not establish generic compression rarity.

Exact sources:

- Local `build/heart-outcome-round2-data-a8f6542e/heart-outcome-round2` and
  `build/heart-outcome-import-20261016-v1/heart-outcome-collection` under the
  primary repository. Each of81 TRAIN archive hashes matches its delivery index
  before parsing; index hashes and source producer headers are retained. Original
  Heart producer card/relic enum tables were checked identical to current ones.
- GitHub data branch `claude/az-gen2-data`, fetched/pinned at
  `43ad57f0e34e5bc34b7cb21c9fa8f8d5bb3039c1`, `gen2/rows` and `gen3/rows_new`:
  2,800 TRAIN row blobs. Git object/tree identity pins the delivered data. These
  converted OOC records are ingredient evidence, not a full combat custody join.
- Paired corrected-canary `Capture_0.public.jsonl` and its complete OOC trace:
  the previous custody audit revalidates receipt, actual artifact/manifest/binary
  hashes, full prebattle inventory and exact Champ identity. No Shard assertion
  is inferred from early floor, red cards or two combat bitsets.
- Tracked `silver_quiescent_queue_item_20260922/native8-captures.jsonl.gz`,
  `silver_forced_action_target_2026-09-19/roots.jsonl`, and
  `silver_prior_root_replay_20260923/prepared/roots.jsonl` at the starting branch.
  File hashes and all screened public identities/reasons are retained.

The newer A20 on-policy512 combat corpus was inspected through current-main
campaign/producer metadata only. Its raw cloud share is absent locally; the GCP
CLI has no active account. It is **not** included in screened-root counts.
The documented producer is a8b801390a2e730c30312522b71a056c3eaca7c7, run commit
db49b3515293711d90356221b63af1617abfe64e, binary0feb879d7e0b54beeb8edbb83e4f02aba860464983b812931b673d1d60ebad68.
`FightRecorder::observe` writes the public wire without full relics; its checked-in
env-i run script enables neither paired OOC nor public trace. Its manifest cannot
restore omitted per-root ownership. No raw remote storage census is claimed.

[Census](census.json), [per-public-root screen](public-screen.jsonl), and
[schema audit](schema-audit.json) preserve these boundaries and exact source IDs.

## Ingredients are visible; approach-to-infinity remains unknown

| Overlapping OOC subclass | Round2 run IDs | AZ gen3 | AZ gen2 | Round1 | Total |
|---|---:|---:|---:|---:|---:|
| Cycle pair + required Vulnerable support | 12 | 9 | 33 | 16 | 70 |
| Sundial + draw | 91 | 89 | 153 | 107 | 440 |
| Headbutt + draw (weak/broad flag) | 539 | 466 | 1,011 | 565 | 2,581 |
| Corruption + Dark Embrace + Dead Branch | 21 | 16 | 42 | 19 | 98 |
| Top + small/cheap | N/A costs | N/A | N/A | N/A | N/A |

There are2,842 OOC run IDs with any K flag, dominated by weak Headbutt+draw.
Examples retain two distinct run IDs per available subrule/source, projected to
public relevant cards/relics. Sundial and cycle-pair ingredients therefore exist
in the retained recent data; this is not just the previous no-Sundial Champ
case. However, deck ingredients do not prove combat compression, playable energy
economics, public-root support or a recurrence. Neither “the policy almost never
approaches infinities” nor “oracle recall is the bottleneck” follows yet.

Concrete public ingredient leads include Heart round2 run111101032 (two
Dropkicks, Bash and Pommel Strike), AZ gen3 run111143169 (two Dropkicks, Bash,
Corruption and two Pommel Strikes), and AZ gen3 run111142899 (Sundial and two
Shrug It Off cards). These projected records are retained in census examples.
They are OOC ingredient leads, not observed near-infinite combat states or
certified witnesses. Their run outcomes were not used.

## Selected roots and unchanged K=4 evidence

The deterministic selector yields **only four old A0 Champ roots**:
run610081002/fight13/decisions1,2,3,5. They have active pools25,25,25,26 and qualify
only through weak K4 (Headbutt+Shrug draw), not cycle pairs, Sundial, Top or G.
The complete run relic inventory is the same ten-relic inventory previously
audited; none of the screened engine relics is present.

The selected JSONL is **byte-identical** to the prior pilot's `inputs-0.jsonl`.
[SELECTION.json](SELECTION.json) binds its hash, four public hashes/reasons,
receipt proof references and the old raw-output hash. Reusing its existing16
world records avoids rerunning deterministic worlds and adding no evidence.
This is explicitly **not a new enriched annotation experiment** and does not
claim novel, independent or current-policy roots. No later root was substituted
to obtain another result, and no search/capture extension followed the blocker.

[MATRIX.md](MATRIX.md) reports each root's identity, active count, relevant
cards/relics, supported worlds, certified/candidate fractions, minimum reach,
all three search cap flags, nodes/CPU and null witness. Retained results are
0 certified /0 damaging candidates;12/16 node-capped worlds (75%, decisions1,2,5)
are **INCONCLUSIVE_NODE_CAP**. Decision3's four worlds have bounded NONE, not an
unrestricted absence proof. No replay or witness exists to inspect.

Reused oracle CPU is77.754ms total from the old records. New oracle runtime is0,
new worlds0, current-policy cap rate **null/not run**. The final read-only census
pass took28.725s wall /28.742s child CPU; earlier exploratory schema/census reads
are outside that measurement. No timing is presented as annotation throughput.

## Exact missing data and smallest next step

The missing combat-root field is **complete owned run relic inventory (including
Prismatic Shard) with explicit completeness and producer identity**, attached to
the public root or a receipt-bound same-run/fight record. The missing OOC field
is **the real public in-combat wire at a player decision**. Arbitrary seed/floor
joins across different policies or trajectories are invalid.

The cheapest future capture route is already implemented: co-emit targeted
`STS_SILVER_PUBLIC_TRACE`/`STS_SILVER_PUBLIC_TARGET` and
`STS_OOC_DECISION_TRACE` under one frozen run receipt. This requires no new
capture infrastructure or field, but would require a separately bounded small
collection; none was launched here. Obtain8–16 public roots across several
combats/runs with ingredient relevance, then apply the frozen screen/K4 path.

If the next task instead uses the `silverazgen` combat-root corpus and wants
single-row custody, the smallest capture-only proposal is inside
`apps/one_combat/silver_synth_gen.cpp::FightRecorder::observe`:

```cpp
// Proposed only: under the existing explicit research-capture path/gate.
nlohmann::json ids = nlohmann::json::array();
for (const auto &relic : view.gc.relics.relics)
    ids.push_back(static_cast<int>(relic.id));
row["public_run_relics"] = {
    {"schema", "public_run_relics_v1"},
    {"inventory_complete", true},
    {"relic_ids", std::move(ids)}
};
```

Bind this to the existing run/fight IDs and source/binary/rows hashes. If exposed
through the normal public trace sink, the same payload goes inside
`NativeSilverBackend.cpp::tracePublicAction`, whose existing trace gate is
default-off and already has `gc`. No new flag or production default is needed
for that existing opt-in route. The raw archive cannot be repaired retroactively
by adding a producer field. **No proposal was implemented.**

Stop at this data decision. Do not increase K or bounds, infer negatives from
caps/nulls, run a random larger cohort, generate counterfactual positives on a
claim of demonstrated ingredient rarity, or probe/train an infinity head.
Current-policy natural positive signal is **BLOCKED_BY_DATA**, with older
implementation/annotation feasibility and original null results unchanged.

## Verification and knowledge impact

`analyze.py --check` validates source-census arithmetic, frozen root/input hashes,
exact reused raw output hash, K4/caps and generated reporting byte agreement.
`census.py --check` independently regenerates the inventory from only TRAIN and
public sources; it does not execute the oracle. Repository/diff/ledger checks
and independent review are recorded on the PR. No game-seed driving command was
run, so no seed-guard simulator invocation is claimed. Existing fixture/pilot
checks regenerate their reports only. No manual CI redispatch, main merge,
model/schema/gameplay modification or new producer run.

Knowledge impact: chronological targeted inventory evidence and maintained
research status updated. The source-symbol name correction (`FightRecorder`,
not `SynthSink`) is recorded here; earlier historical evidence is preserved.
