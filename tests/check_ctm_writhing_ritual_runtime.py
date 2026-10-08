"""writhingRitual capability (#418 PR8): a research candidate that lists it supports Writhing Mass
with a Ritual Dagger; production and unlisted artifacts keep the exclusion."""
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
from tools import ctm_capabilities, ctm_escape as e  # noqa: E402

STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
FIXTURES = ROOT / 'tests/fixtures/combat_transition_near_full.jsonl'
CANDIDATE = 'test-writhing-ritual-candidate'


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    return subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                          env={**clean, **(env or {})}, cwd=ROOT)


def main():
    rows = [json.loads(line) for line in FIXTURES.read_text().splitlines()]
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        fixtures = directory / 'fixtures.jsonl'
        fixtures.write_text(FIXTURES.read_text())
        production = [json.loads(line) for line in probe([STANDARD, fixtures, 'support-only']).stdout.splitlines()]
        intersection = [r['index'] for r in production if r['reason'] == 'writhing_ritual_intersection']
        if not intersection:
            raise RuntimeError('fixtures lack a Writhing Mass + Ritual Dagger row')
        only = directory / 'intersection.jsonl'
        selected = [rows[i] for i in intersection]
        for row in selected:
            row['draws'] = 64
        only.write_text(''.join(json.dumps(r) + '\n' for r in selected))

        metadata, tensors = e.read_artifact(STANDARD)
        candidate = directory / 'candidate.native'
        e.write_artifact(candidate, dict(metadata, researchCandidate={'candidateId': CANDIDATE}), tensors)
        wr = directory / 'writhing.native'
        wr_sha = ctm_capabilities.writhing_ritual(candidate, wr)['artifactSha256']
        try:
            ctm_capabilities.writhing_ritual(wr, directory / 'twice.native')
            raise RuntimeError('capability applied twice')
        except ValueError:
            pass

        def manifest(name, sha, capabilities):
            body = dict(schema='ctm_research_candidate_v3', candidateId=CANDIDATE,
                        domainSha256=metadata['domain']['sha256'],
                        capabilities={'standard': capabilities, 'fast': {}},
                        standard=dict(artifactSha256=sha, sources=metadata['sources']),
                        supportCensus=dict(allSupportedIndexSha256=metadata['supportCensus']['all']['supportedIndexSha256'],
                                           testSupportedIndexSha256=metadata['supportCensus']['TEST']['supportedIndexSha256']),
                        fast=None, activeLizard=None)
            path = directory / name
            path.write_text(json.dumps(body))
            return {'STS_CTM_RESEARCH_CANDIDATE_MANIFEST': str(path),
                    'STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256': hashlib.sha256(path.read_bytes()).hexdigest()}

        env = manifest('wr.json', wr_sha, {'writhingRitual': {}})
        rejected = probe(['--identity', wr], manifest('none.json', wr_sha, {}))
        if rejected.returncode == 0 or 'capabilities are not listed' not in rejected.stderr:
            raise RuntimeError(f'unlisted capability loaded: {rejected.stderr!r}')
        bad = probe(['--identity', wr], manifest('bad.json', wr_sha, {'writhingRitual': {'x': 1}}))
        if bad.returncode == 0 or 'manifest schema' not in bad.stderr:
            raise RuntimeError(f'malformed capability accepted: {bad.stderr!r}')
        print('writhing_ritual_manifest PASS')

        run = probe([wr, only, 'near-full'], env)
        if run.returncode != 0:
            raise RuntimeError(run.stderr)
        sampled = 0
        for row in map(json.loads, run.stdout.splitlines()):
            if not row['supported'] or 'writhing' not in row['diagnostics'] or len(row['diagnostics']['ritualCandidates']) < 2:
                raise RuntimeError(f'intersection row not modelled jointly: {row.get("reason")}')
            for sample in row['samples']:
                if sample['outcome'] == 1:
                    continue
                post = sample['rawPost']
                if not 1 <= post['curHp'] <= post['maxHp']:
                    raise RuntimeError('illegal HP')
                sampled += 1
        if sampled == 0:
            raise RuntimeError('no surviving intersection samples')
        print(f'writhing_ritual_runtime rows={len(selected)} samples={sampled} PASS')

        # Both capabilities compose: escape on top of writhingRitual.
        fitted = {name: tensors[name] for name in e.HP_TENSORS}
        fitted['hp.hp.0.weight'] = np.concatenate((tensors['hp.hp.0.weight'], np.zeros((64, 1), np.float32)), 1)
        fitted['escape.escape.weight'] = np.zeros((1, 64), np.float32)
        fitted['escape.escape.bias'] = np.zeros(1, np.float32)
        checkpoint = directory / 'escape.pt'
        torch.save(dict(tensors=fitted, metadata=dict(baseArtifactSha256=e.sha256(wr))), checkpoint)
        both = directory / 'both.native'
        both_sha = e.extend(wr, checkpoint, both)['artifactSha256']
        both_meta, _ = e.read_artifact(both)
        if both_meta['supportExclusions'] != ['pre_smoke_bomb_used']:
            raise RuntimeError(both_meta['supportExclusions'])
        result = probe(['--identity', both], manifest('both.json', both_sha, both_meta['capabilities']))
        if result.returncode != 0 or f'identity={CANDIDATE}' not in result.stdout:
            raise RuntimeError(result.stderr)
        print('writhing_ritual_with_escape PASS')
    print('writhingRitual capability PASS')


if __name__ == '__main__':
    main()
