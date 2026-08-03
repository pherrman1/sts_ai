//
// CombatCpsiNet.cpp: native C++ inference for the no-peek pre-combat outcome
// model C_psi (train_combat_cpsi.py, text export "combat_cpsi_v1").
// Math helpers mirror CombatPVNet.cpp / CombatDistValueNet.cpp (float32,
// layernorm eps 1e-5, single-head attention loops); the FFN uses the
// erf-based GELU of nn.GELU() so the forward matches the torch checkpoint.
//
#include "sim/search/CombatCpsiNet.h"

#include "game/GameContext.h"
#include "game/Card.h"
#include "constants/Potions.h"
#include "constants/Relics.h"

#include <fstream>
#include <iostream>
#include <algorithm>
#include <cmath>
#include <cstring>

namespace sts::search {

// ---- Math helpers ----------------------------------------------------------
static inline float sigmoid(float x){return 1.0f/(1.0f+std::exp(-x));}
static inline float relu(float x){return x>0.f?x:0.f;}
static inline float gelu(float x){ // nn.GELU(): erf-based, float32
    return x*0.5f*(1.0f+std::erf(x*0.7071067811865475f));
}

static void layernorm(const float*x,int d,const float*g,const float*b,float*o){
    float m=0,v=0;for(int i=0;i<d;++i)m+=x[i];m/=d;
    for(int i=0;i<d;++i){float t=x[i]-m;v+=t*t;}v=v/d+1e-5f;float inv=1.0f/std::sqrt(v);
    for(int i=0;i<d;++i)o[i]=(x[i]-m)*inv*g[i]+b[i];
}

static void linear(const float*in,int C,const float*W,const float*B,int R,float*out){
    for(int r=0;r<R;++r){const float*wr=W+r*C;float s=0.f;for(int c=0;c<C;++c)s+=wr[c]*in[c];out[r]=s;}
    if(B)for(int r=0;r<R;++r)out[r]+=B[r];
}

// ---- Transformer helpers ---------------------------------------------------
static void multiHeadAttn(const float*tok,int nT,int D,int nH,
    const CombatCpsiNet::TransformerLayer&L,float*out){
    int hd=D/nH,qd=3*D;
    thread_local std::vector<float> QKV,attn,tmp;QKV.resize(nT*qd);attn.assign(nT*D,0.f);tmp.resize(std::max(nT*nT,nT*D));
    for(int t=0;t<nT;++t)linear(tok+t*D,D,L.qkvFcW.data(),L.qkvFcB.data(),qd,QKV.data()+t*qd);
    for(int h=0;h<nH;++h){int ho=h*hd,vo=2*D+ho;float*s=tmp.data();
        for(int i=0;i<nT;++i){const float*qi=QKV.data()+i*qd+ho;float sm=-1e30f;
            for(int j=0;j<nT;++j){const float*kj=QKV.data()+j*qd+D+ho;float x=0;for(int d=0;d<hd;++d)x+=qi[d]*kj[d];s[i*nT+j]=x;if(x>sm)sm=x;}
            float sc=1.f/std::sqrt((float)hd),sum=0.f;
            for(int j=0;j<nT;++j){s[i*nT+j]=std::exp((s[i*nT+j]-sm)*sc);sum+=s[i*nT+j];}
            float inv=sum>0.f?1.f/sum:1.f/nT;
            for(int j=0;j<nT;++j){const float*vj=QKV.data()+j*qd+vo;float a=s[i*nT+j]*inv;float*ao=attn.data()+i*D+ho;for(int d=0;d<hd;++d)ao[d]+=a*vj[d];}}
    }
    for(int t=0;t<nT;++t){linear(attn.data()+t*D,D,L.projW.data(),L.projB.data(),D,tmp.data()+t*D);
        float mid[256];for(int i=0;i<D;++i)mid[i]=tok[t*D+i]+tmp[t*D+i];layernorm(mid,D,L.ln1W.data(),L.ln1B.data(),out+t*D);}
}

static void ffn(const float*tok,int nT,int D,int H,
    const CombatCpsiNet::TransformerLayer&L,float*out){
    thread_local std::vector<float> h,r;h.resize(nT*H);r.resize(nT*D);
    for(int t=0;t<nT;++t){linear(tok+t*D,D,L.ffnW1.data(),L.ffnB1.data(),H,h.data()+t*H);for(int i=0;i<H;++i)h[t*H+i]=gelu(h[t*H+i]);}
    for(int t=0;t<nT;++t){linear(h.data()+t*H,H,L.ffnW2.data(),L.ffnB2.data(),D,r.data()+t*D);
        float mid[256];for(int i=0;i<D;++i)mid[i]=tok[t*D+i]+r[t*D+i];layernorm(mid,D,L.ln2W.data(),L.ln2B.data(),out+t*D);}
}

// ---- Model loading (combat_cpsi_v1, strict token-by-token) -----------------
bool CombatCpsiNet::load(const std::string&path){
    std::ifstream f(path);if(!f)return false;
    std::string tok;f>>tok;if(tok!="combat_cpsi_v1")return false;
    float wb=0.f;
    auto R=[&](const char*w,std::vector<float>&v,size_t n)->bool{
        f>>tok;if(tok!=w)return false;v.resize(n);for(float&x:v)f>>x;return bool(f);};
    auto RF=[&](const char*w,float&d)->bool{f>>tok;if(tok!=w)return false;return bool(f>>d);};

    if(!RF("win_bonus",wb))return false;winBonus=wb;
    int ns=0;f>>tok;if(tok!="nscalar")return false;f>>ns;
    if(ns!=kCpsiScalars)return false;
    for(int i=0;i<ns;++i){f>>tok;if(tok!="scalar")return false;f>>tok;}  // names, order documented
    f>>tok;if(tok!="dim")return false;f>>entityDim;
    f>>tok;if(tok!="hidden")return false;f>>hiddenDim;
    f>>tok;if(tok!="heads")return false;f>>numHeads;
    f>>tok;if(tok!="layers")return false;f>>numLayers;
    f>>tok;if(tok!="quantiles")return false;f>>nQuantile;

    const int D=entityDim;
    if(!R("scalar_mean",scalarMean,kCpsiScalars))return false;
    if(!R("scalar_inv",scalarInv,kCpsiScalars))return false;
    if(!R("scalar_weight",scalarW,D*kCpsiScalars))return false;
    if(!R("scalar_bias",scalarB,D))return false;
    if(!R("card_embed",cardEmbed,kCpsiCards*D))return false;
    if(!R("relic_embed",relicEmbed,kCpsiRelics*64))return false;
    if(!R("potion_embed",potionEmbed,kCpsiPotions*32))return false;
    if(!R("encounter_embed",encEmbed,kCpsiEncounters*32))return false;

    hasRelicProj=false;hasPotionProj=false;hasEncProj=false;
    f>>tok;
    if(tok=="relic_proj_weight"){
        hasRelicProj=true;
        relicProjW.resize(D*64);for(float&x:relicProjW)f>>x;
        if(!(f>>tok)||tok!="relic_proj_bias")return false;
        relicProjB.resize(D);for(float&x:relicProjB)f>>x;f>>tok;}
    if(tok=="potion_proj_weight"){
        hasPotionProj=true;
        potionProjW.resize(D*32);for(float&x:potionProjW)f>>x;
        if(!(f>>tok)||tok!="potion_proj_bias")return false;
        potionProjB.resize(D);for(float&x:potionProjB)f>>x;f>>tok;}
    if(tok=="enc_proj_weight"){
        hasEncProj=true;
        encProjW.resize(D*32);for(float&x:encProjW)f>>x;
        if(!(f>>tok)||tok!="enc_proj_bias")return false;
        encProjB.resize(D);for(float&x:encProjB)f>>x;f>>tok;}

    layers.resize(numLayers);
    for(int l=0;l<numLayers;++l){
        auto &L=layers[l];
        std::string pre="layer_"+std::to_string(l)+"_";
        if(tok!=pre+"qkv_weight")return false;
        L.qkvFcW.resize(3*D*D);for(float&x:L.qkvFcW)f>>x;
        f>>tok;if(tok!=pre+"qkv_bias")return false;
        L.qkvFcB.resize(3*D);for(float&x:L.qkvFcB)f>>x;
        f>>tok;if(tok!=pre+"proj_weight")return false;
        L.projW.resize(D*D);for(float&x:L.projW)f>>x;
        f>>tok;if(tok!=pre+"proj_bias")return false;
        L.projB.resize(D);for(float&x:L.projB)f>>x;
        for(const char*suf:{"ln1","ln2"}){
            bool is1=suf[2]=='1';
            f>>tok;if(tok!=pre+suf+"_weight")return false;
            (is1?L.ln1W:L.ln2W).resize(D);
            for(float&x:(is1?L.ln1W:L.ln2W))f>>x;
            f>>tok;if(tok!=pre+suf+"_bias")return false;
            (is1?L.ln1B:L.ln2B).resize(D);
            for(float&x:(is1?L.ln1B:L.ln2B))f>>x;
        }
        for(const char*suf:{"ffn1","ffn2"}){
            bool is1=suf[3]=='1';
            f>>tok;if(tok!=pre+suf+"_weight")return false;
            (is1?L.ffnW1:L.ffnW2).resize(is1?hiddenDim*D:D*hiddenDim);
            for(float&x:(is1?L.ffnW1:L.ffnW2))f>>x;
            f>>tok;if(tok!=pre+suf+"_bias")return false;
            (is1?L.ffnB1:L.ffnB2).resize(is1?hiddenDim:D);
            for(float&x:(is1?L.ffnB1:L.ffnB2))f>>x;
        }
        if(l+1<numLayers)f>>tok;
    }
    f>>tok;  // advance past last layer's last token
    if(tok!="pool_weight")return false;
    poolW.resize(D);for(float&x:poolW)f>>x;
    if(!RF("pool_bias",poolB))return false;
    if(!R("death_weight",deathW,D))return false;if(!RF("death_bias",deathB))return false;
    if(!R("win_weight",winW,D))return false;if(!RF("win_bias",winB))return false;
    if(!R("hp_weight",hpW,D))return false;if(!RF("hp_bias",hpB))return false;
    if(!R("quantile_weight",quantileW,nQuantile*D))return false;
    if(!R("quantile_bias",quantileB,nQuantile))return false;
    if(!R("potion_weight",potionW,kCpsiPotions*D))return false;
    if(!R("potion_bias",potionB,kCpsiPotions))return false;
    if(!R("turns_weight",turnsW,D))return false;
    if(!RF("turns_bias",turnsB))return false;
    if(!f)return false;
    isLoaded=true;return true;
}

// ---- Forward ---------------------------------------------------------------
void CombatCpsiNet::predict(const float scalar[11], const float deck[371],
                            const float relics[128], const float potions[44],
                            int encounter, CpsiOut&out)const{
    const int D=entityDim;
    thread_local std::vector<float> tok;tok.clear();

    {float sn[kCpsiScalars];for(int i=0;i<kCpsiScalars;++i)sn[i]=(scalar[i]-scalarMean[i])*scalarInv[i];
     float t[256];linear(sn,kCpsiScalars,scalarW.data(),scalarB.data(),D,t);
     for(int i=0;i<D;++i)tok.push_back(relu(t[i]));}

    {float t[256]={};
     for(int c=0;c<kCpsiCards;++c){if(deck[c]<=0.f)continue;const float*e=cardEmbed.data()+c*D;for(int j=0;j<D;++j)t[j]+=deck[c]*e[j];}
     tok.insert(tok.end(),t,t+D);}

    {float raw[64]={};
     for(int id=0;id<kCpsiRelics;++id){if(relics[id]<=0.f)continue;const float*e=relicEmbed.data()+id*64;for(int j=0;j<64;++j)raw[j]+=e[j];}
     float t[256]={};
     if(hasRelicProj){linear(raw,64,relicProjW.data(),relicProjB.data(),D,t);}
     else{for(int j=0;j<64&&j<D;++j)t[j]=raw[j];}
     tok.insert(tok.end(),t,t+D);}

    {float raw[32]={};
     for(int id=0;id<kCpsiPotions;++id){if(potions[id]<=0.f)continue;const float*e=potionEmbed.data()+id*32;for(int j=0;j<32;++j)raw[j]+=e[j];}
     float t[256]={};
     if(hasPotionProj){linear(raw,32,potionProjW.data(),potionProjB.data(),D,t);}
     else{for(int j=0;j<32&&j<D;++j)t[j]=raw[j];}
     tok.insert(tok.end(),t,t+D);}

    {const int enc=std::max(0,std::min(kCpsiEncounters-1,encounter));
     float t[256]={};
     for(int j=0;j<32;++j)t[j]=encEmbed[enc*32+j];
     if(hasEncProj){float t2[256];linear(t,32,encProjW.data(),encProjB.data(),D,t2);memcpy(t,t2,sizeof(float)*D);}
     tok.insert(tok.end(),t,t+D);}

    const int nT=(int)tok.size()/D;
    thread_local std::vector<float> buf;buf.resize(nT*D);
    for(int l=0;l<numLayers;++l){multiHeadAttn(tok.data(),nT,D,numHeads,layers[l],buf.data());ffn(buf.data(),nT,D,hiddenDim,layers[l],tok.data());}

    float p[256]={};float as=0.f;
    for(int t=0;t<nT;++t){float s=poolB;for(int i=0;i<D;++i)s+=poolW[i]*tok[t*D+i];s=std::exp(s);as+=s;for(int i=0;i<D;++i)p[i]+=s*tok[t*D+i];}
    if(as>0.f){float inv=1.f/as;for(int i=0;i<D;++i)p[i]*=inv;}

    auto dot=[&](const std::vector<float>&w,float b){float s=b;for(int i=0;i<D;++i)s+=w[i]*p[i];return s;};
    out.death=sigmoid(dot(deathW,deathB));
    out.win=sigmoid(dot(winW,winB));
    out.hp=sigmoid(dot(hpW,hpB));
    for(int q=0;q<nQuantile;++q){float s=quantileB[q];for(int i=0;i<D;++i)s+=quantileW[q*D+i]*p[i];out.quantiles[q]=s;}
    for(int q=0;q<kCpsiPotions;++q){float s=potionB[q];for(int i=0;i<D;++i)s+=potionW[q*D+i]*p[i];out.potionProb[q]=sigmoid(s);}
    out.turns=std::expm1((double)dot(turnsW,turnsB));
}

std::string CombatCpsiNet::description()const{
    return "cpsi d"+std::to_string(entityDim)+" h"+std::to_string(hiddenDim)+" hds"+std::to_string(numHeads)+" L"+std::to_string(numLayers);
}

// ---- No-peek entry builder (pre-combat GameContext) ------------------------
// Mirrors the distgen CSV producer semantics used to train C_psi:
//   deck  = per-card-id counts over the whole deck (bag, orderless)
//   relics= presence 1/0 for RelicId 0..127 (training rows are the combat
//           canonical vector, whose relic flags are presence only)
//   potions = counts per Potion enum id (skipping EMPTY_POTION_SLOT)
//   scalars = ascension, curHp, maxHp + 8 persistent relic counters from
//             RelicInstance.data (0 when the relic is absent)
static int relicDataOr(const GameContext &gc, RelicId id, int fallback) {
    for (const auto &ri : gc.relics.relics) if (ri.id == id) return ri.data;
    return fallback;
}

void buildCpsiEntry(const GameContext &gc, float scalar[11],
                    float deck[371], float relics[128], float potions[44]) {
    std::fill(scalar, scalar + kCpsiScalars, 0.f);
    std::fill(deck, deck + kCpsiCards, 0.f);
    std::fill(relics, relics + kCpsiRelics, 0.f);
    std::fill(potions, potions + kCpsiPotions, 0.f);

    scalar[0] = (float)gc.ascension;
    scalar[1] = (float)gc.curHp;
    scalar[2] = (float)gc.maxHp;
    scalar[3] = (float)relicDataOr(gc, RelicId::HAPPY_FLOWER, 0);
    scalar[4] = (float)relicDataOr(gc, RelicId::INCENSE_BURNER, 0);
    scalar[5] = (float)relicDataOr(gc, RelicId::INK_BOTTLE, 0);
    scalar[6] = (float)relicDataOr(gc, RelicId::INSERTER, 0);
    scalar[7] = (float)relicDataOr(gc, RelicId::NUNCHAKU, 0);
    scalar[8] = (float)relicDataOr(gc, RelicId::PEN_NIB, 0);
    scalar[9] = (float)relicDataOr(gc, RelicId::SUNDIAL, 0);
    scalar[10] = 0.f;   // panacheCtr: Panache is a card/status, not a relic

    for (int i = 0; i < gc.deck.size(); ++i) {
        const int id = (int)gc.deck.cards[i].getId();
        if (id >= 0 && id < kCpsiCards) deck[id] += 1.f;
    }
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kCpsiRelics) relics[id] = 1.f;
    }
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        const int pid = (int)gc.potions[i];
        if (pid >= 2 && pid < kCpsiPotions) potions[pid] += 1.f;  // skip INVALID/EMPTY
    }
}

} // namespace sts::search
