"""One explicitly authorized software-fault recovery; no fitting or game seeds.

Usage: python3 tools/recover_heart_distill_test.py REPO ORIGINAL NEW_ROOT REVIEWED_SHA
Preserves the original failed bundle/latch and evaluates the same selected model.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import heart_rollout_distill as evaluator

ORIGINAL_EVALUATOR = '2ba64f6fa34a39099be4c16c2f3cd16b8a97c29c9e1e95126a60748a63195011'
FIXED_EVALUATOR = 'a3704fc700985276f70c491a89fb043662ea0f7e203214a9e0dcf3b0f03781be'
AUTHORITY = 'Rerun the necessary parts with the bug fixed and continue'
EVIDENCE = Path('docs/experiments/evidence/heart_rollout_distill_20261016')
AMENDMENT = Path('docs/experiments/evidence/heart_rollout_distill_recovery_20261016/PROTOCOL.md')


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def check_repair(original, fixed):
    expected = original.replace('x,b,y,k,e,a=tensor_rows(rows,v)', 'x,b,y,k,e,token_attrs=tensor_rows(rows,v)')
    expected = expected.replace('e[i:i+128],a[i:i+128]', 'e[i:i+128],token_attrs[i:i+128]')
    expected = expected.replace('e[:1],a[:1]', 'e[:1],token_attrs[:1]')
    expected = expected.replace('e[:32],a[:32]', 'e[:32],token_attrs[:32]')
    expected = expected.replace(
        "        a=baseline['perSource'].get(str(seed),{}); z=student['perSource'].get(str(seed),{})\n"
        "        if 'regret' in a and 'regret' in z: deltas.append(a['regret']-z['regret'])",
        "        baseline_source=baseline['perSource'].get(str(seed),{})\n"
        "        student_source=student['perSource'].get(str(seed),{})\n"
        "        if 'regret' in baseline_source and 'regret' in student_source:\n"
        "            deltas.append(baseline_source['regret']-student_source['regret'])")
    if fixed != expected or fixed == original:
        raise ValueError('repair exceeds the exact variable-rename allowlist')


def selection_for_recovery(selection, freeze_sha, evaluator_sha):
    result = copy.deepcopy(selection)
    result['freezeSha256'] = freeze_sha
    result['toolSha256'] = evaluator_sha
    return result


def verify_original(repo, original):
    case = json.loads((repo/EVIDENCE/'result.json').read_text())
    if case['verdict'] != 'INVALID_TEST_EXECUTION':
        raise ValueError('not the documented failed study')
    for path, digest in case['custody'].items():
        if evaluator.sha(original/path) != digest:
            raise ValueError('original custody changed: '+path)
    if (original/'fit/test-result.json').exists():
        raise ValueError('original TEST unexpectedly has a result')
    freeze = json.loads((original/'freeze.json').read_text())
    if freeze['reviewedSha'] != case['sourceSha']:
        raise ValueError('original producer identity changed')
    evaluator.verify_tools(freeze)
    evaluator.verify_bundle(original, freeze)
    evaluator.verify_corpus(original, freeze)  # bytes/hashes/receipts only
    build = json.loads((original/'build-receipt.json').read_text())
    if evaluator.sha(original/'build.log') != build['logSha256']:
        raise ValueError('original build log changed')
    return freeze


def run(repo, original, root, reviewed):
    if root == original or original in root.parents or root.exists():
        raise ValueError('recovery requires a new separate directory')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() != reviewed:
        raise ValueError('recovery source is not the reviewed commit')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip():
        raise ValueError('recovery source must be clean')
    fixed = repo/'tools/heart_rollout_distill.py'
    old = original/'run/heart_rollout_distill.py'
    if evaluator.sha(old) != ORIGINAL_EVALUATOR or evaluator.sha(fixed) != FIXED_EVALUATOR:
        raise ValueError('unexpected evaluator revision')
    check_repair(old.read_text(), fixed.read_text())
    freeze = verify_original(repo, original)
    for name in ('heart_record_encoder.py', 'heart1_leaf_reference.py'):
        if evaluator.sha(repo/'tools'/name) != evaluator.sha(original/'run'/name):
            raise ValueError('recovery preparation imports a changed helper: '+name)
    selection = json.loads((original/'fit/selection.json').read_text())
    root.mkdir()
    shutil.copytree(original/'run', root/'run')
    shutil.copy2(root/'run/PROTOCOL.md', root/'run/ORIGINAL-PROTOCOL.md')
    shutil.copy2(repo/AMENDMENT, root/'run/PROTOCOL.md')
    shutil.copy2(fixed, root/'run/heart_rollout_distill.py')
    shutil.copy2(repo/'tools/recover_heart_distill_test.py', root/'run/recover_heart_distill_test.py')
    for name in ('build-receipt.json', 'build.log', 'corpus-manifest.json'):
        shutil.copy2(original/name, root/name)
    out = root/'fit'
    out.mkdir()
    for name in ('selected.pt', 'vocabulary.json'):
        shutil.copy2(original/'fit'/name, out/name)
    shutil.copy2(original/'fit/selection.json', root/'original-selection.json')
    for seed in freeze['splits']['test']:
        for suffix in ('.receipt.json', '.sib.jsonl'):
            name = f'seed-{seed}'+suffix
            shutil.copy2(original/name, root/name)
    recovery = {'authority': AUTHORITY, 'originalRoot': str(original),
                'originalFreezeSha256': evaluator.sha(original/'freeze.json'),
                'originalSelectionSha256': evaluator.sha(original/'fit/selection.json'),
                'originalTestLatchSha256': evaluator.sha(original/'fit/test-opened.json'),
                'producerReviewedSha': freeze['reviewedSha'], 'analysisReviewedSha': reviewed,
                'samePreviouslyOpenedHoldout': True, 'newAttemptLimit': 1, 'timeoutSeconds': 600}
    freeze['recovery'] = recovery
    for path, digest in freeze['toolHashes'].items():
        if Path(path).name != 'heart_rollout_distill.py' and evaluator.sha(root/'run'/Path(path).name) != digest:
            raise ValueError('unchanged tool copy differs: '+path)
    freeze['toolHashes'] = {str(root/'run'/Path(p).name): evaluator.sha(root/'run'/Path(p).name)
                            for p in freeze['toolHashes']}
    freeze['toolHashes'][str(root/'run/recover_heart_distill_test.py')] = evaluator.sha(root/'run/recover_heart_distill_test.py')
    freeze['protocolSha256'] = evaluator.sha(root/'run/PROTOCOL.md')
    write(root/'freeze.json', freeze)
    selected = selection_for_recovery(selection, evaluator.sha(root/'freeze.json'), FIXED_EVALUATOR)
    write(out/'selection.json', selected)
    evaluator.verify_tools(freeze)
    evaluator.verify_bundle(root, freeze)
    evaluator.verify_corpus(root, freeze, 'test')
    for name, key in [('selected.pt', 'checkpointSha256'), ('vocabulary.json', 'vocabularySha256')]:
        if evaluator.sha(out/name) != selection[key]:
            raise ValueError('selected artifact copy changed')
    write(root/'recovery-authorization.json', recovery)
    started = time.monotonic()
    command = [sys.executable, str(root/'run/heart_rollout_distill.py'), 'test', str(root), str(out)]
    with (root/'test-recovery.log').open('x') as log:
        try:
            code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600).returncode
        except subprocess.TimeoutExpired:
            code = 124
    verify_original(repo, original)
    receipt = {'returncode': code, 'seconds': time.monotonic()-started, 'command': command,
               'originalCustodyRechecked': True, 'recoveryFreezeSha256': evaluator.sha(root/'freeze.json'),
               'recoverySelectionSha256': evaluator.sha(out/'selection.json')}
    if (out/'test-result.json').exists():
        receipt['resultSha256'] = evaluator.sha(out/'test-result.json')
    write(root/'recovery-receipt.json', receipt)
    if code:
        raise RuntimeError('authorized recovery failed; no automatic retry')
    print((out/'test-result.json').read_text())


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), sys.argv[4])
