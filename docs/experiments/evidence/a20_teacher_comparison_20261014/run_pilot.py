#!/usr/bin/env python3
"""Prepare and execute only the fixed follow-up pilot in PROTOCOL-V2.md; never retry a phase.

prepare OUT_DIR --prior FILE --prior-generation 5 --prior-sha256 SHA --prior-source URI --ctm-dir DIR
canary OUT_DIR
cohort OUT_DIR

Preparation requires a clean, reviewed commit and the exact existing models.
It builds Release, exports the seed-free policy specification, and freezes the
binary, models and tooling. Execution uses that freeze and unique phase latches.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

REPO = Path(__file__).resolve().parents[4]
PACKET = Path(__file__).resolve().parent
CTM_HASHES = {
    "fast.native": "ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b",
    "standard.native": "e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d",
    "manifest.json": "704f2a58c70d731c10ea8f4b00dc977f6d57ee0872480bf53e461e88583404d0",
}
CANARY = 97150801
COHORT = list(range(97150810, 97150814))
CPU_LIMIT, WALL_LIMIT = 600, 900


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open("x") as out:
        json.dump(value, out, indent=2, allow_nan=False)
        out.write("\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def checked_copy(source, dest, expected):
    require(sha(source) == expected, f"artifact hash mismatch: {source}")
    require(not dest.exists(), f"existing destination: {dest}")
    shutil.copy2(source, dest)
    require(sha(dest) == expected, f"copy hash mismatch: {dest}")


def prepare(out, prior, ctm_dir, generation, prior_hash, prior_source):
    # All missing/corrupt artifact checks precede any build or output creation.
    require(generation in (5, 6), "requires completed generation 5 or 6")
    require(re.fullmatch(r"[0-9a-f]{64}", prior_hash) and prior_source,
            "requires published/exported prior SHA256 and source location")
    require(sha(prior) == prior_hash, "wrong frozen prior")
    for name, digest in CTM_HASHES.items():
        require(sha(ctm_dir / name) == digest, f"wrong PR524 CTM: {name}")
    require(not git("status", "--porcelain"), "commit/review all scoped work before freezing")
    revision = git("rev-parse", "HEAD")
    out.mkdir(parents=True, exist_ok=False)
    models = out / "models"
    models.mkdir()
    prior_name = f"combat_policy_mlp_gen{generation}.txt"
    checked_copy(prior, models / prior_name, prior_hash)
    for name, digest in CTM_HASHES.items():
        checked_copy(ctm_dir / name, models / name, digest)
    build_commands = [["cmake", "--preset", "linux-gcc-release-ccache"],
                      ["cmake", "--build", "--preset", "linux-gcc-release-ccache-build",
                       "--target", "one_combat", "-j", "2"]]
    with (out / "build.log").open("x") as log:
        for cmd in build_commands:
            subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
    require(git("rev-parse", "HEAD") == revision and not git("status", "--porcelain"),
            "source changed during build")
    source_binary = REPO / "build/linux-gcc-release-ccache/one_combat"
    binary = out / "one_combat"
    checked_copy(source_binary, binary, sha(source_binary))
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": os.environ["HOME"],
        "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
        "STS_EXECUTABLE_GIT_SHA": revision, "STS_FAIR": "1", "STS_SEARCHER3": "0",
        "STS_SILVER_SEARCH": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
        "STS_SILVER_REUSE_CAP_MODE": "allocated", "STS_SILVER_ADAPTIVE": "0",
        "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_LOOP_GUARD": "0",
        "STS_SILVER_VNET_LEAF_DIRECT": "0", "STS_SILVER_ROOT_PRIOR_WEIGHT": "400",
        "STS_SILVER_ROOT_PRIOR_SCOPE": "override",
        "STS_SILVER_ROOT_PRIOR": str(models / prior_name),
        "STS_CTMSILVER_MLP_PRIOR": str(models / prior_name),
        "STS_CTMSILVER_ARMSET": "teacher_a20",
        "STS_CTMSILVER_CANDIDATE_FAST": str(models / "fast.native"),
        "STS_CTMSILVER_CANDIDATE_STANDARD": str(models / "standard.native"),
        "STS_CTM_RESEARCH_CANDIDATE_MANIFEST": str(models / "manifest.json"),
        "STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256": CTM_HASHES["manifest.json"],
        "STS_OOC_MCTS": "0", "STS_COLLECT_KEYS": "0", "STS_STOP_AFTER_ACT": "3",
        "STS_OOC_STRATEGIC_TOK_NN": "selfplay/models/ooc_strategic_tok_final.native",
        "STS_OOC_STRATEGIC_REST": "1", "STS_OOC_STRATEGIC_EVENT": "1",
        "STS_OOC_STRATEGIC_SHOP": "1", "STS_OOC_STRATEGIC_TREASURE": "1",
        "STS_OOC_STRATEGIC_BOSS_RELIC": "1", "STS_OOC_STRATEGIC_MARGIN": "1.0",
        "STS_REST_WIN": "0",
    }
    with (out / "policy.log").open("x") as log:
        subprocess.run([str(binary), "vwinrefreshpolicyspec", str(out / "policy.json")],
                       cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    template = REPO / "docs/experiments/evidence/ctm_vs_lowsim_silver_2026-10-09/teacher.json"
    teacher = json.loads(template.read_text())
    teacher.update(teacher_id=f"a20-teacher-pilot-plain10k-{revision[:12]}",
                   git_sha=revision, executable_sha256=sha(binary), environment=env,
                   ooc_policy=json.loads((out / "policy.json").read_text()))
    write_new(out / "teacher.json", teacher)
    artifacts = [binary, out / "teacher.json", out / "policy.json", out / "build.log",
                 *models.iterdir(), PACKET / "PROTOCOL-V2.md", PACKET / "PROTOCOL.md", PACKET / "ANALYSIS-CONTRACT.md",
                 Path(__file__).resolve(), REPO / "tools/analyze_a20_teachers.py",
                 REPO / "tools/seed_guard.sh", template]
    artifacts.extend(REPO / x["path"] for x in teacher["model_artifacts"])
    artifacts.extend(REPO / x["path"] for x in teacher["ooc_policy"]["model_artifacts"])
    freeze = {
        "schemaVersion": "a20_teacher_comparison_freeze_v2", "producerGitSha": revision,
        "repository": str(REPO), "binary": str(binary), "binarySha256": sha(binary),
        "teacher": str(out / "teacher.json"), "environment": env,
        "canarySeed": CANARY, "cohortSeeds": COHORT,
        "outputs": {str(seed): str(out / ("canary" if seed == CANARY else f"s{seed}"))
                    for seed in [CANARY, *COHORT]},
        "resourceLimits": {"cpuSecondsPerSource": CPU_LIMIT, "wallSecondsPerSource": WALL_LIMIT,
                           "maxConcurrentSources": 2, "maxAttemptedSources": 5},
        "priorIdentity": {"sha256": prior_hash, "generation": generation, "source": prior_source,
                          "treeMinVisits": 8, "weight": 400, "rootBonus": True},
        "ctmIdentity": CTM_HASHES,
        "arms": [{"name": name, "budget": budget, "prior": prior_on, "replicates": 4}
                 for name, budget, prior_on in [("plain2k", 2000, False), ("prior2k", 2000, True),
                                               ("plain10k", 10000, False), ("prior10k", 10000, True)]],
        "buildCommands": build_commands, "artifactFiles": {str(p): sha(p) for p in artifacts},
    }
    write_new(out / "freeze.json", freeze)


def verify(out):
    freeze = json.loads((out / "freeze.json").read_text())
    require(freeze["schemaVersion"] == "a20_teacher_comparison_freeze_v2", "unknown freeze schema")
    require(freeze["canarySeed"] == CANARY and freeze["cohortSeeds"] == COHORT, "wrong seeds")
    require(freeze["resourceLimits"] == {"cpuSecondsPerSource": CPU_LIMIT, "wallSecondsPerSource": WALL_LIMIT,
                                        "maxConcurrentSources": 2, "maxAttemptedSources": 5}, "wrong resource limits")
    require(freeze["repository"] == str(REPO), "wrong repository")
    for path, digest in freeze["artifactFiles"].items():
        require(sha(path) == digest, f"frozen artifact changed: {path}")
    return freeze


def run_source(out, seed):
    freeze = verify(out)
    prefix = out / ("canary" if seed == CANARY else f"s{seed}")
    require(not list(out.glob(prefix.name + ".*")), f"existing source outputs: {prefix}")
    argv = ["bash", str(REPO / "tools/seed_guard.sh"), freeze["binary"],
            "ctmsilvergen", "1", "20", str(prefix), str(seed), freeze["teacher"], "4"]
    write_new(str(prefix) + ".started.json", {"argv": argv, "freezeSha256": sha(out / "freeze.json")})
    # prlimit avoids preexec_fn in the threaded launcher. GNU time measures each
    # command separately, including on a CPU-limit failure; no pooled rusage.
    command = ["/usr/bin/time", "-f", "%U %S", "-o", str(prefix) + ".time",
               "prlimit", f"--cpu={CPU_LIMIT}:{CPU_LIMIT}", "--", *argv]
    start = time.monotonic()
    with open(str(prefix) + ".log", "x") as log:
        process = subprocess.Popen(command, cwd=REPO, env=freeze["environment"],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=WALL_LIMIT)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    cpu = None
    try:
        fields = Path(str(prefix) + ".time").read_text().splitlines()[-1].split()
        cpu = sum(map(float, fields)) if len(fields) == 2 else None
    except (OSError, ValueError, IndexError):
        pass
    receipt = {"returncode": code, "cpuSeconds": cpu, "wallSeconds": time.monotonic() - start,
               "timedOut": timed_out, "argv": argv, "seed": seed,
               "binarySha256": freeze["binarySha256"], "freezeSha256": sha(out / "freeze.json")}
    write_new(str(prefix) + ".receipt.json", receipt)
    print(json.dumps(receipt), flush=True)
    return prefix


def execute(out, phase):
    verify(out)
    if phase == "cohort":
        canary = json.loads((out / "canary-report.json").read_text())
        require(canary["verdict"] == "CANARY_VALID", "canary did not pass")
        require(canary["freezeSha256"] == sha(out / "freeze.json"), "canary belongs to another freeze")
    write_new(out / ("phase-" + phase + ".started.json"), {"freezeSha256": sha(out / "freeze.json")})
    seeds = [CANARY] if phase == "canary" else COHORT
    # All sources are precommitted; no selection or replacement based on outcomes.
    with ThreadPoolExecutor(max_workers=2) as pool:
        prefixes = list(pool.map(lambda seed: run_source(out, seed), seeds))
    cmd = ["python3", str(REPO / "tools/analyze_a20_teachers.py"),
           str(out / (phase + "-report.json")), str(out / "freeze.json"), *map(str, prefixes)]
    if phase == "canary":
        cmd.append("--canary")
    subprocess.run(cmd, cwd=REPO, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "canary", "cohort"))
    parser.add_argument("out", type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--prior-generation", type=int, choices=(5, 6))
    parser.add_argument("--prior-sha256")
    parser.add_argument("--prior-source")
    parser.add_argument("--ctm-dir", type=Path)
    args = parser.parse_args()
    if args.phase == "prepare":
        require(all((args.prior, args.ctm_dir, args.prior_generation, args.prior_sha256, args.prior_source)),
                "prepare needs both artifact paths and completed-prior identity")
        prepare(args.out.resolve(), args.prior.resolve(), args.ctm_dir.resolve(),
                args.prior_generation, args.prior_sha256, args.prior_source)
    else:
        execute(args.out.resolve(), args.phase)


if __name__ == "__main__":
    main()
