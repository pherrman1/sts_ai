#!/usr/bin/env python3
"""Reproduce the Phase-12 M0/M1 Q and strict-model autopsy.

The prediction CSVs are inference-only outputs from the strict checkpoints;
this script does not train or run the simulator.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

SCREENS = {
    1: "EVENT",
    2: "CARD",
    3: "BOSS_RELIC",
    4: "UPGRADE_SELECT",
    6: "TREASURE",
    7: "REST",
    8: "SHOP",
}
LABELS = ("labelWon", "labelHp", "labelFloor", "labelBootstrap")


def argmax(values):
    # First occurrence wins, matching numpy.argmax and the trainer.
    return int(np.argmax(values))


def margin(values):
    return float(np.sort(values)[-1] - np.sort(values)[-2])


def quantiles(values):
    return [float(np.quantile(values, p)) for p in (.05, .25, .5, .75, .95)]


def load_labels(path):
    groups = defaultdict(list)
    rows = 0
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["seed"], row["decIdx"])
            groups[key].append({
                "action": row["action"],
                "screen": int(row["screen"]),
                "chosen": int(row["chosen"]),
                **{name: float(row[name]) for name in LABELS},
            })
            rows += 1
    return groups, rows


def load_predictions(path):
    groups = {}
    with Path(path).open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["seed"], row["decIdx"])
            groups[key] = {
                "screen": int(row["screen"]),
                "policy": np.array([float(x) for x in row["policy"].split("|")]),
                "pred_q": np.array([float(x) for x in row["predQ"].split("|")]),
            }
    return groups


def summarize(records):
    n = len(records)
    target_same = np.array([r["target_same"] for r in records], dtype=bool)
    policy_same = np.array([r["policy_same"] for r in records], dtype=bool)
    pred_q_same = np.array([r["pred_q_same"] for r in records], dtype=bool)
    out = {
        "groups": n,
        "target_disagreement": int((~target_same).sum()),
        "policy_disagreement": int((~policy_same).sum()),
        "pred_q_disagreement": int((~pred_q_same).sum()),
        "target_top2_reversal": int(sum(r["target_reversal"] for r in records)),
        "target_m0_margin": float(np.mean([r["target_m0_margin"] for r in records])),
        "target_m1_margin": float(np.mean([r["target_m1_margin"] for r in records])),
        "policy_m0_margin": float(np.mean([r["policy_m0_margin"] for r in records])),
        "policy_m1_margin": float(np.mean([r["policy_m1_margin"] for r in records])),
        "policy_m0_entropy": float(np.mean([r["policy_m0_entropy"] for r in records])),
        "policy_m1_entropy": float(np.mean([r["policy_m1_entropy"] for r in records])),
        "pred_q_m0_fidelity": float(np.mean([r["pred_q_m0_target_same"] for r in records])),
        "pred_q_m1_fidelity": float(np.mean([r["pred_q_m1_target_same"] for r in records])),
        "target_margin_delta_quantiles": quantiles(
            [r["target_m1_margin"] - r["target_m0_margin"] for r in records]
        ),
        "raw": {},
        "cross": {
            ",".join("same" if flag else "different" for flag in key): count
            for key, count in Counter(
                (r["target_same"], r["policy_same"], r["pred_q_same"])
                for r in records
            ).items()
        },
    }
    for name in LABELS:
        changes = np.array([r["label_delta"][name] for r in records for _ in (0,)], dtype=float)
        relative = np.array([r["label_relative_abs"][name] for r in records], dtype=float)
        out["raw"][name] = {
            "mean": float(changes.mean()),
            "median": float(np.median(changes)),
            "abs_mean": float(np.abs(changes).mean()),
            "quantiles": quantiles(changes),
            "within_decision_centered_abs_mean": float(relative.mean()),
        }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("m0_csv")
    parser.add_argument("m1_csv")
    parser.add_argument("m0_predictions")
    parser.add_argument("m1_predictions")
    parser.add_argument("output")
    args = parser.parse_args()

    m0, m0_rows = load_labels(args.m0_csv)
    m1, m1_rows = load_labels(args.m1_csv)
    p0, p1 = load_predictions(args.m0_predictions), load_predictions(args.m1_predictions)
    assert m0_rows == m1_rows == 210_838, (m0_rows, m1_rows)
    assert set(m0) == set(m1) == set(p0) == set(p1)
    assert len(m0) == 39_870

    records = []
    screen_counts = Counter()
    for key in sorted(m0):
        rows0, rows1 = m0[key], m1[key]
        assert len(rows0) == len(rows1)
        assert [r["action"] for r in rows0] == [r["action"] for r in rows1]
        screen = rows0[0]["screen"]
        assert screen in SCREENS and all(r["screen"] == screen for r in rows0)
        assert p0[key]["screen"] == p1[key]["screen"] == screen
        assert len(p0[key]["policy"]) == len(rows0) == len(p0[key]["pred_q"])
        assert len(p1[key]["policy"]) == len(rows0) == len(p1[key]["pred_q"])
        screen_counts[screen] += 1

        q0 = np.array([10 * r["labelWon"] + r["labelHp"] for r in rows0])
        q1 = np.array([10 * r["labelWon"] + r["labelHp"] for r in rows1])
        t0, t1 = argmax(q0), argmax(q1)
        p0i, p1i = argmax(p0[key]["policy"]), argmax(p1[key]["policy"])
        q0i, q1i = argmax(p0[key]["pred_q"]), argmax(p1[key]["pred_q"])
        prob0 = np.exp(p0[key]["policy"] - p0[key]["policy"].max())
        prob0 /= prob0.sum()
        prob1 = np.exp(p1[key]["policy"] - p1[key]["policy"].max())
        prob1 /= prob1.sum()
        delta = {name: float(np.mean([r1[name] - r0[name] for r0, r1 in zip(rows0, rows1)])) for name in LABELS}
        relative = {}
        for name in LABELS:
            values = np.array([r1[name] - r0[name] for r0, r1 in zip(rows0, rows1)])
            relative[name] = float(np.abs(values - values.mean()).mean())
        records.append({
            "screen": screen,
            "target_same": t0 == t1,
            "policy_same": p0i == p1i,
            "pred_q_same": q0i == q1i,
            "target_reversal": len(rows0) >= 2 and np.array_equal(np.argsort(-q0)[:2], np.argsort(-q1)[:2][::-1]),
            "target_m0_margin": margin(q0), "target_m1_margin": margin(q1),
            "policy_m0_margin": margin(p0[key]["policy"]), "policy_m1_margin": margin(p1[key]["policy"]),
            "policy_m0_entropy": float(-(prob0 * np.log(np.maximum(prob0, 1e-30))).sum()),
            "policy_m1_entropy": float(-(prob1 * np.log(np.maximum(prob1, 1e-30))).sum()),
            "pred_q_m0_target_same": q0i == t0, "pred_q_m1_target_same": q1i == t1,
            "label_delta": delta, "label_relative_abs": relative,
        })

    assert sum(screen_counts.values()) == 39_870
    assert screen_counts == Counter({1: 2832, 2: 27568, 3: 696, 4: 1084, 6: 1294, 7: 3260, 8: 3136}), screen_counts
    all_summary = summarize(records)
    assert sum(all_summary["cross"].values()) == 39_870
    assert sum(v for k, v in all_summary["cross"].items() if k.split(",")[0] == "different") == all_summary["target_disagreement"]
    assert sum(v for k, v in all_summary["cross"].items() if k.split(",")[1] == "different") == all_summary["policy_disagreement"]
    assert sum(v for k, v in all_summary["cross"].items() if k.split(",")[2] == "different") == all_summary["pred_q_disagreement"]

    result = {"screen_mapping": SCREENS, "rows": m0_rows, "groups": len(records),
              "screen_counts": dict(sorted(screen_counts.items())), "all": all_summary}
    for screen in SCREENS:
        result[SCREENS[screen]] = summarize([r for r in records if r["screen"] == screen])
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"rows": m0_rows, "groups": len(records), "screen_counts": dict(sorted(screen_counts.items())), "all": all_summary}, sort_keys=True))


if __name__ == "__main__":
    main()