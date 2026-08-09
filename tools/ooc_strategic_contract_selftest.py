#!/usr/bin/env python3
"""Small regression test for the honest V4 Python feature contract."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from strategic_tok_contract import build_globals, make_layout


def main():
    names = [
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize",
        "potionChance", "cardRarityFactor", "blueKey", "greenKey", "redKey",
        "potionCount", "potionCapacity", "bossId", "nextEliteId", "nextFight0",
        "nextFight1", "nextFight2", "remElites", "remFights", "monOffset",
        "eliteOffset", "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster",
        "pvTreasure", "bottledAtkId", "bottledSkillId", "bottledPowId",
    ]
    names += [f"d{i}" for i in range(372)]
    names += [f"u{i}" for i in range(372)]
    names += [f"r{i}" for i in range(181)]
    names += [f"pot{i}" for i in range(48)]
    names += ["fmDElite", "fmDRest", "fmDShop", "fmDBoss", "fmCElite",
              "fmCRest", "fmCShop", "fmCEvent", "fmCMonster", "fmCTreasure",
              "curMapX", "curMapY"]
    assert len(names) == 1017
    layout = make_layout(names)
    row = np.zeros((1, len(names)), dtype=np.float64)
    row[0, layout["curHp"]] = 30
    row[0, layout["maxHp"]] = 50
    row[0, layout["gold"]] = 75
    row[0, layout["potionCount"]] = 1
    row[0, layout["potionCapacity"]] = 2
    row[0, layout["fmCElite"]] = 2
    row[0, layout["fmDBoss"]] = 3
    row[0, layout["bossId"]] = 7
    row[0, layout["pvShop"]] = 4
    row[0, layout["curMapX"]] = 5
    row[0, layout["curMapY"]] = 6
    got = build_globals(row, layout)[0]
    hidden = row.copy()
    for name in ("nextEliteId", "nextFight0", "nextFight1", "nextFight2",
                 "remElites", "remFights", "monOffset", "eliteOffset"):
        hidden[0, layout[name]] = 999
    assert np.array_equal(got, build_globals(hidden, layout)[0])
    assert got[14] == 7 and got[15] == 4 and got[24] == 0
    assert np.array_equal(got[24:36], [0, 0, 0, 3, 2, 0, 0, 0, 0, 0, 5, 6])
    assert np.array_equal(got[36:], [0.6, 20, 1, 1, 1, 1])
    print("ooc strategic feature contract self-test: PASS")


if __name__ == "__main__":
    main()
