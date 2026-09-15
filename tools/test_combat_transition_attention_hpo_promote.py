import tempfile
import unittest
import json
from unittest import mock
from pathlib import Path

import numpy as np
import torch

try:
    import tools.combat_transition_attention_hpo_promote as promote_module
    from tools.combat_transition_attention_hpo_promote import (
        create_shadow_parent, refit_ids, rebind_downstream, split_hpo_state,
        validate_base_parent,
    )
except ModuleNotFoundError:
    import combat_transition_attention_hpo_promote as promote_module
    from combat_transition_attention_hpo_promote import (
        create_shadow_parent, refit_ids, rebind_downstream, split_hpo_state,
        validate_base_parent,
    )


class AttentionHpoPromoteTest(unittest.TestCase):
    def test_state_split_maps_win_and_drops_point_hp(self):
        state = {"encoder.weight": torch.ones(2, 2),
                 "win.weight": torch.ones(1, 2), "win.bias": torch.zeros(1),
                 "hp.weight": torch.ones(1, 2), "hp.bias": torch.zeros(1)}
        encoder, survival = split_hpo_state(
            state, np.asarray([2.0]), np.asarray([4.0])
        )
        self.assertIn("encoder.weight", encoder)
        self.assertNotIn("hp.weight", encoder)
        self.assertEqual(set(survival), {"weight", "bias"})
        self.assertEqual(float(encoder["scalar_inv"][0]), 0.25)

    def test_refit_ids_preserve_train_then_validation_order(self):
        split = np.asarray([1, 0, 2, 1, 0, 2])
        np.testing.assert_array_equal(refit_ids(split), [1, 4, 0, 3])

    def test_shadow_parent_replaces_only_survival(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"; base.mkdir()
            (base / "full-union-survival-v1").mkdir()
            (base / "full-union-downstream-v1").mkdir()
            (base / "other").mkdir()
            output = root / "output"
            create_shadow_parent(base, output)
            self.assertFalse((output / "full-union-survival-v1").exists())
            self.assertFalse((output / "full-union-downstream-v1").exists())
            self.assertTrue((output / "other").is_symlink())
            with self.assertRaises(FileExistsError):
                create_shadow_parent(base, output)
            nested = base / "nested"
            with self.assertRaises(ValueError):
                create_shadow_parent(base, nested)

    def test_base_parent_is_bound_to_component_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = {}
            preparation = {"upstreamBindings": {}}
            for component in ("survival", "maxHP", "HP", "potion", "downstream"):
                folder = root / f"full-union-{component}-v1"; folder.mkdir()
                artifact = folder / ("downstream.pt" if component == "downstream" else "component.pt")
                artifact.write_bytes(component.encode())
                digest = promote_module.sha256(artifact); hashes[component] = digest
                if component != "downstream":
                    preparation["upstreamBindings"][component] = digest
            (root / "full-union-downstream-v1" / "preparation.json").write_text(json.dumps(preparation))
            (root / "full-union-downstream-v1" / "fit.json").write_text(json.dumps({
                "artifactSha256": hashes["downstream"], "preparation": preparation}))
            for component in ("survival", "maxHP", "HP", "potion"):
                (root / f"full-union-{component}-v1" / "fit.json").write_text(json.dumps({
                    "artifactSha256": hashes[component]}))
            with mock.patch.dict(promote_module.EXPECTED_BASE_COMPONENTS, hashes, clear=True):
                validate_base_parent(root)
                (root / "full-union-HP-v1" / "component.pt").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "HP checkpoint differs"):
                    validate_base_parent(root)

    def test_downstream_rebind_preserves_artifact_and_other_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "base" / "full-union-downstream-v1"
            source.mkdir(parents=True)
            (source / "downstream.pt").write_bytes(b"frozen")
            preparation = {"upstreamBindings": {
                "survival": "old", "maxHP": "max", "HP": "hp", "potion": "potion"}}
            fit = {"artifactSha256": "artifact", "preparation": preparation}
            output = root / "output"; output.mkdir()
            rebind_downstream(root / "base", output,
                              {"downstreamPreparation": preparation,
                               "downstreamFit": fit}, "new", "commit")
            target = output / "full-union-downstream-v1"
            rebound = json.loads((target / "fit.json").read_text())
            self.assertTrue((target / "downstream.pt").is_symlink())
            self.assertEqual(rebound["artifactSha256"], "artifact")
            self.assertEqual(rebound["preparation"]["upstreamBindings"], {
                "survival": "new", "maxHP": "max", "HP": "hp", "potion": "potion"})
            self.assertTrue(rebound["survivalBindingRebound"]["downstreamArtifactUnchanged"])


if __name__ == "__main__":
    unittest.main()
