#!/usr/bin/env python3
import unittest
from unittest.mock import Mock
import numpy as np
try:
    from tools import combat_transition_potion_decoder as d
    from tools import combat_transition_relic_legality as r
    from tools import combat_transition_surrogate as b
except ModuleNotFoundError:
    import combat_transition_potion_decoder as d
    import combat_transition_relic_legality as r
    import combat_transition_surrogate as b
try:
    import torch
except ImportError:
    torch = None

class ContractTests(unittest.TestCase):
    def test_nested_split_groups_original_train_only(self):
        original = {'members': {'train': list(range(10000)), 'validation': [10001], 'test': [10002]}}
        a = d.nested_manifest(original)
        self.assertEqual(a, d.nested_manifest(original))
        groups = [set(x) for x in a['members'].values()]
        self.assertEqual(set.union(*groups), set(range(10000)))
        for i, x in enumerate(groups):
            for y in groups[i+1:]: self.assertFalse(x & y)
        self.assertTrue(.78 < len(groups[0])/10000 < .82)
        with self.assertRaises(ValueError): d.nested_manifest({'members': {'train': [1, 1]}})
    def test_fit_requires_all_provenance_arguments_and_matching_review_sha(self):
        import contextlib
        import io
        pairs = [('--prepared-dir','p'), ('--split-manifest','s'), ('--output-dir','o'), ('--artifact-dir','a'), ('--code-sha','h'), ('--reviewed-sha','h')]
        args = ['fit'] + [v for pair in pairs for v in pair]
        self.assertEqual(d.parser().parse_args(args).code_sha,'h')
        for missing in range(len(pairs)):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                d.parser().parse_args(['fit'] + [v for i, pair in enumerate(pairs) if i != missing for v in pair])
        d.validate_review_sha('h','h','h')
        for values in [(None,'h','h'), ('h',None,'h'), ('h','other','h'), ('other','h','h'), ('h','h','other')]:
            with self.assertRaises(ValueError): d.validate_review_sha(*values)

    def test_roundtrip_all_legal_masks(self):
        for capacity in range(6):
            pre = np.array([[2, 3, 1, 4, 5]])
            legal = np.flatnonzero(d.legal_masks(pre, np.array([capacity]))[0])
            repeated = pre.repeat(len(legal), 0)
            caps = np.full(len(legal), capacity)
            post = d.decode_masks(repeated, caps, legal)
            np.testing.assert_array_equal(d.encode_masks(repeated, post, caps), legal)
            self.assertTrue(np.all((post == repeated) | (post == 1)))
            self.assertTrue(np.all(post[:, capacity:] == repeated[:, capacity:]))
    def test_multiple_consumptions_empty_unavailable(self):
        pre = np.array([[2, 3, 1, 4, 5]])
        np.testing.assert_array_equal(d.decode_masks(pre, [3], [3]), [[1, 1, 1, 4, 5]])
        for mask in [4, 8, 16, 32, -1]:
            with self.assertRaises(ValueError): d.decode_masks(pre, [3], [mask])
    def test_identity_creation_swap_and_substitution_rejected(self):
        for post in [[[3, 2, 1, 1, 1]], [[2, 2, 1, 1, 1]], [[4, 3, 1, 1, 1]], [[2, 3, 4, 1, 1]]]:
            with self.assertRaises(ValueError): d.encode_masks(np.array([[2,3,1,1,1]]), np.array(post), [3])
    def test_teacher_forced_and_sampled_conditioning(self):
        arrays = {'delta_index': np.array([2, 1]), 'y_hp': np.array([.5, .7])}
        delta, hp = d.conditioning(arrays, np.array([1]))
        np.testing.assert_array_equal(delta, [1]); np.testing.assert_allclose(hp, [.7])
        delta, hp = d.conditioning(arrays, np.array([1]), (np.array([0]), np.array([.2])))
        np.testing.assert_array_equal(delta, [0]); np.testing.assert_allclose(hp, [.2])
    def test_raw_audit_requires_predictor_visible_counter_and_rejects_illegal_target(self):
        from unittest.mock import patch
        from pathlib import Path
        import copy
        try:
            from tools.test_combat_transition_surrogate import predictor, state
        except ModuleNotFoundError:
            from test_combat_transition_surrogate import predictor, state
        pi, pre = predictor(), state()
        pi['relics'][0]['relicId'] = b._RELIC_IDS['SUNDIAL']
        pre['relics'][0]['id'] = b._RELIC_IDS['SUNDIAL']
        post = copy.deepcopy(pre); post['relics'][0]['data'] = 3
        row = {'sourceSeed':1,'fightIdx':0,'predictorInput':pi,'transition':{'pre':pre,'post':post}}
        with patch.object(b,'iter_rows',return_value=iter([row])):
            out = r.audit(Path('/unused'))
        self.assertEqual(out['contradictionCount'],1)
        pi['relics'][0]['data'] = 1
        with patch.object(b,'iter_rows',return_value=iter([row])):
            out = r.audit(Path('/unused'))
        self.assertEqual(out['futureSilverRequired']['SUNDIAL_predictor_counter_mismatch'],1)

    def test_native_relic_domain_mask_targets_and_draws(self):
        rng = np.random.default_rng(1)
        for name, period in r.CYCLIC.items():
            rid = b._RELIC_IDS[name]
            for pre in range(period):
                deltas = np.arange(-period, period + 1)
                logp = r.constrained_logp(np.arange(len(deltas), dtype=float), deltas, rid, pre)
                self.assertAlmostEqual(np.exp(logp).sum(), 1)
                for post in r.legal_posts(rid, pre):
                    self.assertTrue(np.isfinite(logp[deltas == post - pre]).all())
                for _ in range(10):
                    delta = rng.choice(deltas, p=np.exp(logp))
                    self.assertIn(pre + delta, r.legal_posts(rid, pre))
            with self.assertRaises(ValueError): r.legal_posts(rid, -1)
    def test_one_way_deterministic_and_copy_counters(self):
        self.assertEqual(r.legal_posts(b._RELIC_IDS['LIZARD_TAIL'], 0), {0})
        self.assertEqual(r.legal_posts(b._RELIC_IDS['LIZARD_TAIL'], 1), {0,1})
        self.assertEqual(r.legal_posts(b._RELIC_IDS['LIZARD_TAIL'], 1, mark_of_bloom=True), {1})
        for pre in range(4): self.assertEqual(r.legal_posts(b._RELIC_IDS['NEOWS_LAMENT'], pre), {max(0, pre-1)})
        for pre in range(3):
            self.assertEqual(r.legal_posts(b._RELIC_IDS['OMAMORI'], pre, 0), {pre})
        for name in r.COPY_COUNTERS: self.assertEqual(r.legal_posts(b._RELIC_IDS[name], 19), {19})
        tea = b._RELIC_IDS['ANCIENT_TEA_SET']
        for pre in (0, 1): self.assertEqual(r.legal_posts(tea, pre), {0})
        with self.assertRaises(ValueError): r.legal_posts(tea, -2)
    def test_death_terminates_before_transition(self):
        decoder = Mock(side_effect=AssertionError('must not call'))
        self.assertIsNone(d.sample_composed({}, 0., {}, decoder, None, {}, np.random.default_rng(1)))
        decoder.assert_not_called()

