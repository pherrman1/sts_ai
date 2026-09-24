#!/usr/bin/env python3
"""Select one Lizard-tail pair target per source from precombat CTM risk only."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools import combat_transition_composed as composed
from tools.combat_transition_contract import ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256, validate_state
from tools.combat_predictor_input_contract import FIELD_SCHEMA_HASH, SCHEMA_VERSION as INPUT_SCHEMA, validate_predictor_input


BANDS = (
    ("p10_20", 0.10, 0.20),
    ("p20_35", 0.20, 0.35),
    ("p35_55", 0.35, 0.55),
    ("p55_plus", 0.55, 1.0000000001),
    ("p00_10_fallback", 0.0, 0.10),
)


def band_for(p_death: float) -> str | None:
    for name, lo, hi in BANDS:
        if lo <= p_death < hi:
            return name
    return None


def stable_rank(seed: int, text: str) -> str:
    return hashlib.sha256(f"{seed}:{text}".encode("utf-8")).hexdigest()


def select(manifest_path: Path, output_path: Path, *, selection_seed: int,
           per_band: int, target_count: int, min_target_count: int = 100) -> dict:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    data = manifest.get("csv", {})
    input_path = Path(data.get("path", ""))
    if not input_path.is_absolute() or not input_path.is_file():
        raise ValueError("candidate JSONL path missing or not absolute")
    if sha256(input_path) != data.get("sha256"):
        raise ValueError("candidate JSONL hash mismatch")
    integrity = manifest.get("integrity", {})
    seed_spec = manifest.get("seedSpec", {})
    if (integrity.get("requestedSeeds") != seed_spec.get("count")
            or integrity.get("completedSeeds") != seed_spec.get("count")
            or integrity.get("quarantinedSeeds") != 0):
        raise ValueError("candidate source cohort is incomplete or quarantined")
    if (manifest.get("schemaVersion") != SCHEMA_VERSION
            or manifest.get("rowSchemaVersion") != ROW_SCHEMA_VERSION
            or manifest.get("predictorInputSchemaVersion") != INPUT_SCHEMA
            or manifest.get("predictorInputFieldSchemaHash") != FIELD_SCHEMA_HASH
            or manifest.get("format") != "jsonl"):
        raise ValueError("candidate manifest schema mismatch")
    if not 1 <= target_count <= 128 or per_band < 1:
        raise ValueError("target count must be 1..128 and each band quota positive")

    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels("cuda" if torch.cuda.is_available() else "cpu")
    candidate_counts: Counter[str] = Counter()
    candidate_sources: dict[str, set[int]] = defaultdict(set)
    seed_sources: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    seen_fights: set[tuple[int, int]] = set()
    rows_read = 0
    for line_number, line in enumerate(input_path.read_text().splitlines(), 1):
        if not line:
            continue
        rows_read += 1
        row = json.loads(line)
        # Selection intentionally reads no combat outcome, post-state, final HP,
        # or treatment result. Validity only excludes quarantined source rows.
        if row.get("runValid") is not True:
            continue
        source_seed = int(row["sourceSeed"])
        fight_idx = int(row["fightIdx"])
        if not int(seed_spec["start"]) <= source_seed < int(seed_spec["start"]) + int(seed_spec["count"]):
            raise ValueError("candidate source seed is outside the manifest range")
        key = (source_seed, fight_idx)
        if key in seen_fights:
            raise ValueError(f"duplicate source fight at line {line_number}")
        seen_fights.add(key)
        predictor_input = row["predictorInput"]
        pre_state = row["transition"]["pre"]
        validate_predictor_input(predictor_input)
        validate_state(pre_state, "candidate.pre")
        globals_ = predictor_input["globals"]
        if (int(globals_["curHp"]) != int(pre_state["curHp"])
                or int(globals_["maxHp"]) != int(pre_state["maxHp"])):
            raise ValueError("candidate visible and persistent precombat HP disagree")
        relic_ids = {int(relic["relicId"]) for relic in predictor_input["relics"]}
        if relic_ids.intersection({composed.base._RELIC_IDS["MARK_OF_THE_BLOOM"], 35}):
            continue
        inputs = models.encode_visible(predictor_input)
        p_death = 1.0 - models.survival(inputs)
        name = band_for(p_death)
        if name is None:
            name = "p00_10_fallback"
        candidate_counts[name] += 1
        candidate_sources[name].add(source_seed)
        input_json = json.dumps(predictor_input, sort_keys=True, separators=(",", ":"))
        pre_json = json.dumps(pre_state, sort_keys=True, separators=(",", ":"))
        target = {
            "sourceSeed": source_seed,
            "fightIdx": fight_idx,
            "riskBand": name,
            "pDeath": p_death,
            "predictorInputSha256": hashlib.sha256(input_json.encode("utf-8")).hexdigest(),
            "preStateSha256": hashlib.sha256(pre_json.encode("utf-8")).hexdigest(),
            "predictorInput": predictor_input,
            "preState": pre_state,
        }
        target["selectionRank"] = stable_rank(
            selection_seed, f"{source_seed}:{fight_idx}:{name}")
        seed_sources[source_seed][name].append(target)

    if rows_read != int(integrity.get("rows", -1)):
        raise ValueError("candidate JSONL row count differs from manifest")

    for by_band in seed_sources.values():
        for entries in by_band.values():
            entries.sort(key=lambda value: value["selectionRank"])

    selected: list[dict] = []
    used_sources: set[int] = set()
    selected_by_band: Counter[str] = Counter()
    # First meet equal quotas where the discovery pass has enough distinct
    # sources, while guaranteeing that each source contributes at most once.
    for name, _, _ in BANDS[:4]:
        available = [source for source in sorted(seed_sources)
                     if name in seed_sources[source] and source not in used_sources]
        available.sort(key=lambda source: stable_rank(selection_seed, f"{source}:{name}"))
        for source in available[:min(per_band, target_count - len(selected))]:
            target = dict(seed_sources[source][name][0])
            target.pop("selectionRank")
            selected.append(target)
            used_sources.add(source)
            selected_by_band[name] += 1
            if len(selected) >= target_count:
                break
        if len(selected) >= target_count:
            break

    # Redistribute unfilled band quotas round-robin across remaining target
    # bands. This adaptation depends only on precombat predictions/availability.
    fill_names = [name for name, _, _ in BANDS]
    fill_cursor = 0
    while len(selected) < target_count:
        progressed = False
        for offset in range(len(fill_names)):
            name = fill_names[(fill_cursor + offset) % len(fill_names)]
            available = [source for source in sorted(seed_sources)
                         if name in seed_sources[source] and source not in used_sources]
            available.sort(key=lambda source: stable_rank(
                selection_seed, f"fill:{name}:{source}"))
            if available:
                source = available[0]
                target = dict(seed_sources[source][name][0])
                target.pop("selectionRank")
                selected.append(target)
                used_sources.add(source)
                selected_by_band[name] += 1
                fill_cursor = (fill_cursor + offset + 1) % len(fill_names)
                progressed = True
                break
        if not progressed:
            break

    if len(selected) < min_target_count:
        raise ValueError(f"only {len(selected)} sources have a target-band combat; need at least {min_target_count}")
    selected.sort(key=lambda target: target["sourceSeed"])
    if [target["sourceSeed"] for target in selected] != sorted(
            target["sourceSeed"] for target in selected):
        raise AssertionError("selected source order is not deterministic")

    result = {
        "schema": "lizard_tail_risk_target_selection_v1",
        "selectionPolicy": "precombat_no_tail_ctm_death_probability_only; never read outcomes or post-states",
        "candidateManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "candidateJsonlSha256": data["sha256"],
        "candidateProducerGitSha": manifest["producerGitSha"],
        "candidateProducerExecutableSha256": manifest["producerExecutableSha256"],
        "candidateSeedSpec": seed_spec,
        "selectionSeed": selection_seed,
        "riskModel": "frozen ordinary CTM survival head; pDeath=1-P(win)",
        "riskModelHashes": models.hashes,
        "riskModelDevice": str(models.device),
        "torchVersion": str(models.torch.__version__),
        "bands": [{"name": name, "lowerInclusive": lo, "upperExclusive": hi,
                   "availableFights": int(candidate_counts[name]),
                   "availableSources": len(candidate_sources[name]),
                   "selectedSources": int(selected_by_band[name])}
                  for name, lo, hi in BANDS],
        "targetCount": len(selected),
        "targets": selected,
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection-seed", type=int, default=20260924)
    parser.add_argument("--per-band", type=int, default=32)
    parser.add_argument("--target-count", type=int, default=128)
    parser.add_argument("--min-target-count", type=int, default=100)
    args = parser.parse_args()
    result = select(args.manifest, args.output, selection_seed=args.selection_seed,
                    per_band=args.per_band, target_count=args.target_count,
                    min_target_count=args.min_target_count)
    print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=2))


if __name__ == "__main__":
    main()
