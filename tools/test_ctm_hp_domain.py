import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

try:
    from tools import ctm_hp_domain as h
    from tools import combat_transition_relic_trajectory as trajectory
    from tools import combat_transition_stochastic_hp as stochastic_hp
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_hp_domain as h
    import combat_transition_relic_trajectory as trajectory
    import combat_transition_stochastic_hp as stochastic_hp

PRODUCTION = dict(min=-160, max=143, classes=304, envelope='all globally supported pre-combat states',
                  preCurHpRange=[1, 161], preMaxHpRange=[24, 172], maxHpDeltaValues=h.PRODUCTION_DELTA_VALUES,
                  rule='[min(1-preCurHp),max(preMaxHp-preCurHp)+max(deltaMaxHp)]')


class TestCtmHpDomain(unittest.TestCase):
    def test_hash_reproduces_the_production_domain(self):
        self.assertEqual(h.domain_sha256(PRODUCTION),
                         'f812c16ab1d220cd60e8a8915ebb368bcd7e6d9e48915eb8cce5c760fad78eec')

    def test_declared_domain(self):
        d = h.declared_domain(220, 220)
        self.assertEqual((d['min'], d['max'], d['classes']), (-219, 231, 451))
        self.assertEqual(d['sha256'], h.domain_sha256(d))
        self.assertEqual(d['preMaxHpRange'], [24, 220])
        with self.assertRaises(ValueError):
            h.declared_domain(221, 220)

    def test_expansion_keeps_old_classes_and_mutes_new_ones(self):
        old = np.arange(-4, 4)
        new = np.arange(-7, 9)
        net = stochastic_hp.new_model(torch, np.zeros(10, np.float32), np.ones(10, np.float32), 11, old, 1)
        relic = trajectory.new_decoder(torch, len(old), 1)
        hp_state = h.expand_hp_state(net.state_dict(), new)
        relic_state = h.expand_relic_state(relic.state_dict(), old, new)
        wide = stochastic_hp.new_model(torch, np.zeros(10, np.float32), np.ones(10, np.float32), 11, new, 2)
        wide.load_state_dict(hp_state, strict=True)
        wide_relic = trajectory.new_decoder(torch, len(new), 2)
        wide_relic.load_state_dict(relic_state, strict=True)
        offset = 3
        hidden = torch.randn(5, 64)
        with torch.no_grad():
            narrow = net.hp[2](hidden)
            widened = wide.hp[2](hidden)
        # Weights copy exactly; outputs of layers of different widths may differ by BLAS reduction order.
        self.assertTrue(torch.equal(wide.hp[2].weight[offset:offset + len(old)], net.hp[2].weight))
        torch.testing.assert_close(widened[:, offset:offset + len(old)], narrow, rtol=0, atol=1e-6)
        self.assertTrue(torch.all(widened[:, :offset] == h.NEW_CLASS_BIAS))
        # On the old support the probabilities move only by FP32 rounding plus the new e^-30 mass.
        p_old = torch.softmax(narrow, -1)
        p_new = torch.softmax(widened, -1)[:, offset:offset + len(old)]
        self.assertLess(float((p_old - p_new).abs().max()), 1e-6)
        delta = relic_state['delta.weight']
        self.assertTrue(torch.equal(delta[offset:offset + len(old)], relic.state_dict()['delta.weight']))
        self.assertTrue(torch.equal(delta[0], relic.state_dict()['delta.weight'][0]))
        self.assertTrue(torch.equal(delta[-1], relic.state_dict()['delta.weight'][-1]))
        with self.assertRaises(ValueError):
            h.expand_relic_state(relic.state_dict(), old, np.arange(-2, 9))

    def test_expand_cli_writes_pins_and_refuses_overwrite(self):
        old = np.arange(-160, 144)
        net = stochastic_hp.new_model(torch, np.zeros(10, np.float32), np.ones(10, np.float32), 11, old, 1)
        relic = trajectory.new_decoder(torch, len(old), 1)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            torch.save(dict(state_dict=net.state_dict(), metadata=dict(domain=dict(PRODUCTION, sha256='x'))), d / 'hp.pt')
            torch.save(dict(state_dict=relic.state_dict()), d / 'relic.pt')
            receipt = h.expand(d / 'hp.pt', d / 'relic.pt', h.declared_domain(220, 220), d / 'out')
            self.assertEqual(receipt['pins'], {'combat_transition_composed.HP_CLASS_RANGE': [-219, 231]})
            payload = torch.load(d / 'out' / 'hp.pt', weights_only=False)
            self.assertEqual(payload['metadata']['domain']['classes'], 451)
            self.assertEqual(payload['state_dict']['hp.2.weight'].shape[0], 451)
            with self.assertRaises(ValueError):
                h.expand(d / 'hp.pt', d / 'relic.pt', h.declared_domain(220, 220), d / 'out')


if __name__ == '__main__':
    unittest.main()
