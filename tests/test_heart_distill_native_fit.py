import importlib.util
import io
import json
import shutil
from pathlib import Path
import tarfile
import tempfile
import unittest
import unittest.mock

REPO = Path(__file__).resolve().parents[1]
try:
    import sklearn, torch  # noqa: F401  (the staged trainer imports them)
    HAVE_TRAINER_DEPS = True
except ImportError:
    HAVE_TRAINER_DEPS = False

spec = importlib.util.spec_from_file_location('native_fit', REPO / 'tools/heart_distill_native_fit.py')
nf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nf)

# Stub for the trainer subprocess: writes what fit/test write, without reading TEST.
STUB = r'''
import hashlib, json, sys
from pathlib import Path
mode, root, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if mode == 'fit':
    out.mkdir()
    (out / 'selected.pt').write_bytes(b'state'); (out / 'vocabulary.json').write_text('[]')
    for n in ('coverage.json', 'training.json', 'resources.json'): (out / n).write_text('{}')
    (out / 'selection.json').write_text(json.dumps({'checkpointSha256': h(out / 'selected.pt'),
        'vocabularySha256': h(out / 'vocabulary.json'), 'freezeSha256': h(root / 'freeze.json'),
        'toolSha256': TRAINER, 'corpusManifestSha256': h(root / 'corpus-manifest.json'), 'weight': .5}))
else:
    with (out / 'test-opened.json').open('x') as f: f.write('{}')
    (out / 'test-result.json').write_text('{"verdict": "NOT_SHOWN"}')
'''


def tar_add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


