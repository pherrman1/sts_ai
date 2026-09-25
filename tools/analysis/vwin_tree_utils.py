#!/usr/bin/env python3
"""Shared parser and evaluators for the compact native v_win tree format."""
from __future__ import annotations

import numpy as np


def load_trees(path):
    """Load compact trees without changing the established split semantics."""
    feats = []
    logistic = 0
    base_score = 0.0
    trees = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "feat":
                feats.append(parts[1])
            elif parts[0] == "logistic":
                logistic = int(parts[1])
            elif parts[0] == "base_score":
                base_score = float(parts[1])
            elif parts[0] == "tree":
                n = int(parts[2])
                nodes = []
                for _ in range(n):
                    p = f.readline().split()
                    if p[0] == "L":
                        nodes.append(("L", float(p[1])))
                    else:
                        nodes.append(("S", int(p[1]), float(p[2]),
                                      int(p[3]), int(p[4])))
                trees.append(nodes)
    base_margin = (float(np.log(base_score / (1.0 - base_score)))
                   if logistic else base_score)
    return feats, trees, logistic, base_score, base_margin


def predict_row(vec, trees, logistic, base_margin):
    """Mirror the existing Python checker and native < split comparison."""
    acc = base_margin
    for nodes in trees:
        idx = 0
        while nodes[idx][0] != "L":
            _, fi, thr, yes, no = nodes[idx]
            idx = yes if vec[fi] < thr else no
        acc += nodes[idx][1]
    return 1.0 / (1.0 + np.exp(-acc)) if logistic else acc


def predict_rows(matrix, trees, logistic, base_margin):
    """Vectorized row evaluator; tree routing is identical to predict_row."""
    x = np.asarray(matrix, dtype=np.float32)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    margin = np.full(x.shape[0], base_margin, dtype=np.float64)
    all_rows = np.arange(x.shape[0], dtype=np.int64)
    for nodes in trees:
        stack = [(0, all_rows)]
        while stack:
            node_idx, rows = stack.pop()
            node = nodes[node_idx]
            if node[0] == "L":
                margin[rows] += node[1]
                continue
            _, fi, thr, yes, no = node
            go_yes = x[rows, fi] < thr
            if np.any(go_yes):
                stack.append((yes, rows[go_yes]))
            if np.any(~go_yes):
                stack.append((no, rows[~go_yes]))
    if not logistic:
        return margin
    out = np.empty_like(margin)
    positive = margin >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-margin[positive]))
    exp_margin = np.exp(margin[~positive])
    out[~positive] = exp_margin / (1.0 + exp_margin)
    return out


def split_counts(trees, feats):
    """Count serialized split occurrences by feature index and model name."""
    counts = np.zeros(len(feats), dtype=np.int64)
    for nodes in trees:
        for node in nodes:
            if node[0] == "S":
                counts[node[1]] += 1
    return {name: int(counts[i]) for i, name in enumerate(feats)}
