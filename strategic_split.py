"""Leakage-safe deterministic splits for strategic decision datasets."""

import numpy as np

SPLIT_VERSION = "seed-v1"


def seed_disjoint_split(seeds, train_fraction=0.8, random_seed=0):
    """Return row/group masks for a deterministic whole-seed split.

    ``seeds`` is one seed value per CSV row.  The returned row mask is suitable
    for normalization and validation; all decisions from a run stay together.
    The decision-group mask is returned separately so callers can keep their
    existing group-ordered batching and per-decision metrics.
    """
    row_seeds = np.asarray(seeds, dtype=np.int64)
    unique = np.unique(row_seeds)
    if unique.size < 2:
        raise ValueError("need at least two unique seeds for a held-out split")
    order = np.random.default_rng(random_seed).permutation(unique.size)
    cut = min(max(1, int(train_fraction * unique.size)), unique.size - 1)
    train_seeds = unique[order[:cut]]
    val_seeds = unique[order[cut:]]
    train_rows = np.isin(row_seeds, train_seeds)
    if np.intersect1d(train_seeds, val_seeds).size:
        raise AssertionError("seed split is not disjoint")
    if not np.all(np.isin(row_seeds[train_rows], train_seeds)):
        raise AssertionError("train row mask contains an unknown seed")
    return train_rows, train_seeds, val_seeds
