"""Native-corpus adapter for the unchanged §494 trainer (tools/heart_rollout_distill.py at 9d83adb).

Subcommands (all refuse to overwrite; TEST capture bytes are copied by hash, never parsed here):
  stage CORPUS PRODUCER STUDENTC ROOT   build the trainer DATA_ROOT from the sealed native corpus
  check ROOT                            identities + TRAIN/VALIDATION coverage gate (no fitting)
  fit ROOT                              the unchanged six fits, once, 1200 s cap; no TEST
  prepare-test CORPUS PRODUCER STUDENTC FITTED NEW_ROOT
                                        evaluator on the collection CPU model: re-stage with this
                                        runtime, bind the fitted selection, freeze the CPU-cost rule
  test NEW_ROOT TEST_PLAN_SHA256        one-shot TEST through the unchanged trainer; no retry

CORPUS is the directory holding corpus-manifest.json, corpus-train-validation.tar and
corpus-test-SEALED.tar. The fit may run on another machine (Philipp's GPU); the CPU-cost
comparison behind the >=4x gate is only evaluated on the CPU model that measured the rollout
cost during collection, so TEST runs in a re-staged root on that hardware.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
SOURCE = '9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3'
CORPUS_MANIFEST_SHA256 = 'cd8929b1226531390d06a6c38250065f9d6e37d00c1903dd688b9ae4c5f11c19'
PRODUCER_SHA256 = '86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf'
STUDENT_C_SHA256 = 'eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509'
COLLECTION_CPU = 'Intel(R) Xeon(R) Processor @ 2.10GHz'
TOOLS = {  # run/ name -> (repository path, sha256 at SOURCE)
    'heart_rollout_distill.py': ('tools/heart_rollout_distill.py',
                                 '9c8b30e7608088bfca755a94f079a0bdad8c45382179e1b1fd1d99894efa7a94'),
    'heart_record_encoder.py': ('tools/heart_record_encoder.py',
                                'a476e8b0aba85ff2089ac9233ba6816ea98ab8992efea3efb65f3ef7d3ccfc34'),
    'heart1_leaf_reference.py': ('tools/heart1_leaf_reference.py',
                                 '8f8bff8e65c80ab8a74cd64456fb11bc68caaf9fdcd856e5252fa15243b3b4b5'),
}
PROTOCOL = ('docs/experiments/evidence/arm_c_rollout_distill_20261016/PROTOCOL.md',
            'f1e2ee75bee754d7e15d3e74d8a9e386d3080c68c2ab85bcb8df18b44e3ee28e')
OPUS490 = ('docs/experiments/evidence/ooc_sibling_leaf_capture64_20261015/tv_within_x2b.json.pt',
           'be88826842290651c149432c595b8404aa80da91622dbca776966e661f76914e')
FIRST = 110164000
SPLITS = {'train': list(range(FIRST, FIRST + 40)), 'validation': list(range(FIRST + 40, FIRST + 48)),
          'test': list(range(FIRST + 48, FIRST + 64))}
FIT_SECONDS = 1200
TEST_SECONDS = 600


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def cpu_model():
    for line in Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith('model name'):
            return line.split(':', 1)[1].strip()
    return None


def trainer(root):
    """The run/ copy of the unchanged trainer (its helper imports resolve to run/ first)."""
    import importlib.util
    run = (Path(root) / 'run').resolve()
    if str(run) not in sys.path:
        sys.path.insert(0, str(run))
    name = 'heart_rollout_distill_' + sha_bytes(str(run).encode())[:12]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, run / 'heart_rollout_distill.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


def _member(tar, name):
    stream = tar.extractfile(name)
    if stream is None:
        raise ValueError('missing archive member: ' + name)
    return stream.read()


def unpack_sources(corpus, root):
    """Copy each source's receipt and capture from the hashed per-source archives."""
    corpus = Path(corpus)
    if sha(corpus / 'corpus-manifest.json') != CORPUS_MANIFEST_SHA256:
        raise ValueError('not the frozen native corpus manifest')
    manifest = json.loads((corpus / 'corpus-manifest.json').read_text())
    if manifest['producerSha256'] != PRODUCER_SHA256 or manifest['studentcSha256'] != STUDENT_C_SHA256:
        raise ValueError('corpus producer/model identity mismatch')
    for name in ('corpus-train-validation.tar', 'corpus-test-SEALED.tar'):
        if sha(corpus / name) != manifest[name]:
            raise ValueError('corpus archive changed: ' + name)
    expected = {str(s): split for split, seeds in SPLITS.items() for s in seeds}
    if {k: v['split'] for k, v in manifest['sources'].items()} != expected:
        raise ValueError('corpus splits are not the frozen 40/8/16 cohort')
    sources = {}
    for name in ('corpus-train-validation.tar', 'corpus-test-SEALED.tar'):
        with tarfile.open(corpus / name) as outer:
            for seed, entry in sorted(manifest['sources'].items()):
                if (entry['split'] == 'test') != (name == 'corpus-test-SEALED.tar'):
                    continue
                if entry['returncode'] != 0:
                    raise ValueError('source did not complete: ' + seed)
                share_receipt = _member(outer, f'receipts/seed-{seed}.receipt.json')
                archive = _member(outer, entry['archive'])
                if sha_bytes(share_receipt) != entry['shareReceiptSha256'] or sha_bytes(archive) != entry['archiveSha256']:
                    raise ValueError('source custody changed: ' + seed)
                share = json.loads(share_receipt)
                stem = Path(entry['archive']).name[:-len('.tar.gz')]
                with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as inner:
                    receipt = _member(inner, f'{stem}/seed-{seed}.receipt.json')
                    capture = _member(inner, f'{stem}/seed-{seed}.sib.jsonl')
                local = json.loads(receipt)
                if (sha_bytes(receipt) != share['receiptSha256'] or local['seed'] != int(seed)
                        or local['returncode'] != 0 or local['attempt'] != entry['attempt']
                        or not local['capture'] or local['captureSha256'] != sha_bytes(capture)
                        or share['files'].get(f'seed-{seed}.sib.jsonl') != local['captureSha256']):
                    raise ValueError('source receipt does not bind its capture: ' + seed)
                base = root / f'seed-{seed}'
                base.with_suffix('.receipt.json').write_bytes(receipt)
                base.with_suffix('.sib.jsonl').write_bytes(capture)
                sources[seed] = {'receiptSha256': sha_bytes(receipt), 'captureSha256': local['captureSha256']}
    if len(sources) != 64:
        raise ValueError('corpus is not 64 sources')
    return manifest, sources


