import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from tools import ctm_lizard as lz
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_lizard as lz

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / 'selfplay/models/combat_transition_deepsets_lizard_t2.native'


def features(path, n=6000, seed=5):
    """Synthetic ctmlizardfeatures output: after the Tail fires, wins follow the reserve survival."""
    rng = np.random.default_rng(seed)
    with open(path, 'w') as out:
        out.write('source_seed,fight_idx,label,child,fairy,brew,supported,reason,p_ordinary,p_reserve\n')
        for i in range(n):
            brew, fairy = rng.random() < 0.3, rng.random() < 0.3
            p = rng.uniform(0.3, 0.99)
            reserve = min(1.0, p + rng.uniform(0, 0.3))
            if rng.random() < p:
                label = 0
            else:
                slope = 2 if brew else 4
                label = 1 if rng.random() < 1 / (1 + np.exp(-(slope * (reserve - 0.7)))) else 2
            out.write(f'{i},0,{label},{"standard" if brew else "fast"},{int(fairy)},{int(brew)},1,supported,{p},{reserve}\n')
        out.write('9999999,0,0,fast,0,0,0,mark_of_bloom_exact_path,,\n')


class TestCtmLizard(unittest.TestCase):
    def test_fit_learns_r_per_child(self):
        with tempfile.TemporaryDirectory() as d:
            features(f'{d}/f.csv')
            receipt = lz.fit([Path(f'{d}/f.csv')], Path(d) / 'fit')
            for child, slope in (('fast', 4), ('standard', 2)):
                model = receipt['rModels'][child]
                self.assertEqual(sorted(model), ['featureMean', 'featureScale', 'standardizedCoefficients'])
                fitted = model['standardizedCoefficients'][1] / model['featureScale'][0]
                self.assertGreater(fitted, slope / 3)
            train = receipt['evaluation']['TRAIN/plain']
            self.assertLess(train['rNll']['model'], train['rNll']['constant'])
            self.assertAlmostEqual(train['meanQ'], train['observedTailRate'], delta=0.05)
            with self.assertRaises(ValueError):
                lz.fit([Path(f'{d}/f.csv')], Path(d) / 'fit')

    def test_extend_writes_capabilities_and_keeps_tensors(self):
        version, header, body = lz.read_header(FAST)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            features(d / 'f.csv', n=3000)
            lz.fit([d / 'f.csv'], d / 'fit')
            with self.assertRaises(ValueError):
                lz.extend(FAST, d / 'fit' / 'fit.json', d / 'production.native', brew=True)
            candidate = d / 'candidate.native'
            encoded = json.dumps(dict(header, researchCandidate={'candidateId': 'x'})).encode()
            candidate.write_bytes(lz.MAGIC + struct.pack('<II', version, len(encoded)) + encoded + body)
            result = lz.extend(candidate, d / 'fit' / 'fit.json', d / 'out.native', fast_r=True, brew=True, fairy=True)
            out_version, out_header, out_body = lz.read_header(d / 'out.native')
            self.assertEqual((out_version, out_body), (version, body))
            receipt = json.loads((d / 'fit' / 'fit.json').read_text())
            self.assertEqual(out_header['capabilities'],
                             {'lizardBrew': {'rModel': receipt['rModels']['standard']}, 'lizardFairy': {}})
            self.assertEqual(out_header['activeLizardCorrection']['rModel'], receipt['rModels']['fast'])
            self.assertEqual(result['manifest']['capabilities']['fast'], out_header['capabilities'])
            self.assertEqual(result['manifest']['activeLizard']['rModelSha256'],
                             lz.model_sha256(receipt['rModels']['fast']))
            with self.assertRaises(ValueError):
                lz.extend(d / 'out.native', d / 'fit' / 'fit.json', d / 'twice.native', fairy=True)


if __name__ == '__main__':
    unittest.main()
