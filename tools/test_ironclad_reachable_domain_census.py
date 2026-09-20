#!/usr/bin/env python3
"""Focused invariants for the source-backed Ironclad domain census."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.ironclad_reachable_domain_census import ROOT, build_census


class IroncladReachableDomainCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.census = build_census()

    def test_every_domain_is_an_exact_partition(self) -> None:
        allowed = {"REACHABLE", "PROVABLY_UNREACHABLE", "UNKNOWN"}
        for name, domain in self.census["domains"].items():
            entries = domain["entries"]
            self.assertEqual(
                [entry["id"] for entry in entries],
                list(range(domain["canonicalDomainSize"])),
                name,
            )
            self.assertTrue(all(entry["classification"] in allowed for entry in entries), name)
            self.assertEqual(sum(domain["counts"].values()), len(entries), name)

    def test_census_is_deterministic(self) -> None:
        first = json.dumps(self.census, sort_keys=True)
        second = json.dumps(build_census(), sort_keys=True)
        self.assertEqual(first, second)

    def test_no_other_character_pool_row_is_reachable(self) -> None:
        cards = self.census["domains"]["cards"]
        self.assertFalse(
            any(
                entry["classification"] == "REACHABLE"
                and entry.get("poolColor") == "OTHER_CHARACTER"
                for entry in cards["entries"]
            )
        )

    def test_prismatic_shard_is_not_a_supported_edge(self) -> None:
        relics = self.census["domains"]["relics"]
        self.assertTrue(relics["prismaticShardExcluded"])
        self.assertTrue(relics["prismaticShardInSourcePool"])
        self.assertFalse(relics["prismaticShardInSupportedEdges"])
        shard = next(entry for entry in relics["entries"] if entry["enumName"] == "PRISMATIC_SHARD")
        self.assertEqual(shard["classification"], "PROVABLY_UNREACHABLE")
        source = (Path(ROOT) / "src/sim/search/OocSemanticAction.cpp").read_text(encoding="utf-8")
        self.assertIn("isSupportedAutonomousOocAction", source)
        self.assertIn("gc.info.shop.relics[index] != RelicId::PRISMATIC_SHARD", source)

    def test_generated_cards_require_reachable_generators(self) -> None:
        cards = {entry["enumName"]: entry for entry in self.census["domains"]["cards"]["entries"]}
        self.assertEqual(cards["MIRACLE"]["classification"], "UNKNOWN")
        self.assertEqual(cards["SHIV"]["classification"], "UNKNOWN")
        self.assertEqual(cards["NECRONOMICURSE"]["classification"], "UNKNOWN")
        self.assertEqual(cards["RITUAL_DAGGER"]["classification"], "REACHABLE")
        self.assertIn("Event::THE_NEST", cards["RITUAL_DAGGER"]["evidence"][0]["symbol"])

    def test_disabled_colosseum_encounters_are_not_reachable(self) -> None:
        encounters = {entry["enumName"]: entry for entry in self.census["domains"]["encounters"]["entries"]}
        for name in ("COLOSSEUM_EVENT_SLAVERS", "COLOSSEUM_EVENT_NOBS"):
            self.assertEqual(encounters[name]["classification"], "PROVABLY_UNREACHABLE")
            self.assertEqual(encounters[name]["reasonClass"], "disabled_event_path")

    def test_reachable_encounter_spawns_are_closed_over(self) -> None:
        monsters = {entry["enumName"]: entry for entry in self.census["domains"]["monsters"]["entries"]}
        for name in ("BRONZE_ORB", "TORCH_HEAD"):
            self.assertEqual(monsters[name]["classification"], "REACHABLE")

    def test_model_capacity_has_source_contracts(self) -> None:
        contracts = self.census["sourceContracts"]
        self.assertEqual(contracts["combatFeatureContract"], 1766)
        self.assertEqual(contracts["oocTrainableFloatParameterTotalExcludingNormalizationBuffers"], 199690)
        self.assertGreaterEqual(len(contracts["checkedPatterns"]), 10)

    def test_domain_drift_is_retained_as_unknown(self) -> None:
        for domain_name, expected_names in {
            "cards": {"UNDEFINED_371"},
            "potions": {"UNDEFINED_44", "UNDEFINED_45", "UNDEFINED_46", "UNDEFINED_47"},
        }.items():
            domain = self.census["domains"][domain_name]
            by_name = {entry["enumName"]: entry for entry in domain["entries"]}
            for name in expected_names:
                self.assertIn(name, by_name)
                self.assertEqual(by_name[name]["classification"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
