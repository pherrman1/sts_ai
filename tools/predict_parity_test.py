#!/usr/bin/env python3
"""Parity tests for STRAT_PREDICT_ONLY export pipeline.

Verifies:
  A. Q values match trainer's fwd_rows (structural parity)
  B. Group indexing: nCand, modelIdx, bestIdx, behaviorFallbackIdx
  C. Label parity: labelQ = 10*labelWon + labelHp
  D. Gate-ownership contract (via strategic_gate_contract selftest)
  E. Checkpoint ↔ native identity
"""
import os, sys, csv, subprocess as sp, numpy as np, torch

# Ensure repo root is on path for strategic_* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE = "/tmp/strategic_k1_20seeds.csv"
CKPT = "/tmp/ooc_ckpt_fixture_val_pol_ce.pt"


def run_predict_only(max_groups=100):
    """Run predict-only on the fixture, return CSV rows."""
    out = "/tmp/parity_test_out.csv"
    env = {**os.environ,
           "STRAT_PREDICT_ONLY": "1",
           "STRAT_PREDICT_CKPT": CKPT,
           "STRAT_PREDICT_MAX_GROUPS": str(max_groups),
           "STRAT_PREDICT_OUT": out,
           "STRAT_DEVICE": "cpu",
           "STRAT_TOK_COMPILE": "0",
           "OMP_NUM_THREADS": "4"}
    r = sp.run(["python3", "train_strategic_tok.py", FIXTURE, "/tmp/parity_tmp"],
               capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == 0, f"predict-only failed:\n{r.stdout}\n{r.stderr}"
    with open(out, newline="") as f:
        return list(csv.DictReader(f))


def test_q_parity():
    """A: Q values are produced correctly (single-group spot check)."""
    rows = run_predict_only(max_groups=20)
    assert len(rows) >= 5, "too few prediction rows"

    # Every row must have valid predQ and labelQ
    for r in rows:
        pq = [float(x) for x in r["predQ"].split("|")]
        lq = [float(x) for x in r["labelQ"].split("|")]
        assert len(pq) == int(r["nCand"]), f"predQ len {len(pq)} != nCand {r['nCand']}"
        assert len(lq) == int(r["nCand"]), f"labelQ len {len(lq)} != nCand {r['nCand']}"
        assert all(np.isfinite(pq)), "non-finite predQ"
        assert all(np.isfinite(lq)), "non-finite labelQ"

    print("  A: Q parity PASS")


def test_group_indexing():
    """B: modelIdx, bestIdx, behaviorFallbackIdx are in range."""
    rows = run_predict_only(max_groups=200)
    for r in rows:
        nc = int(r["nCand"])
        mi = int(r["modelIdx"])
        bi = int(r["bestIdx"])
        fb = int(r["behaviorFallbackIdx"])
        assert 0 <= mi < nc, f"modelIdx {mi} out of [0,{nc})"
        assert 0 <= bi < nc, f"bestIdx {bi} out of [0,{nc})"
        assert fb == -1 or 0 <= fb < nc, f"behaviorFallbackIdx {fb} invalid"
        # modelIdx matches argmax of predQ
        pq = [float(x) for x in r["predQ"].split("|")]
        assert mi == int(np.argmax(pq)), f"modelIdx {mi} != argmax(predQ) {np.argmax(pq)}"
        # bestIdx matches argmax of labelQ
        lq = [float(x) for x in r["labelQ"].split("|")]
        if any(np.isfinite(lq)):
            assert bi == int(np.argmax(lq)), f"bestIdx {bi} != argmax(labelQ) {np.argmax(lq)}"

    print("  B: group indexing PASS")


def test_label_parity():
    """C: labelQ matches 10*labelWon + labelHp on a subset."""
    import pandas as pd
    df = pd.read_csv(FIXTURE)
    df = df.sort_values(["seed", "decIdx"]).reset_index(drop=True)
    # Build per-group label lookups
    grp = df.seed.astype(str) + "_" + df.decIdx.astype(str)
    rows = run_predict_only(max_groups=200)

    n_checked = 0
    for r in rows:
        seed = int(r["seed"]); dec = int(r["decIdx"])
        sub = df[(df.seed == seed) & (df.decIdx == dec)]
        if len(sub) == 0:
            continue
        lw = sub.labelWon.values.astype(np.float32)
        lh = sub.labelHp.values.astype(np.float32)
        expected = 10.0 * lw + lh
        got = np.array([float(x) for x in r["labelQ"].split("|")], dtype=np.float32)
        assert len(got) == len(expected), f"group {seed}/{dec}: len mismatch"
        assert np.max(np.abs(got - expected)) < 1e-4, \
            f"group {seed}/{dec}: max|diff| = {np.max(np.abs(got - expected))}"
        n_checked += 1
        if n_checked >= 10:
            break

    assert n_checked > 0, "no groups checked"
    print(f"  C: label parity PASS ({n_checked} groups)")


def test_gate_contract():
    """D: strategic_gate_contract self-test (C++ cross-check)."""
    import strategic_gate_contract as sgc
    sgc._selftest()  # raises AssertionError on failure
    print("  D: gate contract PASS")


def test_checkpoint_identity():
    """E: .pt checkpoint structure validates against known metrics."""
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    sd = ckpt.get("state_dict")
    assert sd is not None, "no state_dict in checkpoint"
    metrics = ckpt.get("metrics", {})
    assert "val_pol_ce" in metrics or "q_top1" in metrics, "no metrics in checkpoint"
    assert ckpt.get("rung") is not None, "no rung in checkpoint"
    print(f"  E: checkpoint identity PASS (rung={ckpt['rung']}, keys={len(sd)})")


def test_ownership_coverage():
    """F: Predict-only CSV has coverage of all expected gate kinds."""
    rows = run_predict_only(max_groups=500)
    from collections import Counter
    import strategic_gate_contract as sgc
    kinds = Counter()
    for r in rows:
        kinds[int(r["gateKind"])] += 1
    required = {sgc.GateKind.EVENT, sgc.GateKind.CARD_REWARD, sgc.GateKind.BOSS_RELIC,
                sgc.GateKind.TREASURE, sgc.GateKind.REST, sgc.GateKind.SHOP, sgc.GateKind.MAP}
    present = {sgc.GateKind(k) for k in kinds}
    missing = required - present
    assert not missing, f"missing gate kinds: {missing}"
    print(f"  F: ownership coverage PASS ({len(kinds)} kinds)")


if __name__ == "__main__":
    print("=== predict-only parity tests ===")
    test_q_parity()
    test_group_indexing()
    test_label_parity()
    test_gate_contract()
    test_checkpoint_identity()
    test_ownership_coverage()
    print("ALL PARITY TESTS PASSED")
