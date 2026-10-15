"""Research-candidate stamping and manifests for the #418 CTM retrain.

The C++ runtime loads a retrained artifact only as a research candidate: its
header declares `researchCandidate: {candidateId}` and a
`ctm_research_candidate_v3` manifest, pinned by STS_CTM_RESEARCH_CANDIDATE_MANIFEST
and _SHA256, lists its bytes (combat_transition_runtime.cpp). The exports write
plain artifacts; this tool stamps them and writes the manifest from their headers.

Capabilities change an artifact's bytes, and the fast artifact binds the final
standard artifact's SHA256 as its `controlSha256`. So the order is:

    stamp    STD0 -> STD1           (the plain export_combat_transition_near_full output)
    capabilities on STD1 -> STD     (ctm_escape extend, ctm_capabilities writhing-ritual)
    stamp    FAST0 --control STD -> FAST1   (the package_deepsets_lizard_artifact output)
    capabilities on FAST1 -> FAST   (ctm_escape extend, writhing-ritual, then ctm_lizard extend)
    manifest --standard STD --fast FAST

Steps that load a stamped artifact before the end (ctmescapefeatures,
ctmlizardfeatures) need an interim manifest over the current bytes: `manifest
--standard STD1` (fast null) or `manifest --standard STD --fast FAST1`.

    python tools/ctm_candidate.py stamp --artifact STD0.native --candidate-id ID --out STD1.native
    python tools/ctm_candidate.py stamp --artifact FAST0.native --control STD.native --out FAST1.native
    python tools/ctm_candidate.py manifest --standard STD.native [--fast FAST.native] --out M.json

Stamping changes only the JSON header; the tensor payload is copied byte for byte.
Every output refuses to overwrite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

MAGIC = b'COMBAT_TRANSITION_RUNTIME_V2\0'
SCHEMA = 'ctm_research_candidate_v3'


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f'{path}: not a V2 combat transition artifact')
    version, length = struct.unpack_from('<II', data, len(MAGIC))
    offset = len(MAGIC) + 8
    if version != 2:
        raise ValueError(f'{path}: artifact version {version}')
    return json.loads(data[offset:offset + length]), data[offset + length:]


def write(path, header, payload):
    encoded = json.dumps(header, sort_keys=True, separators=(',', ':')).encode()
    with open(path, 'xb') as stream:
        stream.write(MAGIC + struct.pack('<II', 2, len(encoded)) + encoded + payload)


def _candidate_id(header, path):
    candidate = header.get('researchCandidate')
    if not isinstance(candidate, dict) or set(candidate) != {'candidateId'}:
        raise ValueError(f'{path}: not a stamped research candidate')
    return candidate['candidateId']


def _refuse_production(header, path):
    if header.get('defaultForOocMcts') or 'productionPromotionEvidence' in header:
        raise ValueError(f'{path}: a production-promoted artifact cannot become a research candidate')
    deepsets = header.get('experimentalDeepSets')
    if deepsets is not None and (deepsets.get('qualified') or deepsets.get('defaultChanged')):
        raise ValueError(f'{path}: DeepSets stack claims qualification')
    lizard = header.get('activeLizardCorrection')
    if lizard is not None and (lizard.get('status') != 'integration_candidate' or lizard.get('qualified')
                               or lizard.get('defaultChanged')):
        raise ValueError(f'{path}: active-Lizard correction is not an integration candidate')


def stamp(artifact, out, candidate_id=None, control=None):
    header, payload = read(artifact)
    if 'researchCandidate' in header:
        raise ValueError(f'{artifact}: already a research candidate')
    if header.get('capabilities'):
        raise ValueError(f'{artifact}: stamp the plain export; capabilities come after stamping')
    _refuse_production(header, artifact)
    fast = 'experimentalDeepSets' in header
    if fast != (control is not None):
        raise ValueError('a fast (DeepSets) artifact needs --control, the final standard artifact; a standard one takes none')
    header = dict(header, defaultForOocMcts=False)
    if fast:
        control_header, _ = read(control)
        control_id = _candidate_id(control_header, control)
        if candidate_id is not None and candidate_id != control_id:
            raise ValueError('--candidate-id differs from the control artifact')
        candidate_id = control_id
        if 'experimentalDeepSets' in control_header:
            raise ValueError(f'{control}: the control must be the standard (Attention) artifact')
        for key in ('domain', 'supportCensus', 'hpClasses'):
            if header.get(key) != control_header.get(key):
                raise ValueError(f'fast and control artifacts differ in {key}')
        control_sha = sha256(control)
        header['experimentalSurvival'] = dict(header['experimentalSurvival'], controlSha256=control_sha)
        header['experimentalDeepSets'] = dict(header['experimentalDeepSets'], controlSha256=control_sha)
    elif not candidate_id:
        raise ValueError('a standard artifact needs --candidate-id')
    header['researchCandidate'] = {'candidateId': candidate_id}
    write(out, header, payload)
    return dict(artifact=str(out), artifactSha256=sha256(out), baseArtifactSha256=sha256(artifact),
                candidateId=candidate_id, role='fast' if fast else 'standard',
                controlSha256=header['experimentalDeepSets']['controlSha256'] if fast else None)


def build_manifest(standard, fast=None):
    std, _ = read(standard)
    if 'experimentalDeepSets' in std:
        raise ValueError(f'{standard}: --standard must be the Attention artifact')
    candidate_id = _candidate_id(std, standard)
    _refuse_production(std, standard)
    census = std['supportCensus']
    body = dict(schema=SCHEMA, candidateId=candidate_id, domainSha256=std['domain']['sha256'],
                capabilities=dict(standard=std.get('capabilities', {}), fast={}),
                standard=dict(artifactSha256=sha256(standard), sources=std['sources']),
                supportCensus=dict(allSupportedIndexSha256=census['all']['supportedIndexSha256'],
                                   testSupportedIndexSha256=census['TEST']['supportedIndexSha256']),
                fast=None, activeLizard=None)
    if fast is None:
        return body
    head, _ = read(fast)
    if 'experimentalDeepSets' not in head:
        raise ValueError(f'{fast}: --fast must be the DeepSets artifact')
    if _candidate_id(head, fast) != candidate_id:
        raise ValueError('standard and fast artifacts belong to different candidates')
    _refuse_production(head, fast)
    standard_sha = body['standard']['artifactSha256']
    survival, deepsets = head['experimentalSurvival'], head['experimentalDeepSets']
    if survival['controlSha256'] != standard_sha or deepsets['controlSha256'] != standard_sha:
        raise ValueError('the fast artifact was stamped against a different standard artifact')
    for key in ('domain', 'supportCensus'):
        if head[key] != std[key]:
            raise ValueError(f'fast and standard artifacts differ in {key}')
    # No pair-agreement check here: the interim manifest over FAST1 lists a capability-extended STD,
    # and the loader itself refuses a disagreeing pair (escape, writhingRitual) when both load together.
    body['capabilities']['fast'] = head.get('capabilities', {})
    body['fast'] = dict(artifactSha256=sha256(fast),
                        survival={k: survival[k] for k in ('checkpointSha256', 'preparedSha256', 'preparedManifestSha256',
                                                           'scalarMeanSha256', 'scalarInvSha256')},
                        maxHpHpCheckpointSha256=deepsets['maxHpHpCheckpointSha256'],
                        downstreamCheckpointSha256=deepsets['downstreamCheckpointSha256'],
                        potionSpecialistCheckpointSha256=deepsets['potionSpecialistCheckpointSha256'])
    lizard = head.get('activeLizardCorrection')
    if lizard is not None:
        body['activeLizard'] = {k: lizard[k] for k in ('candidateId', 'candidateManifestSha256', 'frozenQrArtifactSha256',
                                                       'rModelSha256', 'rModel')}
    return body


def manifest(standard, out, fast=None):
    body = build_manifest(standard, fast)
    with open(out, 'x', encoding='utf-8') as stream:
        stream.write(json.dumps(body, indent=2, sort_keys=True) + '\n')
    digest = sha256(out)
    return dict(manifest=str(out), manifestSha256=digest, candidateId=body['candidateId'],
                interim=body['fast'] is None, capabilities=body['capabilities'],
                env=dict(STS_CTM_RESEARCH_CANDIDATE_MANIFEST=str(Path(out).resolve()),
                         STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=digest))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('stamp')
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--candidate-id', help='required for the standard artifact; the fast one takes its control\'s')
    p.add_argument('--control', type=Path, help='fast only: the final (capability-extended) standard artifact')
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('manifest')
    p.add_argument('--standard', type=Path, required=True)
    p.add_argument('--fast', type=Path, help='omit for an interim manifest over the standard artifact only')
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'stamp':
        result = stamp(args.artifact, args.out, args.candidate_id, args.control)
    else:
        result = manifest(args.standard, args.out, args.fast)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
