#!/usr/bin/env python3
"""Fail-closed integrity and distribution audit for the clean issue-19 pilot."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

try:
    from tools.verify.vnettest_selftest import canonical_names
except ModuleNotFoundError:
    from verify.vnettest_selftest import canonical_names


PREFIX = [
    "sourceSeed", "decisionIdx", "act", "floor", "screen", "actionIdx",
    "actionBits", "actionSemantic", "legalSiblingCount", "legalSiblingBits",
    "chosen", "futureIdx", "H", "continuationSeed", "hiddenSeed",
    "teacherId", "survivedPrefix", "conditionalAliveValue", "qProduct",
    "denseReferenceValue", "floorBootstrapValue", "silverSimulations",
    "combatDecisions", "transactionSubdecisions", "cpuMs", "wallMs", "valid", "quarantineReason",
    "reachedCombat", "terminalOutcomeBeforeCombat",
    "battleAct", "battleFloor", "battleEncounter", "roomClass",
]
SUFFIX = [
    "won", "endHp", "startHp", "startMaxHp", "endMaxHp", "endHpFrac",
    "startPotionIds", "endPotionIds", "startPotionCount", "endPotionCount",
    "goldDelta", "smokeBombUsed", "changedRelicCounters", "ritualDaggerChanges",
    "deckStructureChanged", "parasiteAdded", "persistentMutationSummary",
]


def audit(path: Path, manifest_path: Path) -> dict:
    from tools.ooc_pipeline_contract import sha256, validate_teacher
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "ooc_clean_pilot_manifest_v1":
        raise ValueError("pilot manifest schema mismatch")
    teacher = manifest.get("combatTeacher", {})
    validate_teacher(teacher)
    if manifest.get("producerGitSha") != teacher.get("git_sha") or manifest.get("producerExecutableSha256") != teacher.get("executable_sha256"):
        raise ValueError("producer and teacher provenance disagree")
    if manifest.get("H") != 1 or manifest.get("futureIdentities") != [0] or manifest.get("schedule") != [10000]:
        raise ValueError("pilot manifest does not bind K1 exact-10k H1")
    if manifest.get("csv", {}).get("sha256") != sha256(path):
        raise ValueError("pilot CSV hash mismatch")
    seed_start = int(manifest["seedSpec"]["start"]); seed_count = int(manifest["seedSpec"]["count"])
    teacher_id = teacher["teacher_id"]
    frame = pd.read_csv(path)
    expected_header = PREFIX + canonical_names() + SUFFIX
    if frame.columns.tolist() != expected_header:
        raise ValueError("pilot schema or canonical feature order mismatch")
    expected_seeds = set(range(seed_start, seed_start + seed_count))
    if not set(map(int, frame.sourceSeed.unique())).issubset(expected_seeds):
        raise ValueError("pilot contains a source seed outside the frozen block")
    integrity = manifest.get("integrity", {})
    if integrity.get("requested") != seed_count or integrity.get("completed") != seed_count or integrity.get("quarantined") != 0 or integrity.get("failures") != 0 or integrity.get("rows") != len(frame):
        raise ValueError("pilot manifest integrity accounting mismatch")
    per_source = manifest.get("perSource")
    if not isinstance(per_source, list) or len(per_source) != seed_count:
        raise ValueError("pilot manifest per-source accounting is incomplete")
    declared = {int(row["sourceSeed"]): int(row["rows"]) for row in per_source}
    declared_decisions = {int(row["sourceSeed"]): int(row["decisions"]) for row in per_source}
    if set(declared) != expected_seeds or any(value < 0 for value in declared.values()):
        raise ValueError("pilot manifest per-source seed/count mismatch")
    actual = frame.sourceSeed.value_counts().to_dict()
    if any(declared[seed] != int(actual.get(seed, 0)) for seed in expected_seeds):
        raise ValueError("pilot CSV disagrees with per-source row accounting")
    actual_decisions = frame.groupby("sourceSeed").decisionIdx.nunique().to_dict()
    if any(declared_decisions[seed] != int(actual_decisions.get(seed, 0)) for seed in expected_seeds):
        raise ValueError("pilot CSV disagrees with per-source decision accounting")
    key = ["sourceSeed", "decisionIdx", "actionIdx", "futureIdx"]
    if frame.duplicated(key).any():
        raise ValueError("duplicate pilot branch key")
    if set(frame.teacherId) != {teacher_id}:
        raise ValueError("teacher identity mismatch")
    if set(map(int, frame.H.unique())) != {1} or set(map(int, frame.futureIdx.unique())) != {0}:
        raise ValueError("pilot is not the frozen H1/future-0 cohort")
    if (frame.valid != 1).any() or frame.quarantineReason.fillna("").astype(str).str.len().ne(0).any():
        raise ValueError("invalid or quarantined row in completed pilot")
    if not frame.reachedCombat.isin([0, 1]).all():
        raise ValueError("non-binary reached-combat marker")
    terminal = frame.reachedCombat == 0
    combat = frame.loc[~terminal]
    if not frame.loc[terminal, "terminalOutcomeBeforeCombat"].isin([0, 2]).all() or (combat.terminalOutcomeBeforeCombat != -1).any():
        raise ValueError("terminal-before-combat outcome marker mismatch")
    groups = frame.groupby(["sourceSeed", "decisionIdx"], sort=False)
    for decision, group in groups:
        actions = sorted(map(int, group.actionIdx))
        if len(actions) < 2 or actions != list(range(len(actions))):
            raise ValueError(f"incomplete sibling coverage at {decision}")
        if group.actionBits.duplicated().any():
            raise ValueError(f"duplicate sibling action identity at {decision}")
        if set(map(int, group.legalSiblingCount)) != {len(actions)}:
            raise ValueError(f"legal sibling count mismatch at {decision}")
        declared = ";".join(str(value) for value in group.sort_values("actionIdx").actionBits)
        if set(group.legalSiblingBits.astype(str)) != {declared}:
            raise ValueError(f"legal sibling identity set mismatch at {decision}")
        if group.actionSemantic.fillna("").astype(str).str.len().eq(0).any():
            raise ValueError(f"missing semantic action identity at {decision}")
        if int(group.chosen.sum()) != 1:
            raise ValueError(f"decision does not have exactly one source-policy action at {decision}")
    numeric = [
        "conditionalAliveValue", "qProduct", "denseReferenceValue", "floorBootstrapValue",
        "silverSimulations", "combatDecisions", "transactionSubdecisions", "cpuMs", "wallMs",
    ]
    combat_numeric = canonical_names() + ["won", "endHp",
        "startHp", "startMaxHp", "endMaxHp", "endHpFrac",
    ]
    values = frame[numeric].to_numpy(float)
    if not all(math.isfinite(value) for value in values.ravel()):
        raise ValueError("non-finite label or cost")
    combat_values = combat[combat_numeric].to_numpy(float)
    if not all(math.isfinite(value) for value in combat_values.ravel()):
        raise ValueError("non-finite combat feature or target")
    if not frame.survivedPrefix.isin([0, 1]).all() or not combat.won.isin([0, 1]).all():
        raise ValueError("non-binary survival target")
    if not (combat.survivedPrefix == combat.won).all():
        raise ValueError("OOC survival and combat target disagree")
    expected_terminal_survival = (frame.loc[terminal, "terminalOutcomeBeforeCombat"] == 2).astype(int)
    if not (frame.loc[terminal, "survivedPrefix"].astype(int) == expected_terminal_survival).all():
        raise ValueError("terminal OOC survival target disagrees with run outcome")
    if not (frame.loc[terminal, "conditionalAliveValue"] == expected_terminal_survival).all() or not (frame.loc[terminal, "qProduct"] == expected_terminal_survival).all():
        raise ValueError("terminal OOC value is not the exact absorbed run outcome")
    if (frame.loc[terminal, ["silverSimulations", "combatDecisions", "transactionSubdecisions"]] != 0).any().any():
        raise ValueError("terminal-before-combat row claims combat search cost")
    unavailable = canonical_names() + SUFFIX[:-1]
    if not frame.loc[terminal, unavailable].isna().all().all():
        raise ValueError("terminal-before-combat row claims a combat surrogate target")
    if (frame.loc[terminal, "battleEncounter"] != -1).any() or (frame.loc[terminal, "roomClass"] != "OTHER").any() or (frame.loc[terminal, "persistentMutationSummary"] != "no_combat_terminal").any():
        raise ValueError("terminal-before-combat sentinel mismatch")
    expected_q = frame.survivedPrefix * frame.conditionalAliveValue
    if (frame.qProduct - expected_q).abs().max() > 1e-9:
        raise ValueError("qProduct does not equal survival times conditional value")
    if ((frame.silverSimulations % 10000) != 0).any():
        raise ValueError("Silver simulation accounting is not in exact-10k root increments")
    accounting = frame[["silverSimulations", "combatDecisions", "transactionSubdecisions"]]
    if (accounting < 0).any().any() or ((accounting % 1) != 0).any().any():
        raise ValueError("Silver simulation and decision counts must be nonnegative integers")
    if (frame.silverSimulations != (frame.combatDecisions + frame.transactionSubdecisions) * 10000).any():
        raise ValueError("Silver simulations disagree with ordinary plus transaction decision count")
    return {
        "rows": int(len(frame)),
        "oocRows": int(len(frame)),
        "combatSurrogateRows": int(len(combat)),
        "terminalBeforeCombatRows": int(terminal.sum()),
        "sourceSeeds": seed_count,
        "decisions": int(groups.ngroups),
        "quarantines": 0,
        "failures": 0,
        "teacherId": teacher_id,
        "producerGitSha": manifest["producerGitSha"],
        "producerExecutableSha256": manifest["producerExecutableSha256"],
        "actComposition": {str(k): int(v) for k, v in frame.act.value_counts().sort_index().items()},
        "screenComposition": {str(k): int(v) for k, v in frame.screen.value_counts().sort_index().items()},
        "roomComposition": {str(k): int(v) for k, v in combat.roomClass.value_counts().sort_index().items()},
        "survival": {"won": int(frame.survivedPrefix.sum()), "lost": int((1-frame.survivedPrefix).sum()), "mean": float(frame.survivedPrefix.mean())},
        "conditionalAliveValue": frame.conditionalAliveValue.describe().to_dict(),
        "qProduct": frame.qProduct.describe().to_dict(),
        "postCombatHpFraction": combat.endHpFrac.describe().to_dict(),
        "floorBootstrapValue": frame.floorBootstrapValue.describe().to_dict(),
        "cost": {
            "silverSimulations": int(frame.silverSimulations.sum()),
            "combatDecisions": int(frame.combatDecisions.sum()),
            "transactionSubdecisions": int(frame.transactionSubdecisions.sum()),
            "cpuSeconds": float(frame.cpuMs.sum()/1000),
            "wallSecondsSum": float(frame.wallMs.sum()/1000),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.csv, args.manifest)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
