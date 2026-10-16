"""Bounded offline rollout3 compression. No trajectory generation or runtime loading.

Subcommands: fit DATA_ROOT OUT; test DATA_ROOT OUT. TEST is never read by fit.
Features are built exclusively from candidate-public-leaf-v1 input plus the
explicit X2-B residual baseline. All paths and source splits come from freeze.json.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import platform
import sklearn
import time

import numpy as np
from sklearn.feature_extraction import DictVectorizer
import torch
from torch import nn
from heart_record_encoder import encode_record, pack_tokens
from heart1_leaf_reference import predict_reference


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_row(r,seed):
    if r['seed']!=seed: raise ValueError('cross-source row')
    e=r.get('extra',{}); reps=e.get('repeats',[])
    if (len(reps)!=64 or any('value' not in v for v in reps) or 'record' not in e or 'x2b' not in e
            or e.get('recordSchema')!='heart1-public-record-v2' or e.get('recordPublicParityQualified') is not False):
        return None
    vals=[float(v['value']) for v in reps]
    if any(not math.isfinite(v) or not 0<=v<=1 for v in vals+[float(e['x2b']),float(r['value'])]): return None
    cpu=float(e.get('rolloutCpuSeconds',0)); anchor=float(e.get('anchorCpuSeconds',-1))
    if not math.isfinite(cpu) or cpu<=0 or not math.isfinite(anchor) or anchor<0: return None
    try: f,tokens=encode_record(e['record'])
    except (KeyError,ValueError,TypeError): return None
    return {'seed':seed,'group':(seed,r['decision'],r['parent']),'action':r['action'],
        'screen':r['parentScreen'],'act':r['act'],'floor':r['floor'],'target':float(np.mean(vals)),
        'variance':float(np.var(vals,ddof=1)/64),'x2b':float(e['x2b']),'r0':float(r['value']),
        'cpu':cpu/64,'anchorCpu':anchor,'features':f,'tokens':tokens,'record':e['record']}


def validate_rows(raw,seed):
    rows=[]; bad=set(); seen=set(); count=0
    for r in raw:
        count+=1; identity=(r['decision'],r['ordinal'])
        if identity in seen: raise ValueError('duplicate capture ordinal')
        seen.add(identity); group=(seed,r['decision'],r['parent'])
        row=validate_row(r,seed)
        if row is None: bad.add(group)
        else: rows.append(row)
    # Complete means every retained captured sibling is valid, not exhaustive legal-action coverage.
    rows=[r for r in rows if r['group'] not in bad]
    groups=defaultdict(list)
    for i,r in enumerate(rows): groups[r['group']].append(i)
    groups=[g for g in groups.values() if len({rows[i]['action'] for i in g})>=2]
    return rows,groups,{'raw':count,'accepted':len(rows),'rejected':count-len(rows),
                        'groups':len(groups),'invalidGroups':len(bad)}


def verify_bundle(root,freeze):
    bundle=root/'run'
    if sha(bundle/'one_combat')!=freeze['binarySha256']:raise ValueError('frozen binary changed')
    for rel,digest in freeze['models'].items():
        if sha(bundle/rel)!=digest:raise ValueError('frozen model changed')
    if sha(bundle/'opus490.pt')!=freeze['opus490CheckpointSha256']:raise ValueError('frozen Opus reference changed')
    if sha(root/'build-receipt.json')!=freeze['buildReceiptSha256']:raise ValueError('build receipt changed')
    if sha(bundle/'PROTOCOL.md')!=freeze['protocolSha256']:raise ValueError('protocol changed')


def verify_corpus(root,freeze,split=None):
    manifest=json.loads((root/'corpus-manifest.json').read_text())
    seeds=freeze['splits'][split] if split else sum(freeze['splits'].values(),[])
    for seed in seeds:
        expected=manifest['sources'][str(seed)]; base=root/f'seed-{seed}'
        receipt=base.with_suffix('.receipt.json'); capture=base.with_suffix('.sib.jsonl')
        if sha(receipt)!=expected['receiptSha256'] or sha(capture)!=expected['captureSha256']:
            raise ValueError('corpus custody changed: '+str(seed))
        r=json.loads(receipt.read_text())
        if r['returncode']!=0 or r['captureSha256']!=expected['captureSha256'] or r['seed']!=seed:
            raise ValueError('invalid source receipt')
    return sha(root/'corpus-manifest.json')


def load_split(root,freeze,split):
    rows=[]; groups=[]; totals=Counter(); per={}; strata=Counter()
    for seed in freeze['splits'][split]:
        path=(root/f'seed-{seed}').with_suffix('.sib.jsonl')
        source,sg,counts=validate_rows((json.loads(line) for line in path.open()),seed)
        offset=len(rows); groups += [[offset+i for i in g] for g in sg]; rows+=source
        per[str(seed)]=counts
        for k,v in counts.items():totals[k]+=v
        for r in source:
            keys=','.join(map(str,r['record']['obs.fixed_observation'][7:10]))
            strata[f"act={r['act']};screen={r['screen']};keys={keys}"]+=1
    cov=dict(totals);cov['sourcesWithGroups']=sum(c['groups']>0 for c in per.values())
    cov['expectedSources']=len(freeze['splits'][split]);cov['perSource']=per;cov['strata']=dict(strata)
    return rows,groups,cov


def metrics(rows,groups,pred):
    seeds=defaultdict(lambda: defaultdict(list))
    for i,r in enumerate(rows): seeds[r['seed']]['mse'].append((float(pred[i])-r['target'])**2)
    for ids in groups:
        actions=defaultdict(list)
        for i in ids: actions[rows[i]['action']].append(i)
        action_rows=list(actions.values())
        t=np.array([np.mean([rows[i]['target'] for i in g]) for g in action_rows])
        p=np.array([np.mean([pred[i] for i in g]) for g in action_rows])
        source=seeds[rows[ids[0]]['seed']]
        source['regret'].append(float(t.max()-t[p.argmax()]))
        concord=[]
        for i in range(len(t)):
            for j in range(i):
                if abs(t[i]-t[j])<=1e-8: continue
                concord.append(.5 if p[i]==p[j] else float((p[i]-p[j])*(t[i]-t[j])>0))
        if concord: source['concordance'].append(float(np.mean(concord)))
    per={str(k):{m:float(np.mean(v)) for m,v in d.items()} for k,d in seeds.items()}
    agg={k:float(np.mean([d.get(k,.5 if k=='concordance' else 0.) for d in per.values()])) for k in ('mse','regret','concordance')}
    return {'aggregate':agg,'perSource':per}


class Net(nn.Module):
    def __init__(self,n,variant):
        super().__init__(); self.variant=variant
        extra=0
        if variant!='counts':
            self.kind=nn.Embedding(11,64,padding_idx=0)
            self.entity=nn.Embedding(1536,64)
            self.attrs=nn.Linear(8,64,bias=False)
            extra=64
            if variant=='attention':
                layer=nn.TransformerEncoderLayer(64,4,128,dropout=0,batch_first=True,norm_first=True)
                self.encoder=nn.TransformerEncoder(layer,2,enable_nested_tensor=False)
                self.cls=nn.Parameter(torch.zeros(1,1,64))
        self.layers=nn.Sequential(nn.Linear(n+extra,128),nn.ReLU(),nn.Linear(128,128),nn.ReLU(),nn.Linear(128,1))
    def forward(self,x,base,kinds=None,entities=None,attrs=None):
        if self.variant!='counts':
            valid=kinds!=0
            t=self.kind(kinds)+self.entity(entities)+self.attrs(attrs)
            if self.variant=='attention':
                cls=self.cls.expand(len(x),-1,-1)
                t=torch.cat([cls,t],dim=1)
                mask=torch.cat([torch.zeros(len(x),1,dtype=torch.bool,device=x.device),~valid],dim=1)
                h=self.encoder(t,src_key_padding_mask=mask)[:,0]
            else:
                h=(t*valid.unsqueeze(-1)).sum(1)/valid.sum(1,keepdim=True).clamp(min=1)
            x=torch.cat([x,h],dim=1)
        return torch.sigmoid(self.layers(x).squeeze(1)+torch.logit(base.clamp(.0001,.9999)))


def check_tensor_bound(row_sets, vocabulary_size):
    # Include the temporary dense transform copy as well as final packed tensors.
    estimated=sum(len(rs)*(2*vocabulary_size*4+max(len(r["tokens"]) for r in rs)*48+8)
                  for rs in row_sets if rs)
    if estimated>2*1024**3:
        raise RuntimeError("frozen2GiB tensor CPU bound before allocation")
    return estimated


def tensor_rows(rows,vectorizer):
    x=torch.from_numpy(vectorizer.transform([r['features'] for r in rows]).astype(np.float32))
    return (x,torch.tensor([r['x2b'] for r in rows]),torch.tensor([r['target'] for r in rows]),
            *[torch.from_numpy(a) for a in pack_tokens(rows)])


def save_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def runtime_identity():
    import numpy.core._multiarray_umath as np_core
    import sklearn.utils._openmp_helpers as sk_core
    files=[Path(sys.executable).resolve(),Path(torch.__file__),Path(torch._C.__file__),
           Path(np.__file__),Path(np_core.__file__),Path(sklearn.__file__),Path(sk_core.__file__)]
    return {'python':sys.version,'platform':platform.platform(),'torch':torch.__version__,
            'cudaBuild':torch.version.cuda,'numpy':np.__version__,'sklearn':sklearn.__version__,
            'tf32Matmul':torch.backends.cuda.matmul.allow_tf32,'tf32Cudnn':torch.backends.cudnn.allow_tf32,
            'deterministicAlgorithms':torch.are_deterministic_algorithms_enabled(),
            'defaultDtype':str(torch.get_default_dtype()),
            'files':{str(p):sha(p) for p in files}}


def verify_tools(freeze):
    for path,digest in freeze['toolHashes'].items():
        if sha(path)!=digest: raise ValueError('frozen tool identity changed: '+path)
    if runtime_identity()!=freeze['runtime']:raise ValueError('frozen Python/dependency identity changed')


def fit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    freeze=json.loads((root/'freeze.json').read_text()); verify_tools(freeze)
    verify_bundle(root,freeze)
    corpus_sha=verify_corpus(root,freeze)
    train,tg,tc=load_split(root,freeze,'train'); val,vg,vc=load_split(root,freeze,'validation')
    save_json(out/'coverage.json',{'train':tc,'validation':vc,'freezeSha256':sha(root/'freeze.json')})
    if len(tg)<500 or len(vg)<100 or any(c['accepted']<.8*c['raw'] or c['sourcesWithGroups']!=c['expectedSources'] for c in (tc,vc)):
        save_json(out/'verdict.json',{'verdict':'INSUFFICIENT','reason':'predeclared training/validation coverage gate'})
        return
    vectorizer=DictVectorizer(sparse=False,dtype=np.float32)
    vectorizer.fit([r['features'] for r in train]) # vocabulary fits TRAIN only
    save_json(out/'vocabulary.json',list(vectorizer.get_feature_names_out()))
    check_tensor_bound((train,val),len(vectorizer.vocabulary_))
    tx,tb,ty,tk,te,ta=tensor_rows(train,vectorizer); vx,vb,vy,vk,ve,va=tensor_rows(val,vectorizer)
    device='cuda' if torch.cuda.is_available() else 'cpu'; torch.set_num_threads(2)
    cpu_bytes=sum(t.numel()*t.element_size() for t in (tx,tb,ty,tk,te,ta,vx,vb,vy,vk,ve,va))
    width=max(tk.shape[1],vk.shape[1]);gpu_est=512*4*width*width*4*2+1024**3
    save_json(out/'resources.json',{'tensorCpuBytes':cpu_bytes,'conservativeGpuBytes':gpu_est})
    if cpu_bytes>2*1024**3:raise RuntimeError('frozen2GiB tensor CPU bound')
    if device=='cuda' and gpu_est>min(4*1024**3,.8*torch.cuda.mem_get_info()[0]):
        raise RuntimeError('frozen GPU memory bound; no adaptive batch/model change')
    best=None; logs=[]; started=time.monotonic()
    for variant in ('counts','pool','attention'):
      for init in (0,1):
        torch.manual_seed(init); rng=random.Random(init)
        net=Net(tx.shape[1],variant).to(device)
        opt=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.0001)
        for epoch in range(30):
            net.train(); order=list(tg); rng.shuffle(order); chunks=[]; current=[]
            for group in order:
                if len(group)>512:raise RuntimeError("parent group exceeds frozen batch bound")
                if current and sum(map(len,current))+len(group)>512:chunks.append(current);current=[]
                current.append(group)
                if sum(map(len,current))==512: chunks.append(current); current=[]
            if current: chunks.append(current)
            for gs in chunks:
                ids=[i for g in gs for i in g]; idx=torch.tensor(ids)
                p=net(*[t[idx].to(device) for t in (tx,tb,tk,te,ta)]); y=ty[idx].to(device); loss=((p-y)**2).mean()
                # Identical ranking-aware objective across representations.
                pieces=[]; offset=0
                for g in gs:
                    n=len(g); d=p[offset:offset+n]-y[offset:offset+n]
                    pieces.append((d-d.mean())**2); offset+=n
                loss=torch.cat(pieces).mean()+.1*loss
                opt.zero_grad(); loss.backward(); opt.step()
            net.eval()
            with torch.no_grad():
                pred=np.concatenate([net(*[t[i:i+128].to(device) for t in (vx,vb,vk,ve,va)]).cpu().numpy() for i in range(0,len(val),128)])
            for weight in (.25,.5,.75,1.):
                blend=weight*pred+(1-weight)*np.array([r['x2b'] for r in val])
                m=metrics(val,vg,blend); a=m['aggregate']
                key=(round(a['regret'],6),a['mse'],sum(p.numel() for p in net.parameters()))
                if best is None or key<best['key']:
                    best={'key':key,'variant':variant,'init':init,'epoch':epoch+1,'weight':weight,
                          'state':copy.deepcopy({k:v.cpu() for k,v in net.state_dict().items()}),'validation':m}
            logs.append({'variant':variant,'init':init,'epoch':epoch+1,'mse':float(((pred-np.array([r['target'] for r in val]))**2).mean())})
            if time.monotonic()-started>1200: raise RuntimeError('frozen training time cap exceeded')
        print(f'finished {variant} init={init}; selected regret={best["key"][0]}',flush=True)
    state=best.pop('state'); torch.save(state,out/'selected.pt')
    save_json(out/'training.json',logs)
    save_json(out/'selection.json',{**best,'inputDim':tx.shape[1],'device':device,'seconds':time.monotonic()-started,
        'checkpointSha256':sha(out/'selected.pt'),'vocabularySha256':sha(out/'vocabulary.json'),
        'freezeSha256':sha(root/'freeze.json'),'baseline':metrics(val,vg,[r['x2b'] for r in val]),
        'toolSha256':sha(__file__),'corpusManifestSha256':corpus_sha,'runtime':freeze['runtime']})


def candidate_passes(student,baseline,ci,speedup):
    return (student['concordance']>=baseline['concordance']+.02
            and student['regret']<=.9*baseline['regret'] and ci[0]>0
            and math.isfinite(speedup) and speedup>=4)


def test(root,out):
    # Verify frozen identities before the irreversible TEST opening. No retry.
    freeze=json.loads((root/'freeze.json').read_text()); selection=json.loads((out/'selection.json').read_text())
    for p,k in [('selected.pt','checkpointSha256'),('vocabulary.json','vocabularySha256')]:
        if sha(out/p)!=selection[k]: raise ValueError('selected artifact changed')
    if sha(root/'freeze.json')!=selection['freezeSha256'] or sha(__file__)!=selection['toolSha256']:
        raise ValueError('freeze/tool identity changed')
    verify_tools(freeze);verify_bundle(root,freeze)
    if sha(root/'corpus-manifest.json')!=selection['corpusManifestSha256']:
        raise ValueError('corpus manifest changed after selection')
    verify_corpus(root,freeze,'test') # hashes/receipts only; no TEST JSONL parse
    with (out/'test-opened.json').open('x') as f:
        json.dump({'selectionSha256':sha(out/'selection.json')},f)
    rows,groups,cov=load_split(root,freeze,'test')
    if not rows or cov['groups']<200 or cov['accepted']<.8*cov['raw'] or cov['sourcesWithGroups']!=cov['expectedSources']:
        save_json(out/'test-result.json',{'verdict':'INSUFFICIENT','coverage':cov,'runtimePromotion':False})
        return
    vocab=json.loads((out/'vocabulary.json').read_text()); v=DictVectorizer(sparse=False,dtype=np.float32)
    v.vocabulary_={k:i for i,k in enumerate(vocab)}; v.feature_names_=vocab
    check_tensor_bound((rows,),len(vocab))
    x,b,y,k,e,token_attrs=tensor_rows(rows,v); torch.set_num_threads(1)
    net=Net(len(vocab),selection['variant']); net.load_state_dict(torch.load(out/'selected.pt',weights_only=True)); net.eval()
    with torch.no_grad(): pred=np.concatenate([net(x[i:i+128],b[i:i+128],k[i:i+128],e[i:i+128],token_attrs[i:i+128]).numpy() for i in range(0,len(rows),128)])
    weight=selection['weight']; pred=weight*pred+(1-weight)*b.numpy()
    student=metrics(rows,groups,pred); baseline=metrics(rows,groups,b.numpy())
    sources=freeze['splits']['test']; deltas=[]
    for seed in sources:
        baseline_source=baseline['perSource'].get(str(seed),{})
        student_source=student['perSource'].get(str(seed),{})
        if 'regret' in baseline_source and 'regret' in student_source:
            deltas.append(baseline_source['regret']-student_source['regret'])
    rng=np.random.default_rng(20261016)
    boot=np.array([np.mean(rng.choice(deltas,len(deltas),replace=True)) for _ in range(2000)]) if deltas else np.array([0.])
    ci=np.quantile(boot,[.025,.975]).tolist()
    with torch.no_grad():
        for _ in range(100): net(x[:1],b[:1],k[:1],e[:1],token_attrs[:1])
        begin=time.process_time()
        for _ in range(1000): net(x[:1],b[:1],k[:1],e[:1],token_attrs[:1])
        latency=(time.process_time()-begin)/1000
        begin=time.process_time()
        for _ in range(100): net(x[:32],b[:32],k[:32],e[:32],token_attrs[:32])
        latency32=(time.process_time()-begin)/100/32
    begin=time.process_time()
    for r in rows[:100]:
        f,tokens=encode_record(r['record']); v.transform([f]); pack_tokens([{'tokens':tokens}])
    feature_cpu=(time.process_time()-begin)/min(100,len(rows))
    cpu=float(np.mean([r['cpu'] for r in rows])); anchor_cpu=float(np.mean([r['anchorCpu'] for r in rows]))
    speedup=cpu/(latency+feature_cpu+anchor_cpu)
    opus_pred=np.asarray(predict_reference(root/'run/opus490.pt',rows))
    opus=metrics(rows,groups,opus_pred)
    domains=defaultdict(list)
    for i,row in enumerate(rows):
        record=row['record']
        domain=('battle' if record['screen_state']==9 else
                'memory_game' if 'leaf.matchSlots' in record else 'original_heart1')
        domains[domain].append(i)
    domain_diagnostics={}
    for domain,ids in domains.items():
        domain_diagnostics[domain]={'rows':len(ids),'sources':len({rows[i]['seed'] for i in ids})}
        for name,values in [('student',pred),('x2b',b.numpy()),('opus490',opus_pred)]:
            domain_diagnostics[domain][name+'Mse']=float(np.mean([(values[i]-rows[i]['target'])**2 for i in ids]))
    sa=student['aggregate']; ba=baseline['aggregate']
    enough=cov['groups']>=200 and cov['accepted']>=.8*cov['raw'] and len(deltas)==len(sources)
    passed=enough and candidate_passes(sa,ba,ci,speedup)
    verdict='OFFLINE_CANDIDATE' if passed else ('NOT_SHOWN' if enough else 'INSUFFICIENT')
    save_json(out/'test-result.json',{'verdict':verdict,'coverage':cov,'student':student,'baseline':baseline,'opus490FrozenReference':opus,'scheduledRolloutBaseline':metrics(rows,groups,[r['r0'] for r in rows]),
        'fixedHalfRolloutHybrid':metrics(rows,groups,.5*pred+.5*np.array([r['r0'] for r in rows])),
        'domainMseDiagnostics':domain_diagnostics,'regretImprovement95CI':ci,'meanRolloutCpuSeconds':cpu,'tensorInferenceCpuSeconds':latency,
        'tensorInferenceCpuSecondsBatch32PerRow':latency32,'featureEncodingCpuSeconds':feature_cpu,
        'requiredX2bCpuSeconds':anchor_cpu,'pythonFeatureAndInferenceSpeedup':speedup,
        'tensorOnlySpeedup':cpu/latency if latency else None,
        'nativeSpeedupQualified':False,'heartWinPredictionQualified':False,'runtimePromotion':False})
    print(verdict,flush=True)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('mode',choices=['fit','test']); ap.add_argument('data',type=Path); ap.add_argument('out',type=Path)
    a=ap.parse_args(); (fit if a.mode=='fit' else test)(a.data,a.out)

if __name__=='__main__': main()
