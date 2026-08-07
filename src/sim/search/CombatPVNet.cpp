//
// CombatPVNet.cpp: shared policy-value network (AlphaZero-style) with BLAS.
//
#include "sim/search/CombatPVNet.h"
#include "sim/search/CombatValueNet.h"
#include "combat/BattleContext.h"
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <cmath>

namespace sts::search {

CombatPVNet g_combatPVNet;
bool g_usePVNet = false;
double g_pvnetAlpha = 1.0;
bool g_pvnetValueOnly = false;
// Value-scale fix (STS_PVNET_HP_SCALE=1, opt-in, §123): the quantile head is
// trained on endHp/maxHp fractions in [0,1], but the terminal value is
// curHp+50 (HP scale). Without scaling, a state one action from a 40/80
// victory leaf-scores ~50.5 while its terminal scores 90 — a ~maxHp-sized
// discontinuity, and the risk term λ(median−cvar) is scaled down ~80x to
// near zero. When enabled, median and cvar are multiplied by maxHp so the
// leaf and terminal scales agree. Default off (recorded §103 behavior).
bool g_pvnetHpScale = false;

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
    std::string paths[2];
    int np=0;
    if(const char*e=std::getenv("STS_OPENBLAS"))paths[np++]=e;
    paths[np++]="/home/philippherrmann/Documents/sts/.venv/lib/python3.12/site-packages/scipy.libs/libscipy_openblas-5f890258.so";
    for(int pi=0;pi<np;++pi){
        const char*p=paths[pi].c_str();
        blas_handle=dlopen(p,RTLD_NOW|RTLD_GLOBAL);if(!blas_handle)continue;
        sgemv_fn=(sgemv_t)dlsym(blas_handle,"scipy_cblas_sgemv");
        if(!sgemv_fn)sgemv_fn=(sgemv_t)dlsym(blas_handle,"cblas_sgemv");
        if(sgemv_fn){blas_ok=true;std::cout<<"BLAS: OpenBLAS "<<p<<'\n';break;}
        dlclose(blas_handle);blas_handle=nullptr;}
    if(!blas_ok){std::cout<<"BLAS: scalar fallback\n";}
}

// ---- Math helpers ----------------------------------------------------------
static inline float sigmoid(float x){return 1.0f/(1.0f+std::exp(-x));}
static inline float relu(float x){return x>0.f?x:0.f;}
static inline float gelu(float x){return 0.5f*x*(1.0f+std::erf(x/1.4142135623730951f));}

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

// ---- Transformer helpers (PVNet version) -----------------------------------
static void multiHeadAttn(const float*tok,int nT,int D,int nH,
    const CombatPVNet::TransformerLayer&L,float*out){
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
    const CombatPVNet::TransformerLayer&L,float*out){
    thread_local std::vector<float> h,r;h.resize(nT*H);r.resize(nT*D);
    for(int t=0;t<nT;++t){linear(tok+t*D,D,L.ffnW1.data(),L.ffnB1.data(),H,h.data()+t*H);for(int i=0;i<H;++i)h[t*H+i]=gelu(h[t*H+i]);}
    for(int t=0;t<nT;++t){linear(h.data()+t*H,H,L.ffnW2.data(),L.ffnB2.data(),D,r.data()+t*D);
        float mid[256];for(int i=0;i<D;++i)mid[i]=tok[t*D+i]+r[t*D+i];layernorm(mid,D,L.ln2W.data(),L.ln2B.data(),out+t*D);}
}

// ---- Feature layout offsets (matching CombatValueNet.cpp) ------------------
static constexpr int ZO=50+128;        // hand pile offset
static constexpr int MO=ZO+4*371+2;    // monster slots offset

