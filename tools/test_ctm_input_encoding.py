import importlib.util
import math
import unittest

import numpy as np

try:
    from tools import ctm_input_encoding as enc
    from tools import combat_transition_model_experiment as base
except ModuleNotFoundError:
    import ctm_input_encoding as enc
    import combat_transition_model_experiment as base

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def _raw(act, floor, keep=4.0):
    values = dict(ascension=20, act=act, floor=floor, curHp=50, maxHp=80, gold=99, potionCount=1,
                  potionCapacity=3, potionKeepValue=keep, isBurningElite=0)
    return np.asarray([values[f] for f in enc.RAW_CONTINUOUS_FIELDS], np.float32)


class TestCtmInputEncoding(unittest.TestCase):
    def test_raw_fields_match_prepared_arrays(self):
        self.assertEqual(enc.RAW_CONTINUOUS_FIELDS, base.CONTINUOUS_GLOBAL_FIELDS)
        self.assertEqual(enc.RAW_CATEGORICAL_FIELDS, base.CATEGORICAL_GLOBAL_FIELDS)

    def test_v1_is_identity_and_clipped_misc(self):
        raw = np.stack([_raw(1, 3), _raw(3, 40)]); cats = np.asarray([[0, 4, 4, 9], [0, 51, 3, 4]])
        g, c = enc.globals_features(raw, cats, enc.V1)
        self.assertIs(g, raw); self.assertIs(c, cats)
        np.testing.assert_array_equal(enc.misc_feature([-30, 15, 25, 35], enc.V1), [-1, .75, 1, 1])
        self.assertEqual(enc.runtime_metadata(enc.V1, base.GLOBAL_CATEGORY_COUNTS),
                         {"continuousFields": list(base.CONTINUOUS_GLOBAL_FIELDS), "globalCategoryCounts": [4, 64, 10, 10]})

    def test_v2_globals(self):
        raw = np.stack([_raw(1, 3), _raw(4, 54, keep=9.0), _raw(3, 54)])
        cats = np.asarray([[0, 4, 4, 9]] * 3)
        g, c = enc.globals_features(raw, cats, enc.V2)
        self.assertEqual(g.shape, (3, len(enc.V2_CONTINUOUS_FIELDS)))
        floor = enc.V2_CONTINUOUS_FIELDS.index("floor")
        np.testing.assert_array_equal(g[:, floor], [3, 54, 54])
        np.testing.assert_array_equal(c[:, -1], [0, 3, 2])
        # Act and potionKeepValue are gone from the scalars: rows 1 and 2 differ only in category.
        np.testing.assert_array_equal(g[1], g[2])
        with self.assertRaises(ValueError):
            enc.globals_features(np.stack([_raw(5, 60)]), cats[:1], enc.V2)
        self.assertEqual(enc.runtime_metadata(enc.V2, base.GLOBAL_CATEGORY_COUNTS)["globalCategoryCounts"],
                         [4, 64, 10, 10, 4])
        mean, std = enc.scalar_stats(raw, enc.V2)
        self.assertEqual(mean.shape, (8,)); self.assertAlmostEqual(float(mean[floor]), 37.0, places=5)

    def test_v2_misc_keeps_counting(self):
        values = enc.misc_feature([0, 15, 20, 25, 30, 100, -7, 20000], enc.V2)
        self.assertEqual(values[0], 0); self.assertAlmostEqual(values[5], 1.0)
        self.assertTrue(np.all(np.diff(values[:6]) > 0))
        self.assertAlmostEqual(values[6], -math.log(8) / math.log(101))
        self.assertAlmostEqual(values[7], math.log1p(10000) / math.log(101))

    def test_unknown_encoding(self):
        with self.assertRaises(ValueError):
            enc.continuous_fields("ctm_input_v3")

    @unittest.skipUnless(TORCH_AVAILABLE, "torch unavailable")
    def test_torch_matches_numpy(self):
        import torch
        raw = np.stack([_raw(1, 3), _raw(4, 54), _raw(2, 20)]); cats = np.asarray([[0, 4, 4, 9]] * 3)
        g, c = enc.globals_features(torch.from_numpy(raw), torch.from_numpy(cats), enc.V2)
        g_ref, c_ref = enc.globals_features(raw, cats, enc.V2)
        np.testing.assert_allclose(g.numpy(), g_ref); np.testing.assert_array_equal(c.numpy(), c_ref)
        misc = np.asarray([-40, -1, 0, 1, 15, 25, 35, 20000], np.float32)
        for encoding in enc.ENCODINGS:
            np.testing.assert_allclose(enc.misc_feature(torch.from_numpy(misc), encoding).numpy(),
                                       enc.misc_feature(misc, encoding), rtol=1e-6, atol=1e-7)

    @unittest.skipUnless(TORCH_AVAILABLE, "torch unavailable")
    def test_encoders_build_both_encodings(self):
        import torch
        from tools import combat_transition_attention_ablation as ablation
        from tools import combat_transition_surrogate as surrogate
        raw = np.stack([_raw(1, 3), _raw(4, 54)]); cats = np.asarray([[0, 4, 4, 9]] * 2)
        batch = (torch.from_numpy(raw), torch.from_numpy(cats),
                 torch.zeros((2, base.MAX_CARDS, 4), dtype=torch.int16),
                 torch.zeros((2, base.MAX_RELICS, 3), dtype=torch.int16),
                 torch.zeros((2, 5, 2), dtype=torch.int16),
                 torch.zeros((2, base.MAX_CARDS), dtype=torch.bool), torch.zeros((2, base.MAX_RELICS), dtype=torch.bool))
        for encoding in enc.ENCODINGS:
            mean, std = enc.scalar_stats(raw, encoding)
            for model in (base.DeepSetsModel(torch, base.MAX_CARDS, base.MAX_RELICS, mean, std, encoding=encoding),
                          base.AttentionModel(torch, base.MAX_CARDS, base.MAX_RELICS, mean, std, encoding=encoding)):
                win, _ = model.net.eval()(*batch); self.assertEqual(tuple(win.shape), (2,))
            for net in (surrogate.DeepSetsEncoder(torch.nn, torch, mean, std, encoding=encoding).net,
                        ablation.AttentionEncoder(torch, mean, std, encoding=encoding).net):
                self.assertEqual(tuple(net.eval()(*batch).shape), (2, 64))
            self.assertEqual(len(base.DeepSetsModel(torch, base.MAX_CARDS, base.MAX_RELICS, mean, std,
                                                    encoding=encoding).net.global_category),
                             4 if encoding == enc.V1 else 5)
        with self.assertRaises(ValueError):  # raw statistics with the v2 encoding
            base.DeepSetsModel(torch, base.MAX_CARDS, base.MAX_RELICS, raw.mean(0), raw.std(0), encoding=enc.V2)


if __name__ == "__main__":
    unittest.main()
