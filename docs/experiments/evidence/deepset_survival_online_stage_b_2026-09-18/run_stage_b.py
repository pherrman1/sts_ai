import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

ROOT = Path('/home/philippherrmann/.codex/worktrees/529c/sts_lightspeed')
OUT = Path(__file__).resolve().parent
SHA = '471ba9a119de2a4f6ae691329467acae1b0f70a0'
PROBE = ROOT / 'build/linux-gcc-release-ccache/combat_transition_runtime_probe'
BINARY = ROOT / 'build/linux-gcc-release-ccache/one_combat'
CONTROL = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
CANDIDATE = OUT / 'candidate.native'
OLD = ROOT / 'docs/experiments/evidence/combat_transition_v2_ooc_mcts_pair64_2026-09-15'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as stream:
        stream.write(json.dumps(data, indent=2) + '\n')


def summary(values):
    return dict(values=values, median=statistics.median(values), mean=statistics.mean(values),
                minimum=min(values), maximum=max(values))


def verify():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == SHA
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
    for path, expected in json.loads((OUT / 'freeze.json').read_text())['hashes'].items():
        assert digest(path) == expected, path


def execute(command, env, stem, timeout=1800):
    verify()
    receipt = dict(command=command, environment=env, frozenSha=SHA, runnerSha256=digest(__file__))
    save(OUT / (stem + '.command.json'), receipt)
    start = time.monotonic()
    print('START', stem, flush=True)
    with (OUT / (stem + '.stdout')).open('x') as stdout, (OUT / (stem + '.stderr')).open('x') as stderr:
        subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
    print('COMPLETE', stem, 'wall', time.monotonic() - start, flush=True)


