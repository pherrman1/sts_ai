import json
import tempfile
import unittest
from pathlib import Path

from tools import collect_lizard_stage_c_shards as collector


class StageCShardIndexTests(unittest.TestCase):
    def test_progress_index_is_atomically_replaced_as_shards_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            teacher = root / "teacher.json"
            index = root / "index.json"
            plan.write_text("{}\n")
            teacher.write_text("{}\n")

            collector.write_index(index, "candidates", plan, teacher, {})
            collector.write_index(index, "candidates", plan, teacher, {
                4202000: {"seed": 4202000, "dataSha256": "first"},
            })
            collector.write_index(index, "candidates", plan, teacher, {
                4202000: {"seed": 4202000, "dataSha256": "first"},
                4202001: {"seed": 4202001, "dataSha256": "second"},
            })

            saved = json.loads(index.read_text())
            self.assertEqual(saved["completedSources"], 2)
            self.assertEqual([entry["seed"] for entry in saved["entries"]],
                             [4202000, 4202001])
            self.assertEqual(saved["workerCount"], 8)
            self.assertEqual(saved["ompThreadsPerProcess"], 1)
            self.assertEqual(list(root.glob("index.json.tmp.*")), [])

    def test_frozen_output_still_refuses_different_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frozen.json"
            collector.atomic_write(output, b"frozen\n")
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                collector.atomic_write(output, b"replacement\n")


if __name__ == "__main__":
    unittest.main()
