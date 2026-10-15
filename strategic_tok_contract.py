"""Shared Python side of the honest V4 token-state feature contract."""

import numpy as np

NRAW = 36
NGLOB = 42
NSTATE = 1017

_RAW_POSITIONS = {
    **{i: name for i, name in enumerate((
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize",
        "potionChance", "cardRarityFactor", "blueKey", "greenKey", "redKey",
        "potionCount", "potionCapacity", "bossId"))},
    **{23 + i: name for i, name in enumerate((
        "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure",
        "bottledAtkId", "bottledSkillId", "bottledPowId"))},
    **{1005 + i: name for i, name in enumerate((
        "fmDElite", "fmDRest", "fmDShop", "fmDBoss", "fmCElite", "fmCRest",
        "fmCShop", "fmCEvent", "fmCMonster", "fmCTreasure", "curMapX", "curMapY"))},
}


def make_layout(state_cols):
    """Validate the rich-state order and return reusable named positions."""
    cols = list(state_cols)
    if len(cols) != NSTATE:
        raise ValueError(f"expected {NSTATE} rich state columns, got {len(cols)}")
    for pos, name in _RAW_POSITIONS.items():
        if cols[pos] != name:
            raise ValueError(f"state_cols[{pos}] = {cols[pos]!r}, expected {name!r}")
    return {name: i for i, name in enumerate(cols)}


def build_globals(raw, layout):
    """Build the 42 raw/derived globals from rows in rich-column order."""
    c = np.asarray(raw)
    if c.ndim != 2 or c.shape[1] != NSTATE:
        raise ValueError(f"expected rows shaped (N,{NSTATE}), got {c.shape}")
    def col(name):
        return c[:, layout[name]]

    g = np.zeros((len(c), NGLOB), dtype=np.float64)
    g[:, :14] = c[:, :14]
    g[:, 14] = col("bossId")
    g[:, 15:24] = c[:, 23:32]
    g[:, 24:34] = c[:, 1005:1015]
    g[:, 34:36] = c[:, 1015:1017]
    hp = col("curHp")
    mx = np.maximum(col("maxHp"), 1.0)
    g[:, NRAW + 0] = hp / mx
    g[:, NRAW + 1] = col("maxHp") - hp
    g[:, NRAW + 2] = (col("potionCount") < col("potionCapacity")).astype(np.float64)
    g[:, NRAW + 3] = (col("gold") >= 75.0).astype(np.float64)
    g[:, NRAW + 4] = ((col("fmCElite") > 0)
                       & ~((col("blueKey") > 0) & (col("greenKey") > 0)
                           & (col("redKey") > 0))).astype(np.float64)
    g[:, NRAW + 5] = (col("fmDBoss") <= 3.0).astype(np.float64)
    return g