def stage(corpus, producer, student_c, root, repo=None, extra=None):
    repo, root = Path(repo or HERE.parent).resolve(), Path(root)
    if sha(producer) != PRODUCER_SHA256 or sha(student_c) != STUDENT_C_SHA256:
        raise ValueError('producer/model is not the frozen identity')
    root.mkdir(parents=True, exist_ok=False)
    run = root / 'run'
    run.mkdir()
    for name, (rel, digest) in TOOLS.items():
        shutil.copy2(repo / rel, run / name)
        if sha(run / name) != digest:
            raise ValueError('trainer source differs from ' + SOURCE[:8] + ': ' + rel)
    shutil.copy2(Path(__file__).resolve(), run / Path(__file__).name)
    for (rel, digest), name in ((PROTOCOL, 'PROTOCOL.md'), (OPUS490, 'opus490.pt')):
        shutil.copy2(repo / rel, run / name)
        if sha(run / name) != digest:
            raise ValueError('frozen file differs: ' + rel)
    shutil.copy2(producer, run / 'one_combat')
    shutil.copy2(student_c, run / 'studentc.bin')
    manifest, sources = unpack_sources(corpus, root)
    write_json(root / 'corpus-manifest.json', {'sources': sources,
                                               'nativeCorpusManifestSha256': CORPUS_MANIFEST_SHA256})
    write_json(root / 'build-receipt.json', {
        'reviewedSha': SOURCE, 'returncode': 0, 'binarySha256': PRODUCER_SHA256,
        'nativeRunCommit': manifest['runCommit'],
        'note': 'hosted rebuild of the reviewed source, byte-identical to the original local producer'})
    module = trainer(root)
    freeze = {
        'reviewedSha': SOURCE, 'binarySha256': PRODUCER_SHA256,
        'models': {'studentc.bin': STUDENT_C_SHA256}, 'splits': SPLITS,
        'capturePolicyContract': 'heart1', 'repeats': 64, 'captureEvery': 4, 'maxLeaves': 64, 'maxDepth': 1,
        'toolHashes': {str(run / n): sha(run / n) for n in [*TOOLS, Path(__file__).name]},
        'protocolSha256': sha(run / 'PROTOCOL.md'), 'opus490CheckpointSha256': sha(run / 'opus490.pt'),
        'buildReceiptSha256': sha(root / 'build-receipt.json'), 'runtime': module.runtime_identity(),
        'nativeCorpus': {k: manifest[k] for k in ('runCommit', 'planSha256', 'canaryJsonSha256',
                                                  'deadlineSha256', 'schema')}
                        | {'manifestSha256': CORPUS_MANIFEST_SHA256},
        'host': {'cpuModel': cpu_model(), 'platform': platform.platform()},
    }
    if extra:
        freeze.update(extra)
    write_json(root / 'freeze.json', freeze)
    verify(root)
    return sha(root / 'freeze.json')


