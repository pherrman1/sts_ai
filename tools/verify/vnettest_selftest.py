#!/usr/bin/env python3
"""Regression self-test for `one_combat vnettest` (asserting C++/Python parity).

The asserting vnettest contract must fail loudly (nonzero exit) on malformed
parity evidence. In particular a non-finite native prediction must NOT be
reported as PASS: `std::max(maxAbs, NaN)` silently leaves maxAbs unchanged, so
before the 2026-08-07 fix a NaN prediction compared as "in tolerance".

The native loader rejects "nan"/"inf" leaf tokens, so the non-finite
prediction fixture is a 1x1 MLP whose all-finite tokens overflow float in the
hidden layer and predict inf; a canonical-header CSV with one row drives it.
A positive control (finite model matching pyPred) must exit 0, and a feature
value that is a finite double but overflows float (1e300 -> inf) must also be
rejected.

Usage: python3 tools/verify/vnettest_selftest.py [--self-test [ONECOMBAT_BIN]]
"""
import os
import subprocess
import sys
import tempfile

DEFAULT_BIN = "build/one_combat"
TOL = "0.001"

# Canonical combat feature names, mirrored from CombatValueNet.cpp
# (combatFeatureNames): kBaseNames + kPowers + relics + per-pile card-id
# counts + enemy aggregate + per-monster slots + potions + misc + counters.
# Order and count (1766) must match C++ combatFeatureNames() exactly.
_CANONICAL = None


def canonical_names():
    global _CANONICAL
    if _CANONICAL is not None:
        return _CANONICAL
    base = ["ascension", "encounter", "turn", "curHp", "maxHp", "block",
            "energy", "strength", "dexterity", "focus", "artifact",
            "monAlive", "monSumHp", "monMaxHp", "monSumBlock", "monSumStr",
            "monSumArt", "hand", "draw", "discard", "exhaust", "nAtkAvail",
            "nSklAvail", "nPowAvail", "nOtherAvail", "potions"]
    powers = ["pDemonForm", "pMetallicize", "pFeelNoPain", "pBarricade",
              "pPlatedArmor", "pRupture", "pCombust", "pDarkEmbrace",
              "pBrutality", "pFireBreath", "pJuggernaut", "pCorruption",
              "pVigor", "pMayhem", "pPanache", "pNoxious", "pFlameBarrier",
              "pThorns", "pRegen", "pBuffer", "pIntangible", "pVulnerable",
              "pWeak", "pFrail"]
    names = list(base) + powers
    names += ["r%d" % i for i in range(128)]                     # relics
    names += ["hd%d" % i for i in range(371)]                    # hand
    names += ["dr%d" % i for i in range(371)]                    # draw
    names += ["ds%d" % i for i in range(371)]                    # discard
    names += ["ex%d" % i for i in range(371)]                    # exhaust
    names += ["incomingDmg", "nAttacking"]
    for i in range(5):                                           # monster slots
        p = "m%d" % i
        names += [p + "Id", p + "Hp", p + "Block", p + "Str",
                  p + "Intent", p + "Atk", p + "Vuln", p + "Weak",
                  p + "Poison"]
    names += ["pot%d" % i for i in range(44)]                    # potions
    names += ["gold", "potionCap", "cardsPlayed", "attacksPlayed",
              "skillsPlayed", "happyFlowerCtr", "incenseBurnerCtr",
              "inkBottleCtr", "inserterCtr", "nunchakuCtr", "penNibCtr",
              "sundialCtr", "panacheCtr"]
    _CANONICAL = names
    return names


def write_model(path, leaf):
    """Minimal single-feature single-tree native model; `leaf` is written
    verbatim as the leaf value token (e.g. "0" or "nan")."""
    with open(path, "w") as f:
        f.write("nfeat 1\n")
        f.write("feat encounter\n")
        f.write("base_score 0\n")
        f.write("ntrees 1\n")
        f.write("tree 0 1\n")
        f.write("L %s\n" % leaf)


