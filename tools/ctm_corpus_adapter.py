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
(STALLED) are listed as quarantined in the merged manifest. In the act4_fork
scope, seeds whose run ended before the Act-3 boss are counted in
`integrity.noAct4Seeds`, not quarantined.

`union` then joins assembled scopes into one corpus for the Phase-1 and
Phase-2 chains, dropping rows outside production candidate support (see
`union`). `audit` validates a union through each scope's shard manifests.

usage:
  ctm_corpus_adapter.py assemble --index INDEX.json --corpus-root DIR --scope none --out DIR
  ctm_corpus_adapter.py union --scope-dir none=DIR [--scope-dir high_maxhp=DIR ...] --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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
    rows = no_act4 = 0
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
            no_act4 += int(manifest["integrity"].get("noAct4Seeds", 0))
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
        "integrity": {"requestedSeeds": hi - lo, "completedSeeds": len(covered) - no_act4,
                      "quarantinedSeeds": len(stalled), "rows": rows},
        "quarantined": stalled,
        "forcedSetup": scope,
        "ctmCorpusAdapter": {"schema": SCHEMA, "indexSha256": sha256(index_path),
                             "units": len(units), "files": len(files)},
    })
    if scope == "act4_fork":
        merged_manifest["integrity"]["noAct4Seeds"] = no_act4
    validate_manifest(merged_manifest)
    (out / "corpus.jsonl.manifest.json").write_text(
        json.dumps(merged_manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"scope": scope, "units": len(units), "files": len(files), "rows": rows,
               "seedSpec": merged_manifest["seedSpec"], "quarantined": stalled,
               "corpusSha256": merged_manifest["csv"]["sha256"]}
    print(json.dumps(summary, indent=1))
    return summary


SCOPES = ("none", "ritual_writhing", "high_maxhp", "lizard_fairy", "lizard_brew", "act4_fork")


WIN = 1


def label_reasons(transition, max_hp_delta_values) -> list:
    """Labels the frozen heads cannot represent. The maxHP head is pinned to the
    production delta classes (the C++ loader requires them), so a winning row
    with any other maxHP gain cannot be trained on."""
    if int(transition["combatOutcome"]) != WIN:
        return []
    delta = int(transition["post"]["maxHp"]) - int(transition["pre"]["maxHp"])
    return [] if delta in set(int(v) for v in max_hp_delta_values) else ["max_hp_delta_domain"]


def production_support_reasons():
    """Rows the frozen near-full chain can hold: production candidate-contract support
    and a winning maxHP gain the frozen maxHP head can represent."""
    try:
        from tools import combat_transition_composed as c
        from tools import combat_transition_near_full_support as support
    except ModuleNotFoundError:  # direct invocation from the tools directory
        import combat_transition_composed as c
        import combat_transition_near_full_support as support
    models = c.FrozenModels("cpu")

    def reasons(row):
        transition = row["transition"]
        if transition is None or not row["runValid"]:
            return ["invalid_row"]
        with support.candidate_contract():
            rejected = c.full_support_reasons(transition["pre"], row["predictorInput"], models)
        return rejected or label_reasons(transition, models.delta_values)
    return reasons


def union(scope_dirs: dict[str, Path], out: Path, reasons=None) -> dict:
    """Concatenate assembled scopes into one corpus the Phase-2 chain can prepare.

    Scopes are written in ascending seed order (their seedSpec starts; the #418
    A0 seed plan already follows SCOPES order, the §443 A20 plan does not).
    Rows the frozen support predicate rejects are dropped, so every kept row
    is a candidate-supported row and later caches satisfy ids == arange(N).
    `row_scopes.json` records each scope's row range so gates can report
    forced rows separately from the main corpus.
    """
    if out.exists():
        raise ValueError("refusing overwrite")
    if not scope_dirs or set(scope_dirs) - set(SCOPES):
        raise ValueError(f"scopes must be a subset of {SCOPES}")
    reasons = reasons or production_support_reasons()
    out.mkdir(parents=True)
    merged = out / "corpus.jsonl"
    teacher = shared = None
    ranges, dropped, seeds, quarantined = {}, {}, set(), []
    rows = 0
    last_seed = None
    manifests = {s: json.loads((scope_dirs[s] / "corpus.jsonl.manifest.json").read_text(encoding="utf-8"))
                 for s in SCOPES if s in scope_dirs}
    with merged.open("w", encoding="utf-8") as sink:
        for scope in sorted(manifests, key=lambda s: int(manifests[s]["seedSpec"]["start"])):
            manifest_path = scope_dirs[scope] / "corpus.jsonl.manifest.json"
            manifest = manifests[scope]
            validate_manifest(manifest)
            if manifest.get("forcedSetup") != scope:
                raise ValueError(f"{scope}: assembled scope has forcedSetup {manifest.get('forcedSetup')!r}")
            ident = {k: manifest[k] for k in ("schemaVersion", "rowSchemaVersion", "predictorInputSchemaVersion",
                                              "predictorInputFieldSchemaHash", "format", "producerGitSha",
                                              "producerExecutableSha256")}
            if teacher is None:
                teacher, shared = manifest["combatTeacher"], ident
            elif _canonical(manifest["combatTeacher"]) != _canonical(teacher) or ident != shared:
                raise ValueError(f"{scope}: mixed producer/teacher identity")
            quarantined += manifest.get("quarantined", [])
            first, kept, drop = rows, 0, Counter()
            with Path(manifest["csv"]["path"]).open(encoding="utf-8") as src:
                for line in src:
                    row = json.loads(line)
                    seed = int(row["sourceSeed"])
                    if last_seed is not None and seed < last_seed:
                        raise ValueError(f"{scope}: rows are not in ascending seed order")
                    last_seed = seed
                    rejected = reasons(row)
                    if rejected:
                        drop.update(rejected)
                        continue
                    sink.write(line if line.endswith("\n") else line + "\n")
                    seeds.add(seed); rows += 1; kept += 1
            # The scope manifest lets `audit` validate the scope's shards (blocks/).
            ranges[scope] = {"firstRow": first, "rows": kept, "seedSpec": manifest["seedSpec"],
                             "manifest": str(manifest_path.resolve()), "manifestSha256": sha256(manifest_path)}
            dropped[scope] = dict(drop)
    lo = min(r["seedSpec"]["start"] for r in ranges.values())
    hi = max(r["seedSpec"]["start"] + r["seedSpec"]["count"] for r in ranges.values())
    # One seedSpec spans every scope; seeds between scopes, generator stalls
    # and seeds whose rows were all dropped count as quarantined.
    union_manifest = dict(shared)
    union_manifest.update({
        "combatTeacher": teacher,
        "seedSpec": {"start": lo, "count": hi - lo},
        "csv": {"path": str(merged.resolve()), "sha256": sha256(merged)},
        "integrity": {"requestedSeeds": hi - lo, "completedSeeds": len(seeds),
                      "quarantinedSeeds": hi - lo - len(seeds), "rows": rows},
        "quarantined": sorted(quarantined),
        "forcedSetup": "union",
        "ctmCorpusAdapter": {"schema": SCHEMA, "union": ranges, "droppedRowReasons": dropped},
    })
    validate_manifest(union_manifest)
    (out / "corpus.jsonl.manifest.json").write_text(
        json.dumps(union_manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "row_scopes.json").write_text(json.dumps(ranges, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"rows": rows, "scopes": ranges, "droppedRowReasons": dropped,
               "corpusSha256": union_manifest["csv"]["sha256"]}
    print(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("assemble")
    p.add_argument("--index", required=True, type=Path)
    p.add_argument("--corpus-root", required=True, type=Path)
    p.add_argument("--scope", required=True,
                   choices=SCOPES)
    p.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("union")
    p.add_argument("--scope-dir", action="append", required=True, metavar="SCOPE=DIR",
                   help="an assembled scope; repeat for each scope to include")
    p.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "assemble":
        assemble(args.index, args.corpus_root, args.scope, args.out)
    else:
        dirs = dict(item.split("=", 1) for item in args.scope_dir)
        union({k: Path(v) for k, v in dirs.items()}, args.out)


if __name__ == "__main__":
    main()
