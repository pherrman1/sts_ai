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
                        'struct VwinDecisionSinkRow {\n    nlohmann::json fullSnapshot379;\n    int observationSeq379 = -1;')
    text = replace_once(text, '    VwinDecisionSinkRow row;\n',
                        '    VwinDecisionSinkRow row;\n'
                        '    row.observationSeq379 = capture.observationSeq379 - 1;\n'
                        '    if (std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT"))\n'
                        '        row.fullSnapshot379 = one_combat::encodeScreenLeafSnapshot(gc, path);\n')
    text = replace_once(text, 'struct VwinCollector {',
                        'struct VwinCollector {\n    int observationSeq379 = 0;\n'
                        '    nlohmann::json observations379 = nlohmann::json::array();\n'
                        '    nlohmann::json forcedPostAction379;')
    text = replace_once(text,
        '    if (gc.screenState == ScreenState::MAP_SCREEN) return;\n'
        '    bool supported = false, complete = false;',
        '    if (gc.screenState == ScreenState::MAP_SCREEN) {\n'
        '        if (std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT"))\n'
        '            capture.observations379.push_back({{"observationSeq", capture.observationSeq379++},\n'
        '                {"kind", "map"}, {"act", gc.act}, {"floor", gc.floorNum},\n'
        '                {"mapX", gc.curMapNodeX}, {"mapY", gc.curMapNodeY},\n'
        '                {"decisionIdx", decisionIdx}, {"mapRowIdx", capture.mapRowIdx},\n'
        '                {"features", richRow(gc, path)}});\n'
        '        return;\n'
        '    }\n'
        '    bool supported = false, complete = false;')
    text = replace_once(text,
        '    const auto logIndex = capture.decisionSinkLog.size();\n',
        '    const auto logIndex = capture.decisionSinkLog.size();\n'
        '    if (std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT"))\n'
        '        capture.observations379.push_back({{"observationSeq", capture.observationSeq379++},\n'
        '            {"kind", "decision"}, {"act", gc.act}, {"floor", gc.floorNum},\n'
        '            {"screen", vwinDecisionScreenName(gc)}, {"decisionIdx", decisionIdx},\n'
        '            {"supported", supported}, {"complete", complete},\n'
        '            {"optionCount", options.size()}, {"sinkLogIndex", logIndex}});\n')
    text = replace_once(text,
        '    if (branch && vwin)\n        vwinResumeContinuation',
        '    if (branch && vwin && std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT")) {\n'
        '        PathHistory postPath379 = path; postPath379.update(gc);\n'
        '        vwin->forcedPostAction379 = {{"observationSeq", vwin->observationSeq379++},\n'
        '            {"sourceDecisionIdx", branch->decision->decisionIdx},\n'
        '            {"branchId", vwin->branchId}, {"act", gc.act}, {"floor", gc.floorNum},\n'
        '            {"screenState", static_cast<int>(gc.screenState)},\n'
        '            {"features", richRow(gc, postPath379)},\n'
        '            {"snapshot", one_combat::encodeScreenLeafSnapshot(gc, postPath379)},\n'
        '            {"definition", "after_forced_semantic_action_before_resumeContinuation"}};\n'
        '    }\n'
        '    if (branch && vwin)\n        vwinResumeContinuation')
    anchor = '        for (const auto &row : capture.decisionSinkRows) {\n'
    code = '''        std::map<int, int> observationRows379;
        std::map<int, nlohmann::json> calibrationLinks379;
        for (const auto &saved : capture.decisionSinkRows)
            observationRows379.emplace(saved.observationSeq379, saved.rowIdx);
        if (const char *snapshotFile = std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT")) {
            auto events = capture.observations379;
            for (auto &event : events) {
                const auto found = observationRows379.find(event.at("observationSeq").get<int>());
                if (event.at("kind") == "decision") {
                    event["finalRowIdx"] = found == observationRows379.end() ? -1 : found->second;
                    const auto logIndex = event.at("sinkLogIndex").get<std::size_t>();
                    event["finalCaptureLog"] = capture.decisionSinkLog.at(logIndex);
                }
            }
            for (const auto &saved : capture.decisionSinkRows) {
                nlohmann::json link = {{"status", "NO_SUBSEQUENT_OBSERVED_MAP"},
                    {"definition", "last_captured_supported_nonsingleton_across_all_screen_families"},
                    {"interveningSingletons", 0}, {"interveningUnsupported", 0}};
                bool laterCaptured = false, unresolved = false;
                for (const auto &event : events) {
                    if (event.at("observationSeq").get<int>() <= saved.observationSeq379) continue;
                    if (event.at("kind") == "map") {
                        link["status"] = laterCaptured ? "LATER_CAPTURED_DECISION" :
                            (unresolved ? "INTERVENING_UNRESOLVED_SUPPORTED_DECISION" :
                             "EXACT_LAST_CAPTURED_TO_OBSERVED_MAP");
                        link["map"] = event;
                        break;
                    }
                    if (event.at("finalRowIdx").get<int>() >= 0) laterCaptured = true;
                    else if (event.at("supported").get<bool>() && event.at("complete").get<bool>()) {
                        if (event.at("optionCount").get<int>() > 1) unresolved = true;
                        else link["interveningSingletons"] = link["interveningSingletons"].get<int>() + 1;
                    } else link["interveningUnsupported"] = link["interveningUnsupported"].get<int>() + 1;
                }
                // Unsupported intervening states are visible in the receipt and
                // excluded: they cannot certify a supported calibration chain.
                if (link["interveningUnsupported"].get<int>() > 0 &&
                    link["status"] == "EXACT_LAST_CAPTURED_TO_OBSERVED_MAP")
                    link["status"] = "INTERVENING_UNSUPPORTED_DECISION";
                calibrationLinks379[saved.observationSeq379] = std::move(link);
            }
            const char *configured = std::getenv("STS_SCREEN_LEAF_TEMPORAL_OUT");
            const std::string temporalPath = configured ? configured : std::string(snapshotFile) + ".temporal.jsonl";
            static std::FILE *temporalFile = std::fopen(temporalPath.c_str(), "wx");
            if (!temporalFile) throw std::runtime_error("cannot open #379 temporal output");
            const std::string temporal = nlohmann::json({{"schema", "screen_leaf_temporal_v1"},
                {"sourceSeed", sourceSeed}, {"branchId", capture.branchId},
                {"observations", events}, {"forcedPostAction", capture.forcedPostAction379}}).dump() + "\\n";
            if (std::fwrite(temporal.data(), 1, temporal.size(), temporalFile) != temporal.size()
                || std::fflush(temporalFile) != 0) throw std::runtime_error("failed #379 temporal output");
        }
        for (const auto &row : capture.decisionSinkRows) {
            if (const char *file = std::getenv("STS_SCREEN_LEAF_SNAPSHOT_OUT")) {
                if (row.fullSnapshot379.is_null()) throw std::runtime_error("missing #379 snapshot");
                static std::FILE *snapshots = std::fopen(file, "wx");
                if (!snapshots) throw std::runtime_error("cannot open #379 snapshot output");
                const std::string encoded = nlohmann::json({{"sourceSeed", sourceSeed},
                    {"branchId", row.branchId}, {"rowIdx", row.rowIdx},
                    {"decisionIdx", row.decisionIdx}, {"features", row.features},
                    {"observationSeq", row.observationSeq379},
                    {"calibrationLink", calibrationLinks379.at(row.observationSeq379)},
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
