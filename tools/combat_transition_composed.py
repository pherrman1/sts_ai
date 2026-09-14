#!/usr/bin/env python3
"""Frozen offline ancestral combat sampler. No labels, training or runtime adapter."""
from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from tools import combat_transition_surrogate as base
from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_stochastic_hp as hp
from tools import combat_transition_potion_decoder as potion
from tools import combat_transition_frozen_composition as frozen
from tools import combat_transition_relic_legality as relic
from tools import combat_transition_relic_trajectory as trajectory
from tools import combat_transition_rng_audit as native_rng
from tools.combat_transition_contract import validate_state

BASELINE = '7316c715bac7fe4559ead59cde1eb374d3437b5b'
RUNS = Path('/home/philippherrmann/sts_sweep/runs')
ARTIFACTS = {
    'survival': (RUNS/'frozen-survival-potion-20260913/point_control_attention.pt', '2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef'),
    'max_hp': (RUNS/'frozen-survival-potion-20260913/phase2_attention.pt', '66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479'),
    'hp': (RUNS/'stochastic-hp-20260914/20260912.pt', trajectory.HP_HASH),
    'potion': (RUNS/'joint-potion-mask-20260913/joint.pt', trajectory.POTION_HASH),
    'potion_encoder': (RUNS/'joint-potion-mask-20260913/encoder.pt', trajectory.ENCODER_HASH),
    'relic': (RUNS/'relic-trajectory-20260914/relic-20260912-0.pt', 'e07e79d487152ae294f4915ef4aecd0e8bd38b8dec8d0133a57b6b58af92bd71'),
}
CLASSES = np.arange(-160, 144, dtype=np.int64)
TRAINED_GROUPS = ('turns', 'attacks', 'cards', 'shuffles')
INPUT_KEYS = ('globals_continuous', 'global_categories', 'cards', 'relics', 'potions', 'card_mask', 'relic_mask')
RECIPE = dict(schema='offline_composed_transition_v1', baseline=BASELINE,
              training=False, artifactSeedConvention=20260912,
              partition='original source-grouped reused engineering TEST',
              corpusSha256=native_rng.FROZEN_SHA, splitSha256=attention.EXPECTED_SPLIT_SHA256,
              draws=32, samplingSeed=20260916, bootstrapSeed=20260917, bootstrapReps=1000,
              exposureThreshold=.1, hpExposureEstimator='exact weighted marginal over all maxHP classes',
              hpMonteCarloRole='32-draw diagnostic only; never used for classification', relicAggregation='mean row gap / observed learned groups on informative rows',
              evaluationPrecision='historical survival/maxHP/potion FP32 MHA fastpath enabled; HP AMP FP16 MHA fastpath disabled; relic FP32',
              latencyPrecision='one-thread CPU FP32, batch 1, full visible encoding, 10 warmups, 100 draws per path',
              rngScope='OOC continuation: copy potionRng and exact replay_misc; omit four recreated battle-local streams')


def verify_hashes(artifacts=ARTIFACTS):
    hashes = {}
    for name, (path, expected) in artifacts.items():
        actual = base.sha256(Path(path))
        if actual != expected:
            raise ValueError(f'frozen artifact hash mismatch: {name}')
        hashes[name] = actual
    return hashes


def visible_arrays(predictor_input):
    # Bookkeeping is constant and labels are absent. The historical encoder only
    # reads post HP for a victory; this dummy death avoids reading any true post.
    row = dict(predictorInput=predictor_input, sourceSeed=0, fightIdx=0,
               transition=dict(combatOutcome=base.DEATH, post={}))
    encoded = base._encode_row(row)
    return {k: v[None] for k, v in zip(INPUT_KEYS, encoded[:7])}


@contextmanager
def attention_backend(torch,enabled):
    """Preserve historical per-component inference arithmetic, restoring global state."""
    previous=torch.backends.mha.get_fastpath_enabled()
    torch.backends.mha.set_fastpath_enabled(enabled)
    try:
        yield
    finally:
        torch.backends.mha.set_fastpath_enabled(previous)


def rng_valid(state):
    return (isinstance(state, dict) and set(state) == {'seed0', 'seed1', 'counter'}
            and all(type(state[k]) is int and 0 <= state[k] <= native_rng.MASK for k in ('seed0', 'seed1'))
            and type(state['counter']) is int and 0 <= state['counter'] <= 2147483647
            and (state['seed0'] != 0 or state['seed1'] != 0))