// ---- Model loading ---------------------------------------------------------
bool CombatPVNet::load(const std::string&path){
    std::ifstream f(path);if(!f)return false;
    std::string tok;f>>tok;if(tok!="combat_pvnet_v1")return false;
    isLoaded=false;
    auto R=[&](const char*w,std::vector<float>&v,size_t n)->bool{
        f>>tok;if(tok!=w)return false;v.resize(n);for(float&x:v)f>>x;return bool(f);};
    auto RF=[&](const char*w,float&d)->bool{f>>tok;if(tok!=w)return false;return bool(f>>d);};
    f>>tok>>entityDim;f>>tok>>hiddenDim;f>>tok>>numHeads;f>>tok>>numLayers;f>>tok>>nQuantile;f>>tok>>winBonus;
    if(entityDim<=0||entityDim>256){std::cout<<"[PVNet load FAILED: entity_dim "<<entityDim<<" unsupported (max 256)]\n";return false;}
    if(numHeads<=0||entityDim%numHeads!=0){std::cout<<"[PVNet load FAILED: heads "<<numHeads<<" must divide entity_dim "<<entityDim<<"]\n";return false;}
    int ns=0;f>>tok>>ns;scalarSel.resize(ns);
    for(int i=0;i<ns;++i)f>>scalarSel[i];
    if(!f)return false;
    
    int D=entityDim;
    if(!R("scalar_mean",scalarMean,64))return false;
    if(!R("scalar_inv",scalarInv,64))return false;
    if(!R("mon_cont_mean",monContMean,7))return false;
    if(!R("mon_cont_inv",monContInv,7))return false;
    if(!R("scalar_weight",scalarW,D*64))return false;
    if(!R("scalar_bias",scalarB,D))return false;
    if(!R("card_embed",cardEmbed,371*D))return false;
    if(!R("zone_pos",zonePosEmbed,4*D))return false;
    if(!R("type_embed",typeEmbed,6*D))return false;
    if(!R("global_token",globalToken,D))return false;
    if(!R("relic_embed",relicEmbed,128*64))return false;
    if(!R("potion_embed",potionEmbed,44*32))return false;
    if(!R("encounter_embed",encEmbed,128*32))return false;
    if(!R("mon_id_embed",monIdEmbed,256*64))return false;
    if(!R("mon_intent_embed",monIntentEmbed,32*16))return false;
    if(!R("mon_enc_weight",monEncW,(7+64+16)*D))return false;
    if(!R("mon_enc_bias",monEncB,D))return false;

    hasRelicProj=false;hasPotionProj=false;hasEncProj=false;
    
    f>>tok;if(tok=="relic_proj_weight"){hasRelicProj=true;
     relicProjW.resize(D*64);for(float&x:relicProjW)f>>x;if(!(f>>tok)||tok!="relic_proj_bias")return false;
     relicProjB.resize(D);for(float&x:relicProjB)f>>x;f>>tok;}
    if(tok=="potion_proj_weight"){hasPotionProj=true;
     potionProjW.resize(D*32);for(float&x:potionProjW)f>>x;if(!(f>>tok)||tok!="potion_proj_bias")return false;
     potionProjB.resize(D);for(float&x:potionProjB)f>>x;f>>tok;}
    if(tok=="enc_proj_weight"){hasEncProj=true;
     encProjW.resize(D*32);for(float&x:encProjW)f>>x;if(!(f>>tok)||tok!="enc_proj_bias")return false;
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
        for(const char*suf:{"ffn0","ffn2"}){
            f>>tok;int idx=suf[3]=='0'?0:1;
            if(tok!=pre+suf+"_weight")return false;
            (idx==0?L.ffnW1:L.ffnW2).resize(idx==0?hiddenDim*D:D*hiddenDim);
            for(float&x:(idx==0?L.ffnW1:L.ffnW2))f>>x;
            f>>tok;
            if(tok!=pre+suf+"_bias")return false;
            (idx==0?L.ffnB1:L.ffnB2).resize(idx==0?hiddenDim:D);
            for(float&x:(idx==0?L.ffnB1:L.ffnB2))f>>x;
        }
        if(l+1<numLayers)f>>tok;
    }
    f>>tok;  // advance past last layer's last token
    if(tok!="policy_act_enc_0_weight")return false;
    policyActEncW0.resize(64*14);for(float&x:policyActEncW0)f>>x;
    f>>tok;if(tok!="policy_act_enc_0_bias")return false;
    policyActEncB0.resize(64);for(float&x:policyActEncB0)f>>x;
    f>>tok;if(tok!="policy_act_enc_2_weight")return false;
    policyActEncW2.resize(D*64);for(float&x:policyActEncW2)f>>x;
    f>>tok;if(tok!="policy_act_enc_2_bias")return false;
    policyActEncB2.resize(D);for(float&x:policyActEncB2)f>>x;
    f>>tok;if(tok!="policy_scorer_0_weight")return false;
    policyScorerW0.resize(D*3*D);for(float&x:policyScorerW0)f>>x;
    f>>tok;if(tok!="policy_scorer_0_bias")return false;
    policyScorerB0.resize(D);for(float&x:policyScorerB0)f>>x;
    f>>tok;if(tok!="policy_scorer_2_weight")return false;
    policyScorerW2.resize(1*D);for(float&x:policyScorerW2)f>>x;
    f>>tok;if(tok!="policy_scorer_2_bias")return false;
    policyScorerB2.resize(1);for(float&x:policyScorerB2)f>>x;

    f>>tok;if(tok!="win_weight")return false;
    winW.resize(D);for(float&x:winW)f>>x;
    f>>tok;if(tok!="win_bias")return false;f>>winB;
    f>>tok;if(tok!="death_weight")return false;
    deathW.resize(D);for(float&x:deathW)f>>x;
    f>>tok;if(tok!="death_bias")return false;f>>deathB;
    f>>tok;if(tok!="quantile_weight")return false;
    quantileW.resize(nQuantile*D);for(float&x:quantileW)f>>x;
    f>>tok;if(tok!="quantile_bias")return false;
    quantileB.resize(nQuantile);for(float&x:quantileB)f>>x;
    f>>tok;if(tok!="potion_weight")return false;
    potionW.resize(44*D);for(float&x:potionW)f>>x;
    f>>tok;if(tok!="potion_bias")return false;
    potionB.resize(44);for(float&x:potionB)f>>x;
    f>>tok;if(tok!="turns_weight")return false;
    turnsW.resize(D);for(float&x:turnsW)f>>x;
    f>>tok;if(tok!="turns_bias")return false;f>>turnsB;
    if(!f)return false;
    g_richCombatFeatures=true;isLoaded=true;init_blas();return true;
}

