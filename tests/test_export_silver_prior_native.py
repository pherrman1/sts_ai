import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "export_silver_prior_native", ROOT / "tools/export_silver_prior_native.py"
)
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class NativePriorExportIdentityTest(unittest.TestCase):
    def test_rejects_non_frozen_checkpoint_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.pt"
            vocabulary = Path(directory) / "vocabulary.json"
            output = Path(directory) / "model.native"
            checkpoint.write_bytes(b"not the frozen checkpoint")
            vocabulary.write_text("{}")
            with mock.patch.object(EXPORTER.torch, "load") as load:
                with self.assertRaisesRegex(ValueError, "checkpoint SHA-256"):
                    EXPORTER.export(checkpoint, vocabulary, output)
                load.assert_not_called()
            self.assertFalse(output.exists())

    def test_rejects_non_frozen_vocabulary(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.pt"
            vocabulary = Path(directory) / "vocabulary.json"
            output = Path(directory) / "model.native"
            checkpoint.write_bytes(b"checkpoint")
            vocabulary.write_text(json.dumps({"canonical_to_compact": {}}))
            with mock.patch.object(EXPORTER, "sha", return_value=EXPORTER.EXPECTED_CHECKPOINT):
                with mock.patch.object(EXPORTER.torch, "load") as load:
                    with self.assertRaisesRegex(ValueError, "compact vocabulary"):
                        EXPORTER.export(checkpoint, vocabulary, output)
                    load.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
