"""Focused scientific contracts, no game seeds or corpus/TEST access."""
import copy
import os
import json
import tempfile
from types import SimpleNamespace
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_value as value


class OutcomeValueTest(unittest.TestCase):
    def test_source_balance_is_not_row_balance(self):
        seeds = [1,1,1,2]
        w = value.source_weights(seeds)
        np.testing.assert_allclose(w,[1/6,1/6,1/6,1/2])
        self.assertAlmostEqual(float(w[:3].sum()),float(w[3]))

    def test_train_only_weighted_normalization(self):
        x = torch.cat([torch.zeros(3,64),torch.full((1,64),4.)])
        w = torch.tensor(value.source_weights([1,1,1,2]))
        h = value.ValueHead(x,w)
        torch.testing.assert_close(h.mean,torch.full((64,),2.))
        torch.testing.assert_close(h.scale,torch.full((64,),2.))
        self.assertEqual(sum(p.numel() for p in h.parameters()),4225)
        self.assertEqual(h(torch.zeros(2,64)).shape,(2,))

    def test_proper_scores_and_tie_auc(self):
        result = value.metric([0,1],[.5,.5],[.5,.5])
        self.assertAlmostEqual(result['bce'],np.log(2))
        self.assertAlmostEqual(result['brier'],.25)
        self.assertAlmostEqual(result['auc'],.5)
        self.assertEqual(value.metric([0,1],[.1,.9],[.8,.2])['auc'],1.)
        self.assertEqual(value.metric([0,1],[.9,.1],[.8,.2])['auc'],0.)
        self.assertIsNone(value.metric([1,1],[.2,.8],[1,1])['auc'])

    def test_invalid_predictions_fail(self):
        for pred in ([np.nan,.1],[-.1,.1],[1.1,.1]):
            with self.assertRaises(ValueError): value.metric([0,1],pred,[1,1])

    def test_sealed_split_cannot_reach_archive_reader(self):
        with patch.object(value.audit,'archive_units',side_effect=AssertionError('parser invoked')):
            with self.assertRaises(ValueError): list(value.read_sources(None,[],'test'))
            with self.assertRaises(ValueError): list(value.read_sources(None,[],'SEALED-test'))

    def test_trim_does_not_mutate_record(self):
        r = {'obs.mapY':2,'obs.map.ys':[1,2,3],'obs.map.xs':[4,5,6],
             'obs.map.roomTypes':[1,2,3],'obs.map.pathXs':[[0],[1],[2]]}
        before = copy.deepcopy(r)
        out = value.trim_record(r)
        self.assertEqual(out['obs.map.ys'],[2,3]);self.assertEqual(r,before)

    def test_source_cluster_bootstrap(self):
        meta = [{'seed':1,'label':0}]*3 + [{'seed':2,'label':1}]
        b = value.bootstrap(meta,np.array([.1,.1,.1,.9]),.5,np.array([-np.log(9)]*3+[np.log(9)]))
        self.assertLess(b['brier']['descriptive95'][1],0)
        self.assertAlmostEqual(b['brier']['mean'],-.24)

    def test_small_fit_only_changes_head(self):
        torch.set_num_threads(1)
        x = torch.zeros(8,64);x[4:,0]=1
        y = torch.tensor([0.]*4+[1.]*4)
        w = torch.full((8,),1/8,dtype=torch.float64)
        before = x.clone()
        best,history = value.train_one(x,y,w,x,y,w,0,time.monotonic()+20,steps=10,every=5)
        self.assertEqual(len(history),2);self.assertTrue(torch.equal(before,x))
        self.assertTrue(np.isfinite(best['validationBce']))
        self.assertEqual(set(best['state']),{'mean','scale','layers.0.weight','layers.0.bias','layers.2.weight','layers.2.bias'})

    def test_extreme_logit_loss_is_not_capped(self):
        logits = torch.tensor([-100.,100.])
        y = torch.tensor([1.,0.])
        expected = torch.nn.functional.binary_cross_entropy_with_logits(logits,y).item()
        m = value.metric(y.numpy(),torch.sigmoid(logits).numpy(),[.5,.5],logits.numpy())
        self.assertAlmostEqual(m['bce'],expected)
        self.assertEqual(m['bce'],100.)

    def test_consumed_run_never_reenters_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory);review = out/'review.json';review.write_text('{}')
            frozen = {'identity':{},'custody':{},'splits':value.SPLITS,'reviewSha256':value.sha(review),'encodingSeconds':3600}
            (out/'freeze.json').write_text(json.dumps(frozen))
            args = SimpleNamespace(out=out,review=review)
            with patch.object(value,'identity',return_value={}), patch.object(value,'audit_inputs',return_value=([],{})), patch.object(value,'load_net',side_effect=RuntimeError('synthetic stop')) as loader:
                with self.assertRaisesRegex(RuntimeError,'synthetic stop'): value.run(args)
                with self.assertRaises(FileExistsError): value.run(args)
                self.assertEqual(loader.call_count,1)

    @unittest.skipUnless(os.environ.get('STS_OUTCOME_ENCODER_REPO'),'optional pinned actual encoder fixture')
    def test_actual_encoder_empty_choice_bridge_and_frozen_policy(self):
        from test_heart_outcome_collect import record
        args = SimpleNamespace(silverbot=Path(os.environ['STS_OUTCOME_ENCODER_REPO']),
                               checkpoint=Path(os.environ['STS_OUTCOME_CHECKPOINT']))
        self.assertEqual(value.sha(args.checkpoint),value.CHECKPOINT)
        for device in ('cpu','cuda'):
            if device == 'cuda' and not torch.cuda.is_available(): continue
            network,net = value.load_net(args,device)
            before = {k:v.detach().cpu().clone() for k,v in net.state_dict().items()}
            companion = record();empty = record()
            for k in ('cards_offered.cards','cards_offered.upgrades','relics_offered','potions_offered','fixed_actions','paths_offered'): empty[k] = []
            row = {'record':empty,'seed':123,'label':1}
            logits,x = value.encode_batch(network,net,[row],companion,device)
            many,mx = value.encode_batch(network,net,[row]*32,companion,device)
            self.assertEqual(x.shape,(1,64));self.assertEqual(mx.shape,(32,64))
            torch.testing.assert_close(mx,x.expand(32,-1),atol=2e-5,rtol=2e-5)
            self.assertTrue(torch.isneginf(logits).all())
            alternate = copy.deepcopy(companion);alternate['obs.fixed_observation'][2] = 200
            _,alternate_x = value.encode_batch(network,net,[row],alternate,device)
            self.assertTrue(torch.equal(x,alternate_x))
            original,_ = value.encode_batch(network,net,[{'record':companion}],companion,device)
            h = value.ValueHead(x,torch.ones(1,device=device,dtype=torch.float64)).to(device)
            with torch.no_grad(): h.layers[-1].bias.add_(1)
            again,_ = value.encode_batch(network,net,[{'record':companion}],alternate,device)
            self.assertTrue(torch.equal(original,again))
            self.assertTrue(all(torch.equal(v.detach().cpu(),before[k]) for k,v in net.state_dict().items()))

    def test_expired_fit_does_not_train(self):
        x = torch.zeros(4,64);y = torch.tensor([0.,0.,1.,1.]);w = torch.full((4,),.25,dtype=torch.float64)
        with self.assertRaisesRegex(ValueError,'wall cap'):
            value.train_one(x,y,w,x,y,w,0,time.monotonic()-1,steps=1)


if __name__ == '__main__': unittest.main()
