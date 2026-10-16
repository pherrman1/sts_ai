#!/usr/bin/env python3
"""§498: source-balanced Heart outcome value head; TEST has no reader here."""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

import heart_outcome_import as audit
from heart_outcome_collect import sha, write

REPO = Path(__file__).resolve().parents[1]
CHECKPOINT = '53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020'
ENCODER = '84ab3ead9d88c01c4be09a6773fb9a947f57d5ff'
AUDIT = 'aafe46933b03b153fc3b3032f0afa3f860663b15e9d96e015f3af06688328d33'
MANIFEST = '1d2c6b03f95ca4750eb9869627f590d11fafeb69f04c43077d927d524117f5c6'
REVIEW = 'e07fce84e152dc4d0bf10c6c8ae833c37ff0d7ed8d49b41ac18fea71b59e01be'
PROTOCOL = REPO/'docs/experiments/evidence/heart_outcome_value_20261017/PROTOCOL.md'
SPLITS = {'train': list(range(110180000,110181080)), 'validation': list(range(110181080,110181440))}
STEPS, EVERY, BATCH, ENCODE_BATCH = 2000, 100, 512, 32


def git(path, *args):
    return subprocess.check_output(['git','-C',str(path),*args], text=True).strip()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(args):
    require(git(args.silverbot,'rev-parse','HEAD') == ENCODER
            and not git(args.silverbot,'status','--porcelain'), 'encoder source dirty/changed')
    require(sha(args.checkpoint) == CHECKPOINT, 'original Arm C changed')
    require(os.environ.get('CUBLAS_WORKSPACE_CONFIG') == ':4096:8', 'CUBLAS configuration required')
    deps = sorted((args.silverbot/'silverbot').glob('*.py')) + sorted((args.silverbot/'build').glob('slaythespire*.so'))
    require(any(p.suffix == '.so' for p in deps), 'missing encoder binding')
    tools = [Path(__file__), REPO/'tools/heart_outcome_import.py', REPO/'tools/heart_outcome_collect.py',
             REPO/'tools/heart_record_encoder.py', REPO/'tools/heart_distill_native_plan.py',
             REPO/'tools/run_heart_distill_pilot.py', REPO/'tests/test_heart_outcome_value.py', PROTOCOL]
    return {'sourceSha':git(REPO,'rev-parse','HEAD'), 'checkpointSha256':sha(args.checkpoint),
        'dependencies':{str(p):sha(p) for p in deps}, 'tools':{str(p.relative_to(REPO)):sha(p) for p in tools},
        'python':platform.python_version(), 'pythonExecutableSha256':sha(Path(sys.executable).resolve()),
        'numpy':np.__version__, 'torch':torch.__version__, 'torchBinarySha256':sha(Path(torch._C.__file__)),
        'cuda':torch.version.cuda, 'gpu':torch.cuda.get_device_name(),
        'gpuCapability':list(torch.cuda.get_device_capability()),
        'gpuDriver':subprocess.check_output(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader'],text=True).strip(),
        'torchLibraries':{str(p):sha(p) for p in sorted((Path(torch.__file__).parent/'lib').glob('*.so*'))},
        'cudaLibraries':{str(p):sha(p) for p in sorted(Path(torch.__file__).parent.parent.glob('nvidia/*/lib/*.so*'))}}


def audit_inputs(args):
    paths = {'report':args.import_root/'audit/import-audit.json',
             'manifest':args.import_root/'audit/train-validation-sources.jsonl',
             'review':args.import_root/'import-reviewed.json'}
    require([sha(paths[k]) for k in ('report','manifest','review')] == [AUDIT,MANIFEST,REVIEW], 'import custody changed')
    report, review = (json.loads(paths[k].read_text()) for k in ('report','review'))
    require(report['verdict'] == 'TRAIN_VALIDATION_READY' and review['verdict'] == 'PASS'
            and review['resultSha256'] == AUDIT and review['sourceManifestSha256'] == MANIFEST
            and review['testClosed'] is True, 'import not independently ready')
    manifest = [json.loads(line) for line in paths['manifest'].read_text().splitlines()]
    require(len(manifest) == 1440 and len({r['seed'] for r in manifest}) == 1440, 'source count/duplicates')
    for split,seeds in SPLITS.items():
        require(sorted(r['seed'] for r in manifest if r['split'] == split) == seeds, 'source split changed')
    root = args.import_root/'heart-outcome-collection'
    archives = {}
    for row in manifest:
        name = f"deliveries/{row['folder']}/{row['split']}.tar.gz"
        require(row['label'] in (0,1) and row['states'] == row['supportedStates'] > 0, 'invalid source labels/support')
        require(name not in archives or archives[name] == row['archiveSha256'], 'conflicting archive hashes')
        archives[name] = row['archiveSha256']
    for name,checksum in archives.items():
        require(sha(root/name) == checksum, 'TRAIN/VALIDATION archive changed')
    require(len(report['sealedCustody']) == 53, 'sealed inventory changed')
    for item in report['sealedCustody']:
        require(item['parsed'] is False and 'SEALED-' in Path(item['path']).name
                and sha(root/item['path']) == item['sha256'], 'opaque seal changed')
    return manifest, {'importReportSha256':AUDIT, 'sourceManifestSha256':MANIFEST,
        'importReviewSha256':REVIEW, 'archives':archives, 'sealedCustody':report['sealedCustody']}


def freeze(args):
    require(not git(REPO,'status','--porcelain'), 'freeze requires clean committed source')
    args.out.mkdir(parents=True,exist_ok=True)
    require(not list(args.out.iterdir()), 'freeze output must be empty')
    ident = identity(args)
    approved = json.loads(args.review.read_text())
    require(approved['verdict'] == 'PASS' and approved['sourceSha'] == ident['sourceSha']
            and approved['toolSha256'] == sha(Path(__file__)) and approved['protocolSha256'] == sha(PROTOCOL),
            'exact source/design review missing')
    _, custody = audit_inputs(args)
    write(args.out/'freeze.json', {'schema':'heart-outcome-value-freeze-v1','identity':ident,
        'custody':custody,'reviewSha256':sha(args.review),'splits':SPLITS,
        'architecture':'64->64 ReLU->1 sigmoid; frozen Arm C encoder/policy',
        'initializations':[0,1],'steps':STEPS,'evaluateEvery':EVERY,'batch':BATCH,
        'encodingSeconds':3600,'fittingSeconds':600,'testOpeningAuthorized':False})


def trim_record(record):
    record = copy.deepcopy(record)
    if record['obs.mapY'] >= 0:
        keep = [i for i,y in enumerate(record['obs.map.ys']) if y >= record['obs.mapY']]
        for key in ('obs.map.xs','obs.map.ys','obs.map.roomTypes','obs.map.pathXs'):
            record[key] = [record[key][i] for i in keep]
    return record


def has_choices(record):
    return any(record[k] for k in ('cards_offered.cards','relics_offered','potions_offered','fixed_actions','paths_offered'))


def load_net(args, device='cuda'):
    sys.path[:0] = [str(args.silverbot),str(args.silverbot/'build')]
    from silverbot import network
    net = network.NN(network.ModelHP(dim=64,n_layers=2,n_heads=4,mlp_dim_mult=4,use_value_head=True))
    net.load_state_dict(torch.load(args.checkpoint,map_location='cpu',weights_only=True),strict=True)
    return network,net.requires_grad_(False).eval().to(device)


def source_weights(seeds):
    ids,counts = np.unique(np.asarray(seeds),return_counts=True)
    sizes = dict(zip(ids,counts))
    return np.array([1/(len(ids)*sizes[s]) for s in seeds],dtype=np.float64)


def read_sources(args, manifest, split):
    require(split in SPLITS, 'only development splits can be parsed')
    rows = {r['seed']:r for r in manifest if r['split'] == split}
    root = args.import_root/'heart-outcome-collection/deliveries'
    for folder in sorted({r['folder'] for r in rows.values()}):
        expected = sorted(s for s,r in rows.items() if r['folder'] == folder)
        for seed,payload in audit.archive_units(root/folder/(split+'.tar.gz'),split,expected):
            row = rows[seed]; data = payload['.states.jsonl']
            require(audit.digest(data) == row['trajectorySha256']
                    and audit.digest(payload['.receipt.json']) == row['receiptSha256'], 'trajectory/receipt changed')
            parsed = [json.loads(line) for line in data.splitlines()]
            states,footer = parsed[1:-1],parsed[-1]
            require(len(states) == row['states'] and footer['label'] == row['label']
                    and footer['complete'] is True and footer['integrityPassed'] is True, 'audited trajectory changed')
            for i,state in enumerate(states):
                require(state['index'] == i and state['supported'] is True and state['origin'] == 'real-run-driver', 'nonactual state')
                yield {'record':state['record'],'seed':seed,'label':row['label'],
                       'act':state['act'],'screen':state['screen'],'floor':state['floor'],'index':i}


def encode_batch(network, net, rows, companion, device='cuda'):
    require(companion is not None and has_choices(companion), 'genuine TRAIN companion required')
    records = [{**trim_record(r['record']), 'chosen_idx':0, 'outcome':0.} for r in rows]
    # Appended real TRAIN choice has no cross-example attention; discard its output.
    records.append({**trim_record(companion),'chosen_idx':0,'outcome':0.})
    batch = network.move_to_device(network.collate_fn(records),device)
    with torch.inference_mode():
        logits,_,pooled = net(batch,return_pooled=True)
    pooled,logits = pooled[:len(rows)],logits[:len(rows)]
    require(torch.isfinite(pooled).all().item() and not torch.isnan(logits).any().item(), 'nonfinite encoder output')
    return logits,pooled


def encode(args, manifest, split, network, net, companion, deadline):
    features,meta,chunk = [],[],[]
    policy = hashlib.sha256()
    def flush():
        require(time.monotonic() < deadline,'encoding wall cap')
        logits,pooled = encode_batch(network,net,chunk,companion)
        policy.update(logits.cpu().contiguous().numpy().tobytes())
        features.append(pooled.cpu());meta.extend([{k:v for k,v in r.items() if k != 'record'} for r in chunk])
        chunk.clear()
    for row in read_sources(args,manifest,split):
        chunk.append(row)
        if len(chunk) == ENCODE_BATCH:
            flush()
    if chunk: flush()
    x = torch.cat(features)
    require(x.shape == (len(meta),64), 'pooled dimensions changed')
    return x,meta,policy.hexdigest(),companion


class ValueHead(nn.Module):
    def __init__(self, x, weights):
        super().__init__()
        mean = (x.double()*weights[:,None]).sum(0)
        scale = ((x.double()-mean).square()*weights[:,None]).sum(0).sqrt().clamp_min(1e-6)
        self.register_buffer('mean',mean.float());self.register_buffer('scale',scale.float())
        self.layers = nn.Sequential(nn.Linear(64,64),nn.ReLU(),nn.Linear(64,1))

    def forward(self,x):
        return self.layers((x-self.mean)/self.scale).squeeze(1)


def metric(y,p,w,logits=None):
    y,p,w = np.asarray(y,dtype=float),np.asarray(p,dtype=float),np.asarray(w,dtype=float)
    require(len(y) == len(p) == len(w) and np.isfinite(p).all() and ((p>=0)&(p<=1)).all(), 'invalid probabilities')
    w = w/w.sum()
    if logits is None:
        require(((p>0)&(p<1)).all(), 'boundary probabilities require stable logits')
        losses = -y*np.log(p)-(1-y)*np.log1p(-p)
    else:
        logits = np.asarray(logits,dtype=float)
        require(logits.shape == y.shape and np.isfinite(logits).all(), 'invalid logits')
        losses = np.logaddexp(0,logits)-y*logits
    order = np.argsort(p,kind='stable');sy,sp,sw = y[order],p[order],w[order]
    credit,negative = 0.,0.
    starts = np.r_[0, np.flatnonzero(np.diff(sp))+1];ends = np.r_[starts[1:],len(sp)]
    for a,b in zip(starts,ends):
        positive = sw[a:b][sy[a:b] == 1].sum();neg = sw[a:b][sy[a:b] == 0].sum()
        credit += positive*(negative+.5*neg);negative += neg
    pos = float((w*y).sum());neg = 1-pos
    bins = []
    for i in range(10):
        mask = (p >= i/10) & ((p < (i+1)/10) if i<9 else (p <= 1))
        mass = float(w[mask].sum())
        if mass:
            bins.append({'lo':i/10,'weight':mass,'probability':float(np.average(p[mask],weights=w[mask])),
                         'outcome':float(np.average(y[mask],weights=w[mask]))})
    return {'bce':float(np.sum(w*losses)),
        'brier':float(np.sum(w*(p-y)**2)), 'auc':float(credit/(pos*neg)) if pos>0 and neg>0 else None,
        'meanProbability':float(np.sum(w*p)),'outcomeRate':pos,'calibration':bins}


def diagnostics(meta,p,constant,logits):
    seeds = np.array([r['seed'] for r in meta]);y = np.array([r['label'] for r in meta])
    weights = source_weights(seeds)
    result = {'aggregate':metric(y,p,weights,logits),'perSource':{},'byAct':{},'byScreen':{}}
    for seed in sorted(set(seeds)):
        mask = seeds == seed
        result['perSource'][str(seed)] = {k:v for k,v in metric(y[mask],p[mask],weights[mask],logits[mask]).items() if k in ('bce','brier','meanProbability','outcomeRate')}
    for field,dest in [('act','byAct'),('screen','byScreen')]:
        values = np.array([r[field] for r in meta])
        for value in sorted(set(values)):
            mask = values == value
            result[dest][str(value)] = {'states':int(mask.sum()),'sourceMass':float(weights[mask].sum()),
                'model':metric(y[mask],p[mask],weights[mask],logits[mask]),
                'constant':metric(y[mask],np.full(mask.sum(),constant),weights[mask])}
    return result


def bootstrap(meta,p,constant,logits):
    seeds = np.array([r['seed'] for r in meta]);y = np.array([r['label'] for r in meta])
    delta = []
    for seed in sorted(set(seeds)):
        mask = seeds == seed
        m = metric(y[mask],p[mask],np.ones(mask.sum()),logits[mask])
        b = metric(y[mask],np.full(mask.sum(),constant),np.ones(mask.sum()))
        delta.append([m[k]-b[k] for k in ('bce','brier')])
    delta = np.asarray(delta);rng = np.random.default_rng(498)
    samples = delta[rng.integers(0,len(delta),size=(1000,len(delta)))].mean(1)
    return {k:{'mean':float(delta[:,i].mean()),'descriptive95':np.quantile(samples[:,i],[.025,.975]).tolist()}
            for i,k in enumerate(('bce','brier'))}


def train_one(x,y,w,vx,vy,vw,init,deadline,steps=STEPS,every=EVERY):
    torch.manual_seed(init)
    head = ValueHead(x,w).to(x.device)
    with torch.no_grad(): head.layers[-1].bias.fill_(torch.logit((y.double()*w).sum()).item())
    optimizer = torch.optim.AdamW(head.parameters(),lr=.001,weight_decay=.001)
    history,best = [],None
    for step in range(1,steps+1):
        require(time.monotonic() < deadline, 'fitting wall cap')
        ids = torch.multinomial(w,BATCH,replacement=True)
        optimizer.zero_grad(set_to_none=True)
        loss = F.binary_cross_entropy_with_logits(head(x[ids]),y[ids])
        require(torch.isfinite(loss).item(), 'nonfinite fit loss')
        loss.backward();optimizer.step()
        if step % every == 0 or step == steps:
            with torch.inference_mode():
                vl = float((F.binary_cross_entropy_with_logits(head(vx),vy,reduction='none').double()*vw).sum())
                tl = float((F.binary_cross_entropy_with_logits(head(x),y,reduction='none').double()*w).sum())
            require(math.isfinite(vl) and math.isfinite(tl),'nonfinite evaluation')
            history.append({'step':step,'trainBce':tl,'validationBce':vl})
            if best is None or vl < best['validationBce']:
                best = {**history[-1],'state':{k:v.detach().cpu().clone() for k,v in head.state_dict().items()}}
    return best,history


def run(args):
    frozen = json.loads((args.out/'freeze.json').read_text())
    require(frozen['identity'] == identity(args), 'frozen implementation/runtime changed')
    require(sha(args.review) == frozen['reviewSha256'], 'source approval changed')
    manifest,custody = audit_inputs(args)
    require(custody == frozen['custody'] and frozen['splits'] == SPLITS, 'frozen inputs changed')
    write(args.out/'cache-started.json',{'freezeSha256':sha(args.out/'freeze.json'),'pid':os.getpid()})
    started = time.monotonic();deadline = started+frozen['encodingSeconds']
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False;torch.backends.cudnn.allow_tf32 = False
    network,net = load_net(args)
    before = {k:v.detach().cpu().clone() for k,v in net.state_dict().items()}
    companion_row = next(r for r in read_sources(args,manifest,'train') if has_choices(r['record']))
    companion = companion_row['record']
    companion_identity = {k:companion_row[k] for k in ('seed','index')}
    companion_identity['recordSha256'] = audit.digest(json.dumps(companion,sort_keys=True).encode())
    cache = {}
    for split in SPLITS:
        print('encoding',split,flush=True)
        x,meta,policy,companion = encode(args,manifest,split,network,net,companion,deadline)
        cache[split] = {'x':x,'meta':meta,'policySha256':policy}
        print('encoded',split,len(meta),'seconds',round(time.monotonic()-started,2),flush=True)
    torch.save(cache,args.out/'pooled.pt')
    write(args.out/'cache.json',{'pooledSha256':sha(args.out/'pooled.pt'),'freezeSha256':sha(args.out/'freeze.json'),
        'counts':{k:len(v['meta']) for k,v in cache.items()},'companion':companion_identity,'seconds':time.monotonic()-started})
    write(args.out/'fit-started.json',{'freezeSha256':sha(args.out/'freeze.json'),'pooledSha256':sha(args.out/'pooled.pt')})
    fit_start = time.monotonic();fit_deadline = fit_start+frozen['fittingSeconds']
    tx,vx = (cache[k]['x'].cuda() for k in SPLITS)
    ty,vy = (torch.tensor([r['label'] for r in cache[k]['meta']],device='cuda',dtype=torch.float32) for k in SPLITS)
    tw,vw = (torch.tensor(source_weights([r['seed'] for r in cache[k]['meta']]),device='cuda') for k in SPLITS)
    constant = float((ty.double()*tw).sum())
    selected,candidates = None,[]
    for init in frozen['initializations']:
        best,history = train_one(tx,ty,tw,vx,vy,vw,init,fit_deadline)
        state = best.pop('state')
        torch.save(state,args.out/f'candidate-{init}.pt')
        candidates.append({'init':init,**best,'history':history,'sha256':sha(args.out/f'candidate-{init}.pt')})
        print('candidate',json.dumps({k:v for k,v in candidates[-1].items() if k != 'history'}),flush=True)
        if selected is None or best['validationBce'] < selected['validationBce']:
            selected = {'init':init,**best,'state':state}
    state = selected.pop('state');head = ValueHead(tx,tw).cuda();head.load_state_dict(state,strict=True);head.eval()
    require(time.monotonic() < fit_deadline,'fitting wall cap')
    fit_seconds = time.monotonic()-fit_start
    with torch.inference_mode():
        tlogits,vlogits = (head(x).cpu().numpy() for x in (tx,vx))
        tp,vp = (torch.sigmoid(torch.from_numpy(z)).numpy() for z in (tlogits,vlogits))
    # Re-encode the entire validation cohort under identical fixed batching.
    repeated,meta,policy,_ = encode(args,manifest,'validation',network,net,companion,deadline+fit_seconds)
    require(meta == cache['validation']['meta'] and torch.equal(repeated,cache['validation']['x'])
            and policy == cache['validation']['policySha256'],'encoder/policy forward parity failed')
    require(all(torch.equal(v.detach().cpu(),before[k]) for k,v in net.state_dict().items()),'Arm C tensor changed')
    with torch.inference_mode(): diff = float((torch.sigmoid(head(repeated.cuda()))-torch.tensor(vp,device='cuda')).abs().max())
    require(diff <= 1e-6,'composed vs cached head mismatch')
    torch.save({'valueHead':state,'encoderCheckpointSha256':CHECKPOINT,'freezeSha256':sha(args.out/'freeze.json')},args.out/'value-head.pt')
    write(args.out/'head.json',{k:v.tolist() for k,v in state.items()})
    val = diagnostics(meta,vp,constant,vlogits)
    require(abs(val['aggregate']['bce']-selected['validationBce']) < 1e-6,'reported BCE differs from selection loss')
    baseline = metric(vy.cpu().numpy(),np.full(len(vy),constant),vw.cpu().numpy())
    _,custody_after = audit_inputs(args)
    require(custody_after == custody and frozen['identity'] == identity(args),'inputs/runtime changed during run')
    report = {'schema':'heart-outcome-value-result-v1','verdict':'VALIDATION_ONLY','selected':selected,
        'developmentSignal':all(val['aggregate'][k] < baseline[k] for k in ('bce','brier')),
        'train':diagnostics(cache['train']['meta'],tp,constant,tlogits),'validation':val,
        'constant':{'probability':constant,'validation':baseline},'pairedSourceBootstrap':bootstrap(meta,vp,constant,vlogits),
        'candidates':candidates,'parameters':sum(p.numel() for p in head.parameters()),
        'companion':companion_identity,'frozenTensors':len(before),'frozenTensorsBitwiseEqual':True,'pooledBitwiseEqual':True,
        'policyLogitsBitwiseEqual':True,'validationPolicySha256':policy,'composedValueMaxAbs':diff,
        'encodingAndParitySeconds':time.monotonic()-started-fit_seconds,'fittingSeconds':fit_seconds,
        'checkpointSha256':sha(args.out/'value-head.pt'),'headSha256':sha(args.out/'head.json'),
        'pooledSha256':sha(args.out/'pooled.pt'),'freezeSha256':sha(args.out/'freeze.json'),
        'testRead':False,'nativeIntegration':False,'runtimePromotion':False,'gameplayQualified':False,
        'sealedArchivesHashedOnly':53}
    write(args.out/'result.json',report)
    print(json.dumps({'verdict':report['verdict'],'selected':selected,'validation':val['aggregate'],
                      'baseline':baseline,'developmentSignal':report['developmentSignal']}),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('freeze','run'))
    for name in ('import-root','checkpoint','silverbot','review','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args = p.parse_args()
    try:
        freeze(args) if args.command == 'freeze' else run(args)
    except Exception as exc:
        if args.out.is_dir() and not (args.out/'failure.json').exists():
            write(args.out/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
        raise


if __name__ == '__main__':
    main()
