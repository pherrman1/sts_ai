#!/usr/bin/env python3
"""Regression self-test for `one_combat winnettest` truncated-tree detection.

WinNet::load (apps/one_combat.cpp) previously set ok=true unconditionally
after parsing: a truncated compact tree file left ntrees=0 (or partially-read
nodes with uninitialized feature indices) yet reported success, producing
silent constant predictions or UB in predict(). Since 2026-08-08 the loader
returns false on truncation (stream-state checks, ntrees<1, non-leaf final
node, trailing-data probe), so the asserting winnettest mode must exit nonzero
on every malformed fixture while a well-formed file still loads and predicts.

Usage: python3 tools/verify/winnettest_selftest.py [--self-test [ONECOMBAT_BIN]]
"""
import os
import subprocess
import sys
import tempfile

DEFAULT_BIN = "build/one_combat"

# Rich layout names are resolved against richIdxMap(); "ascension" is the
# first rich feature after the dropped "seed" prefix (raw index 0).


def write_model(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def ok_model_lines():
    return ["nfeat 1", "feat ascension", "logistic 0", "base_score 0",
            "ntrees 1", "tree 0 1", "L 0.5"]


def write_csv(path):
    # winnettest reads the state block between `chosen` and `won`; a single
    # state column (raw[0] = 0.5) drives the one-feature tree above.
    with open(path, "w") as f:
        f.write("seed,chosen,f0,won\n")
        f.write("0,0,0.5,0\n")


def run_winnettest(bin_path, model, csv):
    # Hermetic: disable the native OOC block (which would otherwise
    # fatal-exit before mode dispatch when its cwd-relative
    # models/v_rich_trees.txt is missing, e.g. under ctest where the working
    # directory is the build dir) and pin the cwd to the repo root so default
    # relative paths never influence the verdict.
    env = dict(os.environ)
    env["STS_NATIVE_OOC"] = "0"
    root = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run([bin_path, "winnettest", model, csv, "10"],
                          capture_output=True, text=True, cwd=root, env=env)


def self_test(bin_path):
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        def expect_fail(name, lines, why):
            nonlocal failures
            model = os.path.join(td, name + ".txt")
            write_model(model, lines)
            r = run_winnettest(bin_path, model, os.path.join(td, "val.csv"))
            if r.returncode == 0:
                print("FAIL: %s accepted as valid\n%s" % (why, r.stdout))
                failures += 1
            else:
                print("PASS: %s exits %d" % (why, r.returncode))

        write_csv(os.path.join(td, "val.csv"))

        # 1. File truncated before the ntrees line: previously loaded with
        #    ntrees=0, ok=true, silent constant predictions.
        expect_fail("trunc_before_ntrees",
                    ["nfeat 1", "feat ascension"],
                    "truncated-before-ntrees file")

        # 2. Header declares zero trees: not a model, constant predictions.
        expect_fail("trunc_zero_ntrees",
                    ["nfeat 1", "feat ascension", "logistic 0",
                     "base_score 0", "ntrees 0"],
                    "zero-tree file")

        # 3. Tree header declares 3 nodes but the block ends after 2
        #    (mid-tree truncation; previously uninitialized ints).
        expect_fail("trunc_mid_tree",
                    ["nfeat 1", "feat ascension", "logistic 0",
                     "base_score 0", "ntrees 1", "tree 0 3",
                     "S 0 0.5 1 2", "L 0.1"],
                    "mid-tree truncated file")

        # 4. Tree whose final node is a split, not a leaf.
        expect_fail("bad_last_node",
                    ["nfeat 1", "feat ascension", "logistic 0",
                     "base_score 0", "ntrees 1", "tree 0 2",
                     "L 0.1", "S 0 0.5 0 1"],
                    "non-leaf final node file")

        # 5. Positive control: well-formed file loads and predicts 0.5.
        model = os.path.join(td, "ok_model.txt")
        csv = os.path.join(td, "val.csv")
        write_model(model, ok_model_lines())
        r = run_winnettest(bin_path, model, csv)
        if r.returncode != 0 or "0,0.500000000" not in r.stdout:
            print("FAIL: well-formed file exited %d\n%s\n%s"
                  % (r.returncode, r.stdout, r.stderr))
            failures += 1
        else:
            print("PASS: well-formed file loads and predicts 0.5")

    if failures:
        print("self-test FAIL: %d case(s) failed" % failures)
        return 1
    print("self-test PASS: 4 truncated/malformed fixtures rejected, 1 control")
    return 0


def main(argv):
    if argv and argv[0] == "--self-test":
        bin_path = argv[1] if len(argv) > 1 else DEFAULT_BIN
        if not os.path.exists(bin_path):
            print("winnettest_selftest: binary not found: %s" % bin_path)
            return 2
        return self_test(bin_path)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
