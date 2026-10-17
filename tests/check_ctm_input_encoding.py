"""CTM input encoding v2: the native runtime against the Python reference (tools/ctm_input_encoding.py).

Builds research-candidate copies of the legacy DeepSets fast and Attention standard artifacts whose
global tensors are reshaped to ctm_input_v2 (8 scalars, act as a fifth category), then checks:
the native DeepSets survival and HP encoding equal a numpy reference that uses the Python encoding
(and the same reference reproduces the unchanged v1 artifact); v2 ignores potionKeepValue, separates
acts and large card misc values; v1 artifacts and malformed v2 declarations behave as before.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ctm_input_encoding as enc  # noqa: E402
from tools import combat_transition_model_experiment as base  # noqa: E402

FAST = ROOT / 'selfplay/models/combat_transition_deepsets_lizard_t2.native'
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
FIXTURE = ROOT / 'tests/fixtures/combat_transition_near_full.jsonl'
MAGIC = b'COMBAT_TRANSITION_RUNTIME_V2\0'
CANDIDATE = 'test-input-v2'
GROUPS = ('survival', 'max_hp', 'hp', 'potion_encoder')


def split(path):
    data = path.read_bytes()
    version, length = struct.unpack_from('<II', data, len(MAGIC))
    offset = len(MAGIC) + 8
    return version, json.loads(data[offset:offset + length]), data[offset + length:]


def tensors(header, body):
    # The runtime reads tensors in sorted name order.
    floats = np.frombuffer(body, '<f4'); out = {}; position = 0
    for name in sorted(header['tensors']):
        shape = header['tensors'][name]; size = int(np.prod(shape))
        out[name] = floats[position:position + size].reshape(shape).copy(); position += size
    if position != len(floats):
        raise RuntimeError('tensor graph does not cover the body')
    return out


def write(path, version, header, weights):
    header = copy.deepcopy(header)
    header['tensors'] = {name: list(weights[name].shape) for name in sorted(weights)}
    body = b''.join(np.ascontiguousarray(weights[name], '<f4').tobytes() for name in sorted(weights))
    encoded = json.dumps(header).encode()
    path.write_bytes(MAGIC + struct.pack('<II', version, len(encoded)) + encoded + body)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def to_v2(header, weights, rng):
    """Reshape every encoder's global tensors to ctm_input_v2: kept scalars keep their columns,
    act gets a fresh 4x8 embedding with its own 8 columns."""
    header = copy.deepcopy(header); weights = dict(weights)
    header.update(enc.runtime_metadata(enc.V2, base.GLOBAL_CATEGORY_COUNTS))
    raw = list(enc.RAW_CONTINUOUS_FIELDS)
    keep = [raw.index(name) for name in enc.V2_CONTINUOUS_FIELDS]
    for group in GROUPS:
        p = f'{group}.encoder.'
        if p + 'scalar_mean' not in weights:
            continue
        weights[p + 'scalar_mean'] = weights[p + 'scalar_mean'][keep].copy()
        weights[p + 'scalar_inv'] = weights[p + 'scalar_inv'][keep].copy()
        weights[p + 'global_category.4.weight'] = rng.normal(0, 1, (enc.ACT_CATEGORIES, 8)).astype(np.float32)
        name = p + ('global_mlp.0.weight' if p + 'global_mlp.0.weight' in weights else 'global_proj.weight')
        old = weights[name]
        weights[name] = np.concatenate(
            (old[:, keep], old[:, len(raw):], rng.normal(0, .3, (old.shape[0], 8)).astype(np.float32)), 1)
    return header, weights


def numpy_deepset(weights, group, predictor, encoding):
    """Reference for CombatTransitionRuntime::encode on a DeepSets group."""
    p = f'{group}.encoder.'
    lin = lambda name, x: weights[p + name + '.weight'] @ x + weights[p + name + '.bias']
    relu = lambda x: np.maximum(x, 0)
    mlp = lambda name, x: relu(lin(name + '.2', relu(lin(name + '.0', x))))
    g = predictor['globals']
    raw = np.asarray([float(g[f]) for f in enc.RAW_CONTINUOUS_FIELDS], np.float64)
    cats = np.asarray([int(g[f]) for f in enc.RAW_CATEGORICAL_FIELDS], np.int64)
    scalars, cats = enc.globals_features(raw, cats, encoding)
    scalars = (scalars - weights[p + 'scalar_mean']) * weights[p + 'scalar_inv']
    global_in = np.concatenate([scalars] + [weights[p + f'global_category.{i}.weight'][c] for i, c in enumerate(cats)])
    pool = lambda rows: np.sum(rows, 0) if rows else np.zeros(64)
    cards = pool([mlp('card_mlp', np.concatenate((weights[p + 'card_id.weight'][c['cardId']],
        [float(c['upgraded']), float(enc.misc_feature(c['misc'], encoding)), (c['bottleBinding'] + 1) / 3])))
        for c in predictor['cards']])
    relics = pool([mlp('relic_mlp', np.concatenate((weights[p + 'relic_id.weight'][r['relicId']],
        [r['data'] / 10, r['orderIndex'] / 64]))) for r in predictor['relics']])
    potions = pool([mlp('potion_mlp', np.concatenate((weights[p + 'potion_id.weight'][q['potionId']],
        weights[p + 'potion_slot.weight'][q['slot']]))) for q in predictor['potions']])
    z = np.concatenate((cards, relics, potions, relu(lin('global_mlp.0', global_in))))
    return relu(lin('trunk.2', relu(lin('trunk.0', z))))


def reference(weights, predictor, encoding):
    z = numpy_deepset(weights, 'survival', predictor, encoding)
    logit = float((weights['survival.survival.weight'] @ z + weights['survival.survival.bias'])[0])
    return 1 / (1 + math.exp(-logit)), numpy_deepset(weights, 'hp', predictor, encoding)


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    result = subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                            env={**clean, **(env or {})}, cwd=ROOT)
    return result


def encode(artifact, inputs, directory, env=None):
    path = directory / 'inputs.jsonl'
    path.write_text(''.join(json.dumps({'predictorInput': p}) + '\n' for p in inputs))
    result = probe(['--encode', artifact, path], env)
    if result.returncode != 0:
        raise RuntimeError(f'probe --encode failed: {result.stderr}')
    return [json.loads(line) for line in result.stdout.splitlines()]


def inputs():
    states = [json.loads(line)['predictorInput'] for line in FIXTURE.read_text().splitlines()]
    out = []
    for state in states[:8]:
        out.append(state)
        variant = copy.deepcopy(state)
        variant['globals'].update(act=4, floor=54)
        for i, card in enumerate(variant['cards'][:3]):
            card['misc'] = [25, 30, -7][i]
        out.append(variant)
    return out


def main():
    rng = np.random.default_rng(20261017)
    states = inputs()
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        fast_version, fast_header, fast_body = split(FAST)
        std_version, std_header, std_body = split(STANDARD)
        fast_weights = tensors(fast_header, fast_body); std_weights = tensors(std_header, std_body)

        # v1: the unchanged artifact and the reference agree, so the reference encodes like the runtime.
        rows = encode(FAST, states[::2], directory)
        for row, state in zip(rows, states[::2]):
            survival, z = reference(fast_weights, state, enc.V1)
            if row['inputV2'] or abs(row['survival'] - survival) > 1e-5 or np.max(np.abs(np.asarray(row['hp']) - z)) > 1e-4:
                raise RuntimeError(f'v1 reference differs from the runtime on state {row["index"]}')
        print('v1_reference PASS')

        # v2 candidate pair (stamped as tests/check_ctm_research_candidate.py does).
        std_header_v2, std_weights_v2 = to_v2(std_header, std_weights, rng)
        std_header_v2['researchCandidate'] = {'candidateId': CANDIDATE}
        std_path = directory / 'standard-v2.native'
        std_sha = write(std_path, std_version, std_header_v2, std_weights_v2)
        header = copy.deepcopy(fast_header)
        header['researchCandidate'] = {'candidateId': CANDIDATE}
        header['defaultForOocMcts'] = False
        header.pop('productionPromotionEvidence', None)
        header['qualification']['classification'] = 'FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS'
        header['experimentalDeepSets'].update(qualified=False, defaultChanged=False, controlSha256=std_sha,
                                              downstreamCheckpointSha256='ab' * 32)
        header['sources']['downstream'] = 'ab' * 32
        header['experimentalSurvival']['controlSha256'] = std_sha
        header['activeLizardCorrection'].update(status='integration_candidate', qualified=False,
                                                defaultChanged=False, rModelSha256='cd' * 32)
        fast_header_v2, fast_weights_v2 = to_v2(header, fast_weights, rng)
        fast_path = directory / 'fast-v2.native'
        fast_sha = write(fast_path, fast_version, fast_header_v2, fast_weights_v2)
        survival = fast_header['experimentalSurvival']; deepsets = fast_header['experimentalDeepSets']
        lizard = fast_header['activeLizardCorrection']

        def manifest(name, fast_sha=fast_sha, standard_sha=std_sha):
            body = {'schema': 'ctm_research_candidate_v1', 'candidateId': CANDIDATE,
                    'standard': {'artifactSha256': standard_sha, 'sources': std_header['sources']},
                    'supportCensus': {
                        'allSupportedIndexSha256': std_header['supportCensus']['all']['supportedIndexSha256'],
                        'testSupportedIndexSha256': std_header['supportCensus']['TEST']['supportedIndexSha256']},
                    'fast': {'artifactSha256': fast_sha,
                             'survival': {key: survival[key] for key in (
                                 'checkpointSha256', 'preparedSha256', 'preparedManifestSha256',
                                 'scalarMeanSha256', 'scalarInvSha256')},
                             'maxHpHpCheckpointSha256': deepsets['maxHpHpCheckpointSha256'],
                             'downstreamCheckpointSha256': 'ab' * 32,
                             'potionSpecialistCheckpointSha256': deepsets['potionSpecialistCheckpointSha256']},
                    'activeLizard': dict({key: lizard[key] for key in (
                        'candidateId', 'candidateManifestSha256', 'frozenQrArtifactSha256', 'rModel')},
                        rModelSha256='cd' * 32)}
            path = directory / f'{name}.json'
            path.write_text(json.dumps(body))
            return {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(path),
                    'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}

        env = manifest('manifest')
        result = probe(['--pair-identity', fast_path, std_path, 1], env)
        if result.returncode != 0 or f'identity={CANDIDATE}' not in result.stdout:
            raise RuntimeError(f'v2 pair does not load: {result.stdout!r} {result.stderr!r}')
        print('v2_pair_loads PASS')

        rows = encode(fast_path, states, directory, env)
        for row, state in zip(rows, states):
            survival_ref, z = reference(fast_weights_v2, state, enc.V2)
            if not row['inputV2'] or abs(row['survival'] - survival_ref) > 1e-5 or np.max(np.abs(np.asarray(row['hp']) - z)) > 1e-4:
                raise RuntimeError(f'v2 runtime differs from the Python reference on state {row["index"]}: '
                                   f'{row["survival"]} vs {survival_ref}')
        print('v2_deepsets_matches_reference PASS')

        # Behavioural contract on both encoders (DeepSets fast, Attention standard).
        state = states[1]
        keep = copy.deepcopy(state); keep['globals']['potionKeepValue'] = 9.5
        act3 = copy.deepcopy(state); act3['globals'].update(act=3)
        dagger = copy.deepcopy(state); dagger['cards'][0]['misc'] = 35
        far = copy.deepcopy(state); far['cards'][0]['misc'] = 40
        for name, artifact in (('deepsets', fast_path), ('attention', std_path)):
            a, b, c, d, e = encode(artifact, [state, keep, act3, dagger, far], directory, env)
            if a['hp'] != b['hp'] or a['survival'] != b['survival']:
                raise RuntimeError(f'{name}: v2 output depends on potionKeepValue')
            if a['hp'] == c['hp']:
                raise RuntimeError(f'{name}: v2 does not separate act 4 from act 3 at the same floor')
            if d['hp'] == e['hp']:
                raise RuntimeError(f'{name}: v2 card misc saturates (35 vs 40)')
            print(f'v2_{name}_contract PASS')
        a, b = encode(FAST, [state, keep], directory)
        if a['hp'] == b['hp']:
            raise RuntimeError('v1 no longer reads potionKeepValue')
        print('v1_keeps_potion_keep_value PASS')

        # Malformed declarations fail closed.
        def rejected(name, edit, error):
            h = copy.deepcopy(std_header_v2); edit(h)
            path = directory / f'{name}.native'
            sha = write(path, std_version, h, std_weights_v2)
            result = probe(['--identity', path], manifest(name, standard_sha=sha))
            if result.returncode == 0 or error not in result.stderr:
                raise RuntimeError(f'{name}: expected {error!r}, got {result.stdout!r} {result.stderr!r}')
            print(f'{name} PASS')
        rejected('explicit_v1', lambda h: h.update(inputEncoding='ctm_input_v1'), 'combat runtime input encoding')
        rejected('v2_with_v1_fields', lambda h: h.update(continuousFields=list(enc.RAW_CONTINUOUS_FIELDS)),
                 'combat runtime global fields')
        rejected('v2_without_act_category', lambda h: h.update(globalCategoryCounts=[4, 64, 10, 10]),
                 'combat runtime global vocab')
        rejected('v1_fields_with_v2_tensors', lambda h: h.pop('inputEncoding'), 'combat runtime global fields')
        bad = copy.deepcopy(state); bad['globals']['act'] = 5
        path = directory / 'bad.jsonl'; path.write_text(json.dumps({'predictorInput': bad}) + '\n')
        result = probe(['--encode', fast_path, path], env)
        if result.returncode == 0 or 'act outside the v2 act categories' not in result.stderr:
            raise RuntimeError(f'act 5 accepted: {result.stdout!r} {result.stderr!r}')
        print('v2_act_domain PASS')
    if list(enc.RAW_CONTINUOUS_FIELDS) != list(base.CONTINUOUS_GLOBAL_FIELDS) or \
            list(enc.RAW_CATEGORICAL_FIELDS) != list(base.CATEGORICAL_GLOBAL_FIELDS):
        raise RuntimeError('raw field order differs from the prepared arrays')
    print('ctm input encoding PASS')


if __name__ == '__main__':
    main()
