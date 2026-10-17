#!/usr/bin/env python3
"""§499 fixed-head, one-shot TEST. No fitting, calibration fit, gameplay or native port."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import time

import numpy as np
import torch

import heart_outcome_value as value
import heart_outcome_import as audit
from heart_outcome_collect import sha, write

REPO = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-import-20261016-v1')
PROTOCOL = REPO/'docs/experiments/evidence/heart_outcome_holdout_20261017/PROTOCOL.md'
SEEDS = list(range(110181440,110181800))
CONSTANT = 126/1080
PARENT_FILES = {'freeze.json':'b5d2e023ecb4c4ba8ff82c827c43a0aa4c5a11b5d5106d5bec79c0984d2b2a44',
    'result.json':'eeee2c1ace7382fa5fa3c4f51b4caeb6e08ea3d04bc54553d299e7f7e22c356c',
    'result-reviewed.json':'c3cc779e11a641b2e6b0e84137ccdd71309e2c28575062f99e5e9e5b42b9b669',
    'value-head.pt':'68c20b521b53a72896293b72442839eb5abfbb7c43222030556874b0a7593de1',
    'head.json':'2c478bca6692e8c69cd70c78cf7cf1758c07c3ed884a97bb64d813424019942c'}
require = value.require


def canonical_root(path):
    require(not path.is_symlink() and path.absolute() == CANONICAL_ROOT
            and path.resolve() == CANONICAL_ROOT.resolve(), 'wrong/copied/symlink import root')
    return CANONICAL_ROOT


def latch_path(args):
    return canonical_root(args.import_root)/'test-opened.json'


def claim_opening(root, packet):
    root = canonical_root(root)
    with (root/'test-opened.json').open('x') as f:
        json.dump(packet,f,sort_keys=True,indent=2,allow_nan=False)
        f.write('\n');f.flush();os.fsync(f.fileno())
    fd = os.open(root,os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def authorization(root, freeze_sha):
    path = canonical_root(root)/'test-opened.json'
    require(path.is_file() and not path.is_symlink(), 'TEST has no exclusive opening latch')
    latch = json.loads(path.read_text())
    require(latch['freezeSha256'] == freeze_sha and latch['testSources'] == SEEDS, 'TEST latch differs')
    return latch


def sealed_units(path, expected, root, freeze_sha, clocks):
    # This guard precedes even tarfile.open; no member listing before opening.
    authorization(root,freeze_sha)
    require(path.name == 'SEALED-test.tar.gz' and path.is_file() and not path.is_symlink(), 'wrong sealed archive')
    require(len(expected) == len(set(expected)) and set(expected).issubset(SEEDS), 'wrong TEST assignment')
    groups,seen,total = {},set(),0
    with tarfile.open(path,'r:gz') as tar:
        for member in tar:
            require(member.name not in seen,'duplicate TEST member');seen.add(member.name)
            require(len(seen) <= 1+8*len(expected),'too many TEST members')
            if member.isdir():
                require(member.name == 'test','unknown TEST directory');continue
            require(member.isfile() and 0 <= member.size <= 64*1024**2,'unsafe/oversized TEST member')
            total += member.size
            require(total <= 256*1024**2,'oversized TEST archive')
            require(clocks[0] <= member.mtime <= clocks[1], 'TEST file outside frozen activation clock')
            match = re.fullmatch(r'test/seed-(\d+)('+ '|'.join(re.escape(s) for s in audit.SUFFIXES)+r')',member.name)
            require(match is not None,'unknown/unsafe TEST path')
            seed = int(match[1])
            require(seed in expected and member.name == f'test/seed-{seed}'+match[2], 'cross-split/noncanonical source')
            groups.setdefault(seed,{})[match[2]] = tar.extractfile(member).read()
    require(set(groups) == set(expected),'missing TEST sources')
    for seed in sorted(groups):
        require(set(groups[seed]) == set(audit.SUFFIXES),'incomplete TEST source')
        yield seed,groups[seed]


def identities(args):
    canonical_root(args.import_root)
    current = value.identity(args)
    parent = json.loads((args.training_root/'freeze.json').read_text())
    for name,checksum in PARENT_FILES.items():
        require(sha(args.training_root/name) == checksum,'selected parent changed: '+name)
    review = json.loads((args.training_root/'result-reviewed.json').read_text())
    require(review['verdict'] == 'PASS' and review['resultSha256'] == PARENT_FILES['result.json'], 'parent review invalid')
    for key,expected in parent['identity'].items():
        if key not in ('sourceSha','tools'):
            require(current[key] == expected,'parent encoder/runtime differs: '+key)
    for name,expected in parent['identity']['tools'].items():
        require(current['tools'][name] == expected,'frozen parent tool changed: '+name)
    current['holdoutTools'] = {str(p.relative_to(REPO)):sha(p) for p in
                              (Path(__file__),REPO/'tests/test_heart_outcome_holdout.py',PROTOCOL)}
    _,custody = value.audit_inputs(args)
    plan,act,selected,sealed,_ = audit.metadata(args.import_root/'heart-outcome-collection')
    require(custody == parent['custody'] and sealed == custody['sealedCustody'],'import custody differs')
    ownership = {}
    for folder,worker,half in selected:
        owned = [s for s in plan['sources'] if s['worker'] == worker]
        if half is not None: owned = owned[half::2]
        ownership[folder] = sorted(s['seed'] for s in owned if s['split'] == 'test')
    require(len(ownership) == 49 and sorted(s for group in ownership.values() for s in group) == SEEDS,'TEST ownership changed')
    return {'runtime':current,'parentFiles':PARENT_FILES,'custody':custody,'ownership':ownership,
            'planSha256':audit.PLAN,'activationSha256':audit.ACTIVATION},plan,act


def freeze(args):
    require(not latch_path(args).exists(),'TEST already consumed; no new freeze')
    require(not value.git(REPO,'status','--porcelain'),'freeze needs clean committed source')
    for protected in (args.import_root,args.training_root):
        require(args.out.resolve() != protected.resolve() and protected.resolve() not in args.out.resolve().parents,'protected output root')
    ident,_,_ = identities(args)
    review = json.loads(args.review.read_text())
    require(review['verdict'] == 'PASS' and review['sourceSha'] == ident['runtime']['sourceSha']
            and review['toolSha256'] == sha(Path(__file__)) and review['protocolSha256'] == sha(PROTOCOL)
            and review['testOpeningAuthorized'] is True,'exact opening review absent')
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'freeze.json',{'schema':'heart-outcome-holdout-freeze-v1','identity':ident,
        'reviewSha256':sha(args.review),'testOpeningAuthorized':True,'seeds':SEEDS,
        'maxSeconds':3600,'baseline':CONSTANT,'bootstrapResamples':10000,'bootstrapSeed':499,
        'landmarks':['start','act1_floor8','act1_floor16'],'meanBiasTolerance':.05})


def opening_approval(out, source_review_sha):
    path = out/'opening-reviewed.json'
    review = json.loads(path.read_text())
    require(review['verdict'] == 'PASS' and review['testOpeningAuthorized'] is True
            and review['freezeSha256'] == sha(out/'freeze.json')
            and review['sourceReviewSha256'] == source_review_sha,'exact freeze-opening review absent')
    return sha(path)


def load_models(args):
    network,net = value.load_net(args)
    # Construction never sees TEST or computes new normalization: all buffers
    # and parameters are immediately replaced by the frozen TRAIN-derived state.
    head = value.ValueHead(torch.zeros(1,64),torch.ones(1,dtype=torch.float64))
    payload = torch.load(args.training_root/'value-head.pt',map_location='cpu',weights_only=True)
    require(payload['encoderCheckpointSha256'] == value.CHECKPOINT,'wrong encoder attachment')
    head.load_state_dict(payload['valueHead'],strict=True)
    portable = json.loads((args.training_root/'head.json').read_text())
    require(all(torch.equal(t,torch.tensor(portable[k],dtype=t.dtype)) for k,t in head.state_dict().items()),'portable head differs')
    require(all(torch.isfinite(t).all().item() for t in head.state_dict().values()) and (head.scale>0).all().item(),'invalid frozen head')
    return network,net,head.requires_grad_(False).eval().cuda()


def tensor_digest(model):
    h = hashlib.sha256()
    for key,tensor in model.state_dict().items():
        h.update(key.encode());h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def landmark_indices(meta,kind):
    chosen = {};all_sources = sorted({r['seed'] for r in meta})
    threshold = {'act1_floor8':8,'act1_floor16':16}.get(kind)
    require(kind == 'start' or threshold is not None,'unknown landmark')
    for i,row in enumerate(meta):
        eligible = row['index'] == 0 if kind == 'start' else row['act'] == 1 and row['floor'] >= threshold
        if eligible and row['seed'] not in chosen: chosen[row['seed']] = i
    return np.array([chosen[s] for s in all_sources if s in chosen],dtype=np.int64)


def bootstrap_interval(values,seed):
    values = np.asarray(values,dtype=np.float64)
    require(len(values)>0 and np.isfinite(values).all(),'invalid bootstrap values')
    rng = np.random.default_rng(seed)
    # Bounded batches avoid large temporary arrays for multi-column diagnostics.
    samples = []
    for _ in range(100):
        ids = rng.integers(0,len(values),size=(100,len(values)))
        samples.append(values[ids].mean(1))
    samples = np.concatenate(samples)
    return {'mean':np.mean(values,axis=0).tolist(),'interval95':np.quantile(samples,[.025,.975],axis=0).tolist()}


def evaluate(meta,logits):
    logits = np.asarray(logits,dtype=np.float64)
    require(len(meta) == len(logits) and np.isfinite(logits).all(),'invalid prediction coverage')
    y = np.array([r['label'] for r in meta],dtype=float)
    p = torch.sigmoid(torch.from_numpy(logits)).numpy()
    source = np.array([r['seed'] for r in meta]);weights = value.source_weights(source)
    model_loss = np.stack((np.logaddexp(0,logits)-y*logits,(p-y)**2),axis=1)
    baseline_loss = np.stack((-y*np.log(CONSTANT)-(1-y)*np.log1p(-CONSTANT),(CONSTANT-y)**2),axis=1)
    per_source = [np.mean((model_loss-baseline_loss)[source==s],axis=0) for s in sorted(set(source))]
    paired = bootstrap_interval(per_source,499)
    # Ratio bootstrap for the fixed visitation diagnostic (sample whole runs).
    stats = np.array([[*(model_loss-baseline_loss)[source==s].sum(0),np.sum(source==s)] for s in sorted(set(source))])
    rng = np.random.default_rng(499);ratios=[]
    for _ in range(100):
        sums=stats[rng.integers(0,len(stats),size=(100,len(stats)))].sum(1)
        ratios.append(sums[:,:2]/sums[:,2:])
    visitation_ci=np.quantile(np.concatenate(ratios),[.025,.975],axis=0).tolist()
    counts = Counter(r['label'] for r in {r['seed']:r for r in meta}.values())
    primary_pass = counts[0]>=5 and counts[1]>=5 and all(v<0 for v in paired['interval95'][1])
    landmarks = {}
    for number,kind in enumerate(('start','act1_floor8','act1_floor16')):
        ids = landmark_indices(meta,kind)
        if not len(ids):
            landmarks[kind] = {'sources':0,'reached':0,'notReached':len(set(source)),'adequate':False,'earlyMeanBiasPass':False}
            continue
        lm_y,lm_p,lm_z = y[ids],p[ids],logits[ids]
        bias = bootstrap_interval(lm_p-lm_y,500+number)
        adequate = len(ids)>=100 and (lm_y==1).sum()>=5 and (lm_y==0).sum()>=5
        if kind == 'start': adequate = adequate and len(ids) == len(set(source))
        landmarks[kind] = {'sources':len(ids),'reached':len(ids),'notReached':len(set(source))-len(ids),
            'wins':int(lm_y.sum()),'losses':int(len(ids)-lm_y.sum()),'adequate':bool(adequate),
            'model':value.metric(lm_y,lm_p,np.ones(len(ids)),lm_z),
            'constant':value.metric(lm_y,np.full(len(ids),CONSTANT),np.ones(len(ids))),
            'bias':bias,'earlyMeanBiasPass':bool(adequate and bias['interval95'][0]>=-.05 and bias['interval95'][1]<=.05)}
    early = all(v['earlyMeanBiasPass'] for v in landmarks.values())
    verdict = ('INSUFFICIENT_TEST_CLASS_COVERAGE' if min(counts[0],counts[1])<5 else
               'NOT_SHOWN' if not primary_pass else
               'HOLDOUT_SIGNAL_CALIBRATION_NOT_SHOWN' if not early else 'OFFLINE_HOLDOUT_PASS')
    return {'verdict':verdict,'sources':len(set(source)),'states':len(meta),'wins':counts[1],'losses':counts[0],
        'primarySignalPass':bool(primary_pass),'earlyMeanBiasPass':early,'sourcePairedBootstrap':paired,
        'sourceBalanced':value.diagnostics(meta,p,CONSTANT,logits),
        'constant':value.metric(y,np.full(len(y),CONSTANT),weights),
        'visitation':{'model':value.metric(y,p,np.ones(len(y)),logits),
                      'constant':value.metric(y,np.full(len(y),CONSTANT),np.ones(len(y))),
                      'pairedDeltaInterval95':visitation_ci},'landmarks':landmarks}


def run(args):
    # A used corpus is rejected before any TEST path can reach a parser.
    require(not latch_path(args).exists(),'TEST already opened; never retry')
    frozen = json.loads((args.out/'freeze.json').read_text())
    require(frozen['testOpeningAuthorized'] is True and sha(args.review) == frozen['reviewSha256'],'opening approval changed')
    opening_sha = opening_approval(args.out,sha(args.review))
    ident,plan,act = identities(args)
    require(ident == frozen['identity'] and frozen['seeds'] == SEEDS,'frozen identities changed')
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    network,net,head = load_models(args)
    before = [tensor_digest(m) for m in (net,head)]
    tv_manifest,_ = value.audit_inputs(args)
    companion_row = next(r for r in value.read_sources(args,tv_manifest,'train') if value.has_choices(r['record']))
    companion = companion_row['record']
    expected_companion = json.loads((args.training_root/'result.json').read_text())['companion']
    require({'seed':companion_row['seed'],'index':companion_row['index'],
             'recordSha256':audit.digest(json.dumps(companion,sort_keys=True).encode())} == expected_companion,'TRAIN companion differs')
    started=time.monotonic();deadline=started+frozen['maxSeconds'];freeze_sha=sha(args.out/'freeze.json')
    claim_opening(args.import_root,{'freezeSha256':freeze_sha,'reviewSha256':sha(args.review),'testSources':SEEDS,
                           'sourceSha':ident['runtime']['sourceSha'],'openingReviewSha256':opening_sha,'out':str(args.out.resolve()),'startedUnix':time.time()})
    print('TEST opened once; auditing and encoding all360 fixed sources',flush=True)
    chunks,features,logit_batches,meta,sources=[],[],[],[],[]
    policy=hashlib.sha256()
    def flush():
        require(time.monotonic()<deadline,'frozen TEST wall cap')
        policy_logits,x=value.encode_batch(network,net,chunks,companion)
        with torch.inference_mode(): z=head(x)
        require(torch.isfinite(z).all().item(),'nonfinite head logits')
        policy.update(policy_logits.cpu().contiguous().numpy().tobytes())
        features.append(x.cpu());logit_batches.append(z.cpu())
        meta.extend([{k:v for k,v in r.items() if k!='record'} for r in chunks]);chunks.clear()
    root=args.import_root/'heart-outcome-collection'
    with tempfile.TemporaryDirectory(prefix='heart-test-audit-') as temp:
        scratch=Path(temp)/'trajectory.jsonl'
        for folder,expected in frozen['identity']['ownership'].items():
            path=root/'deliveries'/folder/'SEALED-test.tar.gz'
            for seed,payload in sealed_units(path,expected,args.import_root,freeze_sha,(act['startedUtc'],act['deadlineUtc'])):
                require(time.monotonic()<deadline,'frozen TEST audit wall cap')
                receipt=audit.verify_unit(seed,payload,plan,act['policy'],scratch)
                require(receipt['states']==receipt['supportedStates']>0,'TEST support less than100percent')
                _,_,states = audit.capture.trajectory(scratch,seed,audit.SOURCE)
                sources.append({**receipt,'folder':folder,'archiveSha256':sha(path)})
                for state in states:
                    chunks.append({'record':state['record'],'seed':seed,'label':receipt['label'],
                                   'index':state['index'],'act':state['act'],'screen':state['screen'],'floor':state['floor']})
                    if len(chunks)==32: flush()
            print('completed sources',len(sources),'of360',flush=True)
    if chunks:flush()
    require(sorted(r['seed'] for r in sources)==SEEDS and len(sources)==360,'incomplete TEST cohort')
    require(before == [tensor_digest(m) for m in (net,head)],'frozen tensors changed')
    pooled=torch.cat(features);logits=torch.cat(logit_batches)
    require(pooled.shape==(len(meta),64),'TEST pooled coverage mismatch')
    torch.save({'pooled':pooled,'logits':logits,'meta':meta},args.out/'test-predictions.pt')
    with (args.out/'test-sources.jsonl').open('x') as f:
        for row in sources:f.write(json.dumps(row,sort_keys=True)+'\n')
    result=evaluate(meta,logits.numpy())
    after,_,_=identities(args)
    require(after==ident and time.monotonic()<deadline,'post-opening identity/wall gate failed')
    result.update({'schema':'heart-outcome-holdout-result-v1','freezeSha256':freeze_sha,
        'openingLatchSha256':sha(latch_path(args)),'predictionsSha256':sha(args.out/'test-predictions.pt'),
        'sourceManifestSha256':sha(args.out/'test-sources.jsonl'),'originalAndHeadTensorsUnchanged':True,
        'testPolicyLogitsSha256':policy.hexdigest(),'seconds':time.monotonic()-started,
        'testArchivesParsed':49,'supersededArchivesParsed':0,'testOpeningCount':1,
        'nativeIntegration':False,'gameplayQualified':False,'runtimePromotion':False,'fittingPerformed':False,
        'calibrationMeaning':'marginal mean bias at fixed reached landmarks only; no conditional/native value qualification'})
    write(args.out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('verdict','sources','states','wins','primarySignalPass','earlyMeanBiasPass','seconds')}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('freeze','run'))
    for name in ('import-root','training-root','checkpoint','silverbot','review','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    try:
        freeze(args) if args.command=='freeze' else run(args)
    except Exception as exc:
        if args.out.is_dir() and not (args.out/'result.json').exists() and not (args.out/'failure.json').exists():
            write(args.out/'failure.json',{'verdict':'INVALID_TEST_EXECUTION','type':type(exc).__name__,'message':str(exc),
                  'testOpened':(CANONICAL_ROOT/'test-opened.json').exists(),'retryAllowed':False})
        raise


if __name__=='__main__':main()
