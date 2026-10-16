import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('worker', REPO / 'tools/heart_distill_native_worker.py')
wk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wk)
p = wk.plan_mod

# Stub producer: writes the files the real one_combat writes and the contract log lines.
STUB = r'''#!/usr/bin/env bash
set -eu
seed="$5"; csv="$6"
echo "[heart1] loaded studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1)"
echo "[ooc mcts] prior=heart1 leaf_policy=heart1"
echo "seed,floor" > "$csv"; echo "$seed,1" >> "$csv"
echo '{"decision":0}' > "$STS_OOC_DECISION_TRACE"
echo '{"action":1}' > "$STS_OOC_MCTS_TRACE.actions.jsonl"
echo "{\"seed\":$seed,\"heart1_prior_nodes\":9,\"heart1_prior_fallbacks\":0,\"prior_leaf_steps\":0,\"heart1_leaf_steps\":4,\"heart1_leaf_fallbacks\":0}" > "$STS_OOC_MCTS_TRACE.support.jsonl"
if [ -n "${STS_OOC_SIBLING_CAPTURE:-}" ]; then echo '{"opaque":true}' > "$STS_OOC_SIBLING_CAPTURE"; fi
'''


class NativeWorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = p.assignment(REPO, 32)
        self.plan_path = self.root / 'plan.json'
        self.plan_path.write_text(json.dumps(self.plan, sort_keys=True))
        self.plan_sha = wk.sha(self.plan_path)
        self.canary = self.root / 'canary.json'
        self.canary.write_text(json.dumps({'gatePass': True}))

    def tearDown(self):
        self.tmp.cleanup()

    def make_bundle(self):
        stub = self.root / 'one_combat'
        stub.write_text(STUB)
        stub.chmod(0o755)
        weights = self.root / 'studentc.bin'
        weights.write_bytes(b'weights')
        old = wk.PRODUCER_SHA256, wk.STUDENT_C_SHA256
        wk.PRODUCER_SHA256, wk.STUDENT_C_SHA256 = wk.sha(stub), wk.sha(weights)
        self.addCleanup(lambda: setattr(wk, 'PRODUCER_SHA256', old[0]) or setattr(wk, 'STUDENT_C_SHA256', old[1]))
        out = self.root / 'bundle'
        wk.bundle(REPO, stub, weights, out)
        return out

    def test_contiguous_split_pure_blocks(self):
        for workers in (8, 16, 32, 64):
            plan = p.assignment(REPO, workers)
            for w in range(workers):
                mine = [s for s in plan['sources'] if s['worker'] == w]
                self.assertEqual(len(mine), 64 // workers)
                self.assertEqual(len({s['split'] for s in mine}), 1)
        mine = [s['seed'] for s in self.plan['sources'] if s['worker'] == 24]
        self.assertEqual(mine, [110164048, 110164049])

    def test_canary_specs_need_frozen_flag_and_tag(self):
        off = p.shard_spec(self.plan, 110163994, '/b', '/o', 100, capture=False, tag='canary-control')
        self.assertNotIn('STS_OOC_SIBLING_CAPTURE', off['environment'])
        self.assertTrue(off['base'].endswith('/canary-control'))
        on = p.shard_spec(self.plan, 110163995, '/b', '/o', 100, capture=True, tag='canary-second')
        self.assertEqual(on['environment']['STS_OOC_SIBLING_REPEATS'], '64')
        for args in [(110163995, False, 'canary-x'), (110163994, True, None), (110164000, True, 'canary-x'),
                     (110164000, False, None), (110163995, True, 'x')]:
            with self.assertRaises(ValueError):
                p.shard_spec(self.plan, args[0], '/b', '/o', 100, capture=args[1], tag=args[2])

    def test_attempts_rerun_once_and_respect_receipts(self):
        share = self.root / 'share'
        here = wk.host_identity()['bootId']
        self.assertEqual(wk.claim_attempt(share, 7, 1, here), 1)
        with self.assertRaises(RuntimeError):  # same container, claimant (this process) still alive
            wk.claim_attempt(share, 7, 1, here)
        self.assertEqual(wk.claim_attempt(share, 7, 1, 'boot-b'), 2)
        with self.assertRaises(RuntimeError):
            wk.claim_attempt(share, 7, 1, 'boot-c')
        (share / 'receipts/seed-8.receipt.json').write_text('{}')
        self.assertIsNone(wk.claim_attempt(share, 8, 1, 'boot-a'))

    def test_deadline_created_once_and_bound(self):
        share = self.root / 'share'
        failed = self.root / 'failed.json'
        failed.write_text(json.dumps({'gatePass': False}))
        with self.assertRaises(ValueError):
            wk.create_deadline(self.plan_path, share, failed)
        value = wk.create_deadline(self.plan_path, share, self.canary)
        self.assertEqual(value['deadlineEpoch'] - value['startEpoch'], 21600)
        with self.assertRaises(FileExistsError):
            wk.create_deadline(self.plan_path, share, self.canary)
        self.assertEqual(wk.read_deadline(share, self.plan_sha), value['deadlineEpoch'])
        with self.assertRaises(ValueError):
            wk.read_deadline(share, '0' * 64)

    def test_bundle_refuses_other_producer(self):
        other = self.root / 'other'
        other.write_bytes(b'not the producer')
        with self.assertRaises(ValueError):
            wk.bundle(REPO, other, other, self.root / 'b2')

    def test_worker_end_to_end_with_sealed_test(self):
        bundle = self.make_bundle()
        share = self.root / 'share'
        wk.create_deadline(self.plan_path, share, self.canary)
        done = wk.worker(self.plan_path, self.plan_sha, REPO, bundle, self.root / 'w25' / 'out', share, 25)
        self.assertEqual([o['returncode'] for o in done['outcomes']], [0, 0])
        for seed in (110164048, 110164049):
            r = json.loads((share / f'receipts/seed-{seed}.receipt.json').read_text())
            self.assertEqual((r['attempt'], r['returncode'], r['split']), (1, 0, 'test'))
            self.assertEqual(r['archive'], f'sources/seed-{seed}.attempt1-SEALED.tar.gz')
            self.assertEqual(wk.sha(share / r['archive']), r['archiveSha256'])
            self.assertNotIn('opaque', json.dumps(r))
            with tarfile.open(share / r['archive']) as tar:
                inner = f'seed-{seed}.attempt1-SEALED/seed-{seed}.receipt.json'
                local = json.loads(tar.extractfile(inner).read())
            self.assertEqual(local['studentPriorContract']['share'], 1.0)
            self.assertEqual(local['environment']['HOME'], os.environ.get('HOME', ''))
            self.assertIn('captureSha256', local)
        self.assertTrue((share / 'w25-test.DONE.json').exists())
        with self.assertRaises(ValueError):
            wk.worker(self.plan_path, '0' * 64, REPO, bundle, self.root / 'x', share, 1)

    def test_interrupted_attempt_is_preserved_and_rerun(self):
        bundle = self.make_bundle()
        share, out = self.root / 'share', self.root / 'w1' / 'out'
        wk.create_deadline(self.plan_path, share, self.canary)
        out.mkdir(parents=True)
        (out / 'seed-110164000.log').write_text('partial')
        for seed in (110164000, 110164001):
            wk.claim_attempt(share, seed, 1, 'lost-container')
        done = wk.worker(self.plan_path, self.plan_sha, REPO, bundle, out, share, 1)
        self.assertEqual([o['attempt'] for o in done['outcomes']], [2, 2])
        r = json.loads((share / 'receipts/seed-110164000.receipt.json').read_text())
        self.assertIn('interrupted-attempt1/seed-110164000.log', r['files'])
        self.assertEqual(r['archive'], 'sources/seed-110164000.attempt2.tar.gz')

    def test_orphaned_producer_is_killed_before_rerun(self):
        share = self.root / 'share'
        here = wk.host_identity()['bootId']
        orphan = subprocess.Popen(['sleep', '300'], start_new_session=True)
        self.addCleanup(lambda: orphan.poll() is None and orphan.kill())
        (share / 'claims').mkdir(parents=True)
        dead = subprocess.Popen(['true']); dead.wait()
        (share / 'claims/seed-9.attempt1.json').write_text(json.dumps({'bootId': here, 'pid': dead.pid}))
        (share / 'claims/seed-9.attempt1.child.json').write_text(json.dumps({'pgid': orphan.pid}))
        self.assertEqual(wk.claim_attempt(share, 9, 1, here), 2)
        orphan.wait(timeout=5)
        self.assertIsNotNone(orphan.returncode)

    def test_receipt_is_published_after_data(self):
        bundle = self.make_bundle()
        share = self.root / 'share'
        wk.create_deadline(self.plan_path, share, self.canary)
        order = []
        real = wk.export_file
        def spy(src, dst):
            order.append(Path(dst).parent.name)
            return real(src, dst)
        wk.export_file = spy
        self.addCleanup(lambda: setattr(wk, 'export_file', real))
        wk.worker(self.plan_path, self.plan_sha, REPO, bundle, self.root / 'w2' / 'out', share, 2)
        per_source = [d for d in order if d in ('sources', 'receipts')]
        self.assertEqual(sorted(per_source), ['receipts', 'receipts', 'sources', 'sources'])
        for i, d in enumerate(per_source):
            if d == 'receipts':
                self.assertGreaterEqual(per_source[:i].count('sources'), per_source[:i + 1].count('receipts'))


if __name__ == '__main__':
    unittest.main()
