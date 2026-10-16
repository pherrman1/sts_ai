import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import unittest.mock

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
        for name, value in [('QUALIFIED_CPU', wk.host_identity()['cpuModel']),
                            ('QUALIFIED_CANARY_SHA256', wk.sha(self.canary))]:
            patch = unittest.mock.patch.object(wk, name, value)
            patch.start()
            self.addCleanup(patch.stop)

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
        with self.assertRaises(RuntimeError):
            wk.claim_attempt(share, 7, 1, 'boot-b')
        self.assertFalse((share / 'claims/seed-7.attempt2.json').exists())
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
            self.prior_claim(share, seed)
        done = wk.worker(self.plan_path, self.plan_sha, REPO, bundle, out, share, 1)
        self.assertEqual([o['attempt'] for o in done['outcomes']], [2, 2])
        r = json.loads((share / 'receipts/seed-110164000.receipt.json').read_text())
        self.assertIn('interrupted-attempt1/seed-110164000.log', r['files'])
        self.assertEqual(r['archive'], 'sources/seed-110164000.attempt2.tar.gz')

    def test_worker_command_line_reports_outcomes(self):
        bundle = self.make_bundle()
        share = self.root / 'share'
        wk.create_deadline(self.plan_path, share, self.canary)
        argv = ['x', 'worker', str(self.plan_path), self.plan_sha, str(bundle), str(self.root / 'w3' / 'out'),
                str(share), '3']
        import contextlib, io, sys
        out = io.StringIO()
        with unittest.mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(out):
            wk.main()
        self.assertIn('worker done w03-train [[110164004, "receipted", 0], [110164005, "receipted", 0]]', out.getvalue())

    def dead_identity(self):
        child = subprocess.Popen(['sleep', '300'], start_new_session=True)
        try:
            identity = wk.process_identity(child.pid)
        finally:
            child.terminate()
            child.wait(timeout=5)
        return identity

    def prior_claim(self, share, seed, owner=None, producer=None):
        claims = share / 'claims'
        claims.mkdir(parents=True, exist_ok=True)
        (claims / f'seed-{seed}.attempt1.json').write_text(json.dumps(
            {'identity': owner or self.dead_identity()}))
        (claims / f'seed-{seed}.attempt1.child.json').write_text(json.dumps(
            {'identity': producer or self.dead_identity()}))

    def test_live_orphan_is_not_signalled_or_retried(self):
        share = self.root / 'share'
        here = wk.host_identity()['bootId']
        orphan = subprocess.Popen(['sleep', '300'], start_new_session=True)
        self.addCleanup(lambda: orphan.poll() is None and orphan.kill())
        self.prior_claim(share, 9, producer=wk.process_identity(orphan.pid))
        with unittest.mock.patch.object(wk.os, 'killpg') as signal_group:
            with self.assertRaises(RuntimeError):
                wk.claim_attempt(share, 9, 1, here)
            signal_group.assert_not_called()
        self.assertIsNone(orphan.poll())
        self.assertFalse((share / 'claims/seed-9.attempt2.json').exists())
        orphan.terminate(); orphan.wait(timeout=5)
        self.assertEqual(wk.claim_attempt(share, 9, 1, here), 2)

    def test_ambiguous_claims_never_create_retry(self):
        here = wk.host_identity()['bootId']
        for case in ('legacy', 'missing-child', 'foreign-boot', 'foreign-namespace', 'bad-identity'):
            with self.subTest(case=case):
                share = self.root / case
                self.prior_claim(share, 9)
                claim = share / 'claims/seed-9.attempt1.json'
                data = json.loads(claim.read_text())
                if case == 'legacy': data = {'bootId': here, 'pid': 123}
                elif case == 'missing-child': (share / 'claims/seed-9.attempt1.child.json').unlink()
                elif case == 'foreign-boot': data['identity']['bootId'] = 'other'
                elif case == 'foreign-namespace': data['identity']['pidNamespace'] = 'pid:[other]'
                else: data['identity']['startTicks'] = None
                claim.write_text(json.dumps(data))
                with self.assertRaises(RuntimeError): wk.claim_attempt(share, 9, 1, here)
                self.assertFalse((share / 'claims/seed-9.attempt2.json').exists())

    def test_pid_reuse_cannot_authorize_signalling_or_skip_live_group(self):
        share = self.root / 'share'
        owner = wk.process_identity(os.getpid())
        owner['startTicks'] -= 1  # old worker exited; this numeric PID has been reused
        self.prior_claim(share, 9, owner=owner)
        with unittest.mock.patch.object(wk, '_group_running', return_value=True), \
                unittest.mock.patch.object(wk.os, 'killpg') as signal_group:
            with self.assertRaises(RuntimeError): wk.claim_attempt(share, 9, 1, owner['bootId'])
            signal_group.assert_not_called()
        self.assertFalse((share / 'claims/seed-9.attempt2.json').exists())
        with unittest.mock.patch.object(wk, '_group_running', side_effect=RuntimeError('unreadable proc')):
            with self.assertRaises(RuntimeError): wk.claim_attempt(share, 9, 1, owner['bootId'])
        self.assertFalse((share / 'claims/seed-9.attempt2.json').exists())
        self.assertEqual(wk.claim_attempt(share, 9, 1, owner['bootId']), 2)

    def test_cpu_qualification_precedes_any_source_or_claim(self):
        share = self.root / 'share'
        wk.create_deadline(self.plan_path, share, self.canary)
        archive = share / 'canaries/w01-canary.tar.gz'
        archive.parent.mkdir(); archive.write_bytes(b'not a qualification approval')
        for pin in ('QUALIFIED_CPU', 'QUALIFIED_CANARY_SHA256'):
            with self.subTest(pin=pin), unittest.mock.patch.object(wk, pin, 'unqualified'), \
                    unittest.mock.patch.object(wk, 'run_unit') as source:
                with self.assertRaises(RuntimeError):
                    wk.worker(self.plan_path, self.plan_sha, REPO, self.root / 'no-bundle',
                              self.root / 'no-output', share, 1)
                source.assert_not_called()
                self.assertFalse((share / 'claims').exists())
                self.assertFalse((self.root / 'no-output').exists())

    def test_group_inspection_errors_are_not_absence(self):
        fake = unittest.mock.Mock()
        fake.read_text.side_effect = PermissionError('unreadable')
        with unittest.mock.patch.object(wk.Path, 'glob', return_value=[fake]):
            with self.assertRaises(RuntimeError): wk._group_running(123)
        fake.read_text.side_effect = None
        fake.read_text.return_value = 'malformed stat'
        with unittest.mock.patch.object(wk.Path, 'glob', return_value=[fake]):
            with self.assertRaises(RuntimeError): wk._group_running(123)

    def test_vanished_snapshot_requires_kernel_group_absence(self):
        gone = unittest.mock.Mock()
        gone.read_text.side_effect = FileNotFoundError('process exited after glob')
        with unittest.mock.patch.object(wk.Path, 'glob', return_value=[gone]):
            with unittest.mock.patch.object(wk.os, 'killpg') as probe:
                self.assertTrue(wk._group_running(123))
                probe.assert_called_once_with(123, 0)
            with unittest.mock.patch.object(wk.os, 'killpg', side_effect=PermissionError('unknown')):
                with self.assertRaises(RuntimeError): wk._group_running(123)
            with unittest.mock.patch.object(wk.os, 'killpg', side_effect=ProcessLookupError('absent')):
                self.assertFalse(wk._group_running(123))

    def test_child_record_failure_aborts_our_owned_process(self):
        bundle = self.make_bundle()
        # A synthetic producer that would outlive a failed on_start callback.
        (bundle/'one_combat').write_text('#!/bin/sh\nexec sleep 300\n')
        manifest = json.loads((bundle/'bundle.json').read_text())
        wk.PRODUCER_SHA256 = manifest['files']['one_combat'] = wk.sha(bundle/'one_combat')
        manifest['producerSha256'] = wk.PRODUCER_SHA256
        (bundle/'bundle.json').write_text(json.dumps(manifest))
        real_popen = wk.subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child
        def fail_record(identity): raise OSError('cannot record child')
        with unittest.mock.patch.object(wk.subprocess, 'Popen', side_effect=launch):
            with self.assertRaisesRegex(OSError, 'cannot record child'):
                wk.run_unit(self.plan, REPO, bundle, self.root, 110164000,
                            wk.time.time()+30, on_start=fail_record)
        # check_output() also uses Popen while verifying the frozen contract.
        self.assertTrue(children)
        self.assertTrue(all(child.poll() is not None for child in children))
        self.assertFalse((self.root/'seed-110164000.receipt.json').exists())

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