// ---- Token construction ----------------------------------------------------
void CombatPVNet::buildTokens(const std::array<float,1766>&feat,
                              float*tokensOut,int&nTokens)const{
    int D=entityDim;
    int off=0;

    for(int i=0;i<D;++i)tokensOut[off++]=globalToken[i];

    {float sn[64];for(int i=0;i<64;++i)sn[i]=(feat[scalarSel[i]]-scalarMean[i])*scalarInv[i];
     float t[D];linear(sn,64,scalarW.data(),scalarB.data(),D,t);
     for(int i=0;i<D;++i)tokensOut[off++]=relu(t[i])+typeEmbed[0*D+i];}

    for(int z=0;z<4;++z){float t[D]={};
        for(int c=0;c<371;++c){float cnt=feat[ZO+z*371+c];if(cnt<=0.f)continue;
            const float*e=cardEmbed.data()+c*D;for(int j=0;j<D;++j)t[j]+=cnt*e[j];}
        for(int j=0;j<D;++j)t[j]+=zonePosEmbed[z*D+j]+typeEmbed[1*D+j];
        for(int i=0;i<D;++i)tokensOut[off++]=t[i];}

    {float raw[64]={};
        for(int id=0;id<128;++id){if(feat[50+id]<=0.f)continue;
            const float*e=relicEmbed.data()+id*64;for(int j=0;j<64;++j)raw[j]+=e[j];}
        float t[D]={};
        if(hasRelicProj){linear(raw,64,relicProjW.data(),relicProjB.data(),D,t);}
        else{for(int j=0;j<64;++j)t[j]=raw[j];}
        for(int i=0;i<D;++i)tokensOut[off++]=t[i]+typeEmbed[2*D+i];}

    {float raw[32]={};int po=ZO+4*371+2+5*9;
        for(int id=0;id<44;++id){if(feat[po+id]<=0.f)continue;
            const float*e=potionEmbed.data()+id*32;for(int j=0;j<32;++j)raw[j]+=e[j];}
        float t[D]={};
        if(hasPotionProj){linear(raw,32,potionProjW.data(),potionProjB.data(),D,t);}
        else{for(int j=0;j<32;++j)t[j]=raw[j];}
        for(int i=0;i<D;++i)tokensOut[off++]=t[i]+typeEmbed[3*D+i];}

    {int enc=std::max(0,std::min(127,(int)feat[1]));
        float raw[32];for(int j=0;j<32;++j)raw[j]=encEmbed[enc*32+j];
        float t[D]={};
        if(hasEncProj){linear(raw,32,encProjW.data(),encProjB.data(),D,t);}
        else{for(int j=0;j<32;++j)t[j]=raw[j];}
        for(int i=0;i<D;++i)tokensOut[off++]=t[i]+typeEmbed[4*D+i];}

    for(int s=0;s<5;++s){const float*m=&feat[MO+s*9];
        if(m[1]<=0.f){for(int i=0;i<D;++i)tokensOut[off++]=0.f;continue;}
        int mid=std::max(0,std::min(255,(int)m[0])),in=std::max(0,std::min(31,(int)m[4]));
        float mi[87];std::copy_n(monIdEmbed.data()+mid*64,64,mi);std::copy_n(monIntentEmbed.data()+in*16,16,mi+64);
        int ci[7]={1,2,3,5,6,7,8};for(int j=0;j<7;++j)mi[80+j]=(m[ci[j]]-monContMean[j])*monContInv[j];
        float t[D];linear(mi,87,monEncW.data(),monEncB.data(),D,t);
        for(int i=0;i<D;++i)tokensOut[off++]=relu(t[i])+typeEmbed[5*D+i];}

    nTokens=off/D;
}

