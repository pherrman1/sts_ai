#!/usr/bin/env python3
"""Reproduce recorded parity without running any game seeds."""
import csv, gzip, hashlib, io, json
from collections import Counter
from pathlib import Path
root = Path(__file__).resolve().parent
packet = json.loads((root / "parity.json").read_text())
def csv_rows(path, compressed=False):
    text = gzip.decompress(path.read_bytes()).decode() if compressed else path.read_text()
    reader = csv.DictReader(io.StringIO(text))
    return reader.fieldnames, list(reader)
h, a = csv_rows(root / "base-1k-16.csv")
h2, b = csv_rows(root / "pr-1k-16.csv")
assert h == h2
columns = [c for c in h if c != "sec"]
def result_rows(rows):
    assert len(rows) == 16 and {int(x["seed"]) for x in rows} == set(range(16))
    return Counter(tuple(x[c] for c in columns) for x in rows)
assert result_rows(a) == result_rows(b)
dh, da = csv_rows(root / "base-decisions.csv.gz", True)
dh2, db = csv_rows(root / "pr-decisions.csv.gz", True)
assert dh == dh2
canonical = Counter(tuple(x[c] for c in dh) for x in da)
assert canonical == Counter(tuple(x[c] for c in dh) for x in db)
assert len(da) == len(db) == packet["decision_records_per_arm"]
digest = hashlib.sha256(json.dumps(sorted(canonical.elements()), separators=(",", ":")).encode()).hexdigest()
assert digest == packet["canonical_diagnostics_sha256"]
telemetry = {}
metadata = {}
for arm, rows, sha in [("base", da, "876e9305a258df3d5a5eafd50e30375b933f8884"),
                       ("pr", db, "1e7ca07613885acfabaa0ed639a026cda904321c")]:
    assert all(int(x["configured_simulations"]) == int(x["simulations_added"]) == 1000 for x in rows)
    assert all(int(x["allocated_nodes_before_root"]) < 32768 for x in rows)
    assert all(x["fallback_reason"] not in ("allocated_cap", "active_cap") for x in rows)
    log = gzip.decompress((root / f"{arm}-1k-16.log.gz").read_bytes()).decode()
    telemetry[arm] = Counter(x for x in log.splitlines() if x.startswith("[silver-combat]"))
    meta = json.loads((root / f"{arm}-1k-16.csv.meta.json").read_text())
    assert meta["config"].pop("executableGitSha") == sha
    meta["config"].pop("silverScalingDiagnosticFile")
    assert (meta["sims"], meta["nSeeds"], meta["asc"], meta["threads"]) == (1000, 16, 0, 4)
    metadata[arm] = (meta["config"], meta["models"])
assert telemetry["base"] == telemetry["pr"]
assert sum(telemetry["base"].values()) == packet["per_combat_telemetry_records_per_arm"]
assert metadata["base"] == metadata["pr"]
assert (root / "canary-debug.log").read_bytes() == (root / "canary-release.log").read_bytes()
print("PASS: 16 non-timing rows, 7008 full decision records, 380 telemetry records and effective metadata match")
