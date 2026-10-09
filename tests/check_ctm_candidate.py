"""#418 step 10: tools/ctm_candidate.py stamps plain exports and writes manifests the native loader accepts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import ctm_candidate as cc, ctm_capabilities  # noqa: E402

FAST = ROOT / 'selfplay/models/combat_transition_deepsets_lizard_t2.native'
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
CANDIDATE = 'test-ctm-candidate-tool'


def probe(args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('STS_CTM_RESEARCH_CANDIDATE')}
    return subprocess.run([sys.argv[1], *map(str, args)], text=True, capture_output=True,
                          env={**clean, **(env or {})}, cwd=ROOT)


def expect(name, result, identity):
    if result.returncode != 0 or f'identity={identity}' not in result.stdout:
        raise RuntimeError(f'{name}: expected identity={identity}, got {result.stdout!r} {result.stderr!r}')
    print(name, 'PASS')


def refuses(name, call, message):
    try:
        call()
    except ValueError as error:
        if message not in str(error):
            raise RuntimeError(f'{name}: wrong refusal {error}') from error
        print(name, 'PASS')
        return
    raise RuntimeError(f'{name}: not refused')


def main():
    production = {path: path.read_bytes() for path in (FAST, STANDARD)}
    with tempfile.TemporaryDirectory() as directory:
        d = Path(directory)
        refuses('production_fast_refused', lambda: cc.stamp(FAST, d / 'x.native', control=STANDARD), 'production-promoted')
        # A plain fast export as package_deepsets_lizard_artifact writes it without --production.
        header, payload = cc.read(FAST)
        header.pop('productionPromotionEvidence')
        header['defaultForOocMcts'] = False
        header['qualification'] = dict(header['qualification'], classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS')
        header['experimentalDeepSets'] = dict(header['experimentalDeepSets'], qualified=False, defaultChanged=False)
        header['activeLizardCorrection'] = dict(header['activeLizardCorrection'], status='integration_candidate',
                                                qualified=False, defaultChanged=False)
        for key in ('gate2ResultsSha256', 'gate2Classification', 'gate2FrozenImplementationSha'):
            header['activeLizardCorrection'].pop(key, None)
        fast0 = d / 'fast0.native'
        cc.write(fast0, header, payload)

        std1 = d / 'std1.native'
        cc.stamp(STANDARD, std1, CANDIDATE)
        refuses('standard_stamped_twice', lambda: cc.stamp(std1, d / 'y.native', CANDIDATE), 'already')
        interim = cc.manifest(std1, d / 'interim.json')
        expect('interim_standard_only', probe(['--identity', std1], interim['env']), CANDIDATE)

        std = d / 'std.native'
        ctm_capabilities.writhing_ritual(std1, std)
        fast1 = d / 'fast1.native'
        stamped = cc.stamp(fast0, fast1, control=std)
        if stamped['controlSha256'] != cc.sha256(std) or cc.read(fast1)[1] != payload:
            raise RuntimeError('fast stamp did not bind the final standard artifact or changed the payload')
        # The interim manifest over FAST1 (ctmescapefeatures on the fast artifact): FAST1 loads alone,
        # and the loader refuses it paired with the capability-extended STD.
        interim_fast = cc.manifest(std, d / 'interim-fast.json', fast1)
        expect('interim_fast_alone', probe(['--identity', fast1], interim_fast['env']), CANDIDATE)
        paired = probe(['--pair-identity', fast1, std, 1], interim_fast['env'])
        if paired.returncode == 0 or 'disagree on the writhingRitual' not in paired.stderr:
            raise RuntimeError(f'interim pair not refused: {paired.stdout!r} {paired.stderr!r}')
        print('interim_pair_refused PASS')
        fast = d / 'fast.native'
        ctm_capabilities.writhing_ritual(fast1, fast)
        final = cc.manifest(std, d / 'final.json', fast)
        expect('final_pair', probe(['--pair-identity', fast, std, 1], final['env']), CANDIDATE)
        expect('final_fast', probe(['--identity', fast], final['env']), CANDIDATE)

        stale = d / 'stale.native'
        cc.stamp(fast0, stale, control=std1)
        refuses('stale_control', lambda: cc.build_manifest(std, stale), 'different standard artifact')
    if any(path.read_bytes() != data for path, data in production.items()):
        raise RuntimeError('production artifact changed')
    print('ctm candidate tool PASS')


if __name__ == '__main__':
    main()
