#!/usr/bin/env python3
"""Reconstruct the Phase 12 malformed strategicmarggen CSV.

The affected producer wrote the 1,017-field ``richState`` value without CSV
quoting.  Legacy rows therefore contain 1,056 physical fields instead of the
intended 40.  This tool streams the legacy file and writes a normal CSV without
loading the dataset into memory.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter


EXPECTED_HEADER = [
    "seed", "decIdx", "act", "floor", "screen", "gateKind", "actionIdx",
    "nCand", "hiddenIdx", "regime", "continuationSeed", "hiddenSeed",
    "labelWon", "labelHp", "labelFloor", "labelBootstrap", "utility",
    "fallbackIdx", "fallbackExact", "chosenIdx", "chosenExact", "v4ModelIdx",
    "v4Margin", "v4Threshold", "v4Fired", "v4ExecutedIdx", "v4Override",
    "richState", "actionBits", "actionType", "c1", "c2", "c3", "cand1",
    "cand2", "cand3", "hiddenChanged", "sourceWon", "sourceFloor", "sourceHp",
]
LEGACY_WIDTH = 1056
RICH_STATE_START = 27
RICH_STATE_WIDTH = 1017
TRAILING_WIDTH = 12


def reconstruct(input_path: str, output_path: str) -> dict:
    physical_widths = Counter()
    regimes = Counter()
    hidden_changed = Counter()
    rows = 0
    digest = hashlib.sha256()

    with open(input_path, newline="") as source, open(output_path, "w", newline="") as target:
        reader = csv.reader(source)
        writer = csv.writer(target, lineterminator="\n")
        header = next(reader)
        if header != EXPECTED_HEADER:
            raise ValueError("unexpected input header")
        writer.writerow(EXPECTED_HEADER)
        for physical in reader:
            rows += 1
            physical_widths[len(physical)] += 1
            if len(physical) != LEGACY_WIDTH:
                raise ValueError(f"row {rows}: expected {LEGACY_WIDTH} fields, got {len(physical)}")
            rich_end = RICH_STATE_START + RICH_STATE_WIDTH
            rich_state = ",".join(physical[RICH_STATE_START:rich_end])
            if len(rich_state.split(",")) != RICH_STATE_WIDTH:
                raise ValueError(f"row {rows}: malformed richState width")
            row = physical[:RICH_STATE_START] + [rich_state] + physical[rich_end:]
            if len(row) != len(EXPECTED_HEADER):
                raise ValueError(f"row {rows}: reconstructed width is {len(row)}")
            writer.writerow(row)
            regimes[row[9]] += 1
            hidden_changed[(row[9], row[36])] += 1

    with open(output_path, "rb") as corrected:
        for chunk in iter(lambda: corrected.read(1024 * 1024), b""):
            digest.update(chunk)

    result = {
        "input": input_path,
        "output": output_path,
        "rows": rows,
        "physical_widths": dict(physical_widths),
        "regimes": dict(regimes),
        "hiddenChanged": {f"{regime}:{value}": count
                           for (regime, value), count in hidden_changed.items()},
        "output_sha256": digest.hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="malformed strategicmarggen CSV")
    parser.add_argument("output", help="corrected 40-column CSV")
    args = parser.parse_args()
    reconstruct(args.input, args.output)


if __name__ == "__main__":
    main()