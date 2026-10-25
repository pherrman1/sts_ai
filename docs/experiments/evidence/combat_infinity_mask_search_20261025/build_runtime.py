#!/usr/bin/env python3
"""Build only a plain archived historical snapshot, never current production C++."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUNTIME = REPO / 'build/infinity-heart-mask-search-20261025'
SOURCE = RUNTIME / 'source'
BASE = HERE.parent / 'combat_infinity_reconstruction_20261024'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')

def main():
    frozen=json.loads((HERE/'FREEZE.json').read_text())
    assert sha(HERE/'FROZEN_INTERVENTIONS.json')==frozen['manifest_sha256']
    assert all(sha(HERE/'manifests'/f'{mask}.json')==digest for mask,digest in frozen['all_masks_sha256'].items())
    plan = json.loads((BASE / 'source-build-plan.json').read_text())
    archive = REPO / 'build/infinity-heart-runtime-20261024/source.tar'
    assert sha(archive) == plan['source_archive_sha256']
    patch = HERE / 'historical-intervention.patch'
    if not SOURCE.exists():
        SOURCE.mkdir(parents=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(SOURCE, filter='data')
        for name in ['json', 'pybind11']:
            (SOURCE / name).symlink_to((REPO / 'build/infinity-heart-runtime-20261024/source' / name).resolve(), target_is_directory=True)
        subprocess.run(['patch', '--batch', '-p1', '-i', str(patch)], cwd=SOURCE, check=True)
    allowed = {'apps/one_combat/run_driver.cpp', 'apps/one_combat/infinity_frozen_skips.h'}
    changed = {p for p,h in plan['tracked_files_sha256'].items() if sha(SOURCE / p) != h}
    assert changed == {'apps/one_combat/run_driver.cpp'}, changed
    added = {str(p.relative_to(SOURCE)) for p in SOURCE.rglob('*') if p.is_file() and str(p.relative_to(SOURCE)) not in plan['tracked_files_sha256'] and 'build' not in p.relative_to(SOURCE).parts and p.relative_to(SOURCE).parts[0] not in ['json','pybind11']}
    assert added == {'apps/one_combat/infinity_frozen_skips.h'}, added
    # A fresh application must byte-match the prepared snapshot; no unrecorded edits.
    import tempfile
    with tempfile.TemporaryDirectory(dir=RUNTIME) as temporary:
        verify = Path(temporary)
        for p in allowed:
            (verify / p).parent.mkdir(parents=True, exist_ok=True)
            if p in plan['tracked_files_sha256']:
                (verify / p).write_bytes((REPO / 'build/infinity-heart-runtime-20261024/source' / p).read_bytes())
        subprocess.run(['patch','--batch','-p1','-i',str(patch)],cwd=verify,check=True)
        assert all((verify/p).read_bytes()==(SOURCE/p).read_bytes() for p in allowed)
    for model in json.loads((HERE / 'FROZEN_INTERVENTIONS.json').read_text())['models']:
        assert sha(Path(model['path'])) == model['expected_sha256']
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.check:
        record=json.loads((HERE/'build-result.json').read_text())
        assert sha(patch)==record['patch_sha256']
        assert sha(Path(record['binary_path']))==record['binary_sha256']
        assert all(sha(SOURCE/p)==h for p,h in record['patched_file_hashes'].items())
        print('PASS base source, fresh patch application, patched file hashes, models and executable custody; no rebuild')
        return
    commands = [['cmake','--preset','linux-gcc-release'],['cmake','--build','--preset','linux-gcc-build','--target','one_combat','--parallel','4']]
    start = time.monotonic()
    for command, name in zip(commands, ['configure.log', 'build.log']):
        with (HERE / name).open('w') as out:
            subprocess.run(command, cwd=SOURCE, stdout=out, stderr=subprocess.STDOUT, check=True)
    (HERE/'configure.log.gz').write_bytes(gzip.compress((HERE/'configure.log').read_bytes(),mtime=0))
    (HERE/'configure.log').unlink()
    binary = SOURCE / 'build/linux-gcc-release/one_combat'
    record = {'status':'BUILT_RESEARCH_PATCHED_RUNTIME_NOT_HISTORICAL_EXECUTABLE','historical_source_sha':plan['source_sha'], 'starting_sha':'13bed5e0060788f58a0138e563877f1e9c312696', 'binary_path':str(binary), 'binary_sha256':sha(binary), 'patch_sha256':sha(patch), 'archive_sha256':sha(archive), 'manifest_sha256':sha(HERE / 'FROZEN_INTERVENTIONS.json'), 'commands':commands, 'compiler':subprocess.check_output(['g++','--version'],text=True), 'cmake':subprocess.check_output(['cmake','--version'],text=True), 'changed_historical_paths':sorted(allowed), 'patched_file_hashes':{p:sha(SOURCE/p) for p in allowed}, 'wall_seconds':time.monotonic()-start, 'worktree_created':False,'production_source_modified':False, 'submodules':{name:{'path':str((SOURCE/name).resolve()),'sha':subprocess.check_output(['git','-C',str((SOURCE/name).resolve()),'rev-parse','HEAD'],text=True).strip()} for name in ['json','pybind11']}}
    write(HERE/'build-result.json',record)
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