def full_support_reasons(pre, predictor_input, models):
    """Before survival, using only visible pre-state and verified loaded recipe."""
    if not models.ready:
        return ['artifacts_not_loaded']
    try:
        validate_state(pre,'pre')
        reasons = base.supported_reasons(predictor_input, pre)
        if not frozen.potion_consumption_only(predictor_input):
            reasons.append('potion_not_certified')
        for key in base.PERSISTENT_KEYS:
            if key not in pre:
                reasons.append('missing_persistent_field')
        if reasons:
            return reasons
        g = predictor_input['globals']
        if (pre['curHp'], pre['maxHp'], pre['potionCapacity'], pre['potionCount']) != tuple(g[k] for k in ('curHp','maxHp','potionCapacity','potionCount')):
            return ['visible_pre_mismatch']
        if [(x['id'],x['data']) for x in pre['relics']] != [(x['relicId'],x['data']) for x in predictor_input['relics']]:
            return ['visible_relic_mismatch']
        if pre['potions'] != [x['potionId'] for x in predictor_input['potions']]:
            return ['visible_potion_mismatch']
        potion.legal_masks(np.asarray([pre['potions']]),np.asarray([pre['potionCapacity']]))
        if sum(x > 1 for x in pre['potions']) != pre['potionCount']:
            return ['potion_count']
        if (not np.array_equal(models.classes,CLASSES) or
                not 1 <= pre['curHp'] <= pre['maxHp']):
            return ['hp_domain']
        # Frozen pre-state envelope, rather than accepting out-of-envelope HP.
        envelope = models.domain
        if not envelope['preCurHpRange'][0] <= pre['curHp'] <= envelope['preCurHpRange'][1] or not envelope['preMaxHpRange'][0] <= pre['maxHp'] <= envelope['preMaxHpRange'][1]:
            return ['hp_envelope']
        if not np.array_equal(models.delta_values,envelope['maxHpDeltaValues']):
            return ['max_hp_domain']
        for delta in models.delta_values:
            if type(delta.item()) is not int or pre['maxHp']+delta <= 0:
                return ['max_hp_state']
            hp.legal_support(models.classes,np.asarray([pre['curHp']]),np.asarray([pre['maxHp']+delta]))
        bloom = any(x['id']==base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
        for entry in pre['relics']:
            rid = entry['id']
            if rid in base.CODE_AUDITED_MUTABLE_RELIC_IDS and rid not in relic.NAMES:
                return ['unknown_mutable_relic']
            name = relic.NAMES.get(rid)
            if name is None:
                continue
            allowed = relic.legal_posts(rid,entry['data'],g['encounter'],bloom)
            if name=='LIZARD_TAIL' and len(allowed)>1:
                return ['active_unqualified_lizard']
            if name in relic.TRAJECTORY and relic.TRAJECTORY[name][0] not in models.trained_groups:
                return ['untrained_trajectory']
        streams = pre['combatRng']
        if len(streams)!=6 or not all(rng_valid(streams[i]) for i in (2,4)):
            return ['inherited_rng']
        if not 0 < g['encounter'] < len(models.encounter_names):
            return ['encounter_domain']
        return []
    except (ValueError,KeyError,TypeError,IndexError,AttributeError):
        return ['invalid_pre_state']


def categorical(probabilities, rng):
    p=np.asarray(probabilities,dtype=np.float64)
    if p.ndim!=1 or np.any(p<0) or not np.isfinite(p).all() or not np.isclose(p.sum(),1,atol=1e-6):
        raise ValueError('invalid categorical distribution')
    return int(rng.choice(len(p),p=p/p.sum()))


def mixture_nll_from_probabilities(draw_probabilities):
    p=np.asarray(draw_probabilities,dtype=float)
    if p.ndim!=2 or np.any(p<0) or np.any(p>1+1e-6) or not np.isfinite(p).all():
        raise ValueError('invalid observed mixture probabilities')
    with np.errstate(divide='ignore'):
        return -np.log(p.mean(axis=0))


def exact_hp_marginal(max_hp_probabilities, conditional_target_probabilities):
    """Sum P(maxHP class) * P(observed signed HP | class), including legal zeros."""
    weights=np.asarray(max_hp_probabilities,dtype=np.float64)
    conditional=np.asarray(conditional_target_probabilities,dtype=np.float64)
    if (weights.ndim!=2 or weights.shape!=conditional.shape or weights.shape[1]==0
            or not np.isfinite(weights).all() or not np.isfinite(conditional).all()
            or np.any(weights<0) or np.any(conditional<0) or np.any(conditional>1+1e-6)
            or not np.allclose(weights.sum(-1),1,atol=1e-6)):
        raise ValueError('invalid exact HP marginal inputs')
    return np.sum(weights*conditional,axis=-1)


def classify(exposure_gaps,validity,provenance=True,reproduction=True):
    if not provenance or not reproduction or any(validity.values()) or any(x>.1 for x in exposure_gaps.values()):
        return 'COMPOSED_TRANSITION_REJECTED'
    if any(not np.isfinite(x) for x in exposure_gaps.values()):
        return 'COMPOSED_TRANSITION_INCONCLUSIVE'
    return 'COMPOSED_TRANSITION_QUALIFIED'


@dataclass
class Transition:
    outcome: str
    post_state: dict | None = None
    reasons: tuple = ()


class FrozenModels:
    """Loaded fixed historical networks. Heads are used without model refactors."""
    def __init__(self, device='cpu'):
        import torch
        self.ready=False
        self.hashes=verify_hashes()  # enforce every hash before deserialization
        self.torch=torch
        self.device=device
        payload={k:torch.load(p,map_location='cpu',weights_only=False) for k,(p,_) in ARTIFACTS.items()}
        spec=payload['max_hp']['targetSpec']
        self.delta_values=np.asarray(spec['maxHpDeltaValues'],dtype=np.int64)
        self.classes=payload['hp']['state_dict']['classes'].numpy()
        self.domain=payload['hp']['metadata']['domain']
        if not np.array_equal(self.classes,CLASSES) or self.domain['min']!=-160 or self.domain['max']!=143:
            raise ValueError('frozen HP class domain mismatch')
        self.trained_groups=TRAINED_GROUPS
        self.encounter_names=native_rng.encounter_names()
        mean=np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS),np.float32)
        std=np.ones_like(mean)  # overwritten by each checkpoint's OWN buffers
        self.survival_net=attention.AttentionPointControlNet(torch,mean,std).net
        self.max_net=attention.AttentionPhase2Net(torch,spec,mean,std).net
        self.hp_net=hp.new_model(torch,mean,std,len(self.delta_values),self.classes,20260912)
        self.potion_encoder=attention.AttentionPointControlNet(torch,mean,std).net
        self.potion_net=potion.new_decoder('joint',len(self.delta_values))
        self.relic_net=trajectory.new_decoder(torch,len(self.classes),20260912)
        for model,key,field in ((self.survival_net,'survival','stateDict'),(self.max_net,'max_hp','stateDict'),
                                (self.hp_net,'hp','state_dict'),(self.potion_encoder,'potion_encoder','stateDict'),
                                (self.relic_net,'relic','state_dict')):
            model.load_state_dict(payload[key][field],strict=True)
        self.potion_net.load_state_dict(payload['potion'],strict=True)
        self.to(device)
        self.ready=True

    def to(self,device):
        self.device=device
        for net in (self.survival_net,self.max_net,self.hp_net,self.potion_encoder,self.potion_net,self.relic_net):
            net.to(device).eval().requires_grad_(False)
        return self

    def encode_visible(self,predictor_input):
        return base._torch_inputs(visible_arrays(predictor_input),np.asarray([0]),self.device,self.torch,trim_padding=True)

    def fp32_encoding(self,encoder,inputs):
        with attention_backend(self.torch,True):
            return encoder(*inputs)

    def survival(self,inputs):
        t=self.torch
        return float(t.sigmoid(self.survival_net.survival(self.fp32_encoding(self.survival_net.encoder,inputs))).item())

    def max_hp(self,inputs):
        t=self.torch
        return t.softmax(self.max_net.max_hp_delta(self.fp32_encoding(self.max_net.encoder,inputs)),dim=-1)[0].cpu().numpy()

    def hp_encoding(self,inputs):
        # HP AMP convention for GPU scoring; CPU latency is FP32.
        with attention_backend(self.torch,False):
            if str(self.device).startswith('cuda'):
                with self.torch.autocast('cuda',dtype=self.torch.float16):
                    return self.hp_net.encoder(*inputs).float()
            return self.hp_net.encoder(*inputs)

    def hp_distribution(self,z,delta,pre,maximum):
        t=self.torch
        d=t.as_tensor([delta],device=self.device,dtype=t.long)
        features=t.cat((z,self.hp_net.delta_embedding(d)),-1)
        if str(self.device).startswith('cuda'):
            with t.autocast('cuda',dtype=t.float16): logits=self.hp_net.hp(features).float()
        else: logits=self.hp_net.hp(features).float()
        legal=hp.legal_support(self.classes,np.asarray([pre]),np.asarray([maximum]))
        return t.softmax(logits.masked_fill(~t.as_tensor(legal,device=self.device),-t.inf),-1)[0].cpu().numpy()

    def potion_distribution(self,inputs,pre,delta,fraction):
        t=self.torch
        z=self.fp32_encoding(self.potion_encoder.encoder,inputs)
        values=(z,t.as_tensor([pre['potions']],device=self.device),t.as_tensor([pre['potionCapacity']],device=self.device),
                t.as_tensor([delta],device=self.device),t.as_tensor([fraction],device=self.device,dtype=t.float32))
        return self.potion_net(*values)[0].exp().cpu().numpy()

    def relic_distribution(self,z,signed_class,fraction,mask):
        t=self.torch
        values=(z,t.as_tensor([signed_class],device=self.device),t.as_tensor([fraction],device=self.device,dtype=t.float32),t.as_tensor([mask],device=self.device))
        return {g:t.softmax(v,-1)[0].cpu().numpy() for g,v in self.relic_net(*values).items() if g in self.trained_groups}