def write_mlp_overflow_model(path):
    """Single-feature 1x1 MLP whose FINITE tokens overflow float in the hidden
    layer: x=1 -> a1 = 1e38 (finite), then w2=1e38 -> a2 = inf. Loads cleanly
    (all tokens are parseable finite floats) yet predicts non-finite, which the
    asserting vnettest must reject."""
    with open(path, "w") as f:
        f.write("combat_mlp_v1\n")
        f.write("nfeat 1\n")
        f.write("feat encounter\n")
        f.write("x_mean 0\n")
        f.write("x_invstd 1\n")
        f.write("y_mean 0\n")
        f.write("y_scale 1\n")
        f.write("h1 1\n")
        f.write("w1 1e38\n")
        f.write("b1 0\n")
        f.write("h2 1\n")
        f.write("w2 1e38\n")
        f.write("b2 0\n")
        f.write("w3 1\n")
        f.write("b3 0\n")


def write_csv(path, feature_values):
    """Canonical header + one data row. feature_values overrides the leading
    columns (default all zeros); the rest stay zero; pyPred is 0.0."""
    names = canonical_names()
    assert len(names) == 1766, "canonical feature list drifted: %d" % len(names)
    with open(path, "w") as f:
        f.write(",".join(names) + ",pyPred\n")
        row = list(feature_values) + ["0"] * (len(names) - len(feature_values))
        f.write(",".join(row) + ",0.0\n")


def run_vnettest(bin_path, model, csv):
    # Hermetic: vnettest only needs the passed model + CSV. Disable the native
    # OOC block (which would otherwise fatal-exit before mode dispatch when its
    # cwd-relative models/v_rich_trees.txt is missing, e.g. under ctest where
    # the working directory is the build dir) and pin the cwd to the repo root
    # so default relative paths never influence the verdict.
    env = dict(os.environ)
    env["STS_NATIVE_OOC"] = "0"
    root = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run([bin_path, "vnettest", model, csv, TOL],
                          capture_output=True, text=True, cwd=root, env=env)


def self_test(bin_path):
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        # 1. Non-finite native prediction must exit nonzero. A tree model's
        #    leaf tokens "nan"/"inf" are rejected by the loader itself, so use
        #    an MLP whose all-finite tokens overflow float in the hidden layer
        #    and predict inf. Before the 2026-08-07 fix, maxAbs ignored the
        #    NaN diff and the run printed PASS.
        model = os.path.join(td, "nan_model.txt")
        csv = os.path.join(td, "nan_val.csv")
        write_mlp_overflow_model(model)
        write_csv(csv, ["0", "1"])   # encounter (canonical index 1) = 1
        r = run_vnettest(bin_path, model, csv)
        if r.returncode == 0:
            print("FAIL: non-finite native prediction was reported as PASS\n%s"
                  % r.stdout)
            failures += 1
        else:
            print("PASS: non-finite native prediction exits %d" % r.returncode)

        # 2. Positive control: finite leaf matching pyPred must exit 0.
        model = os.path.join(td, "ok_model.txt")
        csv = os.path.join(td, "ok_val.csv")
        write_model(model, "0")
        write_csv(csv, ["0"])
        r = run_vnettest(bin_path, model, csv)
        if r.returncode != 0:
            print("FAIL: finite parity evidence exited %d\n%s\n%s"
                  % (r.returncode, r.stdout, r.stderr))
            failures += 1
        else:
            print("PASS: finite parity evidence exits 0")

        # 3. Finite double that overflows float (1e300 -> inf in the canonical
        #    float vector) must be rejected after conversion.
        model = os.path.join(td, "overflow_model.txt")
        csv = os.path.join(td, "overflow_val.csv")
        write_model(model, "0")
        write_csv(csv, ["1e300"])   # ascension = 1e300, finite as double
        r = run_vnettest(bin_path, model, csv)
        if r.returncode == 0:
            print("FAIL: float-overflow feature was reported as PASS\n%s"
                  % r.stdout)
            failures += 1
        else:
            print("PASS: float-overflow feature exits %d" % r.returncode)

    if failures:
        print("self-test FAIL: %d case(s) failed" % failures)
        return 1
    print("self-test PASS: NaN prediction, positive control, float overflow")
    return 0


def main(argv):
    if argv and argv[0] == "--self-test":
        bin_path = argv[1] if len(argv) > 1 else DEFAULT_BIN
        if not os.path.exists(bin_path):
            print("vnettest_selftest: binary not found: %s" % bin_path)
            return 2
        return self_test(bin_path)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
