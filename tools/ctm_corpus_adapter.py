#!/usr/bin/env python3
"""Assemble a sharded CTM transition corpus into the layout `audit` expects.

The #418 Path B corpus was generated in many seed units on several machines
(`one_combat combattransitiongen` / `combattransitionforcedgen`), and a
validator wrote an index of the unit files that cover each planned unit.
`combat_transition_model_experiment.py audit` instead wants one merged JSONL
with one contiguous seedSpec plus shard manifests under `blocks/`.  This
adapter builds that layout for one forced-setup scope without changing audit
semantics: every shard manifest is the unit's own manifest with only
`csv.path` rewritten to the local file, and seeds the generator skipped
(STALLED) are listed as quarantined in the merged manifest.

usage: ctm_corpus_adapter.py assemble --index INDEX.json --corpus-root DIR --scope none --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools.combat_transition_contract import validate_manifest
except ModuleNotFoundError:  # direct invocation from the tools directory
    from combat_transition_contract import validate_manifest

SCHEMA = "ctm_corpus_adapter_v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def assemble(index_path: Path, corpus_root: Path, scope: str, out: Path) -> dict:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("errors"):
        raise ValueError(f"corpus index has {len(index['errors'])} validation errors")
    units = [u for u in index["units"] if u["setup"] == scope]
    if not units:
        raise ValueError(f"no units for scope {scope!r}")
    stalled = sorted(int(seed) for seed, (tag, _reason, _part) in index["stalled"].items()
                     if any(u["unit"] == tag for u in units))
    files = sorted((f for u in units for f in u["files"]), key=lambda f: int(f["seeds"]["start"]))
    lo = min(int(u["unit"].rsplit("-", 2)[1]) for u in units)
    hi = max(int(u["unit"].rsplit("-", 2)[1]) + int(u["unit"].rsplit("-", 2)[2]) for u in units)
    blocks = out / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    teacher = shared = None
    covered: set[int] = set()
    rows = 0
    merged = out / "corpus.jsonl"
    with merged.open("wb") as sink:
        for f in files:
            data = (corpus_root / f["path"]).resolve()
            manifest_path = Path(str(data) + ".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = sha256(data)
            if digest != f["sha256"] or digest != manifest["csv"]["sha256"]:
                raise ValueError(f"{data}: SHA256 disagrees with index or manifest")
            if manifest.get("forcedSetup", "none") != scope:
                raise ValueError(f"{data}: forcedSetup {manifest.get('forcedSetup')!r} is not {scope!r}")
            if manifest["integrity"]["quarantinedSeeds"]:
                raise ValueError(f"{data}: unit has quarantined seeds")
            ident = {k: manifest[k] for k in ("schemaVersion", "rowSchemaVersion",
                                              "predictorInputSchemaVersion", "predictorInputFieldSchemaHash",
                                              "format", "producerGitSha", "producerExecutableSha256")}
            if teacher is None:
                teacher, shared = manifest["combatTeacher"], ident
            elif _canonical(manifest["combatTeacher"]) != _canonical(teacher) or ident != shared:
                raise ValueError(f"{data}: mixed producer/teacher identity")
            spec = manifest["seedSpec"]
            seeds = set(range(int(spec["start"]), int(spec["start"]) + int(spec["count"])))
            if seeds & covered:
                raise ValueError(f"{data}: overlapping seeds")
            covered |= seeds
            local = dict(manifest)
            local["csv"] = dict(manifest["csv"], path=str(data))
            local["ctmCorpusAdapter"] = {"originalManifestSha256": sha256(manifest_path),
                                         "originalCsvPath": manifest["csv"]["path"]}
            validate_manifest(local, verify_data=False)
            (blocks / (data.name + ".manifest.json")).write_text(
                json.dumps(local, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            with data.open("rb") as src:
                for line in src:
                    sink.write(line); rows += 1
    expected = set(range(lo, hi)) - set(stalled)
    if covered != expected:
        raise ValueError(f"scope {scope}: covered seeds do not equal the planned range minus stalled seeds")
    merged_manifest = dict(shared)
    merged_manifest.update({
        "combatTeacher": teacher,
        "seedSpec": {"start": lo, "count": hi - lo},
        "csv": {"path": str(merged.resolve()), "sha256": sha256(merged)},
        "integrity": {"requestedSeeds": hi - lo, "completedSeeds": len(covered),
                      "quarantinedSeeds": len(stalled), "rows": rows},
        "quarantined": stalled,
        "forcedSetup": scope,
        "ctmCorpusAdapter": {"schema": SCHEMA, "indexSha256": sha256(index_path),
                             "units": len(units), "files": len(files)},
    })
    validate_manifest(merged_manifest)
    (out / "corpus.jsonl.manifest.json").write_text(
        json.dumps(merged_manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"scope": scope, "units": len(units), "files": len(files), "rows": rows,
               "seedSpec": merged_manifest["seedSpec"], "quarantined": stalled,
               "corpusSha256": merged_manifest["csv"]["sha256"]}
    print(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("assemble")
    p.add_argument("--index", required=True, type=Path)
    p.add_argument("--corpus-root", required=True, type=Path)
    p.add_argument("--scope", required=True,
                   choices=("none", "ritual_writhing", "high_maxhp", "lizard_fairy", "lizard_brew"))
    p.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    assemble(args.index, args.corpus_root, args.scope, args.out)


if __name__ == "__main__":
    main()
