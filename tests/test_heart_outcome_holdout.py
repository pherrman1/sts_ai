"""Synthetic only: no genuine TEST archive or game seed is accessed."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_holdout as hold


class HoldoutTests(unittest.TestCase):
    def fixture(self,root,mutate=None,seed=110181440):
        path=root/'SEALED-test.tar.gz'
        members=[(f'test/seed-{seed}{suffix}',b'{}',tarfile.REGTYPE,10.) for suffix in hold.audit.SUFFIXES]
        if mutate:members=mutate(members)
        with tarfile.open(path,'w:gz') as tar:
            for name,data,kind,mtime in members:
                info=tarfile.TarInfo(name);info.size=len(data) if kind==tarfile.REGTYPE else 0
                info.type=kind;info.mtime=mtime
                tar.addfile(info,io.BytesIO(data) if kind==tarfile.REGTYPE else None)
        return path

    def claim(self,root):
        hold.claim_opening(root,{'freezeSha256':'synthetic-freeze','testSources':hold.SEEDS})

    def test_unopened_cannot_even_list_test_members(self):
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            with patch.object(hold.tarfile,'open',side_effect=AssertionError('parser reached')):
                with self.assertRaises(ValueError):list(hold.sealed_units(Path(d)/'SEALED-test.tar.gz',[110181440],Path(d),'synthetic-freeze',(0,20)))

    def test_exact_canonical_root_and_symlink_enforcement(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'canonical';root.mkdir();copied=Path(d)/'copy';copied.mkdir()
            link=Path(d)/'link';link.symlink_to(root,target_is_directory=True)
            with patch.object(hold,'CANONICAL_ROOT',root):
                self.assertEqual(hold.canonical_root(root),root)
                for path in (copied,link):
                    with self.assertRaises(ValueError):hold.canonical_root(path)

    def test_durable_latch_is_exclusive_for_every_output_root(self):
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            root=Path(d);self.claim(root)
            before=(root/'test-opened.json').read_bytes()
            with self.assertRaises(FileExistsError):self.claim(root)
            for name in ('same','different'):
                args=SimpleNamespace(import_root=root,out=root/name)
                with patch.object(hold,'identities',side_effect=AssertionError('preflight after consumed latch')):
                    with self.assertRaisesRegex(ValueError,'already opened'):hold.run(args)
            self.assertEqual(before,(root/'test-opened.json').read_bytes())

    def test_opening_review_requires_exact_freeze_and_explicit_true(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'freeze.json').write_text('{}')
            good={'verdict':'PASS','testOpeningAuthorized':True,'freezeSha256':hold.sha(root/'freeze.json'),'sourceReviewSha256':'source'}
            for bad in ({**good,'testOpeningAuthorized':False},{k:v for k,v in good.items() if k!='testOpeningAuthorized'},{**good,'freezeSha256':'changed'},{**good,'sourceReviewSha256':'changed'}):
                (root/'opening-reviewed.json').write_text(json.dumps(bad))
                with self.assertRaises((ValueError,KeyError)):hold.opening_approval(root,'source')
            (root/'opening-reviewed.json').write_text(json.dumps(good))
            hold.opening_approval(root,'source')
            (root/'freeze.json').write_text('{"alteredBudget":true}')
            with self.assertRaises(ValueError):hold.opening_approval(root,'source')

    def test_wrong_freeze_latch_does_not_reach_parser(self):
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            root=Path(d);self.claim(root)
            with patch.object(hold.tarfile,'open',side_effect=AssertionError('parser reached')):
                with self.assertRaises(ValueError):list(hold.sealed_units(root/'SEALED-test.tar.gz',[110181440],root,'different',(0,20)))

    def test_strict_complete_archive_and_assignment(self):
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            root=Path(d);self.claim(root);path=self.fixture(root)
            parsed=list(hold.sealed_units(path,[110181440],root,'synthetic-freeze',(0,20)))
            self.assertEqual(len(parsed),1);self.assertEqual(set(parsed[0][1]),set(hold.audit.SUFFIXES))
            with self.assertRaises(ValueError):list(hold.sealed_units(path,[110181441],root,'synthetic-freeze',(0,20)))
            with self.assertRaises(ValueError):list(hold.sealed_units(path,[110180000],root,'synthetic-freeze',(0,20)))

    def test_unsafe_duplicate_partial_unknown_link_and_clock_refused(self):
        mutations=[lambda m:m[:-1],lambda m:m[:-1]+[m[0]],
                   lambda m:[('../bad',*m[0][1:])]+m[1:],
                   lambda m:[('test/seed-110181440.unknown',*m[0][1:])]+m[1:],
                   lambda m:[(m[0][0],b'',tarfile.SYMTYPE,10.)]+m[1:],
                   lambda m:[(*m[0][:3],21.)]+m[1:]]
        for change in mutations:
            with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
                root=Path(d);self.claim(root);path=self.fixture(root,change)
                with self.assertRaises(ValueError):list(hold.sealed_units(path,[110181440],root,'synthetic-freeze',(0,20)))

    def test_superseded_partial_filename_prohibited(self):
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            root=Path(d);self.claim(root);path=root/'SEALED-partial-out.tar.gz';path.write_bytes(b'opaque')
            with patch.object(hold.tarfile,'open',side_effect=AssertionError('partial parser reached')):
                with self.assertRaises(ValueError):list(hold.sealed_units(path,[110181440],root,'synthetic-freeze',(0,20)))

    def test_complete_synthetic_source_passes_deep_audit_after_guard(self):
        from test_heart_outcome_import import payload
        seed=110181440
        files={suffix:data.replace(b'110180000',str(seed).encode()) for suffix,data in payload().items()}
        rec=json.loads(files['.receipt.json'])
        rec['files']={f'seed-{seed}{suffix}':hold.audit.digest(data) for suffix,data in files.items() if suffix!='.receipt.json'}
        files['.receipt.json']=json.dumps(rec).encode()
        with tempfile.TemporaryDirectory() as d,patch.object(hold,'CANONICAL_ROOT',Path(d)):
            root=Path(d);self.claim(root)
            path=self.fixture(root,lambda _: [(f'test/seed-{seed}{suffix}',data,tarfile.REGTYPE,10.) for suffix,data in files.items()])
            got=list(hold.sealed_units(path,[seed],root,'synthetic-freeze',(0,20)))
            receipt=hold.audit.verify_unit(seed,got[0][1],{'environment':{}},{'fixed':'policy'},root/'synthetic.jsonl')
            self.assertEqual((receipt['seed'],receipt['states'],receipt['label']),(seed,1,0))

    @unittest.skipUnless(os.environ.get('STS_OUTCOME_ENCODER_REPO'),'pinned actual encoder/head synthetic scoring')
    def test_actual_frozen_model_and_head_score_synthetic_public_record(self):
        from test_heart_outcome_import import record
        args=SimpleNamespace(silverbot=Path(os.environ['STS_OUTCOME_ENCODER_REPO']),
            checkpoint=Path(os.environ['STS_OUTCOME_CHECKPOINT']),
            training_root=Path(os.environ['STS_OUTCOME_TRAINING_ROOT']))
        network,net,head=hold.load_models(args)
        before=[hold.tensor_digest(m) for m in (net,head)]
        companion=record();empty=copy.deepcopy(companion)
        for key in ('cards_offered.cards','cards_offered.upgrades','relics_offered','potions_offered','fixed_actions','paths_offered'):empty[key]=[]
        _,x=hold.value.encode_batch(network,net,[{'record':empty}],companion)
        with torch.inference_mode():z=head(x)
        self.assertTrue(torch.isfinite(z).all().item())
        self.assertEqual(before,[hold.tensor_digest(m) for m in (net,head)])
        self.assertFalse(any(t.requires_grad for m in (net,head) for t in m.parameters()))

    def test_landmarks_use_actual_order_and_do_not_invent_survivors(self):
        meta=[{'seed':1,'index':0,'act':1,'floor':0},{'seed':1,'index':1,'act':1,'floor':9},
              {'seed':1,'index':2,'act':1,'floor':16},{'seed':2,'index':0,'act':1,'floor':0},
              {'seed':2,'index':1,'act':2,'floor':18}]
        np.testing.assert_array_equal(hold.landmark_indices(meta,'start'),[0,3])
        np.testing.assert_array_equal(hold.landmark_indices(meta,'act1_floor8'),[1])
        np.testing.assert_array_equal(hold.landmark_indices(meta,'act1_floor16'),[2])

    def data(self,n=200,miscalibrated=False,constant=False):
        meta,z=[],[]
        for source in range(n):
            y=source%2
            p=.5 if constant else (.65 if y else .15) if miscalibrated else (.88 if y else .12)
            for index,floor in enumerate((0,8,16)):
                meta.append({'seed':source,'label':y,'index':index,'act':1,'floor':floor,'screen':5})
                z.append(np.log(p/(1-p)))
        return meta,np.array(z)

    def test_bootstrap_is_clustered_and_deterministic(self):
        got=hold.bootstrap_interval(np.array([[-1.,-2.]]*6),499)
        self.assertEqual(got['interval95'],[[-1.,-2.],[-1.,-2.]])
        self.assertEqual(got,hold.bootstrap_interval(np.array([[-1.,-2.]]*6),499))

    def test_positive_and_miscalibrated_signals_have_separate_verdicts(self):
        good=hold.evaluate(*self.data())
        self.assertEqual(good['verdict'],'OFFLINE_HOLDOUT_PASS')
        bad=hold.evaluate(*self.data(miscalibrated=True))
        self.assertTrue(bad['primarySignalPass']);self.assertFalse(bad['earlyMeanBiasPass'])
        self.assertEqual(bad['verdict'],'HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN')

    def test_mean_bias_gate_does_not_imply_ranking(self):
        r=hold.evaluate(*self.data(n=600,constant=True))
        self.assertTrue(r['earlyMeanBiasPass'])
        self.assertAlmostEqual(r['landmarks']['start']['model']['auc'],.5)

    def test_insufficient_classes_override_numeric_gain(self):
        meta,z=self.data(n=6)
        r=hold.evaluate(meta,z)
        self.assertEqual(r['verdict'],'INSUFFICIENT_TEST_CLASS_COVERAGE')

    def test_invalid_logits_and_missing_early_landmarks_fail_closed(self):
        meta,z=self.data(n=10);z[0]=np.nan
        with self.assertRaises(ValueError):hold.evaluate(meta,z)
        meta,z=self.data()
        for row in meta:row['act']=2
        r=hold.evaluate(meta,z)
        self.assertEqual(r['landmarks']['act1_floor8']['sources'],0)
        self.assertFalse(r['earlyMeanBiasPass'])


if __name__=='__main__':unittest.main()
