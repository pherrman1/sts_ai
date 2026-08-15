#!/usr/bin/env python3
"""Regression test for the diagnostic-to-trainer screen contract."""
import csv
import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "tools" / "convert_marg_to_trainer.py"


def load_converter():
    spec = importlib.util.spec_from_file_location("convert_marg_to_trainer", CONVERTER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def diagnostic_row(screen, gate_kind, action_idx, regime):
    rich = ["0"] * 1017
    return {
        "seed": "1",
        "decIdx": str(screen),
        "act": "1",
        "floor": "1",
        "screen": str(screen),
        "gateKind": str(gate_kind),
        "actionIdx": str(action_idx),
        "nCand": "2",
        "hiddenIdx": "0",
        "regime": regime,
        "labelWon": "0.0",
        "labelHp": "0.0",
        "labelFloor": "0.0",
        "labelBootstrap": "0.0",
        "actionBits": "0",
        "actionType": "-1",
        "c1": "0",
        "c2": "0",
        "c3": "0",
        "cand1": "-1",
        "cand2": "-1",
        "cand3": "-1",
        "richState": ",".join(rich),
        "sourceWon": "0",
        "sourceFloor": "0",
        "sourceHp": "0",
        "chosenIdx": "0",
    }


def main():
    converter = load_converter()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        diag = td / "diag.csv"
        m0 = td / "m0.csv"
        m1 = td / "m1.csv"
        rows = []
        cases = [(1, 1), (2, 2), (3, 3), (4, 4), (6, 5), (7, 6), (8, 7)]
        fields = list(diagnostic_row(1, 1, 0, "fixed"))
        for screen, gate_kind in cases:
            for action_idx in (0, 1):
                for regime in ("fixed", "marg"):
                    rows.append(diagnostic_row(screen, gate_kind, action_idx, regime))
        with diag.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        # The converter's CLI is intentionally simple; invoke its main with the
        # fixture paths so the test covers the actual output schema.
        import sys
        old_argv = sys.argv
        try:
            sys.argv = [str(CONVERTER), str(diag), str(m0), str(m1)]
            converter.main()
        finally:
            sys.argv = old_argv

        for output in (m0, m1):
            with output.open(newline="") as f:
                reader = csv.DictReader(f)
                assert len(reader.fieldnames or []) == 1036
                got = {(int(row["screen"]), int(row["actionType"])) for row in reader}
            assert {screen for screen, _ in got} == {1, 2, 3, 4, 6, 7, 8}
            assert 5 not in {screen for screen, _ in got}

    print("convert_marg_to_trainer screen contract self-test: PASS")


if __name__ == "__main__":
    main()