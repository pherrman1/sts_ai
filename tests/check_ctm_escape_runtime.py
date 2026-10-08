"""Escape capability (#418 PR7): native loading, Python/native head parity and sampled escapes.

Builds an escape-capable research candidate from the production standard artifact with a
synthetic escape fit, then checks the native probe against tools/ctm_escape.py's NumPy heads.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ctm_escape as e  # noqa: E402

STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
FIXTURES = ROOT / 'tests/fixtures/combat_transition_near_full.jsonl'
CANDIDATE = 'test-escape-candidate'


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    result = subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                            env={**clean, **(env or {})}, cwd=ROOT)
    return result


def smoke_fixtures(path):
    """Near-full fixtures with a Smoke Bomb put into the first free usable slot."""
    rows = []
    for line in FIXTURES.read_text().splitlines()[:30]:
        row = json.loads(line)
        pre, pi = row['pre'], row['predictorInput']
        free = [s for s in range(pre['potionCapacity']) if pre['potions'][s] == 1]
        if e.SMOKE not in pre['potions'] and free:
            slot = free[0]
            pre['potions'][slot] = e.SMOKE
            pre['potionCount'] += 1
            pi['globals']['potionCount'] += 1
            pi['potions'][slot]['potionId'] = e.SMOKE
        row['draws'] = 48
        rows.append(row)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        metadata, tensors = e.read_artifact(STANDARD)
        candidate = directory / 'candidate.native'
        e.write_artifact(candidate, dict(metadata, researchCandidate={'candidateId': CANDIDATE}), tensors)
        rng = np.random.default_rng(20261008)
        fitted = {name: tensors[name] for name in e.HP_TENSORS}
        column = rng.normal(scale=2.0, size=(64, 1)).astype(np.float32)
        fitted['hp.hp.0.weight'] = np.concatenate((tensors['hp.hp.0.weight'], column), 1)
        fitted['escape.escape.weight'] = rng.normal(scale=0.3, size=(1, 64)).astype(np.float32)
        fitted['escape.escape.bias'] = np.asarray([0.5], np.float32)
        checkpoint = directory / 'escape.pt'
        torch.save(dict(tensors=fitted, metadata=dict(schema='ctm_escape_fit_v1', baseArtifactSha256=e.sha256(candidate))), checkpoint)
        escape_path = directory / 'escape.native'
        escape_sha = e.extend(candidate, checkpoint, escape_path)['artifactSha256']
        capability = {'escape': {'checkpointSha256': e.sha256(checkpoint)}}

        def manifest(name, standard_sha, capabilities):
            body = dict(schema='ctm_research_candidate_v3', candidateId=CANDIDATE,
                        domainSha256=metadata['domain']['sha256'],
                        capabilities=capabilities,
                        standard=dict(artifactSha256=standard_sha, sources=metadata['sources']),
                        supportCensus=dict(allSupportedIndexSha256=metadata['supportCensus']['all']['supportedIndexSha256'],
                                           testSupportedIndexSha256=metadata['supportCensus']['TEST']['supportedIndexSha256']),
                        fast=None, activeLizard=None)
            path = directory / name
            path.write_text(json.dumps(body))
            return {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(path),
                    'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}

        env = manifest('escape.json', escape_sha, {'standard': capability, 'fast': {}})
        checks = [
            ('capability_listed', probe(['--identity', escape_path], env), 0, f'identity={CANDIDATE}'),
            ('capability_not_listed', probe(['--identity', escape_path], manifest('none.json', escape_sha, {'standard': {}, 'fast': {}})),
             1, 'capabilities are not listed'),
            ('capability_without_artifact_support', probe(['--identity', candidate],
             manifest('plain.json', e.sha256(candidate), {'standard': capability, 'fast': {}})), 1, 'capabilities are not listed'),
            ('capability_unknown', probe(['--identity', escape_path],
             manifest('unknown.json', escape_sha, {'standard': {'teleport': capability['escape']}, 'fast': {}})), 1, 'manifest schema'),
            ('capability_on_missing_fast', probe(['--identity', escape_path],
             manifest('fastcap.json', escape_sha, {'standard': capability, 'fast': capability})), 1, 'manifest schema'),
        ]
        for name, result, code, text in checks:
            stream = result.stdout if code == 0 else result.stderr
            if (result.returncode == 0) != (code == 0) or text not in stream:
                raise RuntimeError(f'{name}: {result.returncode} {result.stdout!r} {result.stderr!r}')
            print(name, 'PASS')

        fixtures = directory / 'smoke.jsonl'
        smoke_fixtures(fixtures)
        production = probe(['--escape', STANDARD, fixtures])
        if production.returncode != 0:
            raise RuntimeError(production.stderr)
        production = [json.loads(line) for line in production.stdout.splitlines()]
        if any(r['supported'] for r in production if r['reason'] == 'smoke_bomb') or \
                sum(r['reason'] == 'smoke_bomb' for r in production) < 10:
            raise RuntimeError('production must keep excluding initial Smoke Bombs')
        print('production_excludes_smoke PASS')

        run = probe(['--escape', escape_path, fixtures], env)
        if run.returncode != 0:
            raise RuntimeError(run.stderr)
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        raw = [json.loads(line) for line in fixtures.read_text().splitlines()]
        _, wide = e.read_artifact(escape_path)
        classes = metadata['hpClasses']
        checked = eligible_rows = boss_rows = escapes = mixed_rows = 0
        for row, fixture in zip(rows, raw):
            if not row['supported']:
                continue
            pre = fixture['pre']
            d = fixture.get('delta', 0)
            maximum = pre['maxHp'] + metadata['maxHpClasses'][d]
            z = np.asarray(row['z'])
            if abs(e.escape_probability(wide, z) - row['escape']) > 1e-5:
                raise RuntimeError(f'escape head parity at {row["index"]}')
            for bit in (0, 1):
                expected = e.hp_probabilities(wide, classes, z, d, pre['curHp'], maximum, bit)
                if np.abs(expected - np.asarray(row[f'hp{bit}'])).max() > 1e-5:
                    raise RuntimeError(f'HP head parity at {row["index"]} bit {bit}')
            # The forecast mixes both escape-conditioned HP heads by the escape head.
            p_escape = row['escape'] if row['eligible'] else 0.0
            fraction = 0.0
            for delta, mass in enumerate(row['maxHp']):
                top = pre['maxHp'] + metadata['maxHpClasses'][delta]
                hp = (1 - p_escape) * e.hp_probabilities(wide, classes, z, delta, pre['curHp'], top, 0) + \
                    p_escape * e.hp_probabilities(wide, classes, z, delta, pre['curHp'], top, 1)
                fraction += mass * float(hp @ ((pre['curHp'] + np.asarray(classes)) / top))
            if abs(fraction - row['expectation']['winningHpFraction']) > 1e-4:
                raise RuntimeError(f'escape-mixed expectation at {row["index"]}')
            mixed_rows += row['eligible'] and np.abs(np.asarray(row['hp0']) - np.asarray(row['hp1'])).max() > 1e-3
            unconditioned = np.asarray(row['potion']['-1'])
            for key, value in row['potion'].items():
                condition = None if key == '-1' else int(key)
                legal = e.potion_legal(pre['potions'], pre['potionCapacity'], row['boss'], condition)
                value = np.asarray(value)
                if not np.array_equal(value > 0, legal & (unconditioned > 0)):
                    raise RuntimeError(f'potion legality at {row["index"]} escape {key}')
                if condition is not None:
                    restricted = np.where(legal, unconditioned, 0)
                    if np.abs(restricted / restricted.sum() - value).max() > 1e-5:
                        raise RuntimeError(f'potion conditioning at {row["index"]} escape {key}')
            if row['eligible']:
                eligible_rows += 1
                escapes += row['samples']['escape']
            elif row['samples']['escape']:
                raise RuntimeError('ineligible row escaped')
            boss_rows += row['boss'] and e.SMOKE in pre['potions'][:pre['potionCapacity']]
            checked += 1
        if checked < 15 or eligible_rows < 10 or boss_rows < 1 or escapes == 0 or mixed_rows < 10:
            raise RuntimeError(f'too little coverage: {checked} {eligible_rows} {boss_rows} {escapes} {mixed_rows}')
        print(f'escape_runtime_parity rows={checked} eligible={eligible_rows} boss_smoke={boss_rows} escapes={escapes} PASS')
    print('escape capability PASS')


if __name__ == '__main__':
    main()
