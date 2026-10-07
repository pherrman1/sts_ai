#!/usr/bin/env python3
"""Exact offline RNG continuation audit; never launches seeds or trains models."""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
try:
    from tools.combat_transition_contract import validate_corpus, sha256
    from tools.combat_transition_surrogate import iter_rows, supported_for_surrogate
except ModuleNotFoundError:  # direct invocation from tools/
    from combat_transition_contract import validate_corpus, sha256
    from combat_transition_surrogate import iter_rows, supported_for_surrogate

try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
FROZEN_SHA = _pins.value("combat_transition_rng_audit.FROZEN_SHA", '74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde')
STREAMS = ('aiRng', 'cardRandomRng', 'miscRng', 'monsterHpRng', 'potionRng', 'shuffleRng')
MASK = (1 << 64) - 1


def next_long(state: dict) -> int:
    """sts::Random::nextLong, unsigned 64-bit xorshift128+."""
    s1, s0 = state['seed0'], state['seed1']
    state['seed0'] = s0
    s1 ^= (s1 << 23) & MASK
    state['seed1'] = (s1 ^ s0 ^ (s1 >> 17) ^ (s0 >> 26)) & MASK
    return (state['seed1'] + s0) & MASK


def bounded_long(state: dict, n: int) -> int:
    if not 0 < n < (1 << 63):
        raise ValueError('invalid bound')
    while True:
        bits = next_long(state) >> 1
        value = bits % n
        if bits - value + n - 1 < (1 << 63):
            return value


def set_counter(pre: dict, target: int) -> dict:
    result = dict(pre)
    # Native setCounter is a no-op for a decreasing target; equality still fails.
    while result['counter'] < target:
        next_long(result)
        result['counter'] += 1
    return result


# Exact misc-only draw closure from MonsterGroup::createMonsters and helpers.
# None denotes randomBoolean(); other entries are nextLong bounds (range + 1).
MISC_SCHEDULES = {
    'GREMLIN_GANG': (8, 7, 6, 5), 'SMALL_SLIMES': (None,),
    'LOTS_OF_SLIMES': (5, 4, 3, 2, 1), 'LARGE_SLIME': (None,),
    'EXORDIUM_THUGS': (None, 3, None, 3),
    'EXORDIUM_WILDLIFE': (2, None, 3), 'GREMLIN_LEADER': (8, 8),
    'FOUR_SHAPES': (6, 5, 4, 3), 'THREE_SHAPES': (6, 5, 4),
    'SPHERE_AND_TWO_SHAPES': (3, 3), 'THREE_LOUSE': (None, None, None),
    'TWO_LOUSE': (None, None),
}


def encounter_names():
    header = Path(__file__).resolve().parents[1] / 'include/constants/MonsterEncounters.h'
    text = header.read_text()
    match = re.search(r'monsterEncounterEnumNames\[\]\s*=\s*\{([^}]+)\}', text)
    if not match:
        raise ValueError('cannot resolve native encounter domain')
    return re.findall(r'"([A-Z0-9_]+)"', match.group(1))


def replay_misc(pre, encounter_name):
    """Deterministic initialization draws, INCLUDING bounded rejection loops.

    Native Monster::construct/preBattleAction do not use misc. All live misc
    mutations are in this initialization closure; later summons use aiRng.
    No post-combat information or learned target is needed.
    """
    result = dict(pre)
    for bound in MISC_SCHEDULES.get(encounter_name, ()):
        result['counter'] += 1
        if bound is None:
            next_long(result)
        else:
            bounded_long(result, bound)
    return result


def metrics(pre: dict, post: dict) -> dict:
    delta = post['counter'] - pre['counter']
    seeds_changed = (pre['seed0'], pre['seed1']) != (post['seed0'], post['seed1'])
    return {'rows': 1, 'exact_equal': int(pre == post),
            'counter_changed': int(delta != 0), 'seed_state_changed': int(seeds_changed),
            'state_changed_counter_unchanged': int(seeds_changed and delta == 0),
            'counter_decreased': int(delta < 0), 'delta': delta}


class Summary:
    def __init__(self):
        self.counts = Counter()
        self.deltas = Counter()
        self.failures = Counter()
        self.examples = []

    def add(self, pre, post, replay, row):
        values = metrics(pre, post)
        self.deltas[values.pop('delta')] += 1
        self.counts.update(values)
        if replay is not None:
            self.counts['replay_tested'] += 1
            self.counts['replay_matches'] += int(replay == post)
            if replay != post:
                self.failures[str(row['encounter'])] += 1
                if len(self.examples) < 5:
                    self.examples.append({k: row[k] for k in ('sourceSeed', 'fightIdx', 'act', 'floor', 'roomClass', 'encounter')}
                                         | {'pre': pre, 'post': post, 'replayed': replay,
                                            'visiblePotions': row['predictorInput']['potions']})

    def result(self):
        out = dict(self.counts)
        out['state_changed'] = out['rows'] - out['exact_equal']
        out['delta_counter_distribution'] = dict(sorted(self.deltas.items()))
        if out.get('replay_tested'):
            out['replay_failures'] = out['replay_tested'] - out['replay_matches']
            out['mismatch_rate'] = out['replay_failures'] / out['replay_tested']
            out['mismatches_by_encounter'] = dict(self.failures)
            out['first_mismatches'] = self.examples
        return out