// ---- Transformer -----------------------------------------------------------
void CombatPVNet::applyTransformer(float*tokens,int nTokens)const{
    int D=entityDim;
    thread_local std::vector<float> buf;buf.resize(nTokens*D);
    for(int l=0;l<numLayers;++l){multiHeadAttn(tokens,nTokens,D,numHeads,layers[l],buf.data());ffn(buf.data(),nTokens,D,hiddenDim,layers[l],tokens);}
}

// ---- Encoder: state features -> global embedding --------------------------
void CombatPVNet::encode(const std::array<float,1766>&feat,float*globalOut)const{
    int D=entityDim;
    thread_local std::vector<float> tokens;
    tokens.resize(14*D);
    int nT=0;
    buildTokens(feat,tokens.data(),nT);
    if(nT<=1){for(int i=0;i<D;++i)globalOut[i]=tokens[i];return;}
    applyTransformer(tokens.data(),nT);
    for(int i=0;i<D;++i)globalOut[i]=tokens[i];
}

// ---- Policy head -----------------------------------------------------------
float CombatPVNet::policyScore(const float*globalEmb,const float*actionFeat)const{
    int D=entityDim;
    float a64[64],aD[D];
    linear(actionFeat,14,policyActEncW0.data(),policyActEncB0.data(),64,a64);
    for(int i=0;i<64;++i)a64[i]=relu(a64[i]);
    linear(a64,64,policyActEncW2.data(),policyActEncB2.data(),D,aD);
    for(int i=0;i<D;++i)aD[i]=relu(aD[i]);
    float concat[3*256];
    for(int i=0;i<D;++i){concat[i]=globalEmb[i];concat[D+i]=aD[i];concat[2*D+i]=globalEmb[i]*aD[i];}
    float h[D];
    linear(concat,3*D,policyScorerW0.data(),policyScorerB0.data(),D,h);
    for(int i=0;i<D;++i)h[i]=relu(h[i]);
    float s=policyScorerB2[0];for(int i=0;i<D;++i)s+=h[i]*policyScorerW2[i];
    return s;
}