class ConsumedTestSealTest(unittest.TestCase):
    def test_completed_corpus_and_copied_delivery_refuse_before_setup(self):
        packet = REPO / 'docs/experiments/evidence/arm_c_native_campaign_20261016'
        self.assertEqual(nf.CONSUMED_CORPORA[nf.CORPUS_MANIFEST_SHA256],
                         nf.sha(packet / 'fit/eval/fit/test-result.json'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = root / 'original'; original.mkdir()
            shutil.copy2(packet / 'corpus-manifest.json', original / 'corpus-manifest.json')
            copied = root / 'copied'; shutil.copytree(original, copied)
            with unittest.mock.patch.object(nf, 'stage') as stage, \
                    unittest.mock.patch.object(nf, 'verify') as verify, \
                    unittest.mock.patch.object(nf.subprocess, 'run') as evaluator:
                for corpus in (original, copied):
                    with self.assertRaisesRegex(FileExistsError, 'TEST consumed'):
                        nf.prepare_test(corpus, root/'binary', root/'model', root/'fit', root/'eval')
                    with self.assertRaisesRegex(FileExistsError, 'TEST consumed'):
                        nf.test(corpus, root/'eval', 'unreviewed')
                    self.assertFalse((corpus / nf.LATCH).exists())
                stage.assert_not_called(); verify.assert_not_called(); evaluator.assert_not_called()
                self.assertFalse((root/'eval').exists())
            (copied/'corpus-manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'no new campaign authorization'):
                nf.require_unopened_test(copied)


@unittest.skipUnless(HAVE_TRAINER_DEPS, 'trainer dependencies (torch, sklearn) not installed')
class NativeFitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.producer = self.root / 'one_combat'
        self.producer.write_bytes(b'producer')
        self.student = self.root / 'studentc.bin'
        self.student.write_bytes(b'student')
        patches = {'PRODUCER_SHA256': nf.sha(self.producer), 'STUDENT_C_SHA256': nf.sha(self.student)}
        self.corpus = self.make_corpus(patches)
        patches['CORPUS_MANIFEST_SHA256'] = nf.sha(self.corpus / 'corpus-manifest.json')
        for name, value in patches.items():
            p = unittest.mock.patch.object(nf, name, value)
            p.start()
            self.addCleanup(p.stop)
        stub = self.root / 'stub_trainer.py'
        stub.write_text(f'TRAINER = {nf.TOOLS["heart_rollout_distill.py"][1]!r}\n' + STUB)
        p = unittest.mock.patch.object(nf, 'trainer_command',
                                       lambda root, mode, out: [nf.sys.executable, str(stub), mode, str(root), str(out)])
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def make_corpus(self, ids, bad_seed=None):
        corpus = self.root / ('corpus-bad' if bad_seed else 'corpus')
        corpus.mkdir()
        sources = {}
        tars = {'corpus-train-validation.tar': tarfile.open(corpus / 'corpus-train-validation.tar', 'w'),
                'corpus-test-SEALED.tar': tarfile.open(corpus / 'corpus-test-SEALED.tar', 'w')}
        for split, seeds in nf.SPLITS.items():
            for seed in seeds:
                stem = f'seed-{seed}.attempt1' + ('-SEALED' if split == 'test' else '')
                capture = json.dumps({'seed': seed, 'opaque': True}).encode() + b'\n'
                claimed = capture if seed != bad_seed else b'other'
                receipt = json.dumps({'seed': seed, 'returncode': 0, 'attempt': 1, 'capture': True,
                                      'captureSha256': nf.sha_bytes(claimed)}).encode()
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode='w:gz') as inner:
                    tar_add(inner, f'{stem}/seed-{seed}.receipt.json', receipt)
                    tar_add(inner, f'{stem}/seed-{seed}.sib.jsonl', capture)
                archive = buf.getvalue()
                share = json.dumps({'receiptSha256': nf.sha_bytes(receipt),
                                    'files': {f'seed-{seed}.sib.jsonl': nf.sha_bytes(claimed)}}).encode()
                tar = tars['corpus-test-SEALED.tar' if split == 'test' else 'corpus-train-validation.tar']
                tar_add(tar, f'sources/{stem}.tar.gz', archive)
                tar_add(tar, f'receipts/seed-{seed}.receipt.json', share)
                sources[str(seed)] = {'archive': f'sources/{stem}.tar.gz', 'archiveSha256': nf.sha_bytes(archive),
                                      'attempt': 1, 'returncode': 0, 'shareReceiptSha256': nf.sha_bytes(share),
                                      'split': split}
        for tar in tars.values():
            tar.close()
        manifest = {name: nf.sha(corpus / name) for name in tars}
        manifest.update({'sources': sources, 'producerSha256': ids['PRODUCER_SHA256'],
                         'studentcSha256': ids['STUDENT_C_SHA256'], 'runCommit': 'c' * 40, 'planSha256': 'p',
                         'canaryJsonSha256': 'k', 'deadlineSha256': 'd', 'schema': 'arm-c-native-corpus-v1'})
        (corpus / 'corpus-manifest.json').write_text(json.dumps(manifest, sort_keys=True))
        return corpus

    def stage(self, name='data'):
        return nf.stage(self.corpus, self.producer, self.student, self.root / name)

    def test_stage_builds_trainer_layout(self):
        self.stage()
        data = self.root / 'data'
        module, freeze = nf.verify(data)
        self.assertEqual(freeze['splits']['test'], list(range(110164048, 110164064)))
        self.assertEqual(freeze['capturePolicyContract'], 'heart1')
        manifest = json.loads((data / 'corpus-manifest.json').read_text())
        self.assertEqual(len(manifest['sources']), 64)
        # TEST bytes are copied verbatim and bound only by hash.
        self.assertEqual(nf.sha(data / 'seed-110164063.sib.jsonl'),
                         manifest['sources']['110164063']['captureSha256'])
        with self.assertRaises(FileExistsError):
            self.stage()

    def test_stage_refuses_unbound_capture(self):
        bad = self.make_corpus({'PRODUCER_SHA256': nf.PRODUCER_SHA256, 'STUDENT_C_SHA256': nf.STUDENT_C_SHA256},
                               bad_seed=110164050)
        with unittest.mock.patch.object(nf, 'CORPUS_MANIFEST_SHA256', nf.sha(bad / 'corpus-manifest.json')):
            with self.assertRaises(ValueError):
                nf.stage(bad, self.producer, self.student, self.root / 'bad')
        with self.assertRaises(ValueError):  # not the frozen manifest
            nf.stage(bad, self.producer, self.student, self.root / 'bad2')

    def test_fit_once_then_bound_one_shot_test(self):
        self.stage()
        data = self.root / 'data'
        receipt = nf.fit(data)
        self.assertEqual(receipt['returncode'], 0)
        with self.assertRaises(FileExistsError):
            nf.fit(data)
        with unittest.mock.patch.object(nf, 'cpu_model', lambda: 'Other CPU'):
            with self.assertRaises(ValueError):
                nf.prepare_test(self.corpus, self.producer, self.student, data, self.root / 'eval0')
        with unittest.mock.patch.object(nf, 'cpu_model', lambda: nf.COLLECTION_CPU):
            plan_sha = nf.prepare_test(self.corpus, self.producer, self.student, data, self.root / 'eval')
            ev = self.root / 'eval'
            selection = json.loads((ev / 'fit/selection.json').read_text())
            self.assertEqual(selection['freezeSha256'], nf.sha(ev / 'freeze.json'))
            plan = json.loads((ev / 'test-plan.json').read_text())
            self.assertEqual(plan['fittedSelectionSha256'], nf.sha(data / 'fit/selection.json'))
            # A second prepared root is allowed before the opening ...
            plan2 = nf.prepare_test(self.corpus, self.producer, self.student, data, self.root / 'eval2')
            with self.assertRaises(ValueError):
                nf.test(self.corpus, ev, '0' * 64)
            self.assertFalse((ev / 'fit/test-opened.json').exists())
            self.assertFalse((self.corpus / nf.LATCH).exists())
            result = nf.test(self.corpus, ev, plan_sha)
            self.assertEqual(result['returncode'], 0)
            self.assertIsNotNone(result['resultSha256'])
            latch = json.loads((self.corpus / nf.LATCH).read_text())
            self.assertEqual(latch['testPlanSha256'], plan_sha)
            with self.assertRaises((ValueError, FileExistsError)):
                nf.test(self.corpus, ev, plan_sha)
            # ... but after it, no other root can open TEST or be prepared.
            with self.assertRaises(FileExistsError):
                nf.test(self.corpus, self.root / 'eval2', plan2)
            self.assertFalse((self.root / 'eval2/fit/test-opened.json').exists())
            with self.assertRaises(FileExistsError):
                nf.prepare_test(self.corpus, self.producer, self.student, data, self.root / 'eval3')

    def test_prepare_test_refuses_changed_selection(self):
        self.stage()
        data = self.root / 'data'
        nf.fit(data)
        (data / 'fit/selected.pt').write_bytes(b'swapped')
        with unittest.mock.patch.object(nf, 'cpu_model', lambda: nf.COLLECTION_CPU):
            with self.assertRaises(ValueError):
                nf.prepare_test(self.corpus, self.producer, self.student, data, self.root / 'eval')


if __name__ == '__main__':
    unittest.main()
