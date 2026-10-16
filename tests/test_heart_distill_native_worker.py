import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
        value = wk.create_deadline(self.plan_path, share)
        self.assertEqual(value['deadlineEpoch'] - value['startEpoch'], 21600)
        with self.assertRaises(FileExistsError):
            wk.create_deadline(self.plan_path, share)
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
        wk.create_deadline(self.plan_path, share)
        done = wk.worker(self.plan_path, self.plan_sha, REPO, bundle, self.root / 'w25' / 'out', share, 25)
        self.assertEqual(done['tar'], 'w25-test-SEALED.tar.gz')
        self.assertEqual([o['returncode'] for o in done['outcomes']], [0, 0])
        for seed in (110164048, 110164049):
            r = json.loads((share / f'receipts/seed-{seed}.receipt.json').read_text())
            self.assertEqual((r['attempt'], r['returncode'], r['studentPriorContract']['share']), (1, 0, 1.0))
            self.assertIn('captureSha256', r)
            self.assertNotIn('opaque', json.dumps(r))
        self.assertEqual(wk.sha(share / done['tar']), done['tarSha256'])
        with tarfile.open(share / done['tar']) as tar:
            self.assertIn('w25-test-SEALED/seed-110164048.sib.jsonl', tar.getnames())
        self.assertEqual(json.loads((share / 'w25-test-SEALED.DONE.json').read_text())['tarSha256'], done['tarSha256'])
        with self.assertRaises(ValueError):
            wk.worker(self.plan_path, '0' * 64, REPO, bundle, self.root / 'x', share, 1)

    def test_interrupted_attempt_is_preserved_and_rerun(self):
        bundle = self.make_bundle()
        share, out = self.root / 'share', self.root / 'w1' / 'out'
        wk.create_deadline(self.plan_path, share)
        out.mkdir(parents=True)
        (out / 'seed-110164000.log').write_text('partial')
        for seed in (110164000, 110164001):
            wk.claim_attempt(share, seed, 1, 'lost-container')
        done = wk.worker(self.plan_path, self.plan_sha, REPO, bundle, out, share, 1)
        self.assertEqual([o['attempt'] for o in done['outcomes']], [2, 2])
        self.assertIn('interrupted-attempt1/seed-110164000.log', done['files'])
        self.assertEqual(done['tar'], 'w01-train.tar.gz')


if __name__ == '__main__':
    unittest.main()
