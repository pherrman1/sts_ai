#!/usr/bin/env python3
"""Build an explicitly derived, snapshot-exporting copy of a frozen #334 producer.

No linked worktree, original artifact mutation, corpus validation, or seed runs.
The caller must verify derived replay output against the sealed source shard.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'expected one source anchor: {old[:100]!r}')
    return text.replace(old, new)


def prepare(repo, revision, destination):
    sha = subprocess.check_output(['git', 'rev-parse', revision], cwd=repo, text=True).strip()
    if sha not in ('1e93bd66cb5ef489028f1a06c22d5f12bd2ca935',
                   subprocess.check_output(['git', 'rev-parse', '06657471'], cwd=repo, text=True).strip()):
        raise ValueError('not a frozen #334 producer')
    destination.mkdir(parents=True, exist_ok=False)
    archive = subprocess.check_output(['git', 'archive', sha], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter='data')
    dependencies = {}
    for name in ('json', 'pybind11'):
        entry = subprocess.check_output(['git', 'ls-tree', sha, name], cwd=repo, text=True)
        dependency_sha = entry.split()[2]
        dependencies[name] = dependency_sha
        payload = subprocess.check_output(['git', 'archive', dependency_sha], cwd=repo / name)
        with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
            tar.extractall(destination / name, filter='data')
    added = ['apps/one_combat/screen_leaf_snapshot.h',
             'apps/one_combat/screen_leaf_snapshot.cpp',
             'apps/one_combat/screen_leaf_continuations.h',
             'apps/one_combat/screen_leaf_continuations.cpp']
    for relative in added:
        shutil.copyfile(repo / relative, destination / relative)
    subprocess.run(['python3', str(repo / 'tools/patch_screen_leaf_frozen_callbacks.py'),
                    '--source-root', str(destination)], check=True)
    path = destination / 'apps/one_combat/combat_datasets.cpp'
    text = path.read_text()
    text = '#include "screen_leaf_snapshot.h"\n' + text
    text = replace_once(text, 'struct VwinDecisionSinkRow {',
                        'struct VwinDecisionSinkRow {\n    nlohmann::json fullSnapshot379;')
    text = replace_once(text, '    VwinDecisionSinkRow row;\n',
                        '    VwinDecisionSinkRow row;\n'
                        '    if (std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT"))\n'
                        '        row.fullSnapshot379 = one_combat::encodeScreenLeafSnapshot(gc, path);\n')
    anchor = '        for (const auto &row : capture.decisionSinkRows) {\n'
    code = '''        for (const auto &row : capture.decisionSinkRows) {
            if (const char *file = std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT")) {
                if (row.fullSnapshot379.is_null()) throw std::runtime_error("missing #379 snapshot");
                static std::FILE *snapshots = std::fopen(file, "wx");
                if (!snapshots) throw std::runtime_error("cannot open #379 snapshot output");
                const std::string encoded = nlohmann::json({{"sourceSeed", sourceSeed},
                    {"branchId", row.branchId}, {"rowIdx", row.rowIdx},
                    {"decisionIdx", row.decisionIdx}, {"features", row.features},
                    {"screenContents", nlohmann::json::parse(row.screenContentsJson)},
                    {"candidateKeys", row.candidateKeys}, {"snapshot", row.fullSnapshot379}}).dump() + "\\n";
                if (std::fwrite(encoded.data(), 1, encoded.size(), snapshots) != encoded.size()
                    || std::fflush(snapshots) != 0) throw std::runtime_error("failed #379 snapshot output");
            }
'''
    text = replace_once(text, anchor, code)
    path.write_text(text)
    cmake = destination / 'CMakeLists.txt'
    text = cmake.read_text()
    text = replace_once(text, 'add_executable(one_combat ',
                        'add_executable(one_combat apps/one_combat/screen_leaf_snapshot.cpp '
                        'apps/one_combat/screen_leaf_continuations.cpp ')
    cmake.write_text(text)
    changed = added + ['apps/one_combat/combat_datasets.cpp', 'CMakeLists.txt',
                        'src/game/GameContext.cpp', 'src/game/Shop.cpp',
                        'src/sim/search/GameAction.cpp']
    manifest = {'schema': 'screen_leaf_379_derived_producer_v1', 'original_source_sha': sha,
                'purpose': 'Exact frozen trajectory recovery only, never current-main S0',
                'dependency_shas': dependencies,
                'derived_files': {p: hashlib.sha256((destination / p).read_bytes()).hexdigest()
                                  for p in changed},
                'preparer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'callback_patcher_sha256': hashlib.sha256(
                    (repo / 'tools/patch_screen_leaf_frozen_callbacks.py').read_bytes()).hexdigest()}
    (destination / 'derived-producer.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[1], args.revision, args.destination.resolve())
