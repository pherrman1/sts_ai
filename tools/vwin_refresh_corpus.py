#!/usr/bin/env python3
"""Validate a provenance-preserving index of strict #334 producer bundles."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

if __package__:
    from .vwin_refresh_contract import ContractError, OUTPUTS, _sha256, validate_bundle
    from .ooc_pipeline_contract import validate_teacher
else:
    from vwin_refresh_contract import ContractError, OUTPUTS, _sha256, validate_bundle
    from ooc_pipeline_contract import validate_teacher

SCHEMA = "vwin_refresh_corpus_v1"
IDENTITY_FIELDS = ("producerGitSha", "producerExecutableSha256",
                   "teacherManifestSha256", "teacherId")
# Only these observed per-bundle measurements are excluded from comparison.
SINK_MEASUREMENTS = ("rows", "trajectories", "byScreen", "bytes", "bytesPerRow",
                     "projectedA2Bytes", "projectionSourceSeeds")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path}: expected JSON object")
    return value


def _path(base: Path, value: str) -> Path:
    _require(isinstance(value, str) and bool(value), "path must be a nonempty string")
    return (base / value).resolve()


def _hash(path: Path, expected: str) -> None:
    _require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected)
             is not None, f"{path}: invalid SHA-256")
    _require(_sha256(path) == expected, f"{path}: SHA-256 mismatch")


def _canonical(value: object) -> str:
    # Unlike Python dict equality, JSON comparison distinguishes booleans/numbers.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Producer:
    git_sha: str
    executable_sha256: str
    teacher_sha256: str
    teacher_id: str
    teacher_path: Path

    @property
    def identity(self) -> tuple[str, ...]:
        return (self.git_sha, self.executable_sha256, self.teacher_sha256, self.teacher_id)


@dataclass(frozen=True)
class Component:
    manifest_path: Path
    manifest_sha256: str
    producer: Producer
    source_seeds: tuple[int, ...]
    # Immutable name/hash pairs; no mutable manifest shared with consumers.
    outputs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Table:
    path: Path
    sha256: str
    component: Component


@dataclass(frozen=True)
class Corpus:
    index_path: Path
    components: tuple[Component, ...]
    source_seeds: tuple[int, ...]

    def manifests(self) -> tuple[Path, ...]:
        return tuple(c.manifest_path for c in self.components)

    def tables(self, table_type: str) -> Iterator[Table]:
        """Yield existing paths with component provenance; never concatenate files.

        Validation is a snapshot: keep input files immutable while consuming them.
        Revalidate the index after any input change.
        """
        _require(table_type in OUTPUTS, f"unknown table type: {table_type}")
        for component in self.components:
            outputs = dict(component.outputs)
            if table_type in outputs:
                yield Table(_table_path(component.manifest_path, table_type),
                            outputs[table_type], component)


def _table_path(manifest: Path, table: str) -> Path:
    return Path(str(manifest)[:-len(".manifest.json")] + OUTPUTS[table])


def _teacher_semantics(teacher: dict, identity: tuple[str, ...]) -> dict:
    validate_teacher(teacher)
    git, executable, _, teacher_id = identity
    _require(teacher.get("git_sha") == git
             and teacher.get("executable_sha256") == executable
             and teacher.get("teacher_id") == teacher_id
             and teacher["environment"].get("STS_EXECUTABLE_GIT_SHA") == git,
             "teacher executable binding disagrees with allowed producer identity")
    _require(teacher.get("rng_regime") == "project_fair", "teacher must be project_fair")
    policy = teacher.get("ooc_policy")
    _require(isinstance(policy, dict) and all(key in policy for key in
             ("schema_version", "policy_chain", "native_ooc", "flags", "parameters",
              "model_artifacts")), "teacher OOC policy is under-specified")
    result = copy.deepcopy(teacher)
    # Exact four differences observed between the old and repaired real freezes.
    # Binding is checked above; no other environment/policy/model fields are removed.
    for key in ("git_sha", "executable_sha256", "teacher_id"):
        del result[key]
    del result["environment"]["STS_EXECUTABLE_GIT_SHA"]
    return result


def _semantics(manifest: dict, teacher: dict, path: Path) -> dict:
    _require(_canonical(manifest.get("combatTeacher")) == _canonical(teacher),
             "embedded combatTeacher differs from hash-bound teacher manifest")
    _require(_canonical(manifest.get("policy")) == _canonical(teacher["ooc_policy"]),
             "effective policy differs from teacher OOC policy")
    sampling = manifest.get("sampling")
    _require(isinstance(sampling, dict) and all(key in sampling for key in
             ("schema", "samplesPerType", "optionCap", "capRule", "capDomain")),
             "sampling contract is under-specified")
    _require(type(manifest["seedSpec"].get("ascension")) is int,
             "seedSpec.ascension must be an integer")
    _require(isinstance(manifest["stateFeatures"].get("schema"), str),
             "stateFeatures.schema is missing")
    result = copy.deepcopy(manifest)
    for key in (*IDENTITY_FIELDS, "teacherPath", "outputs", "integrity", "perType", "branchRows"):
        result.pop(key, None)
    for key in ("start", "count"):
        del result["seedSpec"][key]
    for key in ("checks", "failures"):
        del result["branchParity"][key]
    if "decisionSink" in result:
        for key in SINK_MEASUREMENTS:
            result["decisionSink"].pop(key, None)
    result["combatTeacher"] = _teacher_semantics(teacher,
                                               tuple(manifest[k] for k in IDENTITY_FIELDS))
    # Includes the full combat-label suffix, which the bundle validator permits
    # to extend. Unknown manifest metadata remains in the comparison, fail closed.
    result["tableHeaders"] = {}
    _require(set(manifest["outputs"]) <= OUTPUTS.keys(), "unknown output table")
    for table in manifest["outputs"]:
        with _table_path(path, table).open(newline="", encoding="utf-8") as stream:
            result["tableHeaders"][table] = next(csv.reader(stream))
    return result


def _validate_corpus(index_path: Path) -> Corpus:
    index = _json(index_path)
    _require(set(index) == {"schemaVersion", "sourceSeeds", "allowedProducers", "components"},
             "corpus index fields must be schemaVersion, sourceSeeds, allowedProducers, components")
    _require(index["schemaVersion"] == SCHEMA, "unsupported corpus schema")
    seeds = index["sourceSeeds"]
    _require(isinstance(seeds, list) and bool(seeds)
             and all(type(s) is int and s >= 0 for s in seeds),
             "sourceSeeds must be a nonempty integer seed set")
    _require(len(set(seeds)) == len(seeds), "duplicate intended source seed")
    allowed = index["allowedProducers"]
    _require(isinstance(allowed, list) and bool(allowed), "allowedProducers must be nonempty")
    producers, teachers = {}, {}
    teacher_baseline = None
    for entry in allowed:
        _require(isinstance(entry, dict) and set(entry) == {*IDENTITY_FIELDS, "teacherManifest"},
                 "allowed producer requires exact identities and teacherManifest path")
        identity = tuple(entry[key] for key in IDENTITY_FIELDS)
        _require(all(isinstance(value, str) and value for value in identity),
                 "allowed producer identities must be nonempty strings")
        _require(re.fullmatch(r"[0-9a-f]{40}", identity[0]) is not None
                 and re.fullmatch(r"[0-9a-f]{64}", identity[1]) is not None,
                 "invalid allowed producer Git/executable SHA")
        _require(identity not in producers, "duplicate allowed producer identity")
        teacher_path = _path(index_path.parent, entry["teacherManifest"])
        _hash(teacher_path, identity[2])
        teacher = _json(teacher_path)
        semantics = _canonical(_teacher_semantics(teacher, identity))
        if teacher_baseline is None:
            teacher_baseline = semantics
        _require(semantics == teacher_baseline, "teacher scientific semantics mismatch")
        teachers[identity] = teacher
        producers[identity] = Producer(*identity, teacher_path)
    entries = index["components"]
    _require(isinstance(entries, list) and bool(entries), "components must be nonempty")
    components, observed = [], set()
    baseline = None
    for entry in entries:
        _require(isinstance(entry, dict) and set(entry) == {"manifest", "sha256"},
                 "component requires manifest and sha256")
        path = _path(index_path.parent, entry["manifest"])
        _hash(path, entry["sha256"])
        try:
            summary = validate_bundle(path)  # Existing strict validator, unchanged.
            manifest = _json(path)
            _hash(path, entry["sha256"])
            identity = tuple(manifest[key] for key in IDENTITY_FIELDS)
            _require(identity in producers, "unlisted producer identity")
            spec = manifest["seedSpec"]
            _require(type(spec["start"]) is int and type(spec["count"]) is int,
                     "source seed range must use integers")
            component_seeds = tuple(range(spec["start"], spec["start"] + spec["count"]))
            _require(summary["completed_source_trajectories"] == len(component_seeds)
                     and summary["valid_source_trajectories"] == len(component_seeds),
                     "partial or invalid source cohort")
            _require(not observed.intersection(component_seeds), "duplicate source seed across components")
            observed.update(component_seeds)
            semantics = _canonical(_semantics(manifest, teachers[identity], path))
            if baseline is None:
                baseline = semantics
            _require(semantics == baseline, "component scientific semantics mismatch")
            components.append(Component(path, entry["sha256"], producers[identity], component_seeds,
                                        tuple(sorted(manifest["outputs"].items()))))
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            raise ContractError(f"{path}: {exc}") from exc
    _require(observed == set(seeds),
             f"source cohort mismatch: missing={sorted(set(seeds) - observed)}, "
             f"extra={sorted(observed - set(seeds))}")
    return Corpus(index_path, tuple(components), tuple(sorted(observed)))


def validate_corpus(index_path: str | Path) -> Corpus:
    """Load and validate an index, all component bundles, identities and semantics."""
    try:
        return _validate_corpus(Path(index_path).resolve())
    except ContractError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        raise ContractError(f"{index_path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", help="vwin_refresh_corpus_v1 JSON index")
    args = parser.parse_args(argv)
    try:
        corpus = validate_corpus(args.index)
    except ContractError as exc:
        print(f"vwin refresh corpus: FAIL: {exc}", file=sys.stderr)
        return 1
    print("vwin refresh corpus: PASS " + json.dumps({
        "components": len(corpus.components), "source_seeds": len(corpus.source_seeds),
        "producer_groups": len({c.producer.identity for c in corpus.components}),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