void CombatPVNet::policyScores(const float*globalEmb,const float*actionFeats,int nActions,float*logitsOut)const{
    for(int a=0;a<nActions;++a)logitsOut[a]=policyScore(globalEmb,actionFeats+a*14);
}

// ---- Value head ------------------------------------------------------------
void CombatPVNet::predictValue(const float*globalEmb,
                               float&winProb,float&deathProb,
                               std::array<float,11>*quantiles,
                               std::array<float,44>*potionProbs,
                               float*turnsRemaining)const{
    int D=entityDim;
    float ws=winB;for(int i=0;i<D;++i)ws+=winW[i]*globalEmb[i];winProb=sigmoid(ws);
    float ds=deathB;for(int i=0;i<D;++i)ds+=deathW[i]*globalEmb[i];deathProb=sigmoid(ds);
    if(quantiles){for(int q=0;q<nQuantile;++q){float s=quantileB[q];for(int i=0;i<D;++i)s+=quantileW[q*D+i]*globalEmb[i];(*quantiles)[q]=std::max(0.0f,s);}}
    if(potionProbs){for(int q=0;q<44;++q){float s=potionB[q];for(int i=0;i<D;++i)s+=potionW[q*D+i]*globalEmb[i];(*potionProbs)[q]=sigmoid(s);}}
    if(turnsRemaining){float s=turnsB;for(int i=0;i<D;++i)s+=turnsW[i]*globalEmb[i];*turnsRemaining=std::max(0.0f,s);}
}

// ---- Full inference --------------------------------------------------------
void CombatPVNet::predictFromBC(const BattleContext&bc,float&winProb,float&deathProb,
                                std::array<float,11>*quantiles)const{
    std::array<float,1766>feat{};
    combatExtractFeatures(bc,feat.data());
    thread_local std::vector<float> globalEmb;globalEmb.resize(entityDim);
    encode(feat,globalEmb.data());
    predictValue(globalEmb.data(),winProb,deathProb,quantiles);
}

// ---- Leaf utility ----------------------------------------------------------
double CombatPVNet::leafValue(const BattleContext&bc,double riskLambda)const{
    float wp,dp;
    std::array<float,kPVQuantileBins>qs{};
    predictFromBC(bc,wp,dp,&qs);
    int mid=nQuantile/2;
    double median=(double)qs[mid];
    std::array<double,kPVQuantileBins>sq;
    for(int i=0;i<nQuantile;++i)sq[i]=(double)qs[i];
    std::sort(sq.begin(),sq.begin()+nQuantile);
    int cvCount=std::max(1,(int)(nQuantile*0.25));
    double cvar=0.0;for(int i=0;i<cvCount;++i)cvar+=sq[i];cvar/=cvCount;
    if (g_pvnetHpScale) {
        // §123: quantiles are endHp/maxHp fractions; map back to the HP scale
        // the terminal evaluation (curHp+50) uses, so leaf and terminal agree.
        const double maxHp = std::max(1.0, (double)bc.player.maxHp);
        median *= maxHp;
        cvar *= maxHp;
    }
    return (double)wp*(winBonus+median)-riskLambda*(median-cvar);
}

std::string CombatPVNet::description()const{
    return "pvnet d"+std::to_string(entityDim)+" h"+std::to_string(hiddenDim)+" hds"+std::to_string(numHeads)+" L"+std::to_string(numLayers);
}

} // namespace sts::search
