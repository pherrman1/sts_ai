#!/usr/bin/env python3
"""Read-only custody/join audit. Never runs, samples, hydrates or labels a world."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

E = Path(__file__).resolve().parent
ROOT = E.parents[3]
SOURCE = "3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0"
ARCHIVE = Path("/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/build/overnight_20261008/corrected_canary")
RECEIPT_SHA = "bd1b1d03bf538de6c9d8b195da25bec69fd58292ee1f46b3c2397230b4ad2837"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source(path):
    return subprocess.check_output(["git", "show", SOURCE + ":" + path], cwd=ROOT, text=True)

def audit(archive):
    receipt = archive / "Capture_0.receipt.json"
    assert digest(receipt) == RECEIPT_SHA
    r = json.loads(receipt.read_text())
    assert r["status"] == "completed" and r["exit_code"] == 0 and r["source_sha"] == SOURCE
    assert digest(r["manifest"]) == r["manifest_sha256"]
    assert digest(r["command"][2]) == r["binary_sha256"]
    checked = {}
    for name in ("public", "trace", "meta"):
        item = r["outputs"][name]
        path = Path(item["path"])
        assert digest(path) == item["sha256"] and path.stat().st_size == item["bytes"]
        checked[name] = item
    env = r["environment"]
    assert env["STS_FAIR"] == "1" and env["STS_SILVER_PUBLIC_TARGET"] == "610081002:33"
    assert env["STS_SILVER_PUBLIC_TRACE"] == checked["public"]["path"]
    assert env["STS_OOC_DECISION_TRACE"] == checked["trace"]["path"]
    meta = json.loads(Path(checked["meta"]["path"]).read_text())
    assert meta["asc"] == 0 and meta["config"]["fairPlay"]
    assert meta["config"]["executableGitSha"] == SOURCE
    # Pin the producer implementation, not merely a same-seed coincidence.
    driver = source("apps/one_combat/run_driver.cpp")
    assert "for (const auto &r : gc.relics.relics) relics.push_back(relicEnumNames[static_cast<int>(r.id)])" in driver
    assert "tracePre = oocTraceState(gc)" in driver and '{"pre", tracePre}' in driver
    backend = source("src/sim/search/NativeSilverBackend.cpp")
    assert 'gc.seed != g_publicTarget->first || bc.floorNum != g_publicTarget->second' in backend
    assert 'makeSilverBattleStateConversion(' in backend and 'makeSilverRunContext(gc), 0)' in backend
    trace = [json.loads(x) for x in Path(checked["trace"]["path"]).read_text().splitlines()]
    matches = [(i + 1, x) for i, x in enumerate(trace) if x.get("kind") == "battle"
               and x["seed"] == 610081002 and x["encounter"] == "CHAMP"
               and x["pre"]["act"] == 2 and x["pre"]["floor"] == 33]
    assert len(matches) == 1
    line, battle = matches[0]
    relics = battle["pre"]["relics"]
    assert relics == battle["post"]["relics"] and "PRISMATIC_SHARD" not in relics
    rows = [json.loads(x) for x in Path(checked["public"]["path"]).read_text().splitlines()]
    candidates = []
    for row in rows:
        assert row["seed"] == "610081002" and row["floor"] == 33 and row["act"] == 2
        assert row["encounter"] == "CHAMP" and row["capture_valid"]
        s = row["public_wire"]["state"]
        assert s["floorNum"] == 33 and s["act"] == 2 and s["ascension"] == 0
        assert s["player"]["characterClass"] == 0
        if (s["inputState"] == 1 and not s["intentsHidden"]
                and not s["fullDrawOrderObserved"] and not s["drawPile"]["fullOrderObserved"]):
            candidates.append(row["decision"])
    assert len(rows) == 72 and len(candidates) == 65
    return {"schema": "infinity_provenance_inventory_v1", "audit": "PASS",
            "receipt_sha256": RECEIPT_SHA, "source_sha": SOURCE,
            "binary_sha256": r["binary_sha256"], "manifest_sha256": r["manifest_sha256"],
            "checked_artifacts": checked, "seed": 610081002, "ascension": 0,
            "act": 2, "floor": 33, "encounter": "CHAMP", "trace_line_1based": line,
            "fight": battle["fight"], "full_run_relics": relics,
            "no_shard_provenance": "same_receipt_full_inventory_pre_and_post",
            "public_rows": len(rows), "basic_public_normal_candidates": len(candidates),
            "proposed_first16_decisions": candidates[:16],
            "oracle_eligibility_not_yet_executed": True, "worlds_annotated_by_this_audit": 0,
            "original_pilot_eligible_roots": 0, "original_pilot_annotated_worlds": 0}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    result = json.dumps(audit(args.archive), indent=2) + "\n"
    output = E / "provenance-inventory.json"
    if args.check:
        assert output.read_text() == result, "committed provenance inventory differs"
    else:
        output.write_text(result)
    print("PASS: custody and exact-run join; 72 public rows, 65 basic candidates; 0 worlds annotated")