def ordered_pairs(runs):
    """Order by unique native sourceSeed/fightIdx, never file/shard arrival order."""
    for seed, fights in sorted(runs.items()):
        fights.sort(key=lambda r: r['fightIdx'])
        if [r['fightIdx'] for r in fights] != list(range(len(fights))):
            raise ValueError(f'non-contiguous fight order for source {seed}')
        for previous, current in zip(fights, fights[1:]):
            if current['floor'] < previous['floor']:
                raise ValueError(f'decreasing floor for source {seed}')
            if previous['outcome'] != 1:
                raise ValueError(f'fight after non-victory for source {seed}')
            yield previous, current


def audit(manifest_path: Path):
    manifest = json.loads(manifest_path.read_text())
    if manifest['csv']['sha256'] != FROZEN_SHA:
        raise ValueError('not the frozen corpus')
    integrity = validate_corpus(manifest)
    provenance_path = Path(manifest['csv']['path']).with_suffix('.jsonl.provenance.json')
    provenance = json.loads(provenance_path.read_text())
    bindings = {'dataset_path': manifest['csv']['path'], 'git_sha': manifest['producerGitSha'],
                'rows_written': integrity['rows'], 'completed_seeds': integrity['completedSeeds'],
                'requested_seeds': integrity['requestedSeeds'], 'seed_offset': manifest['seedSpec']['start'],
                'invalid_or_quarantined_seeds': integrity['quarantinedSeeds'], 'generator': 'combattransitiongen'}
    if any(provenance.get(k) != v for k, v in bindings.items()):
        raise ValueError('companion provenance disagrees with frozen manifest')
    quarantined_seeds = {int(k) for k in provenance['quarantined']}
    if len(quarantined_seeds) != integrity['quarantinedSeeds']:
        raise ValueError('provenance quarantine count mismatch')
    if integrity['quarantinedRows']:
        raise ValueError('frozen audit requires valid fully captured rows')
    groups = defaultdict(lambda: [Summary() for _ in STREAMS])
    runs = defaultdict(list)
    support = 0
    names = encounter_names()
    deterministic = Counter()
    deterministic_examples = []
    for row in iter_rows(Path(manifest['csv']['path'])):
        transition = row['transition']
        pre, post = transition['pre'], transition['post']
        eligible = supported_for_surrogate(row['predictorInput'], pre)
        support += eligible
        encounter = row['encounter']
        if not 0 < encounter < len(names):
            raise ValueError('unknown encounter')
        misc_replay = replay_misc(pre['combatRng'][2], names[encounter])
        deterministic['rows'] += 1
        deterministic['matches'] += misc_replay == post['combatRng'][2]
        if eligible:
            deterministic['supported_rows'] += 1
            deterministic['supported_matches'] += misc_replay == post['combatRng'][2]
        if misc_replay != post['combatRng'][2] and len(deterministic_examples) < 5:
            deterministic_examples.append({'sourceSeed': row['sourceSeed'], 'fightIdx': row['fightIdx'],
                                           'encounter': names[encounter], 'replayed': misc_replay,
                                           'post': post['combatRng'][2]})
        outcome = 'victories' if transition['combatOutcome'] == 1 else 'deaths'
        slices = ['all', outcome, f"act:{row['act']}", f"room:{row['roomClass']}", f"encounter:{row['encounter']}"]
        if eligible:
            slices += ['supported', f'supported:{outcome}', f"supported:act:{row['act']}",
                       f"supported:room:{row['roomClass']}", f"supported:encounter:{row['encounter']}"]
        for i in range(6):
            a, b = pre['combatRng'][i], post['combatRng'][i]
            if any(not 0 <= v <= MASK for v in (a['seed0'], a['seed1'], b['seed0'], b['seed1'])):
                raise ValueError('RNG seeds outside uint64 domain')
            replay = set_counter(a, b['counter']) if i in (2, 4) else None
            for name in slices:
                groups[name][i].add(a, b, replay, row)
        runs[row['sourceSeed']].append({k: row[k] for k in ('fightIdx', 'floor', 'act', 'roomClass', 'encounter')}
                                      | {'supported': eligible, 'outcome': transition['combatOutcome']})
    if deterministic['rows'] != integrity['rows']:
        raise ValueError('audited row count disagrees with validated corpus rows: '
                         f"{deterministic['rows']} != {integrity['rows']}")
    requested_seeds = set(range(manifest['seedSpec']['start'],
                                manifest['seedSpec']['start'] + manifest['seedSpec']['count']))
    if set(runs) & quarantined_seeds or set(runs) | quarantined_seeds != requested_seeds:
        raise ValueError('actual source set disagrees with companion quarantine provenance')
    pairs = Counter()
    examples = []
    for a, b in ordered_pairs(runs):
        pairs['consecutive_pairs'] += 1
        if a['floor'] == b['floor']:
            pairs['same_floor'] += 1
            pairs['same_floor_supported_origin'] += a['supported']
            pairs['same_floor_both_supported'] += a['supported'] and b['supported']
            if len(examples) < 10:
                examples.append({'previous': a, 'next': b})
    summaries = {k: dict(zip(STREAMS, (s.result() for s in v))) for k, v in sorted(groups.items())}
    # Candidate visible gate excludes encounter classes with ANY supported misc mutation.
    misc_encounters = sorted(int(k.split(':')[-1]) for k, v in summaries.items()
                             if k.startswith('supported:encounter:') and v['miscRng']['state_changed'])
    excluded = sum(summaries[f'supported:encounter:{e}']['miscRng']['rows'] for e in misc_encounters)
    return {'schemaVersion': 'combat_transition_rng_audit_v1',
            'corpusManifest': str(manifest_path.resolve()), 'manifestSha256': sha256(manifest_path),
            'corpusSha256': FROZEN_SHA, 'companionProvenance': str(provenance_path),
            'companionProvenanceSha256': sha256(provenance_path), 'producerGitSha': manifest['producerGitSha'],
            'producerExecutableSha256': manifest['producerExecutableSha256'],
            'integrity': integrity, 'supportedRows': support,
            'supportImplementation': 'tools.combat_transition_surrogate.supported_for_surrogate',
            'supportImplementationSha256': sha256(Path(__file__).with_name('combat_transition_surrogate.py')),
            'ordering': 'sourceSeed grouped; fightIdx sorted, unique and contiguous from zero; floors nondecreasing; previous outcome victory',
            'sameFloor': {k: pairs[k] for k in ('consecutive_pairs', 'same_floor', 'same_floor_supported_origin', 'same_floor_both_supported')}
                         | {'examples': examples},
            'candidateMiscCopyGate': {'excludedEncounterIds': misc_encounters, 'excludedRows': excluded,
                                      'supportLossFraction': excluded / support},
            'deterministicMiscReplay': dict(deterministic) | {'firstMismatches': deterministic_examples},
            'encounterNames': dict(enumerate(names)), 'summaries': summaries}


