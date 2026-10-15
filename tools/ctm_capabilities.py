"""Exclusion-lifting capabilities for #418 research-candidate CTM artifacts.

`writhing-ritual` marks a near-full candidate as supporting Writhing Mass with a Ritual
Dagger in the deck (capability `writhingRitual: {}`) and drops the
`writhing_ritual_intersection` support exclusion. It changes no tensors: the sampler
already draws the Writhing event and the Dagger payouts jointly. Whether the
retrained heads earn it is the intersection cohort gate at qualification
(combat_transition_near_full_exposure.py --writhing-ritual). A
ctm_research_candidate_v3 manifest must list the same capability.

    python tools/ctm_capabilities.py writhing-ritual --artifact IN.native --out OUT.native

The escape capability has its own fit (tools/ctm_escape.py); either order works.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools import ctm_escape as e
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_escape as e


def writhing_ritual(artifact, out):
    metadata, tensors = e.read_artifact(artifact)
    if 'researchCandidate' not in metadata:
        raise ValueError('only a research candidate may carry a capability')
    capabilities = metadata.get('capabilities', {})
    if 'writhingRitual' in capabilities or 'writhing_ritual_intersection' not in metadata['supportExclusions']:
        raise ValueError('artifact already supports Writhing Mass with Ritual Dagger')
    metadata = dict(metadata, capabilities=dict(capabilities, writhingRitual={}),
                    supportExclusions=[r for r in metadata['supportExclusions'] if r != 'writhing_ritual_intersection'])
    e.write_artifact(out, metadata, tensors)
    return dict(artifact=str(out), artifactSha256=e.sha256(out), baseArtifactSha256=e.sha256(artifact),
                capabilities=metadata['capabilities'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('writhing-ritual')
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(writhing_ritual(args.artifact, args.out), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
