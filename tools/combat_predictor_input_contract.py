#!/usr/bin/env python3
"""Strict validator for combat_predictor_input_v1 JSON objects."""

import argparse
import json
import math
from pathlib import Path

SCHEMA_VERSION = "combat_predictor_input_v1"
FIELD_SCHEMA = (
    "globals.characterClass:int;globals.ascension:int;globals.act:int;"
    "globals.floor:int;globals.curHp:int;globals.maxHp:int;globals.gold:int;"
    "globals.encounter:int;globals.roomClass:int;globals.lastRoom:int;"
    "globals.potionCount:int;globals.potionCapacity:int;"
    "globals.potionKeepValue:float;globals.isBurningElite:bool;"
    "cards[].cardId:int;cards[].upgraded:bool;cards[].misc:int;"
    "cards[].bottleBinding:int;relics[].relicId:int;relics[].data:int;"
    "relics[].orderIndex:int;potions[].slot:int;potions[].potionId:int"
)


def _fnv1a64(value: str) -> str:
    result = 1469598103934665603
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 1099511628211) & ((1 << 64) - 1)
    return f"{result:016x}"


FIELD_SCHEMA_HASH = _fnv1a64(FIELD_SCHEMA)
GLOBAL_KEYS = {
    "characterClass", "ascension", "act", "floor", "curHp", "maxHp", "gold",
    "encounter", "roomClass", "lastRoom", "potionCount", "potionCapacity",
    "potionKeepValue", "isBurningElite",
}
CARD_KEYS = {"cardId", "upgraded", "misc", "bottleBinding"}
RELIC_KEYS = {"relicId", "data", "orderIndex"}
POTION_KEYS = {"slot", "potionId"}
ROOT_KEYS = {"schemaVersion", "fieldSchemaHash", "globals", "cards", "relics", "potions"}


def _integer(value, label):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value, label):
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} keys mismatch")


def validate_predictor_input(value: dict) -> dict:
    _keys(value, ROOT_KEYS, "predictor input")
    if value["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("unsupported predictor input schema")
    if value["fieldSchemaHash"] != FIELD_SCHEMA_HASH:
        raise ValueError("predictor input field schema hash mismatch")

    globals_value = value["globals"]
    _keys(globals_value, GLOBAL_KEYS, "globals")
    for name in GLOBAL_KEYS - {"potionKeepValue", "isBurningElite"}:
        _integer(globals_value[name], f"globals.{name}")
    if (not isinstance(globals_value["potionKeepValue"], (int, float))
            or isinstance(globals_value["potionKeepValue"], bool)
            or not math.isfinite(globals_value["potionKeepValue"])):
        raise ValueError("globals.potionKeepValue must be finite")
    _boolean(globals_value["isBurningElite"], "globals.isBurningElite")

    cards = value["cards"]
    if not isinstance(cards, list):
        raise ValueError("cards must be an array")
    for index, card in enumerate(cards):
        _keys(card, CARD_KEYS, f"cards[{index}]")
        for name in ("cardId", "misc", "bottleBinding"):
            _integer(card[name], f"cards[{index}].{name}")
        if card["bottleBinding"] not in {-1, 0, 1, 2}:
            raise ValueError(f"cards[{index}].bottleBinding is invalid")
        _boolean(card["upgraded"], f"cards[{index}].upgraded")
    if cards != sorted(cards, key=lambda c: (c["cardId"], c["upgraded"], c["misc"], c["bottleBinding"])):
        raise ValueError("cards are not in canonical order")

    relics = value["relics"]
    if not isinstance(relics, list):
        raise ValueError("relics must be an array")
    for index, relic in enumerate(relics):
        _keys(relic, RELIC_KEYS, f"relics[{index}]")
        _integer(relic["relicId"], f"relics[{index}].relicId")
        _integer(relic["data"], f"relics[{index}].data")
        if _integer(relic["orderIndex"], f"relics[{index}].orderIndex") != index:
            raise ValueError("relic orderIndex does not preserve acquisition order")

    potions = value["potions"]
    if not isinstance(potions, list) or len(potions) != 5:
        raise ValueError("potions must contain exactly five explicit slots")
    for index, potion in enumerate(potions):
        _keys(potion, POTION_KEYS, f"potions[{index}]")
        if _integer(potion["slot"], f"potions[{index}].slot") != index:
            raise ValueError("potion slots must preserve slot order")
        _integer(potion["potionId"], f"potions[{index}].potionId")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    validate_predictor_input(json.loads(args.input_json.read_text(encoding="utf-8")))
    print(json.dumps({"schemaVersion": SCHEMA_VERSION,
                      "fieldSchemaHash": FIELD_SCHEMA_HASH}, sort_keys=True))


if __name__ == "__main__":
    main()
