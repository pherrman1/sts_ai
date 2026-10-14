#!/usr/bin/env python3
"""Strict prospective selective OOC audit analysis; never executes games."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

CANARY = 97151001
COHORT = list(range(97151010, 97151018))
PRIOR = 'ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228'
NATIVE_CTM_HASHES = {'combat_transition_deepsets_pathb_a20_lizard.native': 'ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b',
                    'combat_transition_near_full_escape_pathb_a20.native': 'e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d'}
CTM = '00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea'
PHASES = {'search': range(1), 'rescore': range(8), 'matched': range(8, 4096), 'reference': range(16)}
LIMITS = {'parentCpu': 200, 'childrenCpu': 1200, 'wall': 1800, 'workers': 2, 'attempts': 9}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode(text):
    def finite_float(token):
        value = float(token); require(math.isfinite(value), 'nonfinite JSON'); return value
    return json.loads(text, object_pairs_hook=pairs, parse_float=finite_float, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(path):
    return decode(Path(path).read_text())


def streams():
    result = {}
    allocated = set()
    for seed in (CANARY, *COHORT):
        result[str(seed)] = {}
        for act in range(1, 4):
            result[str(seed)][str(act)] = {}
            for phase, indices in PHASES.items():
                values = []
                for r in indices:
                    raw = f'ooc-selective-silver-v1|{seed}|{act}|{phase}|{r}'.encode('ascii')
                    value = int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big')
                    require(value not in allocated, 'derived seed collision')
                    allocated.add(value)
                    values.append(value)
                result[str(seed)][str(act)][phase] = values
    return result


def validate_model_custody(f):
    repo = Path(f['repository']); files = f['artifactFiles']
    manifest = f['ctmManifest']
    require(files.get(manifest) == CTM and sha(manifest) == CTM, 'missing/wrong CTM manifest custody')
    require(read(manifest) == f['spec']['ctmLoadedIdentity'], 'CTM loaded identity join')
    artifacts = f['spec']['sourcePolicy']['model_artifacts']
    require({'floor', 'win', 'ooc_strategic_tok'} <= {x['role'] for x in artifacts}, 'missing source policy models')
    for artifact in artifacts:
        path = str((repo / artifact['path']).resolve())
        require(files.get(path) == artifact['sha256'] and sha(path) == artifact['sha256'], 'source policy model custody')
    for name, digest in NATIVE_CTM_HASHES.items():
        path = str((repo / 'selfplay/models' / name).resolve())
        require(files.get(path) == digest and sha(path) == digest, 'native CTM custody')


def validate_freeze(path):
    f = read(path)
    require(f['schemaVersion'] == 'ooc_selective_silver_freeze_v1', 'wrong freeze')
    require(f['canarySeed'] == CANARY and f['cohortSeeds'] == COHORT and f['limits'] == LIMITS, 'wrong panel/caps')
    require(set(f['outputs']) == set(map(str, (CANARY, *COHORT))), 'wrong output panel')
    require(len(set(f['outputs'].values())) == 9, 'duplicate prefixes')
    repo = Path(f['repository'])
    required = [f['binary'], f['plan'], f['environment']['STS_SILVER_ROOT_PRIOR'], str(Path(__file__).resolve()),
                str(repo / 'tools/seed_guard.sh'), str(repo / 'docs/experiments/evidence/ooc_selective_silver_audit_20261014/run.py'),
                str(repo / 'docs/experiments/evidence/ooc_selective_silver_audit_20261014/PROTOCOL.md')]
    require(all(path in f['artifactFiles'] for path in required), 'missing frozen dependency')
    fixed = {'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'STS_FAIR': '1', 'STS_NATIVE_OOC': '1',
             'STS_SILVER_EXACT_ROOT_BUDGETS': '1', 'STS_SILVER_ROOT_PRIOR_SCOPE': 'override',
             'STS_SILVER_ROOT_PRIOR_WEIGHT': '400', 'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '4096',
             'STS_OOC_MCTS_LEAF_VALUE': 'native', 'STS_OOC_MCTS_LEAF_COMBATS': '3', 'STS_OOC_MCTS_EARLY_STOP': '0',
             'STS_OOC_MCTS_GAP_STOP_20': '0', 'STS_OOC_MCTS_TREE_RULES': '1', 'STS_OOC_MCTS_MERGE_OUTCOMES': '1',
             'STS_OOC_MCTS_ROLLOUT_SHOP': 'greedy', 'STS_COLLECT_KEYS': '0', 'STS_STOP_AFTER_ACT': '3',
             'STS_EXECUTABLE_GIT_SHA': f['producerGitSha']}
    require(all(f['environment'].get(k) == v for k, v in fixed.items()), 'wrong frozen environment')
    for artifact, digest in f['artifactFiles'].items():
        require(sha(artifact) == digest, f'frozen artifact changed: {artifact}')
    require(f['artifactFiles'][f['binary']] == f['binarySha256'], 'binary custody')
    require(f['artifactFiles'][f['environment']['STS_SILVER_ROOT_PRIOR']] == PRIOR, 'prior custody')
    require(f['ctmManifestSha256'] == CTM, 'CTM custody')
    validate_model_custody(f)
    plan = read(f['plan'])
    require(plan == {'schemaVersion': 'ooc_selective_silver_plan_v1', 'canarySeed': CANARY,
                     'streams': streams(), 'ctmLoadedIdentity': f['spec']['ctmLoadedIdentity']}, 'wrong stream plan')
    return f


def number(value, label, lower=0, upper=None):
    require(type(value) in (int, float) and math.isfinite(value) and value >= lower
            and (upper is None or value <= upper), f'invalid {label}')
    return value


def result(value):
    require(set(value) == {'value', 'terminal', 'hp', 'maxHp', 'floor', 'combats', 'steps', 'evaluatorCpuSeconds'}, 'continuation shape')
    number(value['value'], 'return', 0, 1)
    for key in ('hp', 'maxHp', 'floor', 'combats', 'steps'):
        require(type(value[key]) is int, f'noninteger {key}')
    require(type(value['terminal']) is bool and (value['terminal'] or value['combats'] >= 3), 'checkpoint horizon mismatch')
    require(0 <= value['steps'] <= 1024 and 0 <= value['combats'] <= value['steps']
            and 0 <= value['floor'] <= 60 and 0 <= value['hp'] <= value['maxHp'] and value['maxHp'] > 0, 'endpoint/work bounds')
    require(not value['terminal'] or value['value'] in (0, 1), 'fractional terminal return')
    require(value['hp'] > 0 or (value['terminal'] and value['value'] == 0), 'zero HP without death')
    number(value['evaluatorCpuSeconds'], 'evaluator CPU', 0, 60)


def draw(row):
    require(set(row) == {'result', 'parentCpuSeconds', 'childCpuSeconds', 'k', 'candidate', 'futureSeed'}, 'draw shape')
    result(row['result'])
    number(row['parentCpuSeconds'], 'parent transport CPU', 0, 200)
    number(row['childCpuSeconds'], 'child CPU', 0, 60.02)
    require(row['result']['evaluatorCpuSeconds'] <= row['childCpuSeconds'] + .02, 'evaluator/reaped CPU mismatch')


def wrapper(value, cap=60):
    require(set(value) == {'result', 'parentCpuSeconds', 'childCpuSeconds'}, 'fork wrapper shape')
    number(value['parentCpuSeconds'], 'fork parent CPU', 0, 200)
    number(value['childCpuSeconds'], 'fork child CPU', 0, cap + .02)


def job(f, seed, digest):
    prefix = f['outputs'][str(seed)]
    receipt = read(prefix + '.receipt.json')
    argv = ['bash', str(Path(f['repository']) / 'tools/seed_guard.sh'), f['binary'],
            'oocselectivesilvergen', '1', str(seed), f['plan'], prefix + '.jsonl']
    require(receipt['argv'] == argv and receipt['freezeSha256'] == digest and receipt['seed'] == seed, 'job custody/command')
    require(receipt['returncode'] == 0 and not receipt['timedOut'], 'failed source process')
    number(receipt['cpuSeconds'], 'whole process CPU', 0, 1400)
    number(receipt['wallSeconds'], 'wall', 0, 1800)
    time_fields = Path(prefix + '.time').read_text().splitlines()[-1].split()
    require(len(time_fields) == 3, 'invalid GNU-time record')
    measured_cpu = sum(number(float(x), 'GNU-time CPU') for x in time_fields[:2])
    require(math.isclose(measured_cpu, receipt['cpuSeconds'], abs_tol=1e-9), 'receipt/GNU-time CPU mismatch')
    elapsed = number(float(time_fields[2]), 'GNU-time wall', 0, 1800)
    require(elapsed == receipt['gnuWallSeconds'] and -.02 <= receipt['wallSeconds'] - elapsed <= 2., 'receipt/GNU-time wall mismatch')
    require(read(prefix + '.started.json') == {'argv': argv, 'freezeSha256': digest}, 'launch latch')
    raw = Path(prefix + '.jsonl').read_text()
    require(raw.endswith('\n'), 'truncated data')
    rows = [decode(s) for s in raw.splitlines()]
    require(rows and rows[0]['type'] == 'header' and rows[-1]['type'] == 'source_complete', 'incomplete source')
    header, end = rows[0], rows[-1]
    require(header['seed'] == seed and header['planSha256'] == sha(f['plan'])
            and header['producerGitSha'] == f['producerGitSha']
            and header['policy'] == f['spec']['sourcePolicy']
            and header['ctmLoadedIdentity'] == f['spec']['ctmLoadedIdentity'], 'loaded identity/policy mismatch')
    number(end['parentCpuSeconds'], 'parent CPU', 0, 200)
    number(end['childCpuSeconds'], 'children CPU', 0, 1200)
    require(end['parentCpuSeconds'] + end['childCpuSeconds'] <= receipt['cpuSeconds'] + .05, 'process CPU sum mismatch')
    roots = [r for r in rows if r['type'] == 'root_complete']
    require(roots == end['source']['roots'] and 1 <= len(roots) <= 3, 'zero/mismatched source root panel')
    settled_children = number(header['provenanceChildCpuSeconds'], 'provenance child CPU', 0, 1200)
    settled_parent = 0.
    seen, expected = set(), []
    for i, action in enumerate(end['source']['actions']):
        act = action['act']
        # ScreenState::MAP_SCREEN is pinned independently in the freeze by seed-free spec.
        if action['screen'] == f['mapScreenEnum'] and action['floor'] >= 3 and action['legalCount'] >= 2 and action['realCombatsInAct'] >= 1 and act not in seen:
            expected.append((act, i)); seen.add(act)
    require([(r['act'], r['decisionOrdinal']) for r in roots] == expected, 'chronological slot selection mismatch')
    plan = read(f['plan'])['streams'][str(seed)]
    metrics = []
    for root in roots:
        require(root['seed'] == seed and root['floor'] >= 3 and len(set(root['keys'])) == 2 and len(set(root['bits'])) == 2, 'root identity')
        for name in ('baseline', 'baselineControl'):
            wrapper(root[name]); settled_children += root[name]['childCpuSeconds']; settled_parent += root[name]['parentCpuSeconds']
        require(root['baseline']['result'] == root['baselineControl']['result'], 'baseline parity')
        base = root['baseline']['result']
        require(base['selectedKey'] == root['keys'][0] and base['work']['simulations'] == base['work']['attempts'] == 4096, 'wrong baseline work/choice')
        ranked = sorted(base['actions'], key=lambda a: (-a['visits'], a['key']))
        require(next(a['key'] for a in ranked if a['key'] != root['keys'][0]) == root['keys'][1], 'runner-up mismatch')
        selected = {'baseline': 0}
        phases = plan[str(root['act'])]
        for selector, n, phase in (('ctm8', 8, 'rescore'), ('silver8', 8, 'rescore'), ('reference', 16, 'reference')):
            arm = root[selector]
            require(len(arm['rows']) == n * 2, 'incomplete fixed rescorer')
            sums = [0., 0.]
            for i, row in enumerate(arm['rows']):
                draw(row)
                require(row['k'] == i // 2 and row['candidate'] == i % 2 and row['futureSeed'] == phases[phase][i // 2], 'draw identity/seed')
                sums[i % 2] += row['result']['value']
            means = [v / n for v in sums]
            require(arm['means'] == means and arm['selected'] == int(means[1] > means[0]), 'rescore aggregate/tie mismatch')
            number(arm['parentCpuSeconds'], 'selector parent CPU', 0, 200)
            number(arm['childCpuSeconds'], 'selector child CPU', 0, 1200)
            require(math.isclose(arm['childCpuSeconds'], sum(r['childCpuSeconds'] for r in arm['rows']), abs_tol=1e-6), 'selector child settlement')
            require(arm['parentCpuSeconds'] + 1e-6 >= sum(r['parentCpuSeconds'] for r in arm['rows']), 'selector parent settlement')
            settled_children += arm['childCpuSeconds']; settled_parent += arm['parentCpuSeconds']
            selected[selector] = arm['selected']
        matched = root['matched']; m = matched['result']; n = m['count']
        require(type(n) is int and 8 <= n <= 4096 and len(m['rows']) == n, 'matched count')
        sums = [0., 0.]
        silver_cost = root['silver8']['parentCpuSeconds'] + root['silver8']['childCpuSeconds']
        target = min(silver_cost, 50.)
        previous_cpu = 0.
        for k, row in enumerate(m['rows']):
            number(row['cpuAfterPair'], 'matched batch CPU', previous_cpu, 60)
            require(k < 8 or previous_cpu < target, 'matched continued after CPU stop')
            previous_cpu = row['cpuAfterPair']
            require(row['k'] == k and row['futureSeed'] == (phases['rescore'][k] if k < 8 else phases['matched'][k - 8]), 'matched stream identity')
            require(len(row['results']) == 2, 'incomplete matched pair')
            for a, value in enumerate(row['results']):
                result(value); sums[a] += value['value']
                if k < 8:
                    baseline_value = root['ctm8']['rows'][k * 2 + a]['result']
                    require({x: y for x, y in value.items() if x != 'evaluatorCpuSeconds'} == {x: y for x, y in baseline_value.items() if x != 'evaluatorCpuSeconds'}, 'CTM prefix mismatch')
        require(m['means'] == [v / n for v in sums] and m['selected'] == int(sums[1] > sums[0]), 'matched aggregate')
        wrapper(matched)
        number(m['evaluatorCpuSeconds'], 'matched evaluator CPU', 0, 60)
        require(m['evaluatorCpuSeconds'] <= matched['childCpuSeconds'] + .02, 'matched/reaped CPU mismatch')
        require(sum(v['evaluatorCpuSeconds'] for row in m['rows'] for v in row['results']) <= m['evaluatorCpuSeconds'] + 1e-6, 'matched evaluator settlement')
        settled_children += matched['childCpuSeconds']; settled_parent += matched['parentCpuSeconds']
        silver_cost = root['silver8']['parentCpuSeconds'] + root['silver8']['childCpuSeconds']
        target = min(silver_cost, 50.)
        require(previous_cpu <= m['evaluatorCpuSeconds'] + 1e-6, 'matched last pair CPU')
        require(n == 4096 or previous_cpu >= target, 'matched premature CPU stop')
        ratio = (matched['parentCpuSeconds'] + matched['childCpuSeconds']) / silver_cost
        valid = .9 <= ratio <= 1.1 and n < 4096
        require(math.isclose(ratio, root['matchedCostRatio'], rel_tol=1e-12) and valid == root['matchedCostValid'], 'matched budget gate')
        selected['matched'] = m['selected']
        reference = root['reference']['means']
        metrics.append({'act': root['act'], 'floor': root['floor'], 'choices': selected,
                        'referenceUtility': {name: reference[a] for name, a in selected.items()},
                        'matchedCostValid': valid, 'matchedCostRatio': ratio, 'matchedCpuOvershoot': previous_cpu - target,
                        'matchedPairs': n,
                        'selectorCpu': {'ctm8': root['ctm8']['parentCpuSeconds'] + root['ctm8']['childCpuSeconds'], 'silver8': silver_cost, 'matched': matched['parentCpuSeconds'] + matched['childCpuSeconds']}})
    if seed == CANARY:
        controls = [r for r in rows if r['type'] == 'source_control_complete']
        require(len(controls) == 1, 'canary source control missing')
        wrapper(controls[0]['result'], 200)
        settled_children += controls[0]['result']['childCpuSeconds']; settled_parent += controls[0]['result']['parentCpuSeconds']
        x = dict(end['source']); y = dict(controls[0]['result']['result']); x.pop('roots'); y.pop('roots')
        require(x == y, 'canary source trajectory parity')
    require(math.isclose(settled_children, end['childCpuSeconds'], abs_tol=1e-5), 'source child settlement')
    require(settled_parent <= end['parentCpuSeconds'] + 1e-5, 'source parent settlement')
    event_types = ['header']
    if seed == CANARY:
        event_types += ['source_control_start', 'source_control_complete']
    for root in roots:
        event_types += ['root_start'] + ['evaluation_start', 'evaluation_complete'] * 32
        event_types += ['matched_start'] + ['evaluation_start', 'evaluation_complete'] * 32 + ['root_complete']
    event_types += ['source_complete']
    require([r['type'] for r in rows] == event_types, 'progress order/count mismatch')
    lookup = {r['act']: r for r in roots}
    for row in rows:
        if row['type'] == 'evaluation_complete':
            d = row['row']
            require(d == lookup[row['act']][row['selector']]['rows'][d['k'] * 2 + d['candidate']], 'progress retained draw mismatch')
        elif row['type'] == 'matched_start':
            arm = lookup[row['act']]['silver8']
            require(row['targetCpuSeconds'] == min(50., arm['parentCpuSeconds'] + arm['childCpuSeconds']), 'matched target mismatch')
        elif row['type'] == 'root_start':
            require(row['seed'] == seed and row['decisionOrdinal'] == lookup[row['act']]['decisionOrdinal'], 'root-start identity')
    # The event sequence must be complete and bijective with all retained evaluation records.
    starts = [(r['act'], r['selector'], r['k'], r['candidate']) for r in rows if r['type'] == 'evaluation_start']
    completes = [(r['act'], r['selector'], r['row']['k'], r['row']['candidate']) for r in rows if r['type'] == 'evaluation_complete']
    expected_draws = [(r['act'], name, k, a) for r in roots for name, n in (('ctm8', 8), ('silver8', 8), ('reference', 16)) for k in range(n) for a in range(2)]
    require(starts == completes == expected_draws, 'progress sequence/completeness')
    require([r['act'] for r in rows if r['type'] == 'root_start'] == [r['act'] for r in roots], 'root progress mismatch')
    require([r['act'] for r in rows if r['type'] == 'matched_start'] == [r['act'] for r in roots], 'matched progress mismatch')
    require(all(r['type'] in {'header', 'source_control_start', 'source_control_complete', 'root_start', 'evaluation_start', 'evaluation_complete', 'matched_start', 'root_complete', 'source_complete'} for r in rows), 'extra/error record')
    return {'seed': seed, 'roots': metrics, 'receipt': receipt, 'absentActs': sorted({1, 2, 3} - seen)}


def bootstrap(values):
    rng = random.Random(97151099)
    estimates = []
    for _ in range(5000):
        estimates.append(statistics.mean(values[rng.randrange(len(values))] for _ in values))
    estimates.sort()
    def percentile(q):
        x = q * (len(estimates) - 1); lo = int(x)
        return estimates[lo] + (estimates[min(lo + 1, len(estimates) - 1)] - estimates[lo]) * (x - lo)
    return {'estimate': statistics.mean(values), 'interval95': [percentile(.025), percentile(.975)]}


def improvement_flags(effects, matched_valid):
    primary = effects['silver8_minus_baseline']['interval95'][0] > 0
    return {'directionalImprovement': primary,
            'matchedComputeImprovement': primary and matched_valid and effects['silver8_minus_matched']['interval95'][0] > 0}


def analyze(freeze_path, canary=False):
    f = validate_freeze(freeze_path); digest = sha(freeze_path)
    seeds = [CANARY] if canary else COHORT
    phase = 'canary' if canary else 'cohort'
    require(read(Path(freeze_path).parent / f'phase-{phase}.started.json') == {'freezeSha256': digest}, 'phase latch')
    if not canary:
        c = read(Path(freeze_path).parent / 'canary-report.json')
        require(c['verdict'] == 'CANARY_VALID' and c['freezeSha256'] == digest, 'canary prerequisite')
        job(f, CANARY, digest)
    jobs = [job(f, seed, digest) for seed in seeds]
    effects = {}
    for left, right in (('silver8', 'baseline'), ('ctm8', 'baseline'), ('matched', 'baseline'), ('silver8', 'ctm8'), ('silver8', 'matched')):
        values = [statistics.mean(r['referenceUtility'][left] - r['referenceUtility'][right] for r in j['roots']) for j in jobs]
        effects[f'{left}_minus_{right}'] = bootstrap(values)
    matched_valid = all(r['matchedCostValid'] for j in jobs for r in j['roots'])
    disagreements = {name: sum(r['choices'][name] != r['choices']['baseline'] for j in jobs for r in j['roots']) for name in ('ctm8', 'silver8', 'matched')}
    coverage = {str(a): sum(any(r['act'] == a for r in j['roots']) for j in jobs) for a in (1, 2, 3)}
    custody = {str(Path(freeze_path).resolve()): digest}
    for seed in (CANARY, *([] if canary else COHORT)):
        for suffix in ('jsonl', 'receipt.json', 'started.json', 'log', 'time'):
            path = f['outputs'][str(seed)] + '.' + suffix; custody[path] = sha(path)
    return {'schemaVersion': 'ooc_selective_silver_analysis_v1', 'verdict': 'CANARY_VALID' if canary else 'DECISION_AUDIT_MEASURED',
            'freezeSha256': digest, 'sourceSeeds': seeds, 'canaryExcluded': not canary, 'jobs': jobs, 'effects': effects,
            'matchedComputeValid': matched_valid, **improvement_flags(effects, matched_valid),
            'coverage': coverage, 'disagreementsWithBaseline': disagreements, 'adequateLaterActs': coverage['2'] >= 4 and coverage['3'] >= 2, 'inputHashes': custody,
            'limitations': ['Eight-source conditional pilot, two-candidate MAP choices and nominal intervals.',
                            'Held-out native requested-three-combat MAP-checkpoint surrogate reference, not eventual run wins.',
                            'Extra CTM control is continuation rescoring, not extra MCTS or all-action optimal play.']}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('freeze', type=Path); parser.add_argument('out', type=Path); parser.add_argument('--canary', action='store_true'); args = parser.parse_args()
    with args.out.open('x') as stream:
        try:
            report = analyze(args.freeze, args.canary)
        except (OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
            report = {'schemaVersion': 'ooc_selective_silver_analysis_v1', 'verdict': 'INVALID_OR_INSUFFICIENT', 'reason': str(exc), 'freezeSha256': sha(args.freeze)}
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'verdict': report['verdict'], 'reason': report.get('reason')}))
    return int(report['verdict'] == 'INVALID_OR_INSUFFICIENT')


if __name__ == '__main__':
    raise SystemExit(main())