def verify(root):
    root = Path(root)
    module = trainer(root)
    freeze = json.loads((root / 'freeze.json').read_text())
    module.verify_tools(freeze)
    module.verify_bundle(root, freeze)
    module.verify_corpus(root, freeze)  # hashes and receipts only
    return module, freeze


def check(root):
    module, freeze = verify(root)
    out = {}
    for split in ('train', 'validation'):
        _, groups, coverage = module.load_split(Path(root), freeze, split)
        out[split] = {k: coverage[k] for k in ('raw', 'accepted', 'groups', 'sourcesWithGroups', 'expectedSources')}
    t, v = out['train'], out['validation']
    out['gatePass'] = (t['groups'] >= 500 and v['groups'] >= 100
                       and all(c['accepted'] >= .8 * c['raw'] and c['sourcesWithGroups'] == c['expectedSources']
                               for c in (t, v)))
    return out


def trainer_command(root, mode, out):
    return [sys.executable, str(Path(root) / 'run/heart_rollout_distill.py'), mode, str(root), str(out)]


def _gpu():
    try:
        import torch
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:  # identity only
        return None


def fit(root):
    root = Path(root)
    verify(root)
    if (root / 'fit').exists() or (root / 'fit-receipt.json').exists():
        raise FileExistsError('fit already attempted; no refit')
    started = time.monotonic()
    with (root / 'fit.log').open('x') as log:
        try:
            code = subprocess.run(trainer_command(root, 'fit', root / 'fit'), stdout=log,
                                  stderr=subprocess.STDOUT, timeout=FIT_SECONDS).returncode
        except subprocess.TimeoutExpired:
            code = 124
    receipt = {'returncode': code, 'seconds': time.monotonic() - started, 'freezeSha256': sha(root / 'freeze.json'),
               'logSha256': sha(root / 'fit.log'), 'gpu': _gpu(), 'cpuModel': cpu_model(),
               'files': {p.name: sha(p) for p in sorted((root / 'fit').glob('*')) if p.is_file()}
               if (root / 'fit').exists() else {}}
    write_json(root / 'fit-receipt.json', receipt)
    return receipt


