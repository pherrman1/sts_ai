"""Seed-free stability-probe startup refusals; every invocation rejects before play."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    base = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    base.update({
        "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
        "STS_NATIVE_OOC": "1", "STS_OOC_MCTS": "1",
        "STS_OOC_STRATEGIC_TOK_NN": str(repo / "selfplay/models/ooc_strategic_tok_final.native"),
        "STS_OOC_MCTS_LEAF_VALUE": "native", "STS_OOC_MCTS_LEAF_COMBATS": "3",
        "STS_OOC_MCTS_SIMS": "4096", "STS_OOC_MCTS_PRIOR": "policy",
        "STS_OOC_MCTS_LEAF_POLICY": "v4",
    })
    mode = "oocleafstabilityprobe"
    prefix = ["bash", str(repo / "tools/seed_guard.sh"), str(binary), mode]
    valid_args = ["1", "87000000", "20"]
    # Synthetic distinct inputs suffice for parsing. They cannot match a real
    # snapshot; the output exclusions provide an additional pre-game stop.
    plan = {"schema": "ooc-leaf-stability-v1", "runSeed": 87000000, "ascension": 20,
            "leaves": [{"decisionIndex": decision, "ordinal": ordinal,
                        "expectedInput": {"syntheticFixture": index},
                        "repeatSeeds": list(range(1000 + index * 16, 1016 + index * 16))}
                       for index, (decision, ordinal) in enumerate(((0, 1025), (0, 2049), (1, 1), (1, 513)))]}
    cases = 0
    with tempfile.TemporaryDirectory(prefix="sts-leaf-stability-startup-") as directory:
        def reject(label, reason, *, args=None, change=None, raw=None, env_change=None,
                   capture=True, probe_error=True, omit_plan=False, extra=False):
            nonlocal cases
            folder = Path(directory) / label
            folder.mkdir()
            plan_path, output = folder / "plan.json", folder / "capture.jsonl"
            candidate = deepcopy(plan)
            if change:
                change(candidate)
            plan_path.write_text(json.dumps(candidate) if raw is None else raw)
            trace, profile, mcts = (folder / name for name in ("game.trace.jsonl", "game.profile.jsonl", "mcts.csv"))
            env = {**base, **(env_change or {}), "STS_OOC_DECISION_TRACE": str(trace),
                   "STS_RUN_PROFILE": str(profile), "STS_OOC_MCTS_TRACE": str(mcts)}
            # If an earlier gate regresses, these excluded output settings must
            # refuse the probe before a real game can start.
            if capture:
                env["STS_OOC_MCTS_LEAF_CAPTURE"] = str(output)
            command = prefix + (valid_args if args is None else args)
            if not omit_plan:
                command.append(str(plan_path))
            if extra:
                command.append("extra")
            result = subprocess.run(command, cwd=repo, env=env, text=True,
                                    capture_output=True, timeout=30)
            diagnostic = result.stdout + result.stderr
            assert result.returncode != 0 and reason in diagnostic, (label, result.returncode, diagnostic)
            if output.exists():
                rows = [json.loads(line) for line in output.read_text().splitlines()]
                assert rows[0]["type"] == "header", (label, rows)
                assert len(rows) == (2 if probe_error else 1), (label, rows)
                if probe_error:
                    failure = rows[1]
                    assert failure["type"] == "stability_probe" and failure["status"] == "INVALID", (label, failure)
                    assert reason in failure["reason"] and failure["gameplayResult"] is None, (label, failure)
                    assert failure["leaves"] == [] and failure["roots"] == [], (label, failure)
            else:
                assert not capture or reason.startswith("SEED_GUARD:"), label
            for path in (trace, profile, mcts, Path(str(mcts) + ".actions.jsonl"), Path(str(mcts) + ".support.jsonl")):
                assert not path.exists() or not path.read_bytes(), (label, "unexpected gameplay output", path)
            cases += 1

        for count in ("0", "2", "01", "invalid"):
            reject("count-" + count, "SEED_GUARD: oocleafstabilityprobe requires exactly one source seed",
                   args=[count, "87000000", "20"], probe_error=False)
        usage = "usage: one_combat oocleafstabilityprobe 1 SEED ASC PLAN.json"
        reject("missing-plan", usage, omit_plan=True, probe_error=False)
        reject("extra-argument", usage, extra=True, probe_error=False)
        for label, seed, asc in (("negative-seed", "-1", "20"), ("seed-suffix", "87000000x", "20"),
                                 ("negative-asc", "87000000", "-1"), ("asc-suffix", "87000000", "20x")):
            reject(label, "seed and ascension must be nonnegative integers",
                   args=["1", seed, asc], probe_error=False)
        reject("malformed-json", "parse_error", raw="{")
        reject("trailing-json", "parse_error", raw=json.dumps(plan) + " {}")
        reject("duplicate-json-key", "stability_plan_duplicate_key",
               raw=json.dumps(plan).replace('"runSeed": 87000000', '"runSeed": 87000000, "runSeed": 87000000'))
        reject("extra-plan-field", "stability_plan_schema", change=lambda p: p.update(extra=1))
        reject("wrong-run", "stability_plan_run_identity", change=lambda p: p.update(runSeed=87000001))
        reject("wrong-asc", "stability_plan_run_identity", args=["1", "87000000", "0"])
        reject("three-leaves", "stability_plan_requires_four_leaves", change=lambda p: p["leaves"].pop())
        reject("extra-leaf-field", "stability_plan_leaf_schema", change=lambda p: p["leaves"][0].update(extra=1))
        reject("wrong-schedule", "stability_plan_fixed_schedule", change=lambda p: p["leaves"][0].update(ordinal=1))
        reject("empty-input", "stability_plan_distinct_expected_inputs", change=lambda p: p["leaves"][0].update(expectedInput={}))
        reject("duplicate-input", "stability_plan_distinct_expected_inputs",
               change=lambda p: p["leaves"][1].update(expectedInput=p["leaves"][0]["expectedInput"]))
        reject("fifteen-seeds", "stability_plan_requires_sixteen_seeds", change=lambda p: p["leaves"][0]["repeatSeeds"].pop())
        reject("duplicate-seed", "stability_plan_duplicate_repeat_seed",
               change=lambda p: p["leaves"][1]["repeatSeeds"].__setitem__(0, p["leaves"][0]["repeatSeeds"][0]))
        for label, value in (("negative", -1), ("boolean", True), ("string", "1000"),
                             ("fractional", 1000.5), ("overflow", 2**64)):
            reject("seed-" + label, "stability_plan_requires_uint64",
                   change=lambda p, v=value: p["leaves"][0]["repeatSeeds"].__setitem__(0, v))
        reject("missing-capture", "replay_requires_finalized_capture_sink", capture=False)
        teacher_error = "replay_requires_a20_native_4096_rollout3_v4_teacher"
        reject("wrong-sims", teacher_error, env_change={"STS_OOC_MCTS_SIMS": "1024"})
        reject("wrong-horizon", teacher_error, env_change={"STS_OOC_MCTS_LEAF_COMBATS": "1"})
    print(f"PASS stability startup: {cases} argument/plan/teacher refusals, no gameplay output")


if __name__ == "__main__":
    main()
