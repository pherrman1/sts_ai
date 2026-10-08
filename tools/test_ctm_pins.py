import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from tools import ctm_pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins

TOOLS = Path(__file__).resolve().parent
# The pinned tools import siblings as `tools.<module>`; make that work under ctest too.
sys.path.insert(0, str(TOOLS.parent))
PINNED_MODULES = sorted({key.split(".", 1)[0] for key in ctm_pins.declared_keys(TOOLS)})


class TestCtmPins(unittest.TestCase):
    def setUp(self):
        ctm_pins._cache = None
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop(ctm_pins.ENV, None)

    def tearDown(self):
        self.env.stop()
        ctm_pins._cache = None

    def write(self, d, data):
        path = Path(d) / "pins.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        os.environ[ctm_pins.ENV] = str(path)
        return path

    def test_inactive_returns_production_defaults(self):
        self.assertFalse(ctm_pins.active())
        self.assertEqual(ctm_pins.value("m.X", 510030), 510030)
        self.assertEqual(ctm_pins.receipt(), {})

    def test_active_overrides_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, {"schema": ctm_pins.SCHEMA, "pins": {"m.X": 575925}})
            self.assertEqual(ctm_pins.value("m.X", 510030), 575925)
            with self.assertRaisesRegex(KeyError, "m.Y"):
                ctm_pins.value("m.Y", 1)
            self.assertEqual(ctm_pins.value("m.Y", 1, required=False), 1)
            self.assertEqual(ctm_pins.receipt(), {"ctmPinsSha256": ctm_pins.hashlib.sha256(path.read_bytes()).hexdigest()})

    def test_strip_removes_only_the_receipt_key(self):
        self.assertEqual(ctm_pins.strip({"a": 1, "ctmPinsSha256": "x"}), {"a": 1})
        self.assertEqual(ctm_pins.strip({"a": 1}), {"a": 1})
        self.assertEqual(ctm_pins.strip([1]), [1])

    def test_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, {"schema": "other", "pins": {}})
            with self.assertRaisesRegex(ValueError, "ctm_retrain_pins_v1"):
                ctm_pins.value("m.X", 1)

    def test_keys_are_unique_and_module_scoped(self):
        keys = ctm_pins.declared_keys(TOOLS)
        self.assertGreater(len(keys), 50)
        self.assertEqual(keys["combat_transition_deepset_downstream.CACHE_ROWS"], "510030")

    def test_pinned_tools_import_unchanged_without_pins(self):
        # Inertness: with STS_CTM_PINS unset every pinned module imports and
        # keeps its production constants.
        for name in PINNED_MODULES:
            with self.subTest(module=name):
                try:
                    importlib.import_module(f"tools.{name}")
                except ModuleNotFoundError as error:
                    if error.name in ("torch", "xgboost", "sklearn"):
                        self.skipTest(f"{error.name} is not installed")
                    raise
        lizard = importlib.import_module("tools.package_deepsets_lizard_artifact")
        self.assertEqual(lizard.FAST_SOURCE_SHA256[:8], ctm_pins.declared_keys(TOOLS)[
            "package_deepsets_lizard_artifact.FAST_SOURCE_SHA256"][1:9])

    def test_production_valued_pins_reproduce_every_constant(self):
        # A pins file holding the production values must leave every
        # upper-case module constant unchanged, so pinned and unpinned code
        # paths agree and no key is read with the wrong type.
        try:
            for name in PINNED_MODULES:
                importlib.import_module(f"tools.{name}")
        except ModuleNotFoundError as error:
            self.skipTest(f"{error.name} is not installed")
        pins = {}
        for key, source in ctm_pins.declared_keys(TOOLS).items():
            try:
                pins[key] = ast.literal_eval(source)
            except ValueError:  # computed default: take the unpinned module value
                module, attr = key.split(".", 1)
                pins[key] = json.loads(json.dumps(getattr(importlib.import_module(f"tools.{module}"), attr),
                                                  default=str))
        snapshot = (
            "import importlib, json, sys\n"
            "print(json.dumps({m: {k: repr(v) for k, v in vars(importlib.import_module('tools.' + m)).items()"
            " if k.isupper()} for m in sys.argv[1:]}))\n")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pins.json"
            path.write_text(json.dumps({"schema": ctm_pins.SCHEMA, "pins": pins}), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != ctm_pins.ENV}
            run = lambda e: json.loads(subprocess.check_output(
                [sys.executable, "-c", snapshot, *PINNED_MODULES], env=e, cwd=TOOLS.parent))
            self.assertEqual(run(env), run(dict(env, **{ctm_pins.ENV: str(path)})))


if __name__ == "__main__":
    unittest.main()
