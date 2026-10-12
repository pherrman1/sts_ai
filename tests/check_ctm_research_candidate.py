"""Research-candidate CTM loading: only identity pins may change, and only under a pinned manifest."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / 'selfplay/models/combat_transition_deepsets_lizard_t2.native'
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
# The #418 production stack: the pathb-r2 candidate, pinned by its built-in v3 manifest.
PRODUCTION_FAST = ROOT / 'selfplay/models/combat_transition_deepsets_pathb_r2.native'
PRODUCTION_STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_escape_pathb_r2.native'
PRODUCTION_MANIFEST = ROOT / 'tests/fixtures/ctm_production/pathb_r2_candidate_v3.json'
PRODUCTION_MANIFEST_SHA = 'd9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d'
# The §423 Lizard-capable pathb-r2 fast artifact, the default fast artifact since §435; the #418
# fast artifact above stays loadable without a manifest through the previous built-in manifest.
LIZARD_FAST = ROOT / 'selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native'
LIZARD_MANIFEST = ROOT / 'docs/experiments/evidence/ooc_rollout3_lizard_20261010/candidate-v3-lizard.json'
LIZARD_MANIFEST_SHA = '64da17762b08114f28ae4d182fddde82da917951f4717bb95d352c42bc4a933e'
MAGIC = b'COMBAT_TRANSITION_RUNTIME_V2\0'
CANDIDATE = 'test-retrain-candidate'


def split(path):
    data = path.read_bytes()
    version, length = struct.unpack_from('<II', data, len(MAGIC))
    offset = len(MAGIC) + 8
    return version, json.loads(data[offset:offset + length]), data[offset + length:]


def write(path, version, header, body):
    encoded = json.dumps(header).encode()
    path.write_bytes(MAGIC + struct.pack('<II', version, len(encoded)) + encoded + body)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def widen(header, body, domain):
    """Expand the HP-class tensors as tools/ctm_hp_domain.py does: old rows keep their
    place, new HP-head rows get zero weights and bias -30, new relic rows copy an edge."""
    header = json.loads(json.dumps(header))
    old = header['hpClasses']
    offset, count = old[0] - domain['min'], domain['classes']
    floats = struct.unpack(f'<{len(body) // 4}f', body)
    out, position = [], 0
    for name, shape in header['tensors'].items():
        size = 1
        for dim in shape:
            size *= dim
        values = list(floats[position:position + size]); position += size
        if name in ('hp.hp.2.weight', 'hp.hp.2.bias', 'relic.delta.weight'):
            width = shape[1] if len(shape) == 2 else 1
            rows = [values[i * width:(i + 1) * width] for i in range(shape[0])]
            if name == 'relic.delta.weight':
                wide = [rows[min(max(i - offset, 0), len(old) - 1)] for i in range(count)]
            else:
                fill = [0.0] * width if len(shape) == 2 else [-30.0]
                wide = [fill] * count
                wide[offset:offset + len(old)] = rows
            values = [v for row in wide for v in row]
            header['tensors'][name] = [count] + shape[1:]
        out.extend(values)
    if position != len(floats):
        raise RuntimeError('tensor graph does not cover the body')
    header['hpClasses'] = list(range(domain['min'], domain['max'] + 1))
    header['domain'] = domain
    return header, struct.pack(f'<{len(out)}f', *out)


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    return subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                          env={**clean, **(env or {})}, cwd=ROOT)


def expect(name, result, identity=None, error=None):
    if identity is not None and (result.returncode != 0 or f'identity={identity}' not in result.stdout):
        raise RuntimeError(f'{name}: expected identity={identity}, got {result.stdout!r} {result.stderr!r}')
    if error is not None and (result.returncode == 0 or error not in result.stderr):
        raise RuntimeError(f'{name}: expected rejection {error!r}, got {result.stdout!r} {result.stderr!r}')
    print(name, 'PASS')


def main():
    production_standard_sha = hashlib.sha256(STANDARD.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        std_version, std_header, std_body = split(STANDARD)
        fast_version, fast_header, fast_body = split(FAST)

        def standard_header():
            header = json.loads(json.dumps(std_header))
            header['researchCandidate'] = {'candidateId': CANDIDATE}
            return header

        def fast_header_for(standard_sha):
            # The production fast artifact is promoted; a candidate must not be.
            header = json.loads(json.dumps(fast_header))
            header['researchCandidate'] = {'candidateId': CANDIDATE}
            header['defaultForOocMcts'] = False
            header.pop('productionPromotionEvidence', None)
            header['qualification']['classification'] = 'FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS'
            deepsets = header['experimentalDeepSets']
            deepsets.update(qualified=False, defaultChanged=False, controlSha256=standard_sha,
                            downstreamCheckpointSha256='ab' * 32)
            header['sources']['downstream'] = 'ab' * 32
            header['experimentalSurvival']['controlSha256'] = standard_sha
            lizard = header['activeLizardCorrection']
            lizard.update(status='integration_candidate', qualified=False, defaultChanged=False,
                          rModelSha256='cd' * 32)
            return header

        standard_path = directory / 'standard.native'
        standard_sha = write(standard_path, std_version, standard_header(), std_body)
        fast_path = directory / 'fast.native'
        fast_sha = write(fast_path, fast_version, fast_header_for(standard_sha), fast_body)
        lizard = fast_header['activeLizardCorrection']
        survival = fast_header['experimentalSurvival']
        deepsets = fast_header['experimentalDeepSets']

        def manifest(path, **changes):
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
                    'activeLizard': {key: lizard[key] for key in (
                        'candidateId', 'candidateManifestSha256', 'frozenQrArtifactSha256', 'rModel')}}
            body['activeLizard']['rModelSha256'] = 'cd' * 32
            body.update(changes)
            path.write_text(json.dumps(body))
            return {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(path),
                    'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}

        env = manifest(directory / 'manifest.json')
        expect('production_pair_without_manifest', probe(['--pair-identity', FAST, STANDARD, 1]), identity='production')
        expect('production_pair_with_manifest', probe(['--pair-identity', FAST, STANDARD, 1], env), identity='production')
        expect('candidate_without_manifest', probe(['--identity', standard_path]),
               error='requires STS_CTM_RESEARCH_CANDIDATE_MANIFEST')
        # The promoted pathb-r2 stack needs no manifest and still loads beside another candidate's.
        if hashlib.sha256(PRODUCTION_MANIFEST.read_bytes()).hexdigest() != PRODUCTION_MANIFEST_SHA:
            raise RuntimeError('production candidate manifest fixture changed')
        expect('promoted_pair_without_manifest',
               probe(['--pair-identity', PRODUCTION_FAST, PRODUCTION_STANDARD, 1]), identity='production')
        expect('promoted_pair_with_other_manifest',
               probe(['--pair-identity', PRODUCTION_FAST, PRODUCTION_STANDARD, 1], env), identity='production')
        expect('promoted_pair_with_own_manifest',
               probe(['--pair-identity', PRODUCTION_FAST, PRODUCTION_STANDARD, 1],
                     {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(PRODUCTION_MANIFEST),
                      'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': PRODUCTION_MANIFEST_SHA}), identity='pathb-r2')
        # The Lizard-capable fast artifact is the production default and needs no manifest; the
        # #418 fast artifact still loads as production, without the Lizard capabilities.
        if hashlib.sha256(LIZARD_MANIFEST.read_bytes()).hexdigest() != LIZARD_MANIFEST_SHA:
            raise RuntimeError('Lizard production manifest changed')
        result = probe(['--pair-identity', LIZARD_FAST, PRODUCTION_STANDARD, 1])
        expect('lizard_pair_without_manifest', result, identity='production')
        if 'lizard_fairy=1 lizard_brew=1' not in result.stdout:
            raise RuntimeError(f'lizard_pair_without_manifest: Lizard capabilities missing: {result.stdout!r}')
        expect('lizard_pair_with_other_manifest',
               probe(['--pair-identity', LIZARD_FAST, PRODUCTION_STANDARD, 1], env), identity='production')
        expect('lizard_pair_with_own_manifest',
               probe(['--pair-identity', LIZARD_FAST, PRODUCTION_STANDARD, 1],
                     {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(LIZARD_MANIFEST),
                      'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': LIZARD_MANIFEST_SHA}), identity='pathb-r2')
        expect('lizard_fast_with_418_manifest',
               probe(['--pair-identity', LIZARD_FAST, PRODUCTION_STANDARD, 1],
                     {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(PRODUCTION_MANIFEST),
                      'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': PRODUCTION_MANIFEST_SHA}),
               error='not listed in its manifest')
        result = probe(['--pair-identity', PRODUCTION_FAST, PRODUCTION_STANDARD, 1])
        if 'lizard_fairy=0 lizard_brew=0' not in result.stdout:
            raise RuntimeError(f'418_pair_without_manifest: unexpected capabilities: {result.stdout!r}')
        lizard_tampered = directory / 'lizard-tampered.native'
        payload = bytearray(LIZARD_FAST.read_bytes()); payload[-1] ^= 1; lizard_tampered.write_bytes(payload)
        expect('lizard_bytes_not_listed', probe(['--identity', lizard_tampered]), error='not listed in its manifest')
        expect('promoted_fast_with_legacy_standard',
               probe(['--pair-identity', PRODUCTION_FAST, STANDARD, 1]), error='Brew fallback artifact SHA256 differs')
        expect('legacy_fast_with_promoted_standard',
               probe(['--pair-identity', FAST, PRODUCTION_STANDARD, 1]), error='Brew fallback artifact SHA256 differs')
        promoted_tampered = directory / 'promoted-tampered.native'
        payload = bytearray(PRODUCTION_STANDARD.read_bytes()); payload[-1] ^= 1; promoted_tampered.write_bytes(payload)
        expect('promoted_bytes_not_listed', probe(['--identity', promoted_tampered]), error='not listed in its manifest')
        expect('candidate_standard', probe(['--identity', standard_path], env), identity=CANDIDATE)
        expect('candidate_pair', probe(['--pair-identity', fast_path, standard_path, 1], env), identity=CANDIDATE)
        expect('candidate_fast_with_production_standard',
               probe(['--pair-identity', fast_path, STANDARD, 1], env), error='Brew fallback artifact SHA256 differs')
        expect('production_fast_with_candidate_standard',
               probe(['--pair-identity', FAST, standard_path, 1], env), error='Brew fallback artifact SHA256 differs')
        expect('manifest_sha_mismatch', probe(['--identity', standard_path],
               {**env, 'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': '0' * 64}), error='manifest SHA256 differs')
        expect('manifest_sha_missing', probe(['--identity', standard_path],
               {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']}),
               error='must be set together')
        expect('manifest_extra_key', probe(['--identity', standard_path],
               manifest(directory / 'extra.json', capabilities={})), error='manifest schema')
        expect('manifest_bad_hash', probe(['--identity', standard_path],
               manifest(directory / 'badhash.json', supportCensus={'allSupportedIndexSha256': 'x',
                                                                   'testSupportedIndexSha256': 'y'})),
               error='manifest schema')

        # Artifacts that differ only where the candidate mode must keep production rules.
        def altered_standard(name, edit):
            header = standard_header(); edit(header)
            path = directory / f'{name}.native'
            sha = write(path, std_version, header, std_body)
            return path, manifest(directory / f'{name}.json',
                                  standard={'artifactSha256': sha, 'sources': std_header['sources']})

        path, case_env = altered_standard('wrong_id', lambda h: h.update(researchCandidate={'candidateId': 'other'}))
        expect('candidate_id_mismatch', probe(['--identity', path], case_env), error='research candidate identity')
        path, case_env = altered_standard('envelope', lambda h: h['domain'].update(preMaxHpRange=[24, 220]))
        expect('candidate_envelope_change', probe(['--identity', path], case_env), error='frozen envelope')
        path, case_env = altered_standard('exclusions', lambda h: h.update(supportExclusions=['smoke_bomb']))
        expect('candidate_exclusion_change', probe(['--identity', path], case_env), error='support exclusions')
        path, case_env = altered_standard('claims_default', lambda h: h.update(defaultForOocMcts=True))
        expect('candidate_claims_default', probe(['--identity', path], case_env), error='cannot claim production default')
        path, case_env = altered_standard('census', lambda h: h['supportCensus']['all'].update(supportedIndexSha256='ef' * 32))
        expect('candidate_census_not_in_manifest', probe(['--identity', path], case_env), error='qualified cohort')

        # §443: a research candidate may carry an exposure gate waived by a recorded override.
        def overridden(sha):
            def edit(h):
                h['qualification'] = dict(h['qualification'], classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS_BY_OVERRIDE')
                if sha:
                    h['qualification']['exposureOverrideSha256'] = sha
            return edit
        path, case_env = altered_standard('override', overridden('ab' * 32))
        expect('candidate_exposure_override', probe(['--identity', path], case_env), identity=CANDIDATE)
        override_std_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        override_fast = directory / 'override-fast.native'
        override_fast_sha = write(override_fast, fast_version, fast_header_for(override_std_sha), fast_body)
        override_manifest = json.loads(Path(case_env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())
        pair_env = manifest(directory / 'override-pair.json', standard=override_manifest['standard'],
                            fast=dict(override_manifest['fast'], artifactSha256=override_fast_sha))
        expect('candidate_exposure_override_pair', probe(['--pair-identity', override_fast, path, 1], pair_env),
               identity=CANDIDATE)
        path, case_env = altered_standard('override_nosha', overridden(None))
        expect('candidate_exposure_override_without_record', probe(['--identity', path], case_env),
               error='combat runtime qualification')
        path, case_env = altered_standard('fail', lambda h: h['qualification'].update(
            classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL'))
        expect('candidate_exposure_fail', probe(['--identity', path], case_env), error='combat runtime qualification')

        tampered = directory / 'tampered.native'
        payload = bytearray(standard_path.read_bytes()); payload[-1] ^= 1; tampered.write_bytes(payload)
        expect('candidate_bytes_not_listed', probe(['--identity', tampered], env), error='not listed in its manifest')

        promoted = fast_header_for(standard_sha)
        promoted['activeLizardCorrection'].update(status='production_default_when_ooc_enabled', qualified=True,
                                                  defaultChanged=True)
        promoted_path = directory / 'promoted.native'
        promoted_sha = write(promoted_path, fast_version, promoted, fast_body)
        promoted_manifest = json.loads(Path(env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())
        promoted_manifest['fast']['artifactSha256'] = promoted_sha
        case_env = manifest(directory / 'promoted.json', fast=promoted_manifest['fast'])
        expect('candidate_claims_lizard_promotion', probe(['--identity', promoted_path], case_env),
               error='cannot claim production default')
        case_env = manifest(directory / 'nolizard.json', activeLizard=None)
        expect('candidate_lizard_not_in_manifest', probe(['--identity', fast_path], case_env),
               error='active-Lizard candidate identity')

        # v2 manifests pin a declared, wider HP domain (max HP 220: classes -219..231).
        sys.path.insert(0, str(ROOT))
        from tools.ctm_hp_domain import declared_domain
        domain = declared_domain(220, 220)
        wide_std_header, wide_std_body = widen(standard_header(), std_body, domain)
        wide_std_path = directory / 'wide-standard.native'
        wide_std_sha = write(wide_std_path, std_version, wide_std_header, wide_std_body)
        wide_fast_header, wide_fast_body = widen(fast_header_for(wide_std_sha), fast_body, domain)
        wide_fast_path = directory / 'wide-fast.native'
        wide_fast_sha = write(wide_fast_path, fast_version, wide_fast_header, wide_fast_body)
        wide_manifest = json.loads(Path(env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())
        wide_fast = dict(wide_manifest['fast'], artifactSha256=wide_fast_sha)
        wide_standard = dict(wide_manifest['standard'], artifactSha256=wide_std_sha)
        v2 = dict(schema='ctm_research_candidate_v2', domainSha256=domain['sha256'], standard=wide_standard, fast=wide_fast)
        case_env = manifest(directory / 'wide.json', **v2)
        expect('declared_domain_pair', probe(['--pair-identity', wide_fast_path, wide_std_path, 1], case_env),
               identity=CANDIDATE)
        expect('declared_domain_under_v1_manifest', probe(['--identity', wide_std_path],
               manifest(directory / 'wide-v1.json', standard=wide_standard)), error='frozen envelope')
        expect('declared_domain_not_in_manifest', probe(['--identity', wide_std_path],
               manifest(directory / 'wide-othersha.json', **dict(v2, domainSha256='ab' * 32))),
               error='HP domain is not listed in its manifest')
        expect('declared_domain_missing_sha', probe(['--identity', wide_std_path],
               manifest(directory / 'wide-nosha.json', **dict(v2, domainSha256=None))), error='manifest schema')
        tampered_header = json.loads(json.dumps(wide_std_header))
        tampered_header['domain']['rule'] = 'edited'
        tampered_path = directory / 'wide-tampered.native'
        tampered_sha = write(tampered_path, std_version, tampered_header, wide_std_body)
        expect('declared_domain_hash_recomputed', probe(['--identity', tampered_path],
               manifest(directory / 'wide-tampered.json', **dict(v2, standard=dict(wide_standard, artifactSha256=tampered_sha)))),
               error='declared HP domain SHA256')
        # The C++ recomputation reproduces the production domain hash, so v2 also accepts it.
        expect('declared_production_domain', probe(['--identity', standard_path],
               manifest(directory / 'v2-production.json', schema='ctm_research_candidate_v2',
                        domainSha256=std_header['domain']['sha256'])), identity=CANDIDATE)
        # v3 manifests list per-artifact capabilities; the escape capability must agree across the pair.
        import numpy as np
        import torch
        from tools import ctm_escape

        def escape_extend(base, name):
            _, tensors = ctm_escape.read_artifact(base)
            fitted = {key: tensors[key] for key in ctm_escape.HP_TENSORS}
            fitted['hp.hp.0.weight'] = np.concatenate((tensors['hp.hp.0.weight'], np.full((64, 1), 0.1, np.float32)), 1)
            fitted['escape.escape.weight'] = np.zeros((1, 64), np.float32)
            fitted['escape.escape.bias'] = np.zeros(1, np.float32)
            checkpoint = directory / f'{name}.pt'
            torch.save(dict(tensors=fitted, metadata=dict(baseArtifactSha256=ctm_escape.sha256(base))), checkpoint)
            out = directory / f'{name}.native'
            sha = ctm_escape.extend(base, checkpoint, out)['artifactSha256']
            return out, sha, {'escape': {'checkpointSha256': ctm_escape.sha256(checkpoint)}}

        escape_std_path, escape_std_sha, std_capability = escape_extend(standard_path, 'escape-standard')
        plain_fast_path = directory / 'plain-fast.native'
        plain_fast_sha = write(plain_fast_path, fast_version, fast_header_for(escape_std_sha), fast_body)
        escape_fast_path, escape_fast_sha, fast_capability = escape_extend(plain_fast_path, 'escape-fast')
        v3 = dict(schema='ctm_research_candidate_v3', domainSha256=std_header['domain']['sha256'],
                  standard=dict(json.loads(Path(env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())['standard'],
                                artifactSha256=escape_std_sha))
        base_fast = json.loads(Path(env['STS_CTM_RESEARCH_CANDIDATE_MANIFEST']).read_text())['fast']
        case_env = manifest(directory / 'v3-escape.json', **v3, fast=dict(base_fast, artifactSha256=escape_fast_sha),
                            capabilities={'standard': std_capability, 'fast': fast_capability})
        expect('v3_escape_pair', probe(['--pair-identity', escape_fast_path, escape_std_path, 1], case_env), identity=CANDIDATE)
        case_env = manifest(directory / 'v3-mixed.json', **v3, fast=dict(base_fast, artifactSha256=plain_fast_sha),
                            capabilities={'standard': std_capability, 'fast': {}})
        expect('v3_escape_pair_disagrees', probe(['--pair-identity', plain_fast_path, escape_std_path, 1], case_env),
               error='disagree on the escape capability')
        expect('v3_without_capabilities', probe(['--identity', standard_path],
               manifest(directory / 'v3-plain.json', schema='ctm_research_candidate_v3', domainSha256=std_header['domain']['sha256'],
                        capabilities={'standard': {}, 'fast': {}})), identity=CANDIDATE)
        expect('v3_missing_capabilities', probe(['--identity', standard_path],
               manifest(directory / 'v3-nocap.json', schema='ctm_research_candidate_v3', domainSha256=std_header['domain']['sha256'])),
               error='manifest schema')
    if production_standard_sha != hashlib.sha256(STANDARD.read_bytes()).hexdigest():
        raise RuntimeError('production artifact changed')
    print('research candidate loader PASS')


if __name__ == '__main__':
    main()
