import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from tools import ctm_escape, ctm_finetune as f
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_escape
    import ctm_finetune as f

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native'
BASE_SHA = 'ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b'
ROWS = ROOT / 'tests/fixtures/ctm_finetune_rows.jsonl'
TOOL = ROOT / 'tools/ctm_finetune.py'


def run(*args):
    return json.loads(subprocess.run([sys.executable, str(TOOL), *map(str, args)], check=True, cwd=ROOT,
                                     capture_output=True, text=True).stdout)


class TestCtmFinetune(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls.dir.name)
        cls.encoded = run('encode', cls.tmp / 'rows.npz', ROWS)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_encode_keeps_every_fight(self):
        data = np.load(self.tmp / 'rows.npz')
        self.assertEqual(self.encoded['rows'], 32)
        self.assertEqual(self.encoded['deaths'], 4)
        self.assertEqual(int((data['win'] == 0).sum()), 4)

    def test_python_survival_is_the_artifacts(self):
        """The trainable survival encoder starts from the artifact's own weights (no re-initialization)."""
        import torch
        _, tensors = ctm_escape.read_artifact(BASE)
        model = f.Model(torch, tensors)
        for name, value in model.tensors().items():
            np.testing.assert_array_equal(value, tensors[name])

    def test_hp_only_fine_tune_changes_only_the_hp_head(self):
        out = self.tmp / 'hp'
        result = run('train', '--base', BASE, '--base-sha', BASE_SHA, '--new', self.tmp / 'rows.npz', '--epochs', '2',
                     '--lr', '0', '--survival-head-only', '--hp-lr', '1e-2', '--batch', '8', '--threads', '1',
                     '--out', out)
        self.assertIn('hp', result['selectedEpoch'])
        art, manifest = self.tmp / 'hp.native', self.tmp / 'hp.json'
        exported = run('export', '--base', BASE, '--base-sha', BASE_SHA, '--checkpoint', out / 'finetune.pt',
                       '--out', art, '--manifest-out', manifest, '--keep-boss-shift')
        metadata, tensors = ctm_escape.read_artifact(art)
        _, base = ctm_escape.read_artifact(BASE)
        changed = {name for name in base if not np.array_equal(base[name], tensors[name])}
        # On 32 fixture rows the inner validation may keep epoch 0; whatever moved must be the HP head.
        self.assertLessEqual(changed, set(f.HP_HEAD))
        import torch
        saved = torch.load(out / 'finetune.pt', weights_only=False)['tensors']
        self.assertFalse([name for name in saved if name.startswith('survival.encoder.')])
        m = json.loads(manifest.read_text())
        self.assertEqual(m['candidateId'], 'pathb-a20')
        self.assertEqual(m['fast']['artifactSha256'], exported['artifactSha256'])
        self.assertEqual(m['fast']['maxHpHpCheckpointSha256'], exported['checkpointSha256'])
        self.assertEqual(metadata['sources']['HP'], exported['checkpointSha256'])
        self.assertEqual(metadata['experimentalSurvival']['checkpointSha256'], exported['checkpointSha256'])
        self.assertIn('bossSurvivalLogitShift', m)

    def test_export_drops_the_boss_shift_by_default_and_refuses_other_bases(self):
        out = self.tmp / 'surv'
        run('train', '--base', BASE, '--base-sha', BASE_SHA, '--new', self.tmp / 'rows.npz', '--epochs', '1',
            '--batch', '8', '--threads', '1', '--out', out)
        run('export', '--base', BASE, '--base-sha', BASE_SHA, '--checkpoint', out / 'finetune.pt',
            '--out', self.tmp / 's.native', '--manifest-out', self.tmp / 's.json')
        self.assertNotIn('bossSurvivalLogitShift', json.loads((self.tmp / 's.json').read_text()))
        with self.assertRaises(subprocess.CalledProcessError):
            run('export', '--base', BASE, '--base-sha', '0' * 64, '--checkpoint', out / 'finetune.pt',
                '--out', self.tmp / 'x.native', '--manifest-out', self.tmp / 'x.json')


if __name__ == '__main__':
    unittest.main()
