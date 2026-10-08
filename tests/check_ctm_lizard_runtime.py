"""Active Lizard with Entropic Brew / Fairy Potion (#418 PR9): the lizardBrew and lizardFairy
capabilities on a research-candidate fast artifact compose those states; production and an
unlisted candidate keep the old boundaries."""
import copy
import hashlib
import json
import os
import struct
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ctm_lizard as lz  # noqa: E402

FAST = ROOT / 'selfplay/models/combat_transition_deepsets_lizard_t2.native'
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
FIXTURES = ROOT / 'tests/fixtures/combat_transition_near_full.jsonl'
CANDIDATE = 'test-lizard-candidate'
TAIL, EMPTY, BREW, FAIRY, SMOKE = 35, 1, 17, 21, 37


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    return subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                          env={**clean, **(env or {})}, cwd=ROOT)


def fixtures(path):
    """Near-full fixture states with an active Tail added, plain and with Fairy/Brew."""
    out = []
    for index, line in enumerate(FIXTURES.read_text().splitlines()[:24]):
        row = json.loads(line)
        pi, pre = row['predictorInput'], row['pre']
        if any(r['id'] == TAIL for r in pre['relics']):
            continue
        for slot in range(pre['potionCapacity']):
            if pre['potions'][slot] in (BREW, FAIRY, SMOKE):
                pre['potions'][slot] = EMPTY
                pi['potions'][slot]['potionId'] = EMPTY
                pre['potionCount'] -= 1
                pi['globals']['potionCount'] -= 1
        free = [s for s in range(pre['potionCapacity']) if pre['potions'][s] == EMPTY]
        if len(free) < 2:
            continue
        pi['relics'].append({'relicId': TAIL, 'data': 1, 'orderIndex': len(pi['relics'])})
        pre['relics'].append({'id': TAIL, 'data': 1})
        pre['relicBits'][TAIL // 64] = int(pre['relicBits'][TAIL // 64]) | (1 << (TAIL % 64))
        for name, potions in (('plain', ()), ('fairy', (FAIRY,)), ('brew', (BREW,)),
                              ('brew_fairy', (BREW, FAIRY)), ('two_fairies', (FAIRY, FAIRY))):
            p, s = copy.deepcopy(pi), copy.deepcopy(pre)
            for slot, potion in zip(free, potions):
                p['potions'][slot]['potionId'] = potion
                s['potions'][slot] = potion
                p['globals']['potionCount'] += 1
                s['potionCount'] += 1
            out.append({'name': f'{index}/{name}', 'predictorInput': p, 'preState': s})
    path.write_text(''.join(json.dumps(r) + '\n' for r in out))
    return out


def write(path, version, header, body):
    encoded = json.dumps(header).encode()
    path.write_bytes(lz.MAGIC + struct.pack('<II', version, len(encoded)) + encoded + body)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    std_version, std_header, std_body = lz.read_header(STANDARD)
    fast_version, fast_header, fast_body = lz.read_header(FAST)
    production_r = fast_header['activeLizardCorrection']['rModel']
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        rows = fixtures(directory / 'dispatch.jsonl')
        if len(rows) < 20:
            raise RuntimeError(f'too few dispatch fixtures: {len(rows)}')

        standard_path = directory / 'standard.native'
        standard_sha = write(standard_path, std_version, dict(std_header, researchCandidate={'candidateId': CANDIDATE}), std_body)
        header = json.loads(json.dumps(fast_header))
        header['researchCandidate'] = {'candidateId': CANDIDATE}
        header['defaultForOocMcts'] = False
        header.pop('productionPromotionEvidence', None)
        header['qualification']['classification'] = 'FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS'
        header['experimentalDeepSets'].update(qualified=False, defaultChanged=False, controlSha256=standard_sha,
                                              downstreamCheckpointSha256='ab' * 32)
        header['sources']['downstream'] = 'ab' * 32
        header['experimentalSurvival']['controlSha256'] = standard_sha
        header['activeLizardCorrection'].update(status='integration_candidate', qualified=False, defaultChanged=False)
        plain_path = directory / 'fast.native'
        plain_sha = write(plain_path, fast_version, header, fast_body)

        brew_r = dict(production_r, standardizedCoefficients=[0.4, 0.9])
        fit_json = directory / 'fit.json'
        fit_json.write_text(json.dumps(dict(schema='ctm_lizard_fit_v1', rModels=dict(fast=production_r, standard=brew_r))))
        capable_path = directory / 'capable.native'
        extended = lz.extend(plain_path, fit_json, capable_path, brew=True, fairy=True)
        fairy_only = directory / 'fairy.native'
        fairy_ext = lz.extend(plain_path, fit_json, fairy_only, fairy=True)

        survival, deepsets, lizard = header['experimentalSurvival'], header['experimentalDeepSets'], header['activeLizardCorrection']

        def manifest(name, fast_sha, capabilities):
            body = dict(schema='ctm_research_candidate_v3', candidateId=CANDIDATE,
                        domainSha256=std_header['domain']['sha256'],
                        capabilities={'standard': {}, 'fast': capabilities},
                        standard=dict(artifactSha256=standard_sha, sources=std_header['sources']),
                        supportCensus=dict(allSupportedIndexSha256=std_header['supportCensus']['all']['supportedIndexSha256'],
                                           testSupportedIndexSha256=std_header['supportCensus']['TEST']['supportedIndexSha256']),
                        fast=dict(artifactSha256=fast_sha,
                                  survival={k: survival[k] for k in ('checkpointSha256', 'preparedSha256', 'preparedManifestSha256',
                                                                     'scalarMeanSha256', 'scalarInvSha256')},
                                  maxHpHpCheckpointSha256=deepsets['maxHpHpCheckpointSha256'],
                                  downstreamCheckpointSha256='ab' * 32,
                                  potionSpecialistCheckpointSha256=deepsets['potionSpecialistCheckpointSha256']),
                        activeLizard={k: lizard[k] for k in ('candidateId', 'candidateManifestSha256',
                                                             'frozenQrArtifactSha256', 'rModelSha256', 'rModel')})
            path = directory / name
            path.write_text(json.dumps(body))
            return {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(path),
                    'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}

        def dispatch(fast, env=None):
            result = probe(['--lizard-dispatch', fast, standard_path if env else STANDARD, directory / 'dispatch.jsonl'], env)
            if result.returncode != 0:
                raise RuntimeError(result.stderr)
            return {r['name']: r for r in map(json.loads, result.stdout.splitlines())}

        capabilities = extended['manifest']['capabilities']['fast']
        env = manifest('capable.json', extended['artifactSha256'], capabilities)
        checks = [
            ('unlisted', probe(['--pair-identity', capable_path, standard_path, 1],
                               manifest('none.json', extended['artifactSha256'], {})), 'capabilities are not listed'),
            ('malformed_brew_r', probe(['--pair-identity', capable_path, standard_path, 1],
                                       manifest('bad.json', extended['artifactSha256'],
                                                dict(capabilities, lizardBrew={'rModel': {'featureMean': [0.5]}}))),
             'manifest schema'),
        ]
        for name, result, error in checks:
            if result.returncode == 0 or error not in result.stderr:
                raise RuntimeError(f'{name}: {result.returncode} {result.stderr!r}')
            print('lizard_capability', name, 'PASS')
        # A Lizard capability on an artifact without the active-Lizard correction is refused.
        std_cap = directory / 'standard-cap.native'
        std_cap_sha = write(std_cap, std_version, dict(std_header, researchCandidate={'candidateId': CANDIDATE},
                                                       capabilities={'lizardFairy': {}}), std_body)
        body = json.loads(Path(env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())
        body.update(standard=dict(artifactSha256=std_cap_sha, sources=std_header['sources']),
                    capabilities={'standard': {'lizardFairy': {}}, 'fast': {}}, fast=None, activeLizard=None)
        (directory / 'stdcap.json').write_text(json.dumps(body))
        result = probe(['--identity', std_cap], {
            'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(directory / 'stdcap.json'),
            'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256((directory / 'stdcap.json').read_bytes()).hexdigest()})
        if result.returncode == 0 or 'require an active-Lizard artifact' not in result.stderr:
            raise RuntimeError(f'standard Lizard capability: {result.stderr!r}')
        print('lizard_capability on_artifact_without_correction PASS')

        production = dispatch(FAST)
        plain = dispatch(plain_path, manifest('plain.json', plain_sha, {}))
        fairy_env = manifest('fairy.json', fairy_ext['artifactSha256'], fairy_ext['manifest']['capabilities']['fast'])
        fairy_run = dispatch(fairy_only, fairy_env)
        capable = dispatch(capable_path, env)
        counted = dict(plain=0, fairy=0, brew=0, brew_fairy=0, two_fairies=0)
        for name, row in capable.items():
            kind = name.split('/')[1]
            old, base = production[name], plain[name]
            if (old['supported'], old['reason']) != (base['supported'], base['reason']):
                raise RuntimeError(f'{name}: unlisted candidate differs from production')
            if kind == 'plain':
                if row != base or not row['supported']:
                    raise RuntimeError(f'{name}: plain active Lizard changed: {row} vs {base}')
                continue
            brew, fairy = 'brew' in kind, 'fair' in kind
            expected_old = 'active_lizard_entropic_brew_unsupported' if brew else 'fairy_potion_exact_boundary'
            if old['predictionReason'] != expected_old or old['supported']:
                raise RuntimeError(f'{name}: production must keep the boundary: {old}')
            only = fairy_run[name]
            if only['supported'] != (not brew):
                raise RuntimeError(f'{name}: lizardFairy alone: {only}')
            if not row['supported'] or not row['predictionSupported'] or row['sampleOutcome'] < 0:
                raise RuntimeError(f'{name}: not composed: {row}')
            prediction = row['prediction']
            if (prediction['brew'], prediction['fairy']) != (brew, fairy):
                raise RuntimeError(f'{name}: routing flags {prediction}')
            model = brew_r if brew else production_r
            if abs(lz.r_of(model, prediction['pReserveWin']) - prediction['rWinGivenConsumed']) > 1e-9:
                raise RuntimeError(f'{name}: r model')
            q = 1 - prediction['pOrdinaryWin']
            expected = [prediction['pOrdinaryWin'], q * prediction['rWinGivenConsumed'], q * (1 - prediction['rWinGivenConsumed'])]
            if np.abs(np.asarray(expected) - prediction['classProbabilities']).max() > 1e-9:
                raise RuntimeError(f'{name}: class probabilities')
            if abs(row['expectation']['death'] - expected[2]) > 1e-6 or not row['expectation']['forecastSupported']:
                raise RuntimeError(f'{name}: expectation {row["expectation"]}')
            post = row.get('consumedPost')
            if post is None:
                raise RuntimeError(f'{name}: no consumed victory')
            if FAIRY in post['potions'] or [r['data'] for r in post['relics'] if r['id'] == TAIL] != [0]:
                raise RuntimeError(f'{name}: consumed branch kept a Fairy or the Tail: {post["potions"]}')
            counted[kind] += 1
        if min(counted[k] for k in counted if k != 'plain') < 3:
            raise RuntimeError(f'too little coverage: {counted}')
        print(f'lizard_brew_fairy_runtime {counted} PASS')
    print('Lizard Brew/Fairy capability PASS')


if __name__ == '__main__':
    main()
