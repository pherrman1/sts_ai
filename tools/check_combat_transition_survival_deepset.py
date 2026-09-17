#!/usr/bin/env python3
"""Stage-A non-TEST native parity and survival-only artifact binding."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

from tools import combat_transition_composed as composed
from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_rng_audit as audit
from tools import export_combat_transition_survival_deepset as exporter


def check(args):
    if exporter.digest(args.corpus) != audit.FROZEN_SHA:
        raise ValueError("corpus hash mismatch")
    if exporter.digest(args.split) != attention.EXPECTED_SPLIT_SHA256:
        raise ValueError("split hash mismatch")
    args.output.mkdir(exist_ok=False, parents=True)
    torch.set_num_threads(1)
    report = exporter.export(args.control, args.checkpoint, args.evidence,
                             args.output / "candidate.native")
    candidate = exporter.load_candidate(args.checkpoint, args.evidence)
    control_meta, control_tensors = exporter.read_artifact(args.control)
    candidate_meta, candidate_tensors = exporter.read_artifact(args.output / "candidate.native")
    for name in control_tensors:
        if not name.startswith("survival.") and control_tensors[name] != candidate_tensors[name]:
            raise ValueError("non-survival tensor differs: " + name)
    candidate_meta.pop("experimentalSurvival")
    candidate_meta["sources"]["survival"] = control_meta["sources"]["survival"]
    candidate_meta["tensors"] = control_meta["tensors"]
    if candidate_meta != control_meta:
        raise ValueError("non-survival metadata differs")
    members = json.loads(args.split.read_text())["members"]
    allowed = set(members["train"]) | set(members["validation"])
    forbidden = set(members["test"])
    if allowed & forbidden:
        raise ValueError("overlapping source membership")
    rows = []
    strata = set()
    with args.corpus.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["sourceSeed"] not in allowed or row["sourceSeed"] in forbidden:
                continue
            globals_row = row["predictorInput"]["globals"]
            stratum = (globals_row["act"], globals_row["roomClass"], globals_row["curHp"] < 20)
            if stratum in strata:
                continue
            strata.add(stratum)
            rows.append(dict(predictorInput=row["predictorInput"], pre=row["transition"]["pre"],
                sourceSeed=row["sourceSeed"], draws=0))
            if len(rows) == 12:
                break
    if len(rows) != 12:
        raise ValueError("representative fixture count differs")
    for row in list(rows):
        variant = copy.deepcopy(row)
        variant["pre"]["maxHp"] = variant["predictorInput"]["globals"]["maxHp"] = 173
        rows.append(variant)
    fixture = args.output / "fixtures.jsonl"
    fixture.write_text("".join(json.dumps(row) + "\n" for row in rows))
    outputs = []
    for name, artifact in (("control", args.control), ("candidate", args.output / "candidate.native")):
        command = [str(args.probe.resolve()), str(artifact.resolve()), str(fixture.resolve()), "near-full"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        (args.output / (name + ".jsonl")).write_text(result.stdout)
        outputs.append([json.loads(line) for line in result.stdout.splitlines()])
    errors = []
    supported = 0
    for row, control, native in zip(rows, *outputs, strict=True):
        if (control["supported"], control["reason"]) != (native["supported"], native["reason"]):
            raise ValueError("support mismatch")
        if not native["supported"]:
            if not control["unsupportedNoDraw"] or not native["unsupportedNoDraw"]:
                raise ValueError("fallback consumes RNG")
            continue
        supported += 1
        for name in ("maxHp", "hp", "diagnostics"):
            if control[name] != native[name]:
                raise ValueError("non-survival native output differs: " + name)
        inputs = composed.base._torch_inputs(composed.visible_arrays(row["predictorInput"]),
            np.asarray([0]), "cpu", torch, trim_padding=True)
        with torch.inference_mode():
            expected = float(torch.sigmoid(candidate(inputs)).item())
        errors.append(abs(expected - native["survival"]))
    if supported < 6 or max(errors) > 1e-4:
        raise ValueError("native parity failed or insufficient supported fixtures")
    report.update(fixtures=len(rows), supported=supported, unsupported=len(rows)-supported,
        testInferenceRows=0, maxAbsoluteError=max(errors), tolerance=1e-4,
        supportIdentical=True, nonSurvivalOutputsIdentical=True, unsupportedNoDraw=True,
        sourceSha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        sourceDirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
        hashes={str(path): exporter.digest(path) for path in
            (args.probe, args.split, fixture, args.output / "control.jsonl", args.output / "candidate.jsonl")})
    (args.output / "parity.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("control", "checkpoint", "evidence", "corpus", "split", "probe", "output"):
        parser.add_argument("--" + field, required=True, type=Path)
    print(json.dumps(check(parser.parse_args()), indent=2))