def prepare_test(corpus, producer, student_c, fitted, new_root, repo=None):
    fitted, new_root = Path(fitted), Path(new_root)
    if cpu_model() != COLLECTION_CPU:
        raise ValueError('TEST must run on the collection CPU model: ' + COLLECTION_CPU)
    receipt = json.loads((fitted / 'fit-receipt.json').read_text())
    freeze = json.loads((fitted / 'freeze.json').read_text())
    selection_path = fitted / 'fit/selection.json'
    selection = json.loads(selection_path.read_text())
    if (receipt['returncode'] != 0 or receipt['freezeSha256'] != sha(fitted / 'freeze.json')
            or selection['freezeSha256'] != receipt['freezeSha256']
            or receipt['files'].get('selection.json') != sha(selection_path)
            or (fitted / 'fit/test-opened.json').exists() or (fitted / 'fit/verdict.json').exists()):
        raise ValueError('fitted root is not one completed, unopened selection')
    for name, key in (('selected.pt', 'checkpointSha256'), ('vocabulary.json', 'vocabularySha256')):
        if sha(fitted / 'fit' / name) != selection[key] or receipt['files'].get(name) != selection[key]:
            raise ValueError('selected artifact changed: ' + name)
    adapter = sha(Path(__file__).resolve())
    fitted_tools = {Path(p).name: d for p, d in freeze['toolHashes'].items()}
    if (selection['toolSha256'] != TOOLS['heart_rollout_distill.py'][1]
            or fitted_tools != {**{n: d for n, (_, d) in TOOLS.items()}, Path(__file__).name: adapter}
            or freeze['nativeCorpus']['manifestSha256'] != CORPUS_MANIFEST_SHA256):
        raise ValueError('fitted root used other tools or another corpus')
    provenance = {'fittedFreezeSha256': receipt['freezeSha256'], 'fittedSelectionSha256': sha(selection_path),
                  'fitReceiptSha256': sha(fitted / 'fit-receipt.json'), 'fitRuntime': freeze['runtime'],
                  'fitGpu': receipt.get('gpu'), 'fitSeconds': receipt['seconds']}
    freeze_sha = stage(corpus, producer, student_c, new_root, repo, {'fitProvenance': provenance})
    if sha(new_root / 'corpus-manifest.json') != selection['corpusManifestSha256']:
        raise ValueError('re-staged corpus manifest differs from the fitted one')
    out = new_root / 'fit'
    out.mkdir()
    for name in ('selected.pt', 'vocabulary.json', 'coverage.json', 'training.json', 'resources.json'):
        shutil.copy2(fitted / 'fit' / name, out / name)
    write_json(out / 'selection.json', {**selection, 'freezeSha256': freeze_sha})
    plan = {'freezeSha256': freeze_sha, 'selectionSha256': sha(out / 'selection.json'), **provenance,
            'trainerSha256': TOOLS['heart_rollout_distill.py'][1], 'attemptLimit': 1, 'timeoutSeconds': TEST_SECONDS,
            'cpuCostComparison': {
                'evaluatorCpuModel': cpu_model(), 'collectionCpuModel': COLLECTION_CPU,
                'rule': 'unchanged trainer test(): speedup = mean per-rollout producer CPU seconds '
                        '(rolloutCpuSeconds/64, measured during collection on the collection CPU model) / '
                        '(single-row tensor inference + feature encoding + required X2-B anchor CPU), '
                        'inference and encoding timed by process_time on this host with torch threads=1; '
                        'gate >=4x is part of the unchanged TEST gate'}}
    write_json(new_root / 'test-plan.json', plan)
    return sha(new_root / 'test-plan.json')


def test(root, plan_sha):
    root = Path(root)
    if sha(root / 'test-plan.json') != plan_sha:
        raise ValueError('test plan is not the reviewed one')
    if cpu_model() != COLLECTION_CPU:
        raise ValueError('TEST must run on the collection CPU model')
    plan = json.loads((root / 'test-plan.json').read_text())
    verify(root)
    if (sha(root / 'freeze.json') != plan['freezeSha256'] or sha(root / 'fit/selection.json') != plan['selectionSha256']
            or (root / 'fit/test-opened.json').exists() or (root / 'test-receipt.json').exists()):
        raise ValueError('frozen selection changed or TEST already opened; no retry')
    started = time.monotonic()
    with (root / 'test.log').open('x') as log:
        try:
            code = subprocess.run(trainer_command(root, 'test', root / 'fit'), stdout=log,
                                  stderr=subprocess.STDOUT, timeout=TEST_SECONDS).returncode
        except subprocess.TimeoutExpired:
            code = 124
    result = root / 'fit/test-result.json'
    receipt = {'returncode': code, 'seconds': time.monotonic() - started, 'testPlanSha256': plan_sha,
               'logSha256': sha(root / 'test.log'), 'cpuModel': cpu_model(),
               'resultSha256': sha(result) if result.exists() else None}
    write_json(root / 'test-receipt.json', receipt)
    return receipt


def main():
    a = sys.argv[1:]
    usage = SystemExit(__doc__)
    if not a:
        raise usage
    if a[0] == 'stage' and len(a) == 5:
        print('freeze', stage(*a[1:]))
    elif a[0] == 'check' and len(a) == 2:
        print(json.dumps(check(a[1]), sort_keys=True))
    elif a[0] == 'fit' and len(a) == 2:
        r = fit(a[1])
        print('fit returncode', r['returncode'], 'seconds', round(r['seconds']), 'gpu', r['gpu'])
        if r['returncode']:
            raise SystemExit(1)
    elif a[0] == 'prepare-test' and len(a) == 6:
        print('test-plan', prepare_test(*a[1:]))
    elif a[0] == 'test' and len(a) == 3:
        r = test(a[1], a[2])
        print('test returncode', r['returncode'], 'result', r['resultSha256'])
        if r['returncode']:
            raise SystemExit(1)
    else:
        raise usage


if __name__ == '__main__':
    main()
