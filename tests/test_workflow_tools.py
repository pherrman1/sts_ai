"""Tests for the workflow tools: tools/ledger_assign.py, tools/cloud/worker.sh, tools/cloud/verify_campaign.py.

Each test builds a throwaway git repository in a temp dir; no game seeds run.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd, env=None, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError(f"{cmd} rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def git(cwd, *args):
    return run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd).stdout.strip()


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        git(self.path, "init", "-q", "-b", "main")

    def write(self, rel, text):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg="c"):
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", msg)
        return git(self.path, "rev-parse", "HEAD")


class LedgerAssignTest(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.r.write("EXPERIMENTS.md", "# ledger\n")
        self.r.write("docs/experiments/ledger-01.md", "## §1 — a\n\n## §7 — b\n")
        self.r.write("decisions/0003-old.md", "# ADR-0003\n")
        self.base = self.r.commit("base")
        git(self.r.path, "checkout", "-q", "-b", "pr")
        self.r.write("docs/experiments/ledger-01.md",
                     "## §1 — a\n\n## §7 — b\n\n## §TBD — new (see ADR-TBD)\n\n## §TBD-b — second\n")
        self.r.write("decisions/TBD-new-rule.md", "# ADR-TBD: new rule\nEvidence §TBD and §TBD-b.\n")
        self.r.write("docs/kb.md", "See §TBD and [ADR](../decisions/TBD-new-rule.md).\n")
        self.reviewed = self.r.commit("pr")
        self.tool = [sys.executable, str(ROOT / "tools" / "ledger_assign.py")]

    def tearDown(self):
        self.r.tmp.cleanup()

    def test_assign_skips_reserved_and_check_passes(self):
        out = run(self.tool + ["assign", "--base", "main", "--skip", "8"], self.r.path).stdout
        self.assertIn("§TBD -> §9", out)
        self.assertIn("§TBD-b -> §10", out)
        self.assertIn("ADR-TBD -> ADR-0004", out)
        led = (self.r.path / "docs/experiments/ledger-01.md").read_text()
        self.assertIn("## §9 — new (see ADR-0004)", led)
        self.assertIn("## §10 — second", led)
        adr = (self.r.path / "decisions/0004-new-rule.md").read_text()
        self.assertEqual(adr, "# ADR-0004: new rule\nEvidence §9 and §10.\n")
        self.assertFalse((self.r.path / "decisions/TBD-new-rule.md").exists())
        self.assertIn("decisions/0004-new-rule.md", (self.r.path / "docs/kb.md").read_text())
        new = self.r.commit("assign")
        run(self.tool + ["check", self.reviewed, new, "--base", "main", "--skip", "8"], self.r.path)
        # Without the same skip list, the check recomputes §8 and rejects the commit.
        p = run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_check_reads_skip_lists_from_commit_message(self):
        out = run(self.tool + ["assign", "--base", "main", "--skip", "8-9", "--skip-adr", "4"], self.r.path).stdout
        msg = out.strip().splitlines()[-1].strip()
        self.assertIn("--skip 8-9 --skip-adr 4)", msg)
        git(self.r.path, "add", "-A")
        git(self.r.path, "commit", "-q", "-m", msg)
        new = git(self.r.path, "rev-parse", "HEAD")
        run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path)

    def test_check_rejects_colliding_numbers(self):
        for path, old, new in [("docs/experiments/ledger-01.md", "§TBD — new (see ADR-TBD)", "§5 — new (see ADR-0001)"),
                               ("docs/experiments/ledger-01.md", "§TBD-b", "§100"),
                               ("decisions/TBD-new-rule.md", "ADR-TBD", "ADR-0001"),
                               ("decisions/TBD-new-rule.md", "§TBD and §TBD-b", "§5 and §100"),
                               ("docs/kb.md", "§TBD", "§5")]:
            f = self.r.path / path
            f.write_text(f.read_text().replace(old, new))
        git(self.r.path, "mv", "decisions/TBD-new-rule.md", "decisions/0001-new-rule.md")
        kb = self.r.path / "docs/kb.md"
        kb.write_text(kb.read_text().replace("TBD-new-rule.md", "0001-new-rule.md"))
        new = self.r.commit("hand numbering")
        p = run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not numbering-only", p.stdout)

    def test_check_requires_current_base(self):
        run(self.tool + ["assign", "--base", "main"], self.r.path)
        new = self.r.commit("assign")
        git(self.r.path, "checkout", "-q", "main")
        self.r.write("docs/experiments/ledger-01.md", "## §1 — a\n\n## §7 — b\n\n## §8 — main took it\n")
        self.r.commit("main moves")
        git(self.r.path, "checkout", "-q", "pr")
        p = run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_duplicate_unlabelled_headings_rejected(self):
        f = self.r.path / "docs/experiments/ledger-01.md"
        f.write_text(f.read_text() + "\n## §TBD — third\n")
        self.r.commit("dup")
        p = run(self.tool + ["assign", "--base", "main", "--dry-run"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("two ledger headings", p.stdout + p.stderr)

    def test_reserved_ranges_branch_numbers_and_code_spans(self):
        f = self.r.path / "docs/experiments/ledger-01.md"
        f.write_text(f.read_text() + "\n## §20 — hand-numbered on the branch\n")
        self.r.write("docs/howto.md", "Write `§TBD` and `ADR-TBD`.\n```\n## §TBD — example\n```\n")
        self.r.write("tools/x.py", '"""Mentions §TBD and ADR-TBD."""\n')
        self.r.commit("more")
        out = run(self.tool + ["assign", "--base", "main", "--skip", "21-22", "--skip-adr", "4,5"], self.r.path).stdout
        self.assertIn("§TBD -> §23", out)
        self.assertIn("§TBD-b -> §24", out)
        self.assertIn("ADR-TBD -> ADR-0006", out)
        self.assertEqual((self.r.path / "docs/howto.md").read_text(),
                         "Write `§TBD` and `ADR-TBD`.\n```\n## §TBD — example\n```\n")
        self.assertIn("§TBD", (self.r.path / "tools/x.py").read_text())

    def test_assign_runs_from_a_subdirectory(self):
        out = run(self.tool + ["assign", "--base", "main", "--dry-run"], self.r.path / "docs").stdout
        self.assertIn("§TBD -> §8", out)

    def test_check_rejects_other_edits(self):
        run(self.tool + ["assign", "--base", "main"], self.r.path)
        self.r.write("docs/kb.md", "changed text\n")
        new = self.r.commit("assign plus edit")
        p = run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_check_accepts_clean_base_merge(self):
        git(self.r.path, "checkout", "-q", "main")
        self.r.write("other.txt", "main moved\n")
        self.r.commit("main moves")
        git(self.r.path, "checkout", "-q", "pr")
        git(self.r.path, "merge", "-q", "--no-edit", "main")
        run(self.tool + ["assign", "--base", "main"], self.r.path)
        new = self.r.commit("assign")
        run(self.tool + ["check", self.reviewed, new, "--base", "main"], self.r.path)

    def test_assign_requires_base_merged(self):
        git(self.r.path, "checkout", "-q", "main")
        self.r.write("other.txt", "x\n")
        self.r.commit("main moves")
        git(self.r.path, "checkout", "-q", "pr")
        p = run(self.tool + ["assign", "--base", "main"], self.r.path, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_orphan_label_rejected(self):
        self.r.write("docs/kb.md", "See §TBD-zz.\n")
        self.r.commit("orphan")
        p = run(self.tool + ["assign", "--base", "main", "--dry-run"], self.r.path, check=False)
        self.assertIn("without a ledger heading", p.stdout + p.stderr)


class CloudWorkerTest(unittest.TestCase):
    """End to end on a fake campaign whose 'binary' is a small shell script served from the binary cache."""

    def setUp(self):
        self.r = Repo()
        shutil.copy(ROOT / "tools/cloud/worker.sh", self.r.path / "worker.sh")
        (self.r.path / "tools/cloud").mkdir(parents=True)
        shutil.move(self.r.path / "worker.sh", self.r.path / "tools/cloud/worker.sh")
        self.tmp = Path(self.r.tmp.name)
        self.cache = self.tmp / "cache"
        self.share = self.tmp / "share"
        self.home = self.tmp / "home"
        self.home.mkdir()
        fake = self.tmp / "fake_one_combat"
        fake.write_text("#!/bin/sh\necho fake \"$@\"\n")
        self.bin_sha = hashlib.sha256(fake.read_bytes()).hexdigest()
        inp = self.tmp / "model.bin"
        inp.write_text("weights\n")
        inp_sha = hashlib.sha256(inp.read_bytes()).hexdigest()
        self.r.write("README", "x\n")
        code = self.r.commit("code")
        c = "docs/experiments/evidence/fake"
        self.r.write(f"{c}/campaign.manifest", "\n".join([
            "name fake", f"code_commit {code}", f"binary_sha256 {self.bin_sha}", "workers 2",
            f"share {self.share}", "parallel 2", f"input model.bin {inp} {inp_sha}", ""]))
        self.r.write(f"{c}/units.txt", "# seed arm\n111 a\n111 b\n112 a\n112 b\n113 a\n")
        self.r.write(f"{c}/run_unit.sh",
                     'repo=$1 run=$2 out=$3; shift 3\n"$run/one_combat" "$@" > "$out/result.txt"\n'
                     'test -f "$run/model.bin"\n')
        self.r.commit("campaign")
        self.c = c
        self.env = {**os.environ, "HOME": str(self.home), "CW_BIN_CACHE": str(self.cache)}
        self.w = ["bash", "tools/cloud/worker.sh"]
        run(self.w + ["cache-put", str(fake), code], self.r.path, self.env)

    def tearDown(self):
        self.r.tmp.cleanup()

    def test_campaign_round_trip(self):
        p = run(self.w + ["setup", self.c, "1"], self.r.path, self.env)
        self.assertIn("setup ok", p.stdout)
        self.assertIn("source=cache", p.stdout)
        self.assertIn("units=3", p.stdout)
        p = run(self.w + ["run", self.c, "1"], self.r.path, self.env)
        self.assertIn("WORKER_OK w01", p.stdout)
        res = (self.home / "cw-fake-w01/out/units/112_a/result.txt").read_text()
        self.assertEqual(res, "fake 112 a\n")
        verify = [sys.executable, str(ROOT / "tools/cloud/verify_campaign.py"), self.c, "--json"]
        rows = json.loads(run(verify, self.r.path, check=False).stdout)
        self.assertEqual([r["state"] for r in rows], ["OK", "MISSING"])
        run(self.w + ["setup", self.c, "2"], self.r.path, self.env)
        run(self.w + ["run", self.c, "2"], self.r.path, self.env)
        run(verify, self.r.path)
        # A tampered tar is caught.
        (self.share / "w02.tar").write_bytes(b"junk")
        rows = json.loads(run(verify, self.r.path, check=False).stdout)
        self.assertEqual(rows[1]["state"], "BAD")

    def test_setup_refuses_a_different_freeze(self):
        run(self.w + ["setup", self.c, "1"], self.r.path, self.env)
        f = self.r.path / self.c / "run_unit.sh"
        f.write_text(f.read_text() + "# v2\n")
        self.r.commit("v2")
        p = run(self.w + ["setup", self.c, "1"], self.r.path, self.env, check=False)
        self.assertIn("different freeze", p.stdout)
        p = run(self.w + ["run", self.c, "1"], self.r.path, self.env, check=False)
        self.assertIn("no longer matches", p.stdout)

    def test_campaign_must_be_committed_inside_repo(self):
        outside = self.tmp / "elsewhere"
        shutil.copytree(self.r.path / self.c, outside)
        p = run(self.w + ["setup", str(outside), "1"], self.r.path, self.env, check=False)
        self.assertIn("inside the repository", p.stdout)
        shutil.copytree(self.r.path / self.c, self.r.path / "docs/experiments/evidence/untracked")
        p = run(self.w + ["setup", "docs/experiments/evidence/untracked", "1"], self.r.path, self.env, check=False)
        self.assertIn("not tracked", p.stdout)
        f = self.r.path / self.c / "run_unit.sh"
        f.write_text(f.read_text() + "# edited\n")
        p = run(self.w + ["setup", self.c, "1"], self.r.path, self.env, check=False)
        self.assertIn("STOP", p.stdout)

    def test_retry_starts_from_an_empty_unit_dir(self):
        # Appends like one_combat's CSVs; unit "112 a" fails the first time after writing a row.
        (self.r.path / self.c / "run_unit.sh").write_text(
            'repo=$1 run=$2 out=$3; shift 3\necho "row $*" >> "$out/rows.csv"\n'
            'if [ "$*" = "112 a" ] && [ ! -e "$run/second" ]; then touch "$run/second"; exit 1; fi\n')
        self.r.commit("appending unit")
        run(self.w + ["setup", self.c, "1"], self.r.path, self.env)
        p = run(self.w + ["run", self.c, "1"], self.r.path, self.env, check=False)
        self.assertEqual(p.returncode, 3)
        run(self.w + ["run", self.c, "1"], self.r.path, self.env)
        self.assertEqual((self.home / "cw-fake-w01/out/units/112_a/rows.csv").read_text(), "row 112 a\n")

    def test_verify_checks_frozen_and_stray_units(self):
        for w in ("1", "2"):
            run(self.w + ["setup", self.c, w], self.r.path, self.env)
            run(self.w + ["run", self.c, w], self.r.path, self.env)
        verify = [sys.executable, str(ROOT / "tools/cloud/verify_campaign.py"), self.c, "--json"]
        run(verify, self.r.path)
        # A stray unit dir and a .failed marker in a re-packed tar (with a matching DONE.json) are caught.
        rd = self.home / "cw-fake-w01"
        (rd / "out/units/999_z").mkdir()
        (rd / "out/units/111_a.failed").write_text("rc=1\n")
        run(["tar", "-C", str(rd), "-cf", str(self.share / "w01.tar"), "out", "FROZEN.txt", "SETUP.txt"], self.r.path)
        meta = json.loads((self.share / "w01.DONE.json").read_text())
        meta["tar_sha256"] = hashlib.sha256((self.share / "w01.tar").read_bytes()).hexdigest()
        (self.share / "w01.DONE.json").write_text(json.dumps(meta))
        rows = json.loads(run(verify, self.r.path, check=False).stdout)
        self.assertEqual(rows[0]["state"], "BAD")
        self.assertIn("unexpected unit", rows[0]["detail"])
        # The lead's campaign files differing from the ones the workers froze is caught.
        f = self.r.path / self.c / "units.txt"
        f.write_text(f.read_text() + "# note\n")
        rows = json.loads(run(verify, self.r.path, check=False).stdout)
        self.assertEqual(rows[1]["state"], "BAD")
        self.assertIn("hashes differ", rows[1]["detail"])

    def test_dot_unit_ids_rejected(self):
        (self.r.path / self.c / "units.txt").write_text("..\n111 a\n")
        self.r.commit("dot unit")
        p = run(self.w + ["setup", self.c, "1"], self.r.path, self.env, check=False)
        self.assertIn("starts with a dot", p.stdout)

    def test_padded_worker_number_rejected(self):
        p = run(self.w + ["setup", self.c, "01"], self.r.path, self.env, check=False)
        self.assertIn("unpadded", p.stdout)

    def test_wrong_cached_binary_rejected(self):
        for f in self.cache.glob("one_combat-*"):
            f.write_text("tampered\n")
        p = run(self.w + ["setup", self.c, "1"], self.r.path, self.env, check=False)
        # Cache miss on hash falls back to a build, which fails in this fake repo: never runs a wrong binary.
        self.assertIn("STOP", p.stdout)
        self.assertFalse((self.home / "cw-fake-w01/one_combat").exists())

    def test_failed_unit_blocks_upload(self):
        (self.r.path / self.c / "run_unit.sh").write_text("exit 7\n")
        self.r.commit("break")
        run(self.w + ["setup", self.c, "1"], self.r.path, self.env)
        p = run(self.w + ["run", self.c, "1"], self.r.path, self.env, check=False)
        self.assertEqual(p.returncode, 3)
        self.assertFalse((self.share / "w01.tar").exists())


class CloudQueueTest(unittest.TestCase):
    """Queue schedule claims: several workers and lanes race for the same units (no game seeds run).

    CW_TEST_SHARE=/mnt/project-files/<scratch dir> runs the share-backed cases against that directory."""

    def setUp(self):
        CloudWorkerTest.setUp(self)
        base = os.environ.get("CW_TEST_SHARE")
        if base:
            self.share = Path(base) / f"cwq-{os.getpid()}-{self._testMethodName}"
        m = self.r.path / self.c / "campaign.manifest"
        text = m.read_text().replace("workers 2", "workers 3")
        text = "\n".join(l if not l.startswith("share ") else f"share {self.share}" for l in text.splitlines())
        m.write_text(text + "\nschedule queue\nclaim_settle_seconds 2\n")
        (self.r.path / self.c / "units.txt").write_text("".join(f"{s} a\n" for s in range(200, 212)))
        (self.r.path / self.c / "run_unit.sh").write_text(
            'repo=$1 run=$2 out=$3; shift 3\necho "$*" >> "$CW_TEST_LOG"\nsleep 1\n"$run/one_combat" "$@" > "$out/result.txt"\n')
        self.r.commit("queue campaign")
        self.log = self.tmp / "ran.log"
        self.env = {**self.env, "CW_TEST_LOG": str(self.log)}

    def tearDown(self):
        if os.environ.get("CW_TEST_SHARE"):
            shutil.rmtree(self.share, ignore_errors=True)
        self.r.tmp.cleanup()

    def test_split_share_claim_has_one_winner(self):
        # Every claimer "wins" the mkdir, as on a share whose containers see each other's dirs late.
        env = {**self.env, "CW_TEST_SPLIT_SHARE": "1"}
        for rnd, mine in enumerate([["0"] * 6, ["0", "0", "1", "0", "0", "0"]]):
            uid = f"20{rnd}_a"
            procs = [subprocess.Popen(self.w + ["_claim", self.c, str(i % 3 + 1), uid, m], cwd=self.r.path, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for i, m in enumerate(mine)]
            rcs = [p.wait() for p in procs]
            self.assertEqual(rcs.count(0), 1, rcs)
            cands = list((self.share / "claims" / f"{uid}.a1").glob("cand.*"))
            self.assertEqual(len(cands), 6)
            if "1" in mine:
                self.assertEqual(rcs[mine.index("1")], 0)  # the static owner never waits and always wins

    def test_concurrent_workers_run_each_unit_once(self):
        for w in ("1", "2", "3"):
            run(self.w + ["setup", self.c, w], self.r.path, self.env)
        procs = [subprocess.Popen(self.w + ["run", self.c, w], cwd=self.r.path, env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for w in ("1", "2", "3")]
        outs = [p.communicate()[0] for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0, 0], outs)
        ran = self.log.read_text().splitlines()
        self.assertEqual(sorted(ran), sorted(f"{s} a" for s in range(200, 212)))
        verify = [sys.executable, str(ROOT / "tools/cloud/verify_campaign.py"), self.c, "--json"]
        run(verify, self.r.path)

    def test_central_stop_finishes_open_ended_queue(self):
        # The lead's SHARE/STOP ends the run: running units finish and upload, no new unit starts, DONE.json is written.
        (self.r.path / self.c / "run_unit.sh").write_text(
            'repo=$1 run=$2 out=$3; shift 3\necho "$*" >> "$CW_TEST_LOG"\n'
            '[ "$1" = 203 ] && touch "$CW_TEST_STOP"\nsleep 1\n"$run/one_combat" "$@" > "$out/result.txt"\n')
        self.r.commit("stop campaign")
        env = {**self.env, "CW_TEST_STOP": str(self.share / "STOP")}
        run(self.w + ["setup", self.c, "1"], self.r.path, env)
        p = run(self.w + ["run", self.c, "1"], self.r.path, env)
        self.assertIn("central_stop", p.stdout)
        ran = self.log.read_text().splitlines()
        self.assertLess(len(ran), 8, ran)
        done = json.loads((self.share / "w01.DONE.json").read_text())
        self.assertTrue(done["central_stop"])
        self.assertEqual(done["unit_count"], len(ran))
        self.assertTrue((self.home / "cw-fake-w01/FINISHED").exists())
        # STOP_AT in the past also stops before any claim.
        (self.share / "STOP").unlink()
        (self.share / "STOP_AT").write_text("1\n")
        run(self.w + ["setup", self.c, "2"], self.r.path, env)
        p = run(self.w + ["run", self.c, "2"], self.r.path, env)
        self.assertIn("units_uploaded=0 central_stop", p.stdout)
        self.assertEqual(len(self.log.read_text().splitlines()), len(ran))


if __name__ == "__main__":
    unittest.main()