def main():
    verify()
    reference = json.loads((OLD / 'plan.json').read_text())
    common = {
        'STS_FAIR': '1', 'STS_SEARCHER3': '0', 'STS_SILVER_SEARCH': '1',
        'STS_SILVER_EXACT_ROOT_BUDGETS': '1', 'STS_SILVER_REUSE_CAP_MODE': 'allocated',
        'STS_SILVER_ADAPTIVE': '0', 'STS_SILVER_VNET_LEAF_DIRECT': '0',
        'STS_SILVER_TELEMETRY': '1', 'STS_NATIVE_OOC': '1', 'STS_OOC_STRATEGIC_REST': '1',
        'STS_OOC_STRATEGIC_EVENT': '1', 'STS_OOC_STRATEGIC_SHOP': '1',
        'STS_OOC_STRATEGIC_TREASURE': '1', 'STS_OOC_STRATEGIC_BOSS_RELIC': '1',
        'STS_OOC_STRATEGIC_MARGIN': '1.0', 'STS_STOP_AFTER_ACT': '3', 'STS_COLLECT_KEYS': '0',
        'OMP_NUM_THREADS': '1', 'STS_OOC_MCTS': '1',
        'STS_EXECUTABLE_GIT_SHA': SHA,
        'STS_OOC_STRATEGIC_TOK_NN': str(ROOT / 'selfplay/models/ooc_strategic_tok_final.native'),
        **reference['oocMctsProfile'], **reference['explicitControls']}
    assert digest(common['STS_OOC_STRATEGIC_TOK_NN']) == reference['strategicModelSha256']
    for path, expected in reference['treeModelSha256'].items():
        assert digest(ROOT / path) == expected
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('STS_', 'STRATEGIC_', 'OMP_', 'MKL_', 'OPENBLAS_'))}
    environment.update(common)
    spec = importlib.util.spec_from_file_location('prior_runner', OLD / 'run.py')
    prior_runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior_runner)
    arms = dict(control=CONTROL, candidate=CANDIDATE)
    plan = dict(frozenSha=SHA, stage='B only', candidateHash=digest(CANDIDATE),
        nativeRepetitions=4, nativeFixtures='first 12 supported non-TEST Stage-A rows',
        e2eSeeds=[12002032, 12002033], e2eRepetitionsPerSeed=2, fullRunInvocations=8,
        ordering='AB for seed0/repeat0 and seed1/repeat1; BA for other blocks',
        criterion='candidate/control median user+system CPU per full run <=0.90',
        commonEnvironment=common, controls='same executable, models except survival, seed and search profile',
        inferenceMetrics=['survival', 'referenceSampleNs', 'preparedSampleNs', 'preparationNs'],
        deviations=['OMP_NUM_THREADS=1 for isolated per-run CPU timing, instead of PR187 12-way outer parallelism',
                    'historical PR187 first two seeds reused only for timing; no fresh gameplay cohort launched'],
        inventory='Stage A has no timing. PR187 timing uses old binaries and wall time, not current CPU. Neither qualifies as Stage B.',
        runtimeDifference='Current main includes boss-leaf fixes after PR187; preserve current-main code and use unchanged native leaf-value profile.',
        gameplayGateRun=False, testInferenceRows=0, runnerSha256=digest(__file__))
    save(OUT / 'stage-b-plan.json', plan)
    fixtures = ROOT / 'docs/experiments/evidence/deepset_survival_online_stage_a_2026-09-17/fixtures.jsonl'
    native_fixture = OUT / 'native-timing-fixtures.jsonl'
    with native_fixture.open('x') as stream:
        stream.write('\n'.join(fixtures.read_text().splitlines()[:12]) + '\n')
    metrics = {arm: {key: [] for key in plan['inferenceMetrics']} for arm in arms}
    for repeat in range(4):
        for arm in (('control', 'candidate') if repeat % 2 == 0 else ('candidate', 'control')):
            stem = f'native-{repeat}-{arm}'
            execute(['bash', str(ROOT / 'tools/seed_guard.sh'), str(PROBE), str(arms[arm]),
                     str(native_fixture), 'smoke-and-parity'], environment, stem)
            rows = [json.loads(line) for line in (OUT / (stem + '.stdout')).read_text().splitlines()]
            assert len(rows) == 12 and all(row['supported'] for row in rows)
            for row in rows:
                assert row['preparedParity']['fullPersistentStateEqual'] and row['preparedParity']['plannerRngPostEqual']
                for key in plan['inferenceMetrics']:
                    value = row['componentsNs']['survival'] if key == 'survival' else row['preparedParity'][key]
                    metrics[arm][key].append(value)
    native = {arm: {key: summary(values) for key, values in entries.items()} for arm, entries in metrics.items()}
    save(OUT / 'native-timing.json', native)
    outcomes = []
    for repeat in range(2):
        for index, seed in enumerate(plan['e2eSeeds']):
            for arm in (('control', 'candidate') if (repeat + index) % 2 == 0 else ('candidate', 'control')):
                stem = f'e2e-{repeat}-{seed}-{arm}'
                result = OUT / (stem + '.csv')
                trace = OUT / (stem + '.mcts.csv')
                env = environment | {'STS_OOC_MCTS_COMBAT_MODEL': str(arms[arm]), 'STS_OOC_MCTS_TRACE': str(trace)}
                command = ['/usr/bin/time', '-f', '%U %S %e', '-o', str(OUT / (stem + '.time')),
                           'bash', str(ROOT / 'tools/seed_guard.sh'), str(BINARY), 'bestbench',
                           '10000', '1', '0', str(seed), str(result)]
                execute(command, env, stem)
                rows = list(csv.DictReader(result.open()))
                assert len(rows) == 1 and int(rows[0]['seed']) == seed
                records = [json.loads(line) for line in Path(str(result) + '.meta.json').read_text().splitlines()]
                assert len(records) == 1
                prior_runner.validate_record(records[0], {'sourceSha': SHA},
                    {'combatSimulations': 10000, 'ompThreads': 1}, seed, 1, result)
                prior_runner.validate_canary_log(OUT / (stem + '.stdout'), Path(common['STS_OOC_STRATEGIC_TOK_NN']),
                    arms[arm], {'id': arm}, plan)
                telemetry = list(csv.DictReader(trace.open()))
                assert len(telemetry) == 1 and int(telemetry[0]['seed']) == seed
                reasons = [json.loads(line) for line in Path(str(trace) + '.support.jsonl').read_text().splitlines()]
                assert len(reasons) == 1 and int(reasons[0]['seed']) == seed
                assert int(telemetry[0]['continuationLimitAborts']) == 0
                user, system, wall = map(float, (OUT / (stem + '.time')).read_text().split())
                outcomes.append(dict(arm=arm, seed=seed, repeat=repeat, cpu=user+system, user=user,
                    system=system, wall=wall, outcome=rows[0], telemetry=telemetry[0], support=reasons[0]))
                save(OUT / (stem + '.receipt.json'), outcomes[-1])
    cpu = {arm: summary([row['cpu'] for row in outcomes if row['arm'] == arm]) for arm in arms}
    ratio = cpu['candidate']['median'] / cpu['control']['median']
    result = dict(frozenSha=SHA, candidateSha256=digest(CANDIDATE), native=native, runs=outcomes,
        cpu=cpu, medianCpuRatio=ratio, medianCpuReductionPercent=100*(1-ratio),
        materialSpeedScreenPassed=ratio <= .90, gameplayGateRun=False,
        interpretation='Two historical seeds, repeated matched timings; not a fresh gameplay quality result.')
    save(OUT / 'stage-b-results.json', result)
    verify()
    print('STAGE_B_COMPLETE', json.dumps(cpu), 'ratio', ratio, flush=True)


if __name__ == '__main__':
    main()
