#!/usr/bin/env python3
"""Strict analysis for the prospective fixed larger A20 teacher comparison."""
import copy
import importlib.util
import math
from pathlib import Path
import random
import statistics

spec = importlib.util.spec_from_file_location('teacher_core_large', Path(__file__).with_name('analyze_a20_teachers.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
CANARY = 97150901
COHORT = list(range(97150910, 97150942))
ANCHORS = COHORT[::4]
MAIN = {'plain2k': (2000, False), 'prior2k': (2000, True)}
ALL = dict(core.ARM_CONFIG)
ALL_CONTRASTS = dict(core.CONTRASTS)
LIMITS = {'cpuSecondsPerSource': 1200, 'wallSecondsPerSource': 1800,
          'maxConcurrentSources': 4, 'maxAttemptedSources': 33}
BOOTSTRAP = {'replicates': 5000, 'seed': 97150999, 'intervalPercentiles': [2.5, 97.5]}
COVERAGE = {'act2BossSourceClusters': 12, 'act3BossSourceClusters': 8}
PRIOR_HASH = 'ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228'
EXTRA = ('anchorSeeds', 'anchorTeacher', 'anchorEnvironment', 'anchorArms', 'bootstrap', 'coverageMinimum')
core.CANARY, core.COHORT = CANARY, COHORT
core.FREEZE_SCHEMA = 'a20_teacher_comparison_large_freeze_v1'
core.RUNTIME_SCHEMA = 'ctm_vs_silver_teacher_a20_large_v1'
core.ARM_SET = 'teacher_a20_large'
core.RUNNER_FILE, core.PROTOCOL_FILE = 'run_large.py', 'PROTOCOL-LARGE.md'
core.REPLICATES, core.RESOURCE_LIMITS = 16, LIMITS
core.CTM_HASHES['manifest.json'] = '00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea'


def configure(anchor=False):
    core.ARM_CONFIG = ALL if anchor else MAIN
    core.FORECASTERS = ('ctm', *core.ARM_CONFIG)
    core.CONTRASTS = ALL_CONTRASTS if anchor else {'prior2k_minus_plain2k': ('prior2k', 'plain2k')}


def arms(anchor=False):
    return [dict(name=n, budget=b, prior=p, replicates=16) for n, (b, p) in (ALL if anchor else MAIN).items()]


def validate_freeze(freeze):
    configure()
    base = {k: v for k, v in freeze.items() if k not in EXTRA}
    teacher = core.validate_freeze(base)
    core.require(set(freeze) == set(base) | set(EXTRA), 'missing larger-study fields')
    core.require(freeze['anchorSeeds'] == ANCHORS and freeze['anchorArms'] == arms(True), 'wrong anchor panel')
    core.require(freeze['bootstrap'] == BOOTSTRAP and freeze['coverageMinimum'] == COVERAGE, 'wrong analysis plan')
    core.require(freeze['priorIdentity']['generation'] == 6 and freeze['priorIdentity']['sha256'] == PRIOR_HASH,
                 'requires exact gen6 E')
    env = freeze['environment']
    core.require(env.get('STS_CTMSILVER_LARGE_ANCHOR') == '0', 'wrong main environment')
    core.require(freeze['anchorEnvironment'] == env | {'STS_CTMSILVER_LARGE_ANCHOR': '1'}, 'anchor environment differs')
    for path in (str(Path(__file__).resolve()), freeze['anchorTeacher'],
                 str(Path(freeze['repository']) / 'docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py')):
        core.require(path in freeze['artifactFiles'], 'unfrozen larger-study dependency')
    anchor = core.read_json(freeze['anchorTeacher'])
    expected = teacher | {'teacher_id': teacher['teacher_id'] + '-anchor', 'environment': freeze['anchorEnvironment']}
    core.require(anchor == expected, 'anchor teacher differs beyond dataset flag/id')
    return teacher, anchor


def job(freeze, seed, digest, teachers):
    anchor = seed == CANARY or seed in ANCHORS
    configure(anchor)
    f = dict(freeze)
    if anchor:
        f.update(teacher=freeze['anchorTeacher'], environment=freeze['anchorEnvironment'], arms=freeze['anchorArms'])
    return core.validate_job(f['outputs'][str(seed)], seed, f, digest, teachers[int(anchor)])


def trim(rows):
    result = copy.deepcopy(rows)
    for r in result:
        for field in ('forecast', 'repeat', 'cost'):
            r[field] = {k: v for k, v in r[field].items() if k in ('ctm', *MAIN)}
        r['controllerContrasts'] = {k: v for k, v in r['controllerContrasts'].items() if k == 'prior2k_minus_plain2k'}
    return result


def bootstrap(summaries):
    """Paired resampling of independent source clusters; all selected fights stay together."""
    names = core.FORECASTERS
    vectors = {}
    for name in names:
        for metric in ('hpSquaredError', 'deathBrier', 'hpBias', 'deathBias'):
            vectors[f'{name}.{metric}'] = [s['forecast'][name][metric] for s in summaries]
        if name != 'ctm':
            vectors[f'{name}.forecastCpuSeconds'] = [s['cost'][name]['forecastCpuSeconds'] for s in summaries]
    for contrast, (a, b) in core.CONTRASTS.items():
        for metric in ('hpSquaredError', 'deathBrier'):
            vectors[f'{contrast}.forecast.{metric}'] = [s['forecast'][a][metric] - s['forecast'][b][metric] for s in summaries]
        for metric in ('rawHp', 'death', 'cpuSeconds'):
            vectors[f'{contrast}.controller.{metric}'] = [s['controllerContrasts'][contrast][metric] for s in summaries]
    # Direct CTM-versus-main fidelity contrasts share exactly the same source resamples.
    for name in names[1:]:
        for metric in ('hpSquaredError', 'deathBrier'):
            vectors[f'{name}_minus_ctm.forecast.{metric}'] = [s['forecast'][name][metric] - s['forecast']['ctm'][metric] for s in summaries]
    rng = random.Random(BOOTSTRAP['seed'])
    draws = {key: [] for key in vectors}
    for _ in range(BOOTSTRAP['replicates']):
        indices = [rng.randrange(len(summaries)) for _ in summaries]
        for key, values in vectors.items():
            draws[key].append(statistics.mean(values[i] for i in indices))
    def quantile(values, q):
        values = sorted(values)
        position = (len(values) - 1) * q
        lo = int(position)
        return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (position - lo)
    result = {key: {'estimate': statistics.mean(vectors[key]), 'interval95': [quantile(vals, .025), quantile(vals, .975)]}
              for key, vals in draws.items()}
    for name in names:
        mse = result[f'{name}.hpSquaredError']
        result[f'{name}.hpRmse'] = {'estimate': math.sqrt(mse['estimate']), 'interval95': list(map(math.sqrt, mse['interval95']))}
    return {'sourceClusters': len(summaries), 'method': BOOTSTRAP, 'metrics': result}


def panel(jobs, anchor=False):
    configure(anchor)
    rows_by_source = {str(j['seed']): j['metrics'] if anchor else trim(j['metrics']) for j in jobs}
    summaries = {seed: core.summarize_states(rows) for seed, rows in rows_by_source.items()}
    rows = [r for rs in rows_by_source.values() for r in rs]
    return {'sourceSeeds': [j['seed'] for j in jobs], 'matchedStates': len(rows), 'perSource': summaries,
            'equalSourceMeans': core.equal_source_summary(list(summaries.values())),
            'pooledStateMeans': core.summarize_states(rows), 'clusterBootstrap': bootstrap(list(summaries.values()))}


def analyze(freeze_path, prefixes, canary=False):
    digest = core.sha(freeze_path)
    freeze = core.read_json(freeze_path)
    teachers = validate_freeze(freeze)
    seeds = [CANARY] if canary else COHORT
    normalized = [str(Path(p).resolve()) for p in prefixes]
    core.require(len(normalized) == len(seeds) and set(normalized) == {freeze['outputs'][str(s)] for s in seeds}, 'wrong source panel')
    phase = 'canary' if canary else 'cohort'
    core.require(core.read_json(Path(freeze_path).parent / f'phase-{phase}.started.json') == {'freezeSha256': digest}, 'phase latch mismatch')
    jobs = [job(freeze, seed, digest, teachers) for seed in seeds]
    all_jobs = list(jobs)
    if not canary:
        report = core.read_json(Path(freeze_path).parent / 'canary-report.json')
        core.require(report['verdict'] == 'CANARY_VALID' and report['freezeSha256'] == digest and report['sourceSeeds'] == [CANARY], 'canary mismatch')
        all_jobs.append(job(freeze, CANARY, digest, teachers))
    cpu = sum(j['receipt']['cpuSeconds'] for j in all_jobs)
    core.require(cpu <= LIMITS['cpuSecondsPerSource'] * LIMITS['maxAttemptedSources'], 'aggregate CPU exceeded')
    custody = {str(Path(freeze_path).resolve()): digest}
    for j in all_jobs:
        for extension in ('states.csv', 'arms.csv', 'samples.csv', 'progress.jsonl', 'manifest.json', 'receipt.json', 'started.json', 'log', 'time'):
            path = j['prefix'] + '.' + extension
            custody[path] = core.sha(path)
    coverage = {f'act{act}BossSourceClusters': sum(any(r['act'] == act and r['roomClass'] == 'BOSS' for r in j['metrics']) for j in jobs) for act in (2, 3)}
    result = {'schemaVersion': 'a20_teacher_comparison_large_analysis_v1', 'verdict': 'CANARY_VALID' if canary else 'DESCRIPTIVE_COMPARISON_MEASURED',
              'reasons': [], 'freezeSha256': digest, 'sourceSeeds': seeds, 'canaryExcluded': not canary, 'inputHashes': custody,
              'coverage': coverage | {'adequateLaterActs': all(coverage[k] >= v for k, v in COVERAGE.items())},
              'jobs': jobs, 'execution': {'totalCpuSecondsIncludingExcludedCanary': cpu},
              'limitations': ['Conditional on fixed source policy and selected slots; no gameplay win-rate or default qualification.',
                              'One original-future reference per state; nominal source-bootstrap intervals do not remove reference randomness.',
                              'Categorical scores use 32 CTM draws versus 16 Silver futures; unequal Monte Carlo precision.',
                              'Silver timers measure playoutBattle; CTM expectation and sample timers have different scopes.']}
    if canary:
        result['anchorPanel'] = panel(jobs, True)
    else:
        result['mainPanel'] = panel(jobs)
        result['anchorPanel'] = panel([j for j in jobs if j['seed'] in ANCHORS], True)
    return result


if __name__ == '__main__':
    core.analyze = analyze
    raise SystemExit(core.main())