@unittest.skipIf(torch is None, 'Torch unavailable')
class TorchTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.z = torch.zeros((2,64), requires_grad=True)
        self.pre = torch.tensor([[2,3,1,1,1],[2,1,1,1,1]])
        self.capacity = torch.tensor([3,1])
        self.delta = torch.tensor([0,1])
        self.hp = torch.tensor([.5,.7])
    def inputs(self): return self.z, self.pre, self.capacity, self.delta, self.hp
    def test_both_models_mask_normalize_and_freeze_state(self):
        for kind in ['independent','joint']:
            model = d.new_decoder(kind, 2)
            logp = model(*self.inputs())
            torch.testing.assert_close(logp.exp().sum(-1), torch.ones(2))
            legal = d.legal_masks(self.pre.numpy(), self.capacity.numpy())
            self.assertTrue(np.all(logp.detach().numpy()[~legal] == -np.inf))
            loss = -logp[0,3] - logp[1,0]; loss.backward()
            self.assertIsNone(self.z.grad)
            self.assertTrue(any(x.grad is not None for x in model.parameters()))
    def test_independent_exact_product_bernoulli(self):
        model = d.new_decoder('independent', 2)
        for parameter in model.parameters(): parameter.data.zero_()
        model.mlp[-1].bias.data.fill_(float(np.log(3)))
        prob = model(*self.inputs()).exp().detach().numpy()
        self.assertAlmostEqual(float(prob[0,3]), .75**2, places=6)
        self.assertAlmostEqual(float(prob[0,0]), .25**2, places=6)
        self.assertAlmostEqual(float(prob[1,1]), .75, places=6)
    def test_arms_receive_identical_full_inventory_features_and_hidden_architecture(self):
        independent = d.new_decoder('independent', 2)
        joint = d.new_decoder('joint', 2)
        features = independent.features(self.z, self.pre, self.delta, self.hp)
        self.assertEqual(features.shape, (2,133))
        torch.testing.assert_close(features, joint.features(self.z, self.pre, self.delta, self.hp), rtol=0, atol=0)
        torch.testing.assert_close(independent.mlp[0].weight, joint.mlp[0].weight, rtol=0, atol=0)
        torch.testing.assert_close(independent.mlp[0].bias, joint.mlp[0].bias, rtol=0, atol=0)
        received = {}
        hooks = [model.mlp.register_forward_pre_hook(lambda module, inputs, name=name: received.__setitem__(name, inputs[0].detach().clone())) for name, model in [('independent',independent),('joint',joint)]]
        try:
            independent(*self.inputs()); joint(*self.inputs())
        finally:
            for hook in hooks: hook.remove()
        torch.testing.assert_close(received['independent'], features, rtol=0, atol=0)
        torch.testing.assert_close(received['joint'], features, rtol=0, atol=0)
        self.assertEqual(type(independent.mlp[1]), type(joint.mlp[1]))
    def test_other_slot_can_affect_independent_slot_logit(self):
        model = d.new_decoder('independent', 2)
        for parameter in model.parameters(): parameter.data.zero_()
        model.potion.weight.data[4,0] = 1
        # Inventory starts at feature 73; slot 1's potion feature starts at 85.
        model.mlp[0].weight.data[0,85] = 1
        model.mlp[-1].weight.data[0,0] = 1
        before = model.output_logits(self.z,self.pre,self.delta,self.hp)
        changed = self.pre.clone(); changed[:,1] = 4
        after = model.output_logits(self.z,changed,self.delta,self.hp)
        torch.testing.assert_close(after[:,0] - before[:,0], torch.ones(2))
    def test_unmasked_independent_probability_is_product_of_five_terms(self):
        model = d.new_decoder('independent', 2)
        logits = model.output_logits(self.z,self.pre,self.delta,self.hp)
        bernoulli = torch.sigmoid(logits)
        bits = torch.tensor(d.BITS)
        expected = torch.where(bits[None], bernoulli[:,None], 1-bernoulli[:,None]).prod(-1)
        actual = model.unmasked_log_probabilities(self.z,self.pre,self.delta,self.hp).exp()
        torch.testing.assert_close(actual,expected)
        torch.testing.assert_close(actual.sum(-1),torch.ones(2))
        legal = torch.tensor(d.legal_masks(self.pre.numpy(),self.capacity.numpy()))
        constrained = torch.where(legal, expected, 0)
        constrained /= constrained.sum(-1,keepdim=True)
        torch.testing.assert_close(model(*self.inputs()).exp(),constrained)
    def test_both_arms_use_exact_same_legal_support(self):
        expected = d.legal_masks(self.pre.numpy(),self.capacity.numpy())
        supports = []
        for kind in ('independent','joint'):
            model = d.new_decoder(kind,2)
            support = np.isfinite(model(*self.inputs()).detach().numpy())
            np.testing.assert_array_equal(support,expected)
            supports.append(support)
        np.testing.assert_array_equal(*supports)

    def test_encoder_parameters_get_no_decoder_gradients(self):
        encoder = torch.nn.Linear(3,64)
        encoder.requires_grad_(False)
        z = encoder(torch.ones((2,3)))
        model = d.new_decoder('joint', 2)
        (-model(z, *self.inputs()[1:])[0,3]).backward()
        self.assertTrue(all(x.grad is None for x in encoder.parameters()))
    def test_ancestral_uses_sampled_conditioning(self):
        # A real valid upstream draw and decoder roundtrip, distinct from teacher forcing.
        model = d.new_decoder('joint', 2).eval()
        pre = {'maxHp': 80, 'potions': [2,3,1,1,1], 'potionCapacity': 3}
        hp = np.zeros((2,101)); hp[:, 25] = 1
        post = d.sample_composed(pre, 1., {'pDelta': np.array([0.,1.]), 'hpConditional': hp}, model, np.zeros(64), {'maxHpDeltaValues':[0,4]}, np.random.default_rng(1))
        self.assertEqual(post['maxHp'], 84)
        self.assertEqual(post['curHp'], 21)
        self.assertTrue(np.array_equal(d.encode_masks(np.array([pre['potions']]), np.array([post['potions']]), [3]), [post['mask']]))

    def test_selection_refit_and_ancestral_pipeline_on_tiny_fixture(self):
        from unittest.mock import patch
        arrays = {'potions': np.zeros((6,5,2), dtype=np.int16),
                  'potionCapacity': np.full(6,3), 'delta_index': np.zeros(6,dtype=int),
                  'y_hp': np.full(6,.5,dtype=np.float32), 'preMaxHp': np.full(6,80)}
        arrays['potions'][:,:,1] = [2,3,1,1,1]
        z = np.zeros((6,64),dtype=np.float32)
        targets = np.array([0,3,0,3,0,3])
        spec = {'maxHpDeltaValues':[0]}
        recipe = {**d.RECIPE, 'maxEpochs':2, 'batch':2, 'ancestralDraws':2}
        with patch.dict(d.RECIPE, recipe):
            for kind in ('independent','joint'):
                _, selected, history = d.train_decoder(kind, arrays, spec, z, targets, np.array([0,1]), np.array([2,3]), 'cpu')
                self.assertIn(selected, [1,2]); self.assertTrue(history)
                model, _, _ = d.train_decoder(kind, arrays, spec, z, targets, np.array([0,1,2,3]), None, 'cpu', selected)
                hp = np.zeros((2,1,101)); hp[:,:,50] = 1
                result = d.ancestral(model, arrays, z, np.array([4,5]), {'pDelta':np.ones((2,1)), 'hpConditional':hp}, targets[[4,5]], spec)
                self.assertEqual(result['structurallyInvalid'],0)
                self.assertTrue(np.isfinite(result['mixtureJointNll']))
                self.assertAlmostEqual(sum(result['consumedCountFrequency']),1)
    def test_full_composed_latency_path(self):
        from unittest.mock import patch
        from pathlib import Path
        try:
            from tools.test_combat_transition_surrogate import predictor, state
        except ModuleNotFoundError:
            from test_combat_transition_surrogate import predictor, state
        pi = predictor(potion_id=2)
        pre = state(); pre['relics'] = pre['relics'][:1]
        row = {'sourceSeed':1,'fightIdx':0,'predictorInput':pi,'transition':{'pre':pre,'post':pre,'combatOutcome':1}}
        mean = np.zeros(len(b.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32)
        std = np.ones_like(mean)
        encoder = d.attention.AttentionPointControlNet(torch,mean,std)
        point = d.attention.AttentionPointControlNet(torch,mean,std)
        point.net.survival.weight.data.zero_(); point.net.survival.bias.data.fill_(30)
        spec = {'maxHpDeltaValues':[0], 'relicDeltaValues':[0,1,2], 'relicDeltaValuesById':{'26':[0,1,2]}}
        phase2 = d.attention.AttentionPhase2Net(torch,spec,mean,std)
        arrays = {'sourceSeed':np.array([1]), 'fightIdx':np.array([0])}
        with patch.object(b,'iter_rows',return_value=iter([row])):
            result = d.composed_latency({'joint':d.new_decoder('joint',1)},encoder,phase2,point,arrays,np.array([0]),spec,Path('/unused'))
        self.assertEqual(result['joint']['draws'],100)
        self.assertEqual(result['joint']['deathDraws'],0)
        self.assertGreater(result['joint']['meanMs'],0)

if __name__ == '__main__': unittest.main()
