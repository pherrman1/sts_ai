"""Row-layout helpers for the V4 strategic token-state cache."""

from __future__ import annotations

import numpy as np


# Bump this whenever the serialized row layout or raw-to-grouped mapping changes.
STATE_CACHE_LAYOUT_VERSION = "raw-to-grouped-v2"


def build_raw_to_grouped(sorted_raw_rows: np.ndarray,
                         grouped_order: np.ndarray) -> np.ndarray:
    """Map each raw CSV row index to its final grouped-cache row index.

    ``sorted_raw_rows`` gives raw CSV row IDs in the order of the sorted label
    dataframe. ``grouped_order`` maps final grouped row positions back into
    that dataframe. The returned array is indexed by raw row ID.
    """
    sorted_raw_rows = np.asarray(sorted_raw_rows, dtype=np.int64)
    grouped_order = np.asarray(grouped_order, dtype=np.int64)
    nrows = len(sorted_raw_rows)
    if sorted_raw_rows.ndim != 1 or grouped_order.ndim != 1:
        raise ValueError("row mappings must be one-dimensional")
    if len(grouped_order) != nrows:
        raise ValueError("group order length differs from sorted raw row count")
    expected = np.arange(nrows, dtype=np.int64)
    if not np.array_equal(np.sort(sorted_raw_rows), expected):
        raise ValueError("sorted raw row IDs must be a permutation of all CSV rows")
    if not np.array_equal(np.sort(grouped_order), expected):
        raise ValueError("group order must be a permutation of sorted dataframe rows")

    raw_rows_in_grouped_order = sorted_raw_rows[grouped_order]
    raw_to_grouped = np.empty(nrows, dtype=np.int64)
    raw_to_grouped[raw_rows_in_grouped_order] = expected
    return raw_to_grouped


def train_mask_for_raw_chunk(grouped_train_rows: np.ndarray,
                             raw_to_grouped: np.ndarray,
                             raw_lo: int,
                             raw_hi: int) -> np.ndarray:
    """Select normalization rows from a raw-order CSV chunk."""
    return np.asarray(grouped_train_rows, dtype=bool)[raw_to_grouped[raw_lo:raw_hi]]


def write_raw_state_chunk(state_mem: np.ndarray,
                          raw_to_grouped: np.ndarray,
                          raw_lo: int,
                          state_rows: np.ndarray) -> None:
    """Scatter one raw-order CSV chunk into final grouped cache order."""
    raw_hi = raw_lo + len(state_rows)
    row_ids = raw_to_grouped[raw_lo:raw_hi]
    if len(row_ids) != len(state_rows):
        raise ValueError("raw state chunk extends past the row mapping")
    state_mem[row_ids] = state_rows


def add_layout_version(fingerprint, version: str = STATE_CACHE_LAYOUT_VERSION) -> None:
    """Bind a cache fingerprint to its row-layout schema."""
    fingerprint.update(b"\0state-cache-layout\0")
    fingerprint.update(version.encode("ascii"))
