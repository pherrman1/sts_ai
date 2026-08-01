//
// CombatDistValueNet.cpp: native C++ inference with BLAS-accelerated matmul.
//
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatValueNet.h"
#include "combat/BattleContext.h"
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <cmath>

namespace sts::search {

CombatDistValueNet g_combatDistVNet;
bool g_useDistVNet = false;

// ---- BLAS integration ------------------------------------------------------
static void *blas_handle = nullptr;
static bool blas_ok = false;
typedef void (*sgemv_t)(const int,const int,const int,const int,const float,
                        const float*,const int,const float*,const int,
                        const float,float*,const int);
static sgemv_t sgemv_fn = nullptr;
static bool blas_probed = false;
static void init_blas(){
    if(blas_handle||blas_probed)return;
    blas_probed=true;
    const char*ps[]={
        "/home/philippherrmann/Documents/sts/.venv/lib/python3.12/site-packages/scipy.libs/libscipy_openblas-5f890258.so",
    };
    for(const char*p:ps){blas_handle=dlopen(p,RTLD_NOW|RTLD_GLOBAL);if(!blas_handle)continue;
        sgemv_fn=(sgemv_t)dlsym(blas_handle,"scipy_cblas_sgemv");
        if(sgemv_fn){blas_ok=true;break;}dlclose(blas_handle);blas_handle=nullptr;}
    if(blas_ok){std::cout<<"BLAS: OpenBLAS "<<ps[0]<<'\n';}
    else{std::cout<<"BLAS: scalar fallback\n";}
}

static inline float sigmoid(float x){return 1.0f/(1.0f+std::exp(-x));}
static inline float relu(float x){return x>0.f?x:0.f;}
static void layernorm(const float*x,int d,const float*g,const float*b,float*o){
    float m=0,v=0;for(int i=0;i<d;++i)m+=x[i];m/=d;
    for(int i=0;i<d;++i){float t=x[i]-m;v+=t*t;}v=v/d+1e-5f;float inv=1.0f/std::sqrt(v);
    for(int i=0;i<d;++i)o[i]=(x[i]-m)*inv*g[i]+b[i];
}
static void linear(const float*in,int C,const float*W,const float*B,int R,float*out){
    init_blas();
    if(blas_ok&&C>=8&&R>=8){sgemv_fn(101,111,R,C,1.0f,W,C,in,1,0.0f,out,1);}
    else{for(int r=0;r<R;++r){const float*wr=W+r*C;float s=0.f;for(int c=0;c<C;++c)s+=wr[c]*in[c];out[r]=s;}}
    if(B)for(int r=0;r<R;++r)out[r]+=B[r];
}

double CombatDistOutcome::riskAdjustedValue(double l,double mH,double wB)const{double p=winProbability,e=expectedEndHp(),ev=p*(wB+e);return l<=0.0?ev:ev-l*(e-cvarEndHp(0.25));}
double CombatDistOutcome::expectedEndHp()const{double s=0;for(auto q:endHpQuantiles)s+=q;return s/kQuantileBins;}
double CombatDistOutcome::cvarEndHp(double a)const{auto s=endHpQuantiles;std::sort(s.begin(),s.end());int n=std::max(1,int(kQuantileBins*a));double t=0;for(int i=0;i<n;++i)t+=s[i];return t/n;}

static void multiHeadAttn(const float*tok,int nT,int D,int nH,
    const CombatDistValueNet::TransformerLayer&L,float*out){
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
    const CombatDistValueNet::TransformerLayer&L,float*out){
    thread_local std::vector<float> h,r;h.resize(nT*H);r.resize(nT*D);
    for(int t=0;t<nT;++t){linear(tok+t*D,D,L.ffnW1.data(),L.ffnB1.data(),H,h.data()+t*H);for(int i=0;i<H;++i)h[t*H+i]=relu(h[t*H+i]);}
    for(int t=0;t<nT;++t){linear(h.data()+t*H,H,L.ffnW2.data(),L.ffnB2.data(),D,r.data()+t*D);
        float mid[256];for(int i=0;i<D;++i)mid[i]=tok[t*D+i]+r[t*D+i];layernorm(mid,D,L.ln2W.data(),L.ln2B.data(),out+t*D);}
}

bool CombatDistValueNet::load(const std::string&path){
    std::ifstream f(path);if(!f)return false;
    std::string tok;f>>tok;if(tok!="combat_dist_v1")return false;
    isLoaded=false;
    auto R=[&](const char*w,std::vector<float>&v,size_t n)->bool{
        f>>tok;if(tok!=w)return false;v.resize(n);for(float&x:v)f>>x;return bool(f);};
    auto RF=[&](const char*w,float&d)->bool{f>>tok;if(tok!=w)return false;return bool(f>>d);};
    f>>tok>>entityDim;f>>tok>>hiddenDim;f>>tok>>numHeads;f>>tok>>numLayers;f>>tok>>winBonus;
    int ns=0;f>>tok>>ns;scalarSel.resize(ns);f.clear();
    for(int i=0;i<ns;++i)f>>scalarSel[i];while(f.peek()==' '){int _d;f>>_d;}if(!f)return false;
    if(!R("scalar_mean",scalarMean,64))return false;
    if(!R("scalar_inv",scalarInv,64))return false;
    if(!R("scalar_weight",scalarW,entityDim*64))return false;
    if(!R("scalar_bias",scalarB,entityDim))return false;
    if(!R("card_embed",cardEmbed,371*entityDim))return false;
    if(!R("relic_embed",relicEmbed,128*64))return false;
    if(!R("potion_embed",potionEmbed,44*32))return false;
    if(!R("encounter_embed",encEmbed,128*32))return false;
    if(!R("zone_pos",zonePosEmbed,4*entityDim))return false;
    if(!R("mon_id_embed",monIdEmbed,256*64))return false;
    if(!R("mon_intent_embed",monIntentEmbed,32*16))return false;
    if(!R("mon_cont_mean",monContMean,7))return false;
    if(!R("mon_cont_inv",monContInv,7))return false;
    if(!R("mon_enc_weight",monEncW,entityDim*(64+16+7)))return false;
    if(!R("mon_enc_bias",monEncB,entityDim))return false;
    layers.resize(numLayers);
    for(int l=0;l<numLayers;++l){auto&L=layers[l];std::string p="layer_"+std::to_string(l)+"_";
        if(!R((p+"qkv_weight").c_str(),L.qkvFcW,3*entityDim*entityDim))return false;
        if(!R((p+"qkv_bias").c_str(),L.qkvFcB,3*entityDim))return false;
        if(!R((p+"proj_weight").c_str(),L.projW,entityDim*entityDim))return false;
        if(!R((p+"proj_bias").c_str(),L.projB,entityDim))return false;
        if(!R((p+"ln1_weight").c_str(),L.ln1W,entityDim))return false;
        if(!R((p+"ln1_bias").c_str(),L.ln1B,entityDim))return false;
        if(!R((p+"ln2_weight").c_str(),L.ln2W,entityDim))return false;
        if(!R((p+"ln2_bias").c_str(),L.ln2B,entityDim))return false;
        if(!R((p+"ffn1_weight").c_str(),L.ffnW1,hiddenDim*entityDim))return false;
        if(!R((p+"ffn1_bias").c_str(),L.ffnB1,hiddenDim))return false;
        if(!R((p+"ffn2_weight").c_str(),L.ffnW2,entityDim*hiddenDim))return false;
        if(!R((p+"ffn2_bias").c_str(),L.ffnB2,entityDim))return false;
    }
    if(!R("pool_weight",poolAttnW,entityDim))return false;
    if(!R("death_head_weight",deathW,entityDim))return false;if(!RF("death_head_bias",deathB))return false;
    if(!R("win_head_weight",winW,entityDim))return false;if(!RF("win_head_bias",winB))return false;
    if(!R("quantile_head_weight",quantileW,kQuantileBins*entityDim))return false;if(!R("quantile_head_bias",quantileB,kQuantileBins))return false;
    if(!R("potion_head_weight",potionW,44*entityDim))return false;if(!R("potion_head_bias",potionB,44))return false;
    if(!R("turns_head_weight",turnsW,entityDim))return false;if(!RF("turns_head_bias",turnsB))return false;
    if(!f)return false;
    g_richCombatFeatures=true;isLoaded=true;init_blas();return true;
}

static constexpr int ZO=50+128,MO=ZO+4*371+2;

CombatDistOutcome CombatDistValueNet::predict(const CombatObservation&,const std::array<float,1766>&canon)const{
    int D=entityDim;
    thread_local std::vector<float> tok;tok.clear();
    {float sn[64];for(int i=0;i<64;++i)sn[i]=(canon[scalarSel[i]]-scalarMean[i])*scalarInv[i];
     float t[D];linear(sn,64,scalarW.data(),scalarB.data(),D,t);for(int i=0;i<D;++i)tok.push_back(relu(t[i]));}
    for(int z=0;z<4;++z){float t[D]={};bool a=false;
        for(int c=0;c<371;++c){float cnt=canon[ZO+z*371+c];if(cnt<=0.f)continue;a=true;
            const float*e=cardEmbed.data()+c*D;for(int j=0;j<D;++j)t[j]+=cnt*e[j];}
        if(!a)continue;for(int j=0;j<D;++j)t[j]+=zonePosEmbed[z*D+j];tok.insert(tok.end(),t,t+D);}
    {float t[D]={};bool a=false;
        for(int id=0;id<128;++id){if(canon[50+id]<=0.f)continue;a=true;
            const float*e=relicEmbed.data()+id*64;for(int j=0;j<64;++j)t[j]+=e[j];}
        if(a)tok.insert(tok.end(),t,t+D);}
    {float t[D]={};bool a=false;int po=ZO+4*371+2+5*9;
        for(int id=0;id<44;++id){if(canon[po+id]<=0.f)continue;a=true;
            const float*e=potionEmbed.data()+id*32;for(int j=0;j<32;++j)t[j]+=e[j];}
        if(a)tok.insert(tok.end(),t,t+D);}
    {int enc=std::max(0,std::min(127,(int)canon[1]));float t[D]={};
        for(int j=0;j<32;++j)t[j]=encEmbed[enc*32+j];tok.insert(tok.end(),t,t+D);}
    for(int s=0;s<5;++s){const float*m=&canon[MO+s*9];if(m[1]<=0.f)continue;
        int mid=std::max(0,std::min(255,(int)m[0])),in=std::max(0,std::min(31,(int)m[4]));
        float mi[87];std::copy_n(monIdEmbed.data()+mid*64,64,mi);std::copy_n(monIntentEmbed.data()+in*16,16,mi+64);
        int ci[7]={1,2,3,5,6,7,8};for(int j=0;j<7;++j)mi[80+j]=(m[ci[j]]-monContMean[j])*monContInv[j];
        float t[D];linear(mi,87,monEncW.data(),monEncB.data(),D,t);for(int i=0;i<D;++i)tok.push_back(relu(t[i]));}
    int nT=(int)tok.size()/D;if(!nT)return{};
    thread_local std::vector<float> buf;buf.resize(nT*D);
    for(int l=0;l<numLayers;++l){multiHeadAttn(tok.data(),nT,D,numHeads,layers[l],buf.data());ffn(buf.data(),nT,D,hiddenDim,layers[l],tok.data());}
    float p[D]={};float as=0.f;
    for(int t=0;t<nT;++t){float s=0;for(int i=0;i<D;++i)s+=poolAttnW[i]*tok[t*D+i];s=std::exp(s);as+=s;for(int i=0;i<D;++i)p[i]+=s*tok[t*D+i];}
    if(as>0.f){float inv=1.f/as;for(int i=0;i<D;++i)p[i]*=inv;}
    auto dot=[&](const std::vector<float>&w,float b){float s=b;for(int i=0;i<D;++i)s+=w[i]*p[i];return s;};
    CombatDistOutcome o;o.deathProbability=sigmoid(dot(deathW,deathB));o.winProbability=sigmoid(dot(winW,winB));
    for(int q=0;q<kQuantileBins;++q){float s=quantileB[q];for(int i=0;i<D;++i)s+=quantileW[q*D+i]*p[i];o.endHpQuantiles[q]=std::max(0.0,(double)s);}
    for(int q=0;q<44;++q){float s=potionB[q];for(int i=0;i<D;++i)s+=potionW[q*D+i]*p[i];o.potionUseProbability[q]=sigmoid(s);}
    o.expectedTurnsRemaining=std::max(0.0,(double)dot(turnsW,turnsB));return o;
}
CombatDistOutcome CombatDistValueNet::predictFromBC(const BattleContext&bc)const{std::array<float,1766>feat{};combatExtractFeatures(bc,feat.data());return predict(CombatObservation::fromBattleContext(bc),feat);}
double CombatDistValueNet::predictScalar(const BattleContext&bc)const{auto o=predictFromBC(bc);return o.riskAdjustedValue(0.5,bc.player.maxHp,winBonus);}
std::string CombatDistValueNet::description()const{return "dist d"+std::to_string(entityDim)+" h"+std::to_string(hiddenDim)+" hds"+std::to_string(numHeads)+" L"+std::to_string(numLayers);}
}
