#!/usr/bin/env python3
"""Audit the pinned recovered §497 delivery. Never parse any SEALED archive.

Only TRAIN/VALIDATION archives are decoded. TEST/partial bytes are hashed opaquely.
No game execution, fitting, TEST opener, seed replacement or training default.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import platform
import re
import tarfile
import tempfile

import heart_outcome_collect as capture

REPO = Path(__file__).resolve().parents[1]
TRANSPORT = 'e3b649ced5a392f78e9412787a84d458cffd60a1'
INDEX = 'e3621c3873dc0155edd651f787802412560b632ee6cca3f32b6e4ed2be746026'
SOURCE = '7527b5d5d07467688101212660461995665512b9'
BINARY = '178e7076934097987e473ab04c2dc80eec5368f9dcb12b274a631bad62f43e4e'
PLAN = '4b49a40427dde2470044847e8e843cc349a460e183d6fa2ddbdda4c0494d14a3'
BUNDLE = '836a34129c99bfd68e691ed802f0a403cd75e37db7effd0e1b01f51b4697f6d5'
ACTIVATION = '9f66ee277e52874b8c74dcd11561027f827029b336da28f81c534e3c5a041b22'
LOST = (7, 8, 27, 34)
SPLITS = ('train', 'validation')
SCREENS = ('INVALID', 'EVENT', 'REWARDS', 'BOSS_RELIC', 'CARD_SELECT',
           'MAP', 'TREASURE', 'REST', 'SHOP', 'BATTLE')
SUFFIXES = ('.log', '.mcts.csv', '.mcts.csv.actions.jsonl', '.mcts.csv.support.jsonl',
            '.receipt.json', '.started.json', '.states.jsonl', '.trace.jsonl')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def selected_deliveries():
    return [(f'w{w:02d}', w, None) for w in range(45) if w not in LOST] + [
        (f'r{w:02d}-{half}', w, half) for w in LOST for half in (0, 1)]


def verify_checksums(root):
    listed = {}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (?:\./)?(.+)', line)
        require(match is not None, 'invalid checksum manifest line')
        checksum, name = match.groups()
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and name not in listed,
                'unsafe/duplicate checksum path')
        target = root/name
        require(target.is_file() and not target.is_symlink(), 'non-regular transport path')
        require(capture.sha(target) == checksum, 'transport hash mismatch: '+name)
        listed[name] = checksum
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    require(actual == set(listed) | {'SHA256SUMS'}, 'transport manifest inventory differs')
    return listed


def metadata(root):
    checksums = verify_checksums(root)
    require(capture.sha(root/'DELIVERY-INDEX.json') == INDEX, 'wrong pinned delivery index')
    require(capture.sha(REPO/'docs/experiments/evidence/heart_outcome_collection_20261016/delivery-index.json') == INDEX,
            'main delivery-index binding changed')
    index = read_json(root/'DELIVERY-INDEX.json')
    camp = root/'campaign'
    plan, bundle, act = (read_json(camp/name) for name in
                        ('plan.json', 'bundle-manifest/bundle.json', 'activation.json'))
    require(capture.sha(camp/'plan.json') == PLAN and capture.sha(camp/'activation.json') == ACTIVATION
            and capture.sha(camp/'bundle-manifest/bundle.json') == BUNDLE, 'campaign identity mismatch')
    require(plan['sources'] == capture.assignments() and plan['sourceSha'] == SOURCE
            and bundle['sourceSha'] == SOURCE and plan['bundleSha256'] == BUNDLE,
            'source/assignment binding changed')
    require((plan['sourceSeconds'], plan['campaignSeconds'], plan['processesPerWorker']) == (3600,21600,4),
            'frozen budgets changed')
    require(plan['environment'] == read_json(camp/'bundle-manifest/environment.json'), 'environment mismatch')
    expected_env = capture.scientific_environment(REPO)
    expected_env['STS_EXECUTABLE_GIT_SHA'] = SOURCE
    require(plan['environment'] == expected_env, 'teacher environment changed')
    # This is offline artifact validation, not invoking the cloud producer under a new runtime.
    for name, checksum in bundle['files'].items():
        if name == 'one_combat': require(checksum == BINARY, 'wrong producer binary')
        elif name == 'studentc.bin': require(checksum == capture.STUDENT_C, 'wrong Arm C')
        elif name == 'environment.json': require(capture.sha(camp/'bundle-manifest/environment.json') == checksum, 'environment hash')
        else:
            path = REPO/name if name.startswith(('models/', 'selfplay/')) else REPO/'tools'/name
            require(capture.sha(path) == checksum, 'frozen model/tool differs: '+name)
    approval = camp/'cloud-canary/canary-reviewed.json'
    review = read_json(approval);canary_path = approval.parent/'canary.json';canary = read_json(canary_path)
    require(review['verdict'] == canary['verdict'] == 'PASS' and canary['role'] == 'cloud'
            and review['sourceSha'] == SOURCE and review['planSha256'] == canary['planSha256'] == PLAN
            and review['bundleSha256'] == canary['bundleSha256'] == BUNDLE
            and review['canarySha256'] == capture.sha(canary_path)
            and review['exportReceiptSha256'] == capture.sha(approval.parent/'export-roundtrip.json'), 'canary review binding')
    for name, checksum in canary['files'].items():
        require(capture.sha(approval.parent/name) == checksum, 'canary completion artifact changed')
    require(act['planSha256'] == PLAN and act['bundleSha256'] == BUNDLE
            and act['approvalSha256'] == capture.sha(approval)
            and act['latchSha256'] == capture.sha(camp/'COHORT-STARTED.json')
            and act['deadlineUtc']-act['startedUtc'] == 21600
            and act['policy'] == canary['policy'], 'activation chain mismatch')
    require(read_json(camp/'COHORT-STARTED.json') == {'planSha256':PLAN,'startedUtc':act['startedUtc']}, 'global latch changed')
    rows = {d['folder']:d for d in index['deliveries']}
    selected = selected_deliveries()
    require(len(rows) == len(index['deliveries']) == 49 and set(rows) == {s[0] for s in selected}, 'delivery selection differs')
    all_seeds = set();test_custody = []
    for folder, worker, half in selected:
        row = rows[folder];directory = root/'deliveries'/folder
        receipt = read_json(directory/'worker-receipt.json');start = read_json(directory/'worker-started.json')
        owned = [s['seed'] for s in plan['sources'] if s['worker'] == worker]
        expected = owned if half is None else owned[half::2]
        require(row['worker'] == worker and row['half'] == half and row['verified'] is True
                and row['complete'] is True and row['nonzeroReturncodes'] == 0, 'invalid indexed delivery')
        require(receipt['worker'] == worker and receipt['sources'] == expected and receipt['complete'] is True
                and len(receipt['returncodes']) == len(expected)
                and all(type(c) is int and c == 0 for c in receipt['returncodes'])
                and receipt['planSha256'] == PLAN and receipt['activationSha256'] == ACTIVATION,
                'worker receipt/accounting mismatch: '+folder)
        require(not all_seeds.intersection(expected), 'duplicate source ownership')
        all_seeds.update(expected)
        require(capture.sha(directory/'worker-receipt.json') == row['receiptSha256']
                and capture.sha(directory/'worker-started.json') == row['workerStartedSha256'], 'delivery receipt hash')
        require(start['worker'] == worker and start['planSha256'] == PLAN and start['activationSha256'] == ACTIVATION
                and len(set(start['affinity'])) >= 4, 'worker resource/identity mismatch')
        quota, period = start['cpuMax'].split()
        require(int(period) > 0 and (quota == 'max' or int(quota)/int(period) >= 4), 'worker CPU quota')
        for name in ('train.tar.gz','validation.tar.gz','SEALED-test.tar.gz'):
            archive = directory/name;checksum = capture.sha(archive)
            require(checksum == receipt['archives'][name] == row['archives'][name]['sha256']
                    and archive.stat().st_size == row['archives'][name]['bytes'], 'archive binding mismatch')
            if name.startswith('SEALED'):
                test_custody.append({'path':str(archive.relative_to(root)), 'sha256':checksum, 'parsed':False})
    require(all_seeds == {s['seed'] for s in plan['sources']}, 'incomplete cohort')
    for partial in index['superseded']:
        require(partial['folder'] in {f'w{w:02d}' for w in LOST}, 'unexpected superseded worker')
        archive = root/'deliveries'/partial['folder']/'SEALED-partial-out.tar.gz'
        require(capture.sha(archive) == partial['partialArchive']['sha256'], 'superseded partial hash')
        test_custody.append({'path':str(archive.relative_to(root)), 'sha256':capture.sha(archive), 'parsed':False})
    return plan, act, selected, test_custody, checksums


def archive_units(path, split, expected):
    """Only these two literal archive names can ever reach a tar parser."""
    require(split in SPLITS and path.name == split+'.tar.gz', 'sealed/unknown archive decoding prohibited')
    with tarfile.open(path, 'r:gz') as tar:
        groups = {};seen = set()
        for member in tar:
            require(member.name not in seen, 'duplicate archive member');seen.add(member.name)
            if member.isdir():
                require(member.name == split, 'unexpected archive directory');continue
            require(member.isfile() and member.size <= 64*1024**2, 'unsafe/oversized archive member')
            match = re.fullmatch(re.escape(split)+r'/seed-(\d+)('+ '|'.join(re.escape(s) for s in SUFFIXES)+r')', member.name)
            require(match is not None, 'unsafe/unknown archive path')
            seed = int(match[1]);require(seed in expected, 'cross-split/unassigned archive source')
            require(member.name == f'{split}/seed-{seed}'+match[2], 'noncanonical archive source name')
            groups.setdefault(seed,{})[match[2]] = tar.extractfile(member).read()
        require(set(groups) == set(expected), 'missing split sources')
        for seed, payload in groups.items():
            require(set(payload) == set(SUFFIXES), 'incomplete source files')
            yield seed, payload


def verify_unit(seed, payload, plan, policy, scratch):
    prefix = 'seed-'+str(seed)
    receipt = json.loads(payload['.receipt.json'])
    expected_hashes = {prefix+suffix:digest(body) for suffix,body in payload.items() if suffix != '.receipt.json'}
    require(receipt['files'] == expected_hashes, 'source receipt raw-file hash mismatch')
    require(receipt['seed'] == seed and receipt['sourceSha'] == SOURCE and receipt['binarySha256'] == BINARY
            and receipt['returncode'] == receipt['processReturncode'] == 0, 'source completion/identity mismatch')
    require(type(receipt['seconds']) in (int,float) and math.isfinite(receipt['seconds'])
            and 0 <= receipt['seconds'] <= 3600, 'source exceeded frozen cap')
    env = receipt['environment']
    require(set(env) == set(plan['environment']) | {'HOME','PATH','STS_OOC_DECISION_TRACE','STS_OOC_MCTS_TRACE'}
            and all(env[k] == v for k,v in plan['environment'].items()), 'source teacher environment mismatch')
    require(env['STS_OOC_DECISION_TRACE'].endswith('/'+prefix+'.trace.jsonl')
            and env['STS_OOC_MCTS_TRACE'].endswith('/'+prefix+'.mcts.csv'), 'source trace path mismatch')
    command = receipt['command']
    require(len(command) == 8 and command[0] == 'bash' and Path(command[1]).name == 'seed_guard.sh'
            and Path(command[2]).name == 'one_combat' and command[3:6] == ['heartoutcomegen','1',str(seed)]
            and Path(command[6]).name == prefix+'.states.jsonl' and command[7] == 'on', 'source guarded invocation mismatch')
    started = json.loads(payload['.started.json'])
    require(started == {'seed':seed,'capture':True,'sourceSha':SOURCE}, 'source start binding')
    scratch.write_bytes(payload['.states.jsonl'])
    header, footer, states = capture.trajectory(scratch, seed, SOURCE)
    require(header['policy'] == receipt['policy'] == policy, 'source effective policy changed')
    support = [json.loads(l) for l in payload['.mcts.csv.support.jsonl'].splitlines()]
    require(len(support) == 1, 'source telemetry count')
    contract = capture.runtime_contract(REPO/'tools', payload['.log'].decode(), support[0], seed)
    require(contract == receipt['modelUse'], 'source Arm C use contract differs')
    require(receipt['states'] == footer['states'] and receipt['supportedStates'] == footer['supportedStates'], 'source coverage mismatch')
    trace = [json.loads(l) for l in payload['.trace.jsonl'].splitlines()]
    require(len(trace) == len(states), 'actual-state/trace coverage mismatch')
    for state, observed in zip(states, trace):
        pre = observed['pre']
        require(observed['seed'] == seed and (state['act'],state['floor']) == (pre['act'],pre['floor'])
                and SCREENS[state['screen']] == pre['screen'], 'state is not aligned to actual public trace')
        if state['supported']:
            record = state['record'];fixed = record['obs.fixed_observation']
            require(fixed[:4] == [pre['hp'],pre['maxHp'],pre['gold'],pre['floor']]
                    and [record['obs.mapX'],record['obs.mapY']] == [pre['x'],pre['y']], 'public observation disagrees with trace')
    post = trace[-1]['post']
    require([footer[k] for k in ('finalAct','finalFloor','finalHp')] == [post[k] for k in ('act','floor','hp')], 'outcome/trace endpoint mismatch')
    return {'seed':seed,'label':footer['label'],'states':footer['states'],'supportedStates':footer['supportedStates'],
            'finalAct':footer['finalAct'],'finalFloor':footer['finalFloor'],'seconds':receipt['seconds'],
            'receiptSha256':digest(payload['.receipt.json']), 'trajectorySha256':digest(payload['.states.jsonl']),
            'priorShare':contract['share'],'rolloutShare':contract['rolloutShare']}


def audit(root, out):
    out.mkdir(parents=True, exist_ok=False)
    plan, act, selected, custody, checksums = metadata(root)
    sources = []
    with tempfile.TemporaryDirectory(prefix='heart-outcome-audit-') as temp:
        scratch = Path(temp)/'trajectory.jsonl'
        for folder, worker, half in selected:
            for split in SPLITS:
                owned = [s for s in plan['sources'] if s['worker'] == worker]
                if half is not None: owned = owned[half::2]
                expected = [s['seed'] for s in owned if s['split'] == split]
                archive = root/'deliveries'/folder/(split+'.tar.gz')
                archive_sha = capture.sha(archive)
                for seed, payload in archive_units(archive, split, expected):
                    sources.append({**verify_unit(seed,payload,plan,act['policy'],scratch),
                                    'split':split,'folder':folder,'archiveSha256':archive_sha})
            print('audited',folder,flush=True)
    require(len(sources) == len({s['seed'] for s in sources}) == 1440, 'TRAIN/VALIDATION source accounting')
    require(verify_checksums(root) == checksums, 'transport changed during audit')
    counts = {}
    for split in SPLITS:
        rows = [s for s in sources if s['split'] == split]; labels = Counter(s['label'] for s in rows)
        counts[split] = {'sources':len(rows),'wins':labels[1],'losses':labels[0],
                         'states':sum(s['states'] for s in rows),'supportedStates':sum(s['supportedStates'] for s in rows),
                         'finalActCounts':dict(sorted(Counter(s['finalAct'] for s in rows).items()))}
    gate = plan['trainingGate']
    enough = all(counts[split][label] >= gate[split+suffix]
                 for split in SPLITS for label,suffix in (('wins','Wins'),('losses','Losses')))
    report = {'schema':'heart-outcome-import-audit-v1','transportCommit':TRANSPORT,'deliveryIndexSha256':INDEX,
              'producerSourceSha':SOURCE,'planSha256':PLAN,'bundleSha256':BUNDLE,'activationSha256':ACTIVATION,
              'verdict':'TRAIN_VALIDATION_READY' if enough else 'INSUFFICIENT_CLASS_COVERAGE',
              'splits':counts,'trainingGate':gate,'selectedDeliveries':len(selected),'verifiedTransportFiles':len(checksums),
              'testAssignedSources':360,'testArchivesParsed':0,'supersededArchivesParsed':0,
              'sealedCustody':custody,'analysisPython':platform.python_version(),
              'producerRuntime':read_json(root/'campaign/bundle-manifest/bundle.json')['runtime'],
              'testOpeningAuthorized':False,'nativeIntegration':False,
              'limitations':['Operational recovery and one-way export deviations remain recorded; not unchanged original protocol.',
                             'No cross-CPU byte-parity proof for W11; fixed simulations alone do not establish it.',
                             'Public-record/native parity unqualified; sampled actual driver boundaries.',
                             'TEST validated only by opaque hashes and producer completion receipts; no TEST outcomes inspected.']}
    capture.write(out/'import-audit.json',report)
    with (out/'train-validation-sources.jsonl').open('x') as f:
        for source in sorted(sources,key=lambda s:s['seed']):f.write(json.dumps(source,sort_keys=True)+'\n')
    print(json.dumps({'verdict':report['verdict'],'splits':counts,'testArchivesParsed':0},indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('out',type=Path)
    args = parser.parse_args()
    try: audit(args.root.resolve(),args.out.resolve())
    except Exception as error:
        if args.out.is_dir() and not (args.out/'failure.json').exists():
            capture.write(args.out/'failure.json',{'verdict':'IMPORT_FAILED','error':str(error),'testArchivesParsed':0})
        raise


if __name__ == '__main__':main()