def compact_result(result):
    """Keep full six-stream totals; diagnostic slices need inherited streams only."""
    supported = result['summaries']['supported']
    exact_misc = result['deterministicMiscReplay']['supported_matches'] == result['supportedRows']
    potion_copy = supported['potionRng']['exact_equal'] == result['supportedRows']
    no_supported_same_floor = result['sameFloor']['same_floor_supported_origin'] == 0
    # The continuation-boundary/source proof is recorded with the evidence.
    # Plain setCounter remains a corpus property, not an API-wide theorem.
    result['decision'] = {
        'classification': 'RNG_COUNTER_DELTA_EXACT' if exact_misc and potion_copy and no_supported_same_floor else 'RNG_CONTINUATION_UNRESOLVED',
        'scope': 'current supported-v1; native normal run controller; exact encounter initialization replay',
        'minimalLearnedRngTargets': [],
        'derivedCounterDeltas': {'delta_misc': 'length of encounter initialization draw schedule', 'delta_potion': 0},
        'reconstruction': 'replay native misc encounter draw schedule from pre.miscRng, preserving bounded rejection; copy pre.potionRng',
        'plainSetCounterUniversal': False,
        'supportPredicateChanged': False,
        'proposedGuardNeeded': False,
    }
    primary = {'all', 'supported', 'victories', 'deaths', 'supported:victories', 'supported:deaths'}
    compact = {}
    for name, values in result['summaries'].items():
        if name in primary:
            compact[name] = values
        else:
            inherited = {k: values[k] for k in ('miscRng', 'potionRng')}
            if 'encounter:' not in name or any(r['state_changed'] for r in inherited.values()):
                compact[name] = inherited
    for name, values in compact.items():
        for stream, counts in values.items():
            if stream not in ('miscRng', 'potionRng') or name not in ('all', 'supported'):
                counts.pop('delta_counter_distribution', None)
    result['summaries'] = compact
    root = Path(__file__).resolve().parents[1]
    result['staticAuditSourceSha256'] = {p: sha256(root / p) for p in (
        'include/game/Random.h', 'src/combat/BattleContext.cpp', 'src/combat/MonsterGroup.cpp',
        'src/combat/Monster.cpp', 'src/combat/MonsterSpecific.cpp', 'src/game/Game.cpp',
        'src/game/GameContext.cpp', 'src/sim/search/NativeSilverBackend.cpp')}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus-manifest', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    result = audit(args.corpus_manifest)
    result = compact_result(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ('integrity', 'supportedRows', 'sameFloor', 'candidateMiscCopyGate', 'deterministicMiscReplay', 'decision')}, sort_keys=True))


if __name__ == '__main__':
    main()