def assemble_victory(pre,predictor_input,maximum,ending_hp,mask,residues,encounter_names):
    post={k:copy.deepcopy(pre[k]) for k in base.PERSISTENT_KEYS}
    post['maxHp']=int(maximum)
    post['curHp']=int(ending_hp)
    if not 1 <= post['curHp'] <= post['maxHp']:
        raise ValueError('invalid sampled HP')
    post['potions']=potion.decode_masks(np.asarray([pre['potions']]),np.asarray([pre['potionCapacity']]),np.asarray([mask]))[0].tolist()
    post['potionCount']=sum(x>1 for x in post['potions'])
    bloom=any(x['id']==base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
    encounter=predictor_input['globals']['encounter']
    post['relics']=relic.reconstruct(pre['relics'],residues,encounter,bloom)
    post['oocContinuationRng']={
        'miscRng':native_rng.replay_misc(pre['combatRng'][2],encounter_names[encounter]),
        'potionRng':copy.deepcopy(pre['combatRng'][4]),
    }
    validate_victory(pre,predictor_input,post,residues,encounter_names)
    return post


def validate_victory(pre,predictor_input,post,residues,encounter_names):
    if type(post['curHp']) is not int or type(post['maxHp']) is not int or not 1<=post['curHp']<=post['maxHp']:
        raise ValueError('invalid HP')
    potion.encode_masks(np.asarray([pre['potions']]),np.asarray([post['potions']]),np.asarray([pre['potionCapacity']]))
    if post['potionCount']!=sum(x>1 for x in post['potions']):
        raise ValueError('invalid potion count')
    for k in (*base.COPY_THROUGH_KEYS,'smokeBombUsed'):
        if post[k]!=pre[k]: raise ValueError(f'copy-through mismatch: {k}')
    bloom=any(x['id']==base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
    encounter=predictor_input['globals']['encounter']
    if post['relics']!=relic.reconstruct(pre['relics'],residues,encounter,bloom):
        raise ValueError('native relic mismatch')
    for k,v in post['oocContinuationRng'].items():
        if not rng_valid(v): raise ValueError(f'invalid inherited RNG: {k}')
    if post['oocContinuationRng']!={'miscRng':native_rng.replay_misc(pre['combatRng'][2],encounter_names[encounter]),'potionRng':pre['combatRng'][4]}:
        raise ValueError('inherited RNG mismatch')


class ComposedSampler:
    def __init__(self,models):
        self.models=models

    def sample_transition(self,pre,predictor_input,rng):
        m=self.models
        reasons=full_support_reasons(pre,predictor_input,m)
        if reasons:
            return Transition('FULL_SURROGATE_FALLBACK',reasons=tuple(reasons))
        with m.torch.inference_mode():
            inputs=m.encode_visible(predictor_input)
            pwin=m.survival(inputs)
            if not np.isfinite(pwin) or not 0<=pwin<=1:
                raise ValueError('invalid protected survival')
            if rng.random()>=pwin:
                return Transition('DEATH')
            delta=categorical(m.max_hp(inputs),rng)
            maximum=pre['maxHp']+int(m.delta_values[delta])
            if maximum<=0:
                raise ValueError('invalid sampled maxHP state')
            z=m.hp_encoding(inputs)
            signed_class=categorical(m.hp_distribution(z,delta,pre['curHp'],maximum),rng)
            ending_hp=pre['curHp']+int(m.classes[signed_class])
            if not 1<=ending_hp<=maximum:
                raise ValueError('invalid sampled HP')
            fraction=ending_hp/maximum
            mask=categorical(m.potion_distribution(inputs,pre,delta,fraction),rng)
            residues={g:categorical(p,rng) for g,p in m.relic_distribution(z,signed_class,fraction,mask).items()}
            post=assemble_victory(pre,predictor_input,maximum,ending_hp,mask,residues,m.encounter_names)
            return Transition('VICTORY',post)
