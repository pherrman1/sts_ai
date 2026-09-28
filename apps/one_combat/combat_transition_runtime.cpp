#include "combat_transition_runtime.h"
#include "combat_transition_near_full.h"
#include "run_features.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <memory>
#include <numeric>
#include <openssl/evp.h>
#include <sstream>
#include <stdexcept>

namespace one_combat {
namespace {
using Vec=std::vector<float>;
void require(bool value,const char *why) { if(!value) throw std::runtime_error(why); }
std::string sha256File(const std::string &path) {
    std::ifstream file(path,std::ios::binary);
    require(bool(file),"cannot open combat artifact for SHA256");
    std::unique_ptr<EVP_MD_CTX,decltype(&EVP_MD_CTX_free)> context(EVP_MD_CTX_new(),EVP_MD_CTX_free);
    require(bool(context) && EVP_DigestInit_ex(context.get(),EVP_sha256(),nullptr)==1,
        "cannot initialize combat artifact SHA256");
    char buffer[64*1024];
    while(file) {
        file.read(buffer,sizeof(buffer));
        const auto count=file.gcount();
        if(count>0) require(EVP_DigestUpdate(context.get(),buffer,static_cast<std::size_t>(count))==1,
            "cannot update combat artifact SHA256");
    }
    require(file.eof(),"cannot read combat artifact for SHA256");
    unsigned char digest[EVP_MAX_MD_SIZE];unsigned int length=0;
    require(EVP_DigestFinal_ex(context.get(),digest,&length)==1 && length==32,
        "cannot finalize combat artifact SHA256");
    std::ostringstream result;
    result << std::hex << std::setfill('0');
    for(unsigned int i=0;i<length;++i) result << std::setw(2) << unsigned(digest[i]);
    return result.str();
}
bool hasEntropicBrew(const CombatPredictorInputV1 &input) {
    return std::any_of(input.potions.begin(),input.potions.end(),[](const auto &p) {
        return p.potionId==int(sts::Potion::ENTROPIC_BREW);
    });
}
using R=sts::RelicId;
using P=sts::Potion;
int lizardId() { return static_cast<int>(R::LIZARD_TAIL); }
int bloomId() { return static_cast<int>(R::MARK_OF_THE_BLOOM); }
bool hasRelic(const CombatPredictorInputV1 &input,int id) {
    return std::any_of(input.relics.begin(),input.relics.end(),[&](const auto &r){return r.relicId==id;});
}
bool predictorHasActiveLizard(const CombatPredictorInputV1 &input) {
    return std::any_of(input.relics.begin(),input.relics.end(),[](const auto &r) {
        return r.relicId==static_cast<int>(R::LIZARD_TAIL) && r.data==1;
    });
}
bool hasFairyPotion(const CombatPredictorInputV1 &input) {
    return std::any_of(input.potions.begin(),input.potions.end(),[](const auto &p) {
        return p.potionId==static_cast<int>(P::FAIRY_POTION);
    });
}
CombatPredictorInputV1 withoutLizard(CombatPredictorInputV1 input) {
    input.relics.erase(std::remove_if(input.relics.begin(),input.relics.end(),[](const auto &r) {
        return r.relicId==static_cast<int>(R::LIZARD_TAIL);
    }),input.relics.end());
    for(std::size_t i=0;i<input.relics.size();++i)
        input.relics[i].orderIndex=static_cast<int>(i);
    return input;
}
std::pair<CombatTransitionPersistentState,std::size_t> withoutLizard(
    CombatTransitionPersistentState input) {
    const auto it=std::find_if(input.relics.begin(),input.relics.end(),[](const auto &r) {
        return r.id==static_cast<int>(R::LIZARD_TAIL);
    });
    const std::size_t position=it==input.relics.end()?input.relics.size():
        static_cast<std::size_t>(it-input.relics.begin());
    input.relics.erase(std::remove_if(input.relics.begin(),input.relics.end(),[](const auto &r) {
        return r.id==static_cast<int>(R::LIZARD_TAIL);
    }),input.relics.end());
    constexpr int id=static_cast<int>(R::LIZARD_TAIL);
    input.relicBits.at(id/64)&=~(std::uint64_t{1}<<(id%64));
    return {std::move(input),position};
}
std::pair<CombatTransitionPersistentState,CombatPredictorInputV1> withHeadInputHp(
    CombatTransitionPersistentState pre,CombatPredictorInputV1 input,int hp) {
    require(hp>=1 && hp<=pre.maxHp,"conditional-head HP treatment outside legal state domain");
    pre.curHp=hp;
    input.globals.curHp=hp;
    return {std::move(pre),std::move(input)};
}
void restoreLizard(CombatTransitionPersistentState &post,
    const CombatTransitionPersistentState &original,std::size_t position,int tailData) {
    const auto it=std::find_if(original.relics.begin(),original.relics.end(),[](const auto &r) {
        return r.id==static_cast<int>(R::LIZARD_TAIL);
    });
    require(it!=original.relics.end() && it->data==1,"active Lizard post-state restoration identity");
    const auto insertAt=post.relics.begin()+static_cast<std::ptrdiff_t>(std::min(position,post.relics.size()));
    auto restored=*it;
    require(tailData==0 || tailData==1,"invalid Lizard post-state data");
    restored.data=tailData;
    post.relics.insert(insertAt,restored);
    constexpr int id=static_cast<int>(R::LIZARD_TAIL);
    post.relicBits.at(id/64)|=(std::uint64_t{1}<<(id%64));
}
void append(Vec &a,const Vec &b) { a.insert(a.end(),b.begin(),b.end()); }
Vec relu(Vec x) { for(auto &v:x) v=std::max(0.f,v); return x; }
void add(Vec &a,const Vec &b) { require(a.size()==b.size(),"runtime add dimensions"); for(size_t i=0;i<a.size();++i) a[i]+=b[i]; }
Vec softmax(Vec x) {
    require(!x.empty(),"empty runtime distribution");
    float maximum=*std::max_element(x.begin(),x.end());
    require(std::isfinite(maximum),"empty/nonfinite legal support");
    float sum=0;
    for(auto &v:x) { require(!std::isnan(v) && v!=std::numeric_limits<float>::infinity(),"invalid logit"); v=std::exp(v-maximum); sum+=v; }
    require(std::isfinite(sum) && sum>0,"invalid softmax");
    for(auto &v:x) v/=sum;
    return x;
}
const std::map<std::string,std::string> sourceHashes={
 {"survival","2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef"},
 {"max_hp","66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479"},
 {"hp","a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9"},
 {"potion","8e04bcd5265fb11b8fa91b4553a84690915f437e7b3afee0b93358e312de3ad6"},
 {"potion_encoder","2085010f1aeef7a7957cdc45c851b2424d640037fd0fa981eb7ae7274190f6ef"},
 {"relic","e07e79d487152ae294f4915ef4aecd0e8bd38b8dec8d0133a57b6b58af92bd71"}};
}
void CombatTransitionRuntime::requireCurrentStandardFallbackArtifact(const std::string &path) {
    static const std::string expected="e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd";
    require(sha256File(path)==expected,
        "Brew fallback artifact SHA256 differs from the pinned current standard Attention CTM");
}
CombatTransitionRuntime::CombatTransitionRuntime(const std::string &path) {
    std::ifstream f(path,std::ios::binary);
    require(bool(f),"combat runtime cannot open requested artifact");
    auto read=[&](void *p,size_t n) { require(bool(f.read(static_cast<char*>(p),n)),"truncated combat runtime"); };
    auto u32=[&]() { unsigned char b[4];read(b,4);return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24); };
    constexpr char magic[]="COMBAT_TRANSITION_RUNTIME_V1";
    char actual[sizeof(magic)];read(actual,sizeof(actual));
    const bool full=std::memcmp(actual,"COMBAT_TRANSITION_RUNTIME_V2",sizeof(magic))==0;
    require(full || std::memcmp(actual,magic,sizeof(magic))==0,"combat runtime magic");
    require(u32()==(full?2u:1u),"combat runtime version");
    uint32_t length=u32();require(length>0 && length<=1024*1024,"combat runtime header size");
    std::string header(length,'\0');read(header.data(),length);metadata_=nlohmann::json::parse(header);
    require(metadata_.at("schema")==std::string(full?"COMBAT_TRANSITION_RUNTIME_V2":magic) && metadata_.at("version")== (full?2:1),"combat runtime schema");
    const bool deepSurvival=metadata_.contains("experimentalSurvival");
    const bool deepsetStack=metadata_.contains("experimentalDeepSets");
    const auto phase1Survival=nlohmann::json({
        {"architecture","deepset64_phase1_v1"},
        {"checkpointSha256","328c65f150ac7daa9db7dc7e2047b77cf8b88ef3c09b3da8ef57d75b7a2fd4c3"},
        {"controlSha256","e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"},
        {"preparedSha256","a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9"},
        {"preparedManifestSha256","fdf1ca760c971b212e60d9cb86beec78afae6b124958aa53c56a8aea5bb92f51"},
        {"scalarMeanSha256","b210c9834974eb30c80362ae10fbdeb97d15a835915bbbb2239e2b2cc81e18d9"},
        {"scalarInvSha256","48a4f84b2de751a5e49f157b980a3fbb33f31db330e580ecc4c258a3f424be55"},
        {"qualified",false}});
    const auto strongWdSurvival=nlohmann::json({
        {"architecture","deepset64_linear_strongWd"},
        {"checkpointSha256","3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b"},
        {"controlSha256","e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"},
        {"qualified",false}});
    if(deepSurvival) require(full && (metadata_.at("experimentalSurvival")==phase1Survival ||
        metadata_.at("experimentalSurvival")==strongWdSurvival),"combat runtime experimental survival identity");
    const auto legacyDeepSets=nlohmann::json({
        {"architecture","deepset64_shared_transition"},
        {"controlSha256","e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"},
        {"maxHpHpCheckpointSha256","bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663"},
        {"downstreamCheckpointSha256","c00ed677b8b2b2854fb62982247853982bc58d9fc20afdd96c593bcc6c07423a"},
        {"potionCheckpointSha256","06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1"},
        {"potionOfflineDecision","DEEPSET_POTION_REJECTED"},
        {"qualified",false}});
    const auto specialistDeepSets=nlohmann::json({
        {"architecture","deepset64_shared_hp_with_dedicated_potion_specialist"},
        {"controlSha256","e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"},
        {"maxHpHpCheckpointSha256","bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663"},
        {"downstreamCheckpointSha256","c00ed677b8b2b2854fb62982247853982bc58d9fc20afdd96c593bcc6c07423a"},
        {"potionSpecialistCheckpointSha256","71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace"},
        {"potionOfflineDecision","POTION_DEEPSET_SPECIALIST_REJECTED"},
        {"requiresEntropicBrewFallback",true},{"qualified",false},{"defaultChanged",false}});
    auto qualifiedDeepSets=specialistDeepSets;
    qualifiedDeepSets["qualified"]=true;
    qualifiedDeepSets["defaultChanged"]=true;
    const auto productionPromotionEvidence=nlohmann::json({
        {"gate2Classification","GATE2_ACTIVE_LIZARD_COMPOSED_RUNTIME_CANARY_PASS"},
        {"gate2ResultsSha256","1ecd285c78e69249b6e5f46943d84cc10bc4bb86eea4e912f1c0abe774fef1d9"},
        {"gate2FrozenImplementationSha","5c818c0e30aa20fb178bfde19355c01852afef84"},
        {"deepsetsQualificationClassification","OOC_HYBRID_QUALITY_CONFIRMED"},
        {"deepsetsQualificationSummarySha256","0afa5319c21706ef380b76825035514c76dbe694bbafa4ed6293a75ce48b98ce"},
        {"lizardCandidateManifestSha256","15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617"}});
    const bool lizardCandidate=metadata_.contains("activeLizardCorrection");
    const bool promotedLizard= lizardCandidate &&
        metadata_.at("activeLizardCorrection").value("status",std::string{})=="production_default_when_ooc_enabled";
    if(lizardCandidate) {
        const auto &c=metadata_.at("activeLizardCorrection");
        const auto expectedModel=nlohmann::json({
            {"featureMean",{0.7449433381740863}},
            {"featureScale",{0.24032617420774785}},
            {"standardizedCoefficients",{1.8256833712449918,1.1142687252357397}}});
        require(c.value("candidateId",std::string{})=="active-lizard-mechanical-q-learned-r-t2" &&
            c.value("candidateManifestSha256",std::string{})=="15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617" &&
            c.value("frozenQrArtifactSha256",std::string{})=="9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9" &&
            c.value("rModelSha256",std::string{})=="fbf29bf742e3c40b18a358386509a74ced54e97a2a7e760ff988de5c14a335a8" &&
            c.value("qMode",std::string{})=="mechanical_b1" &&
            c.value("qDefinition",std::string{})=="q = 1 - pOrdinaryWin" &&
            c.value("rMode",std::string{})=="frozen_learned_r" &&
            c.value("rFeatureOrder",nlohmann::json::array())==nlohmann::json({"pReserveWin"}) &&
            c.value("treatment",std::string{})=="T2_revive" &&
            c.value("t2Rule",std::string{})=="T2_revive: curHp = floor(maxHP/2) for WIN_CONSUMED conditional CTM heads" &&
            c.value("rModel",nlohmann::json::object())==expectedModel,
            "combat runtime frozen active-Lizard candidate identity");
        const bool statusOk=c.value("status",std::string{})=="integration_candidate" || promotedLizard;
        require(statusOk && c.value("qualified",false)==promotedLizard &&
            c.value("defaultChanged",false)==promotedLizard,
            "combat runtime active-Lizard promotion status");
        if(promotedLizard) {
            require(sha256File(path)==
                    "abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab",
                "combat runtime production artifact bytes differ from the Gate 2-reviewed package");
            require(metadata_.value("defaultForOocMcts",false) &&
                metadata_.at("qualification").value("classification",std::string{})=="DEEPSETS_BREW_LIZARD_T2_PRODUCTION_QUALIFIED",
                "combat runtime production default qualification");
            require(c.value("gate2ResultsSha256",std::string{})==
                    productionPromotionEvidence.at("gate2ResultsSha256") &&
                c.value("gate2Classification",std::string{})==
                    productionPromotionEvidence.at("gate2Classification") &&
                c.value("gate2FrozenImplementationSha",std::string{})==
                    productionPromotionEvidence.at("gate2FrozenImplementationSha") &&
                metadata_.value("productionPromotionEvidence",nlohmann::json::object())==
                    productionPromotionEvidence,
                "combat runtime production Gate 2 provenance");
        } else
            require(!metadata_.value("defaultForOocMcts",false),
                "combat runtime candidate cannot claim production default");
        lizardCorrection_=c;
    }
    if(deepsetStack) require(full && (metadata_.at("experimentalDeepSets")==legacyDeepSets ||
        metadata_.at("experimentalDeepSets")==specialistDeepSets ||
        (promotedLizard && metadata_.at("experimentalDeepSets")==qualifiedDeepSets)),
        "combat runtime experimental DeepSets identity");
    const bool dedicatedPotion=deepsetStack &&
        (metadata_.at("experimentalDeepSets")==specialistDeepSets ||
         (promotedLizard && metadata_.at("experimentalDeepSets")==qualifiedDeepSets));
    if(deepsetStack) require(deepSurvival && metadata_.at("experimentalSurvival")==phase1Survival,
        "combat runtime DeepSets stack requires Phase-1 survival");
    require(metadata_.at("predictorSchema")==CombatPredictorInputV1::SCHEMA && metadata_.at("predictorHash")==combatPredictorInputFieldSchemaHash()
        && metadata_.at("predictorFieldSchema")==CombatPredictorInputV1::FIELD_SCHEMA,"combat runtime predictor schema");
    require(metadata_.at("width")==64 && metadata_.at("layers")==2 && metadata_.at("heads")==4 && metadata_.at("feedForward")==128,"combat runtime encoder dimensions");
    require(metadata_.at("cardCount")==kNumCardIds && metadata_.at("relicCount")==kNumRelics && metadata_.at("potionCount")==kNumPotions,"combat runtime vocab");
    if(!full) require(metadata_.at("sources")==nlohmann::json(sourceHashes),"combat runtime source identities");
    else {
        std::map<std::string,std::string> hashes={
        {"survival","ccc3c210060be34b38fe0671d93c6acde4242563c80a25c5978b4190b80010c9"},
        {"maxHP","2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0"},
        {"HP","0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b"},
        {"potion","ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db"},
        {"downstream","d07ead94b3abb9d12f272337e18aece6acd261cc4a39a36b21b82f904236af91"}};
        if(deepSurvival) hashes["survival"]=metadata_.at("experimentalSurvival").at("checkpointSha256").get<std::string>();
        if(deepsetStack) {
            hashes["maxHP"]="bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663";
            hashes["HP"]=hashes["maxHP"];
            hashes["potion"]=dedicatedPotion ? "71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace"
                                             : "06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1";
            hashes["downstream"]="c00ed677b8b2b2854fb62982247853982bc58d9fc20afdd96c593bcc6c07423a";
        }
        require(metadata_.at("sources")==nlohmann::json(hashes),"combat runtime near-full source identities");
        require(metadata_.at("supportExclusions")==nlohmann::json({"smoke_bomb","pre_smoke_bomb_used","writhing_ritual_intersection"}),"combat runtime support exclusions");
        const auto qualification=metadata_.at("qualification").value("classification",std::string{});
        require(qualification=="FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS" ||
            (promotedLizard && qualification=="DEEPSETS_BREW_LIZARD_T2_PRODUCTION_QUALIFIED"),
            "combat runtime qualification");
        require(metadata_.at("supportCensus").at("all").at("supportedIndexSha256")=="969a239845e7638a5797bcf1f2d03dc7c599c83b22e8dd76337cb31c3c20e0ef" && metadata_.at("supportCensus").at("TEST").at("supportedIndexSha256")=="71f2ca52769aa36a39f5684bf408090deb10edf8c13e55803cc0fd46ce1bfc31","combat runtime qualified cohort");
    }
    require(metadata_.at("maxHpClasses")==nlohmann::json({0,3,4,5,6,7,8,9,10,11,12}),"combat runtime maxHP classes");
    std::vector<int> classes;for(int i=-160;i<=143;++i) classes.push_back(i);
    require(metadata_.at("hpClasses")==classes,"combat runtime HP classes");
    const auto &domain=metadata_.at("domain");
    require(domain.at("preCurHpRange")==nlohmann::json({1,161}) && domain.at("preMaxHpRange")==nlohmann::json({24,172}) && domain.at("maxHpDeltaValues")==metadata_.at("maxHpClasses") && domain.at("min")==-160 && domain.at("max")==143 && domain.at("classes")==304 && domain.at("sha256")=="f812c16ab1d220cd60e8a8915ebb368bcd7e6d9e48915eb8cce5c760fad78eec","combat runtime frozen envelope");
    require(metadata_.at("continuousFields")==nlohmann::json({"ascension","act","floor","curHp","maxHp","gold","potionCount","potionCapacity","potionKeepValue","isBurningElite"}),"combat runtime global fields");
    require(metadata_.at("globalCategoryCounts")==nlohmann::json({4,64,10,10}),"combat runtime global vocab");
    // Exact shape graph, including historical unused heads: reject missing/extra tensors.
    std::map<std::string,std::vector<int>> expected;
    auto shape=[&](std::string name,std::vector<int> dims) { expected.emplace(std::move(name),std::move(dims)); };
    auto lin=[&](std::string name,int out,int in) { shape(name+".weight",{out,in});shape(name+".bias",{out}); };
    for(std::string group:{"survival","max_hp","hp","potion_encoder"}) {
        std::string p=group+".encoder.";
        if((group=="survival" && deepSurvival) || (deepsetStack && (group=="max_hp" || group=="hp" || group=="potion_encoder"))) {
            shape(p+"scalar_mean",{10});shape(p+"scalar_inv",{10});
            shape(p+"card_id.weight",{kNumCardIds,48});shape(p+"relic_id.weight",{kNumRelics,48});
            shape(p+"potion_id.weight",{kNumPotions,32});shape(p+"potion_slot.weight",{5,8});
            auto categories=metadata_.at("globalCategoryCounts").get<std::vector<int>>();
            for(int category=0;category<4;++category) shape(p+"global_category."+std::to_string(category)+".weight",{categories[category],8});
            for(const auto &entry:std::map<std::string,int>{{"card_mlp",51},{"relic_mlp",50},{"potion_mlp",40}}) {
                lin(p+entry.first+".0",64,entry.second);lin(p+entry.first+".2",64,64);
            }
            lin(p+"global_mlp.0",64,42);lin(p+"trunk.0",128,256);lin(p+"trunk.2",64,128);
            if(group=="survival") lin("survival.survival",1,64);
            else if(group=="max_hp") lin("max_hp.max_hp_delta",11,64);
            else if(group=="hp") {shape("hp.delta_embedding.weight",{11,8});lin("hp.hp.0",64,72);lin("hp.hp.2",304,64);}
            continue;
        }
        shape(p+"scalar_mean",{10});shape(p+"scalar_inv",{10});
        shape(p+"card_id.weight",{kNumCardIds,64});shape(p+"relic_id.weight",{kNumRelics,64});shape(p+"potion_id.weight",{kNumPotions,64});shape(p+"type_embedding.weight",{4,64});
        auto cats=metadata_.at("globalCategoryCounts").get<std::vector<int>>();
        for(int i=0;i<4;++i) shape(p+"global_category."+std::to_string(i)+".weight",{cats[i],8});
        lin(p+"global_proj",64,42);lin(p+"card_fields",64,3);lin(p+"relic_fields",64,2);shape(p+"potion_slot.weight",{5,64});
        for(int i=0;i<2;++i) {
            auto l=p+"encoder.layers."+std::to_string(i)+".";
            shape(l+"self_attn.in_proj_weight",{192,64});shape(l+"self_attn.in_proj_bias",{192});lin(l+"self_attn.out_proj",64,64);
            lin(l+"linear1",128,64);lin(l+"linear2",64,128);
            for(auto n:{"norm1","norm2"}) {shape(l+n+".weight",{64});shape(l+n+".bias",{64});}
        }
        lin(p+"trunk.0",64,64);
        if(group=="hp") {shape(group+".delta_embedding.weight",{11,8});lin(group+".hp.0",64,72);lin(group+".hp.2",304,64);}
        else {lin(group+".survival",1,64);if(group!="max_hp") lin(group+".hp",1,64);}
        if(group=="max_hp") {
            lin(group+".max_hp_delta",11,64);shape(group+".hp_delta_embedding.weight",{11,8});lin(group+".hp.0",64,72);lin(group+".hp.2",101,64);
            shape(group+".potion_slot.weight",{5,8});lin(group+".potion",kNumPotions,72);shape(group+".relic_token_id.weight",{kNumRelics,16});lin(group+".relic.0",64,82);
            // Historical relic class count is frozen by its shape, below.
            shape(group+".relic.2.weight",{19,64});
            shape(group+".relic.2.bias",{expected.at(group+".relic.2.weight")[0]});
        }
    }
    shape("potion.delta.weight",{11,8});shape("potion.potion.weight",{kNumPotions,8});shape("potion.slot.weight",{5,4});lin("potion.mlp.0",64,133);lin("potion.mlp.2",full?64:32,64);
    shape("relic.delta.weight",{304,16});shape("relic.mask.weight",{32,8});lin("relic.shared.0",64,full?90:89);
    for(auto entry:std::map<std::string,int>{{"turns",6},{"attacks",10},{"cards",10},{"shuffles",3},{"lizard",2}}) lin("relic.heads."+entry.first,entry.second,64);
    if(full) {
        for(std::string g:{"writhing","ritual"}) {lin(g+".context.0",64,80);lin(g+".context.2",32,64);lin(g+".event.0",32,3);}
        lin("gold.condition.0",64,87);lin("gold.condition.2",32,64);lin("gold.candidates.0",32,6);lin("gold.bias",1,6);
    }
    require(metadata_.at("tensors")==nlohmann::json(expected),"combat runtime tensor graph/dimensions");
    for(const auto &entry:expected) {
        Tensor t;t.shape=entry.second;size_t count=1;for(int dim:t.shape) { require(dim>0 && dim<=4096,"combat tensor dimension");count*=dim; }
        t.values.resize(count);
        for(float &value:t.values) { uint32_t bits=u32();std::memcpy(&value,&bits,4);require(std::isfinite(value),"combat runtime nonfinite weight"); }
        weights.emplace(entry.first,std::move(t));
    }
    require(f.peek()==std::char_traits<char>::eof(),"combat runtime trailing bytes");
}
const CombatTransitionRuntime::Tensor &CombatTransitionRuntime::tensor(const std::string &name) const {return weights.at(name);}
Vec CombatTransitionRuntime::linear(const std::string &name,const Vec &x) const {
    const auto &w=tensor(name+".weight"),&b=tensor(name+".bias");require(w.shape.size()==2 && size_t(w.shape[1])==x.size(),"combat linear dimension");
    Vec out=b.values;
    for(int i=0;i<w.shape[0];++i) {float sum=0;for(size_t j=0;j<x.size();++j) sum+=w.values[i*x.size()+j]*x[j];out[i]+=sum;}
    return out;
}
Vec CombatTransitionRuntime::embedding(const std::string &name,int index) const {
    const auto &w=tensor(name+".weight");require(w.shape.size()==2 && index>=0 && index<w.shape[0],"combat embedding domain");
    return Vec(w.values.begin()+index*w.shape[1],w.values.begin()+(index+1)*w.shape[1]);
}
Vec CombatTransitionRuntime::encode(const std::string &group,const CombatPredictorInputV1 &input) const {
    require(input.cards.size()<=128 && input.relics.size()<=64 && input.potions.size()==5,"combat input token bound");
    const auto &g=input.globals;const std::string p=group+".encoder.";
    Vec global={float(g.ascension),float(g.act),float(g.floor),float(g.curHp),float(g.maxHp),float(g.gold),float(g.potionCount),float(g.potionCapacity),float(g.potionKeepValue),float(g.isBurningElite)};
    const auto &mean=tensor(p+"scalar_mean").values,&inv=tensor(p+"scalar_inv").values;
    for(int i=0;i<10;++i) global[i]=(global[i]-mean[i])*inv[i];
    int cats[4]={g.characterClass,g.encounter,g.roomClass,g.lastRoom};
    for(int i=0;i<4;++i) append(global,embedding(p+"global_category."+std::to_string(i),cats[i]));
    if((group=="survival" && metadata_.contains("experimentalSurvival")) ||
       (metadata_.contains("experimentalDeepSets") && (group=="max_hp" || group=="hp" || group=="potion_encoder"))) {
        auto transform=[&](const std::string &name,const Vec &fields) {
            return relu(linear(p+name+".2",relu(linear(p+name+".0",fields))));
        };
        Vec cardPool(64),relicPool(64),potionPool(64);
        for(const auto &card:input.cards) {
            auto fields=embedding(p+"card_id",card.cardId);
            append(fields,{float(card.upgraded),float(std::clamp(card.misc,-20,20))/20,float(card.bottleBinding+1)/3});
            add(cardPool,transform("card_mlp",fields));
        }
        for(const auto &relic:input.relics) {
            auto fields=embedding(p+"relic_id",relic.relicId);
            append(fields,{float(relic.data)/10,float(relic.orderIndex)/64});
            add(relicPool,transform("relic_mlp",fields));
        }
        for(const auto &potion:input.potions) {
            auto fields=embedding(p+"potion_id",potion.potionId);
            append(fields,embedding(p+"potion_slot",potion.slot));
            add(potionPool,transform("potion_mlp",fields));
        }
        append(cardPool,relicPool);append(cardPool,potionPool);
        append(cardPool,relu(linear(p+"global_mlp.0",global)));
        return relu(linear(p+"trunk.2",relu(linear(p+"trunk.0",cardPool))));
    }
    std::vector<Vec> tokens;
    auto token=linear(p+"global_proj",global);add(token,embedding(p+"type_embedding",0));tokens.push_back(token);
    for(const auto &c:input.cards) {token=embedding(p+"card_id",c.cardId);add(token,linear(p+"card_fields",{float(c.upgraded),float(std::clamp(c.misc,-20,20))/20,float(c.bottleBinding+1)/3}));add(token,embedding(p+"type_embedding",1));tokens.push_back(token);}
    for(const auto &r:input.relics) {token=embedding(p+"relic_id",r.relicId);add(token,linear(p+"relic_fields",{float(r.data)/10,float(r.orderIndex)/64}));add(token,embedding(p+"type_embedding",2));tokens.push_back(token);}
    for(const auto &pot:input.potions) {token=embedding(p+"potion_id",pot.potionId);add(token,embedding(p+"potion_slot",pot.slot));add(token,embedding(p+"type_embedding",3));tokens.push_back(token);}
    auto norm=[&](Vec x,const std::string &name) {float mean=0;for(float v:x)mean+=v;mean/=64;float variance=0;for(float v:x)variance+=(v-mean)*(v-mean);variance/=64;float scale=1/std::sqrt(variance+1e-5f);const auto &w=tensor(name+".weight").values,&b=tensor(name+".bias").values;for(int i=0;i<64;++i)x[i]=(x[i]-mean)*scale*w[i]+b[i];return x;};
    for(int layer=0;layer<2;++layer) {
        auto l=p+"encoder.layers."+std::to_string(layer)+".";
        const auto &w=tensor(l+"self_attn.in_proj_weight").values,&b=tensor(l+"self_attn.in_proj_bias").values;
        std::vector<Vec> qkv(tokens.size(),Vec(192));
        for(size_t t=0;t<tokens.size();++t) {
            // The final encoder layer returns only the global token. Its query
            // uses every token's K/V, but no other token's Q is consumed.
            const int firstOutput=(layer==1 && t>0)?64:0;
            for(int i=firstOutput;i<192;++i){float sum=0;for(int j=0;j<64;++j)sum+=w[i*64+j]*tokens[t][j];qkv[t][i]=sum+b[i];}
        }
        std::vector<Vec> next;
        const size_t queryCount=layer==1?1:tokens.size();
        for(size_t t=0;t<queryCount;++t) {
            Vec attention(64,0);
            for(int head=0;head<4;++head) {
                Vec score(tokens.size());
                for(size_t k=0;k<tokens.size();++k) {float sum=0;for(int j=head*16;j<(head+1)*16;++j)sum+=qkv[t][j]*qkv[k][64+j];score[k]=sum*.25f;}
                auto prob=softmax(score);
                for(size_t k=0;k<tokens.size();++k)for(int j=head*16;j<(head+1)*16;++j)attention[j]+=prob[k]*qkv[k][128+j];
            }
            auto x=tokens[t];add(x,linear(l+"self_attn.out_proj",attention));x=norm(x,l+"norm1");
            auto ff=linear(l+"linear1",x);for(auto &v:ff)v=.5f*v*(1+std::erf(v/std::sqrt(2.f)));
            add(x,linear(l+"linear2",ff));next.push_back(norm(x,l+"norm2"));
        }
        tokens=std::move(next);
    }
    return relu(linear(p+"trunk.0",tokens[0]));
}
bool CombatTransitionRuntime::requiresEntropicBrewFallback() const {
    return metadata_.contains("experimentalDeepSets") &&
        metadata_.at("experimentalDeepSets").value("requiresEntropicBrewFallback",false);
}
double CombatTransitionRuntime::activeLizardReserveProbability(double pReserveWin) const {
    require(hasActiveLizardCorrection(),"active-Lizard parameters missing from combat artifact");
    require(std::isfinite(pReserveWin) && pReserveWin>=0.0 && pReserveWin<=1.0,
        "invalid active-Lizard reserve survival probability");
    const auto &model=lizardCorrection_.at("rModel");
    const auto mean=model.at("featureMean").at(0).get<double>();
    const auto scale=model.at("featureScale").at(0).get<double>();
    const auto &beta=model.at("standardizedCoefficients");
    require(std::isfinite(mean) && std::isfinite(scale) && scale>0.0 && beta.size()==2,
        "malformed frozen active-Lizard r model");
    const double z=std::clamp(beta.at(0).get<double>()+
        beta.at(1).get<double>()*((pReserveWin-mean)/scale),-40.0,40.0);
    return 1.0/(1.0+std::exp(-z));
}
float CombatTransitionRuntime::survival(const CombatPredictorInputV1 &p) const {float logit=linear("survival.survival",encode("survival",p))[0];require(std::isfinite(logit),"nonfinite survival");return 1/(1+std::exp(-logit));}
Vec CombatTransitionRuntime::maxHpEncoding(const CombatPredictorInputV1 &p) const {return encode("max_hp",p);}
Vec CombatTransitionRuntime::maxHp(const CombatPredictorInputV1 &p) const {return softmax(linear("max_hp.max_hp_delta",encode("max_hp",p)));}
Vec CombatTransitionRuntime::maxHp(const Vec &encoding) const {return softmax(linear("max_hp.max_hp_delta",encoding));}
Vec CombatTransitionRuntime::hpEncoding(const CombatPredictorInputV1 &p) const {return encode("hp",p);}
Vec CombatTransitionRuntime::signedHp(const Vec &z,int delta,int preHp,int maximum) const {auto x=z;append(x,embedding("hp.delta_embedding",delta));auto logits=linear("hp.hp.2",relu(linear("hp.hp.0",x)));for(int i=0;i<304;++i)if(preHp+i-160<1 || preHp+i-160>maximum)logits[i]=-std::numeric_limits<float>::infinity();return softmax(logits);}
Vec CombatTransitionRuntime::potion(const CombatPredictorInputV1 &p,int delta,float fraction) const {
    return potion(potionEncoding(p),p,delta,fraction);
}
Vec CombatTransitionRuntime::potionEncoding(const CombatPredictorInputV1 &p) const {return encode("potion_encoder",p);}
Vec CombatTransitionRuntime::potion(const Vec &encoding,const CombatPredictorInputV1 &p,int delta,float fraction) const {
    if(nearFull()){std::array<int,5> inventory;for(int i=0;i<5;++i)inventory[i]=p.potions.at(i).potionId;return potionInventory(encoding,inventory,p.globals.potionCapacity,delta,fraction,sts::isBossEncounter(static_cast<sts::MonsterEncounter>(p.globals.encounter)));}
    auto x=encoding;append(x,embedding("potion.delta",delta));x.push_back(fraction);
    for(const auto &pot:p.potions) {append(x,embedding("potion.potion",pot.potionId));append(x,embedding("potion.slot",pot.slot));}
    auto logits=linear("potion.mlp.2",relu(linear("potion.mlp.0",x)));
    // #174 first normalizes all 32 logits, then masks and normalizes again.
    float largest=*std::max_element(logits.begin(),logits.end());float total=0;for(float value:logits)total+=std::exp(value-largest);float logTotal=std::log(total);for(auto &value:logits)value=value-largest-logTotal;
    for(int mask=0;mask<32;++mask)for(int slot=0;slot<5;++slot)if((mask&(1<<slot)) && (slot>=p.globals.potionCapacity || p.potions.at(slot).potionId<=1))logits[mask]=-std::numeric_limits<float>::infinity();
    return softmax(logits);
}
std::map<std::string,Vec> CombatTransitionRuntime::relic(const Vec &z,int hpClass,float fraction,int mask,bool escaped) const {auto x=z;append(x,embedding("relic.delta",hpClass));x.push_back(fraction);append(x,embedding("relic.mask",mask));if(nearFull())x.push_back(float(escaped));auto shared=relu(linear("relic.shared.0",x));std::map<std::string,Vec> out;for(auto g:{"turns","attacks","cards","shuffles"})out.emplace(g,softmax(linear(std::string("relic.heads.")+g,shared)));return out;}
Vec CombatTransitionRuntime::potionInventory(const Vec &encoding,const std::array<int,5>& inventory,int capacity,int delta,float fraction,bool boss) const {
    require(nearFull(),"near-full potion interface on legacy artifact");
    auto x=encoding;append(x,embedding("potion.delta",delta));x.push_back(fraction);
    for(int slot=0;slot<5;++slot){append(x,embedding("potion.potion",inventory[slot]));append(x,embedding("potion.slot",slot));}
    auto logits=linear("potion.mlp.2",relu(linear("potion.mlp.0",x)));
    for(int a=0;a<64;++a){int mask=a&31,triggers=0;bool valid=true,smoke=false;
        for(int slot=0;slot<5;++slot)if(mask&(1<<slot)){
            valid&=slot<capacity && inventory[slot]>1;
            triggers+=inventory[slot]==int(sts::Potion::ENTROPIC_BREW)||inventory[slot]==int(sts::Potion::SMOKE_BOMB);
            smoke|=inventory[slot]==int(sts::Potion::SMOKE_BOMB);
        }
        valid&=triggers<=1 && (a<32 || (triggers==1 && !(boss&&smoke)));
        if(!valid)logits[a]=-std::numeric_limits<float>::infinity();
    }return softmax(logits);
}
Vec CombatTransitionRuntime::event(const std::string &group,const Vec &context,const std::vector<std::vector<Vec>>& candidates,const std::vector<bool>& legal) const {
    auto state=linear(group+".context.2",relu(linear(group+".context.0",context)));Vec logits;
    require(candidates.size()==legal.size(),"event legality dimensions");
    for(size_t i=0;i<candidates.size();++i){Vec embedded(32,0.f);
        for(const auto &card:candidates[i]){auto value=linear(group+".event.0",card);for(int j=0;j<32;++j)embedded[j]+=std::tanh(value[j]);}
        float score=0;for(int j=0;j<32;++j)score+=embedded[j]*state[j];
        logits.push_back(legal[i]?score/std::sqrt(32.f):-std::numeric_limits<float>::infinity());
    }return softmax(logits);
}
Vec CombatTransitionRuntime::gold(const Vec &context,const std::vector<Vec>& candidates) const {
    auto state=linear("gold.condition.2",relu(linear("gold.condition.0",context)));Vec logits;
    for(const auto &candidate:candidates){auto value=linear("gold.candidates.0",candidate);float score=0;
        for(int j=0;j<32;++j)score+=std::tanh(value[j])*state[j];
        logits.push_back(score/std::sqrt(32.f)+linear("gold.bias",candidate)[0]);
    }return softmax(logits);
}

}

namespace one_combat {
namespace {
CombatTransitionExpectation calculateForecastExpectation(
    const CombatTransitionRuntime &runtime, const NativeComposedDomain &domain,
    const CombatPredictorInputV1 &p) {
    const float survival = runtime.survival(p);
    const auto maxHp = runtime.maxHp(p), z = runtime.hpEncoding(p);
    double expectedFraction = 0;
    int maximumHp = p.globals.maxHp;
    for (const int delta : domain.maxHpClasses)
        maximumHp = std::max(maximumHp, p.globals.maxHp + delta);
    std::vector<float> histogram(static_cast<size_t>(maximumHp + 1), 0.0f);
    for (size_t delta = 0; delta < maxHp.size(); ++delta) {
        const int maximum = p.globals.maxHp + domain.maxHpClasses.at(delta);
        const auto hp = runtime.signedHp(z, int(delta), p.globals.curHp, maximum);
        double conditional = 0;
        for (size_t cls = 0; cls < hp.size(); ++cls) {
            const int finalHp = p.globals.curHp + domain.hpClasses.at(cls);
            conditional += hp[cls] * double(finalHp) / maximum;
            if (finalHp >= 0 && finalHp < static_cast<int>(histogram.size()))
                histogram.at(static_cast<size_t>(finalHp)) += maxHp.at(delta) * hp.at(cls);
        }
        expectedFraction += maxHp[delta] * conditional;
    }
    return {true, 1 - survival, float(expectedFraction), 0, std::move(histogram)};
}
CombatTransitionExpectation combineLizardExpectation(
    const CombatTransitionExpectation &ordinary,const CombatTransitionExpectation &consumed,
    const ActiveLizardPrediction &prediction) {
    const double ordinaryWin=prediction.classProbabilities[0];
    const double consumedWin=prediction.classProbabilities[1];
    const double totalWin=ordinaryWin+consumedWin;
    require(totalWin>0.0 && ordinary.supported && consumed.supported,
        "active-Lizard winning expectation is empty");
    std::vector<float> histogram(std::max(ordinary.winningHpHistogram.size(),
        consumed.winningHpHistogram.size()),0.0f);
    for(std::size_t i=0;i<histogram.size();++i) {
        const double ordinaryMass=i<ordinary.winningHpHistogram.size()?
            ordinary.winningHpHistogram[i]:0.0;
        const double consumedMass=i<consumed.winningHpHistogram.size()?
            consumed.winningHpHistogram[i]:0.0;
        histogram[i]=static_cast<float>((ordinaryWin*ordinaryMass+consumedWin*consumedMass)/totalWin);
    }
    const double expected=(ordinaryWin*ordinary.winningHpFraction+
        consumedWin*consumed.winningHpFraction)/totalWin;
    return {true,static_cast<float>(prediction.classProbabilities[2]),
        static_cast<float>(expected),0,std::move(histogram)};
}
}

NativeCombatTransitionSampler::NativeCombatTransitionSampler(const std::string &path):runtime_(path) {
    const auto &m=runtime_.metadata(),&d=m.at("domain");
    domain_.preCurHpRange=d.at("preCurHpRange").get<std::array<int,2>>();
    domain_.preMaxHpRange=d.at("preMaxHpRange").get<std::array<int,2>>();
    domain_.hpClasses=m.at("hpClasses").get<std::vector<int>>();domain_.maxHpClasses=m.at("maxHpClasses").get<std::vector<int>>();
    domain_.maxHpDeltaValues=d.at("maxHpDeltaValues").get<std::vector<int>>();
    domain_.trainedGroups={"turns","attacks","cards","shuffles"};domain_.nearFull=runtime_.nearFull();domain_.ready=true;
}
CombatRuntimeSupport NativeCombatTransitionSampler::support(const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    return supportState(captureCombatTransitionState(gc),p);
}
CombatRuntimeSupport NativeCombatTransitionSampler::supportState(
    const CombatTransitionPersistentState &pre,const CombatPredictorInputV1 &p) const {
    if(runtime_.requiresEntropicBrewFallback() && hasEntropicBrew(p))
        return {false,"entropic_brew_requires_standard_ctm"};
    auto reasons=nativeComposedSupportReasons(p,pre,domain_);
    return {reasons.empty(),reasons.empty()?"supported":reasons.front()};
}
CombatRuntimeSupport NativeCombatTransitionSampler::forecastSupport(const CombatPredictorInputV1 &p) const {
    if(runtime_.requiresEntropicBrewFallback() && hasEntropicBrew(p))
        return {false,"entropic_brew_requires_standard_ctm"};
    auto reasons = nativeComposedForecastSupportReasons(p, domain_);
    return {reasons.empty(), reasons.empty() ? "supported" : reasons.front()};
}
CombatTransitionExpectation NativeCombatTransitionSampler::forecastExpectation(
    const CombatPredictorInputV1 &p) const {
    if (!forecastSupport(p).supported) return {};
    return calculateForecastExpectation(runtime_, domain_, p);
}
CombatTransitionExpectation NativeCombatTransitionSampler::expectation(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    return expectationState(captureCombatTransitionState(gc),p);
}
CombatTransitionExpectation NativeCombatTransitionSampler::expectationState(
    const CombatTransitionPersistentState &pre,const CombatPredictorInputV1 &p) const {
    if(!supportState(pre,p).supported)return {};
    return calculateForecastExpectation(runtime_, domain_, p);
}
CombatRuntimeSample NativeCombatTransitionSampler::sample(const sts::GameContext &gc,const CombatPredictorInputV1 &p,std::mt19937_64 &rng) const {
    if(!support(gc,p).supported)return {};
    if(runtime_.nearFull())return sampleNearFull(runtime_,domain_,captureCombatTransitionState(gc),p,rng,runtime_.survival(p),{},{},{});
    auto uniform=[&]() {return std::generate_canonical<double,53>(rng);};
    auto category=[&](const Vec &prob) {double draw=uniform(),sum=0;int last=-1;for(size_t i=0;i<prob.size();++i){require(std::isfinite(prob[i]) && prob[i]>=0,"invalid sampler probability");sum+=prob[i];if(prob[i]>0)last=int(i);if(draw<sum)return int(i);}require(last>=0 && std::abs(sum-1)<1e-6,"invalid sampler total");return last;};
    if(uniform()>=runtime_.survival(p))return {CombatRuntimeSample::Outcome::DEATH,{}};
    auto post=captureCombatTransitionState(gc);
    int delta=category(runtime_.maxHp(p));post.maxHp+=domain_.maxHpClasses.at(delta);
    auto z=runtime_.hpEncoding(p);int signedClass=category(runtime_.signedHp(z,delta,post.curHp,post.maxHp));post.curHp+=domain_.hpClasses.at(signedClass);
    float fraction=float(post.curHp)/post.maxHp;int mask=category(runtime_.potion(p,delta,fraction));
    for(int slot=0;slot<5;++slot)if(mask&(1<<slot))post.potions[slot]=1;
    post.potionCount=0;for(int potion:post.potions)post.potionCount+=potion>1;
    std::map<std::string,int> residues;auto probs=runtime_.relic(z,signedClass,fraction,mask);
    // Preserve the Python decoder ModuleDict draw order, independent of map ordering.
    for(auto group:{"turns","attacks","cards","shuffles"})residues.emplace(group,category(probs.at(group)));
    post.relics=reconstructNativeComposedRelics(post.relics,residues,p.globals.encounter);
    post.combatRng[2]=replayNativeComposedMisc(post.combatRng[2],p.globals.encounter);
    return {CombatRuntimeSample::Outcome::VICTORY,std::move(post)};
}
// Keep sample() above as the uncached reference. This object owns only one
// immutable pre-combat edge; conditional heads and draws remain uncached.
std::unique_ptr<PreparedCombatTransition> NativeCombatTransitionSampler::prepare(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    return prepareState(captureCombatTransitionState(gc),p);
}
std::unique_ptr<PreparedCombatTransition> NativeCombatTransitionSampler::prepareState(
    const CombatTransitionPersistentState &pre,const CombatPredictorInputV1 &p) const {
    class NativePrepared final : public PreparedCombatTransition {
        const CombatTransitionRuntime &runtime_;
        const NativeComposedDomain &domain_;
        CombatRuntimeSupport support_;
        CombatTransitionPersistentState pre_;
        CombatPredictorInputV1 input_;
        float survival_ = 0;
        Vec maxHp_,hpEncoding_,potionEncoding_;
    public:
        NativePrepared(const CombatTransitionRuntime &runtime,const NativeComposedDomain &domain,
            CombatRuntimeSupport support,const CombatTransitionPersistentState &pre,
            const CombatPredictorInputV1 &p)
            :runtime_(runtime),domain_(domain),support_(std::move(support)),
             pre_(pre),input_(p) {
            if(support_.supported) {
                survival_=runtime_.survival(p);
                if(runtime_.metadata().contains("experimentalDeepSets")) {
                    auto transition=runtime_.hpEncoding(p);
                    maxHp_=runtime_.maxHp(transition);
                    hpEncoding_=transition;
                    if(runtime_.requiresEntropicBrewFallback()) potionEncoding_=runtime_.potionEncoding(p);
                    else potionEncoding_=std::move(transition);
                } else {
                    maxHp_=runtime_.maxHp(p);
                    hpEncoding_=runtime_.hpEncoding(p);
                    potionEncoding_=runtime_.potionEncoding(p);
                }
            }
        }
        const CombatRuntimeSupport &support() const override { return support_; }
        CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
            if(!support_.supported)return {};
            if(runtime_.nearFull())return sampleNearFull(runtime_,domain_,pre_,input_,rng,survival_,maxHp_,hpEncoding_,potionEncoding_);
            auto uniform=[&]() {return std::generate_canonical<double,53>(rng);};
            auto category=[&](const Vec &prob) {double draw=uniform(),sum=0;int last=-1;for(size_t i=0;i<prob.size();++i){require(std::isfinite(prob[i]) && prob[i]>=0,"invalid sampler probability");sum+=prob[i];if(prob[i]>0)last=int(i);if(draw<sum)return int(i);}require(last>=0 && std::abs(sum-1)<1e-6,"invalid sampler total");return last;};
            if(uniform()>=survival_)return {CombatRuntimeSample::Outcome::DEATH,{}};
            auto post=pre_;
            int delta=category(maxHp_);post.maxHp+=domain_.maxHpClasses.at(delta);
            int signedClass=category(runtime_.signedHp(hpEncoding_,delta,post.curHp,post.maxHp));post.curHp+=domain_.hpClasses.at(signedClass);
            float fraction=float(post.curHp)/post.maxHp;int mask=category(runtime_.potion(potionEncoding_,input_,delta,fraction));
            for(int slot=0;slot<5;++slot)if(mask&(1<<slot))post.potions[slot]=1;
            post.potionCount=0;for(int potion:post.potions)post.potionCount+=potion>1;
            std::map<std::string,int> residues;auto probs=runtime_.relic(hpEncoding_,signedClass,fraction,mask);
            for(auto group:{"turns","attacks","cards","shuffles"})residues.emplace(group,category(probs.at(group)));
            post.relics=reconstructNativeComposedRelics(post.relics,residues,input_.globals.encounter);
            post.combatRng[2]=replayNativeComposedMisc(post.combatRng[2],input_.globals.encounter);
            return {CombatRuntimeSample::Outcome::VICTORY,std::move(post)};
        }
        CombatRuntimeSample sampleConditionedVictory(std::mt19937_64 &rng) const override {
            if(!support_.supported || !runtime_.nearFull())return {};
            return sampleNearFull(runtime_,domain_,pre_,input_,rng,1.f,maxHp_,hpEncoding_,
                potionEncoding_,true);
        }
    };
    return std::make_unique<NativePrepared>(runtime_,domain_,supportState(pre,p),pre,p);
}

EntropicBrewFallbackCombatTransitionSampler::EntropicBrewFallbackCombatTransitionSampler(
    std::string fastPath,std::string standardPath,bool activeLizardEnabled)
    :fast_(std::make_shared<NativeCombatTransitionSampler>(fastPath)),
     standard_(std::make_shared<NativeCombatTransitionSampler>(standardPath)),
     activeLizardEnabled_(activeLizardEnabled) {
    CombatTransitionRuntime::requireCurrentStandardFallbackArtifact(standardPath);
    require(fast_->runtime().requiresEntropicBrewFallback(),
        "fast combat artifact must require Entropic Brew fallback");
    const auto &standardMetadata=standard_->runtime().metadata();
    const nlohmann::json currentStandardSources={
        {"survival","ccc3c210060be34b38fe0671d93c6acde4242563c80a25c5978b4190b80010c9"},
        {"maxHP","2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0"},
        {"HP","0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b"},
        {"potion","ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db"},
        {"downstream","d07ead94b3abb9d12f272337e18aece6acd261cc4a39a36b21b82f904236af91"}};
    require(!standard_->runtime().requiresEntropicBrewFallback() &&
        standardMetadata.at("version")==2 &&
        !standardMetadata.contains("experimentalSurvival") &&
        !standardMetadata.contains("experimentalDeepSets") &&
        standardMetadata.at("sources")==currentStandardSources &&
        standardMetadata.at("supportExclusions")==nlohmann::json({"smoke_bomb","pre_smoke_bomb_used","writhing_ritual_intersection"}) &&
        standardMetadata.at("qualification").at("classification")=="FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS",
        "Brew fallback must be the current standard Attention CTM artifact");
    require(!activeLizardEnabled_ || fast_->runtime().hasActiveLizardCorrection(),
        "active-Lizard correction enabled without its frozen artifact metadata");
}
bool EntropicBrewFallbackCombatTransitionSampler::hasActiveLizard(
    const CombatPredictorInputV1 &p) const {
    return predictorHasActiveLizard(p);
}
ActiveLizardPrediction EntropicBrewFallbackCombatTransitionSampler::predictActiveLizard(
    const CombatTransitionPersistentState &pre,const CombatPredictorInputV1 &p,
    bool forecastOnly) const {
    ActiveLizardPrediction result;
    if(!activeLizardEnabled_)return result;
    if(!fast_->runtime().hasActiveLizardCorrection()) {
        result.reason="active_lizard_parameters_missing";
        return result;
    }
    const int lid=lizardId();
    const auto inputCount=std::count_if(p.relics.begin(),p.relics.end(),[&](const auto &r){return r.relicId==lid;});
    const auto inputIt=std::find_if(p.relics.begin(),p.relics.end(),[&](const auto &r){return r.relicId==lid;});
    if(inputCount!=1 || inputIt==p.relics.end() || inputIt->data!=1) {
        result.reason="active_lizard_predictor_state_mismatch";
        return result;
    }
    if(!forecastOnly) {
        const auto stateCount=std::count_if(pre.relics.begin(),pre.relics.end(),[&](const auto &r){return r.id==lid;});
        const auto stateIt=std::find_if(pre.relics.begin(),pre.relics.end(),[&](const auto &r){return r.id==lid;});
        if(stateCount!=1 || stateIt==pre.relics.end() || stateIt->data!=1 ||
            static_cast<std::size_t>(inputIt->orderIndex)>=pre.relics.size() ||
            pre.relics.at(inputIt->orderIndex).id!=lid || pre.relics.at(inputIt->orderIndex).data!=1) {
            result.reason="active_lizard_state_mismatch";
            return result;
        }
    }
    const bool bloom=hasRelic(p,bloomId());
    const bool fairy=hasFairyPotion(p) ||
        (!forecastOnly && std::find(pre.potions.begin(),pre.potions.end(),static_cast<int>(P::FAIRY_POTION))!=pre.potions.end());
    if(bloom) { result.reason="mark_of_bloom_exact_path"; return result; }
    if(fairy) { result.reason="fairy_potion_exact_boundary"; return result; }
    if(hasEntropicBrew(p)) { result.reason="active_lizard_entropic_brew_unsupported"; return result; }

    auto ordinaryInput=withoutLizard(p);
    CombatRuntimeSupport ordinarySupport;
    CombatTransitionPersistentState ordinaryState;
    if(forecastOnly) ordinarySupport=fast_->forecastSupport(ordinaryInput);
    else {
        ordinaryState=withoutLizard(pre).first;
        ordinarySupport=fast_->supportState(ordinaryState,ordinaryInput);
    }
    if(!ordinarySupport.supported) {
        result.reason="unsupported:"+ordinarySupport.reason;
        return result;
    }
    const int reserveHp=std::min(ordinaryInput.globals.maxHp,
        ordinaryInput.globals.curHp+ordinaryInput.globals.maxHp/2);
    auto reserveInput=ordinaryInput;
    reserveInput.globals.curHp=reserveHp;
    CombatRuntimeSupport reserveSupport;
    if(forecastOnly) reserveSupport=fast_->forecastSupport(reserveInput);
    else {
        auto reserveHead=withHeadInputHp(ordinaryState,ordinaryInput,reserveHp);
        reserveSupport=fast_->supportState(reserveHead.first,reserveHead.second);
    }
    if(!reserveSupport.supported) {
        result.reason="reserve_unsupported:"+reserveSupport.reason;
        return result;
    }
    result.t2HeadInputHp=ordinaryInput.globals.maxHp/2;
    if(result.t2HeadInputHp<1) {
        result.reason="t2_revive_hp_outside_legal_domain";
        return result;
    }
    auto consumedInput=ordinaryInput;
    consumedInput.globals.curHp=result.t2HeadInputHp;
    CombatRuntimeSupport consumedSupport;
    if(forecastOnly) consumedSupport=fast_->forecastSupport(consumedInput);
    else {
        auto consumedHead=withHeadInputHp(ordinaryState,ordinaryInput,result.t2HeadInputHp);
        consumedSupport=fast_->supportState(consumedHead.first,consumedHead.second);
    }
    if(!consumedSupport.supported) {
        result.reason="t2_unsupported:"+consumedSupport.reason;
        return result;
    }
    result.pOrdinaryWin=fast_->runtime().survival(ordinaryInput);
    result.pReserveWin=fast_->runtime().survival(reserveInput);
    result.qTailConsumed=1.0-result.pOrdinaryWin;
    result.rWinGivenConsumed=fast_->runtime().activeLizardReserveProbability(result.pReserveWin);
    result.classProbabilities={result.pOrdinaryWin,
        result.qTailConsumed*result.rWinGivenConsumed,
        result.qTailConsumed*(1.0-result.rWinGivenConsumed)};
    const double total=std::accumulate(result.classProbabilities.begin(),
        result.classProbabilities.end(),0.0);
    if(!std::isfinite(total) || std::abs(total-1.0)>1e-12 ||
        std::any_of(result.classProbabilities.begin(),result.classProbabilities.end(),
            [](double value){return !std::isfinite(value)||value<0.0||value>1.0;})) {
        result.reason="active_lizard_invalid_class_probabilities";
        return result;
    }
    result.reason="supported";
    result.supported=true;
    return result;
}
bool EntropicBrewFallbackCombatTransitionSampler::useFallback(const CombatPredictorInputV1 &p) const {
    // Recursive Entropic Brew trajectories require Brew in the starting potion
    // inventory. Route the entire transition from predictor-visible pre-state;
    // never inspect sampled or generated potion outcomes to switch models.
    return hasEntropicBrew(p);
}
void EntropicBrewFallbackCombatTransitionSampler::recordBrewState(const CombatPredictorInputV1 &p) const {
    if(!hasEntropicBrew(p))return;
    std::lock_guard<std::mutex> lock(brewStatesMutex_);
    brewStates_.insert(combatPredictorInputJson(p).dump());
}
CombatRuntimeSupport EntropicBrewFallbackCombatTransitionSampler::support(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        auto prediction=predictActiveLizard(captureCombatTransitionState(gc),p);
        if(prediction.supported)return {true,"supported"};
        if(prediction.reason=="active_lizard_entropic_brew_unsupported") {
            lizardBoundaryExclusions_.fetch_add(1);
            lizardSupportFailures_.fetch_add(1);
            return {false,prediction.reason};
        }
        if(prediction.reason!="mark_of_bloom_exact_path" &&
            prediction.reason!="fairy_potion_exact_boundary") {
            lizardSupportFailures_.fetch_add(1);
            return {false,prediction.reason};
        }
        lizardBoundaryExclusions_.fetch_add(1);
    }
    const bool fallback=useFallback(p);
    auto result=(fallback?standard_:fast_)->support(gc,p);
    if(!result.supported)(fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    return result;
}
CombatRuntimeSupport EntropicBrewFallbackCombatTransitionSampler::forecastSupport(
    const CombatPredictorInputV1 &p) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        auto prediction=predictActiveLizard({},p,true);
        if(prediction.supported)return {true,"supported"};
        if(prediction.reason=="active_lizard_entropic_brew_unsupported") {
            lizardBoundaryExclusions_.fetch_add(1);
            lizardSupportFailures_.fetch_add(1);
            return {false,prediction.reason};
        }
        if(prediction.reason!="mark_of_bloom_exact_path" &&
            prediction.reason!="fairy_potion_exact_boundary") {
            lizardSupportFailures_.fetch_add(1);
            return {false,prediction.reason};
        }
        lizardBoundaryExclusions_.fetch_add(1);
    }
    const bool fallback=useFallback(p);
    auto result=(fallback?standard_:fast_)->forecastSupport(p);
    if(!result.supported)(fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    return result;
}
CombatTransitionExpectation EntropicBrewFallbackCombatTransitionSampler::forecastExpectation(
    const CombatPredictorInputV1 &p) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        auto prediction=predictActiveLizard({},p,true);
        if(prediction.supported) {
            auto ordinaryInput=withoutLizard(p);
            auto ordinary=fast_->forecastExpectation(ordinaryInput);
            auto consumedInput=ordinaryInput;
            consumedInput.globals.curHp=prediction.t2HeadInputHp;
            auto consumed=fast_->forecastExpectation(consumedInput);
            return combineLizardExpectation(ordinary,consumed,prediction);
        }
        if(prediction.reason=="active_lizard_entropic_brew_unsupported") {
            lizardBoundaryExclusions_.fetch_add(1);
            lizardSupportFailures_.fetch_add(1);
            return {};
        }
        if(prediction.reason!="mark_of_bloom_exact_path" &&
            prediction.reason!="fairy_potion_exact_boundary") {
            lizardSupportFailures_.fetch_add(1);
            return {};
        }
        lizardBoundaryExclusions_.fetch_add(1);
    }
    const bool fallback=useFallback(p);
    auto result=(fallback?standard_:fast_)->forecastExpectation(p);
    if(!result.supported)(fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    return result;
}
CombatTransitionExpectation EntropicBrewFallbackCombatTransitionSampler::expectation(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        auto original=captureCombatTransitionState(gc);
        auto prediction=predictActiveLizard(original,p);
        if(prediction.supported) {
            auto ordinary=withoutLizard(p);
            auto stripped=withoutLizard(original);
            auto ordinaryExpected=fast_->expectationState(stripped.first,ordinary);
            auto consumedHead=withHeadInputHp(stripped.first,ordinary,prediction.t2HeadInputHp);
            auto consumedExpected=fast_->expectationState(consumedHead.first,consumedHead.second);
            return combineLizardExpectation(ordinaryExpected,consumedExpected,prediction);
        }
        if(prediction.reason=="active_lizard_entropic_brew_unsupported") {
            lizardBoundaryExclusions_.fetch_add(1);
            lizardSupportFailures_.fetch_add(1);
            return {};
        }
        if(prediction.reason!="mark_of_bloom_exact_path" &&
            prediction.reason!="fairy_potion_exact_boundary") {
            lizardSupportFailures_.fetch_add(1);
            return {};
        }
        lizardBoundaryExclusions_.fetch_add(1);
    }
    const bool fallback=useFallback(p);
    auto result=(fallback?standard_:fast_)->expectation(gc,p);
    if(!result.supported)(fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    return result;
}
CombatRuntimeSample EntropicBrewFallbackCombatTransitionSampler::sample(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p,std::mt19937_64 &rng) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        auto prepared=prepare(gc,p);
        if(!prepared->support().supported)return {};
        return prepared->sample(rng);
    }
    const bool fallback=useFallback(p);
    (fallback?fallbackSamples_:fastSamples_).fetch_add(1);
    auto result=(fallback?standard_:fast_)->sample(gc,p,rng);
    if(result.outcome==CombatRuntimeSample::Outcome::UNSUPPORTED)
        (fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    return result;
}
std::unique_ptr<PreparedCombatTransition> EntropicBrewFallbackCombatTransitionSampler::prepare(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    recordBrewState(p);
    if(activeLizardEnabled_ && hasActiveLizard(p)) {
        const auto original=captureCombatTransitionState(gc);
        auto prediction=predictActiveLizard(original,p);
        const bool existingBoundary=prediction.reason=="mark_of_bloom_exact_path" ||
            prediction.reason=="fairy_potion_exact_boundary";
        if(!prediction.supported && !existingBoundary) {
            preparations_.fetch_add(1);
            lizardPreparations_.fetch_add(1);
            if(prediction.reason=="active_lizard_entropic_brew_unsupported")
                lizardBoundaryExclusions_.fetch_add(1);
            else lizardSupportFailures_.fetch_add(1);
            class RejectedPrepared final : public PreparedCombatTransition {
                CombatRuntimeSupport support_;
            public:
                explicit RejectedPrepared(CombatRuntimeSupport s):support_(std::move(s)){}
                const CombatRuntimeSupport &support() const override{return support_;}
                CombatRuntimeSample sample(std::mt19937_64 &) const override{return {};}
            };
            return std::make_unique<RejectedPrepared>(CombatRuntimeSupport{false,prediction.reason});
        }
        if(prediction.supported) {
            preparations_.fetch_add(1);
            lizardPreparations_.fetch_add(1);
            fastPreparations_.fetch_add(1);
            auto stripped=withoutLizard(original);
            auto ordinaryInput=withoutLizard(p);
            auto ordinaryChild=fast_->prepareState(stripped.first,ordinaryInput);
            auto consumedHead=withHeadInputHp(stripped.first,ordinaryInput,prediction.t2HeadInputHp);
            auto consumedChild=fast_->prepareState(consumedHead.first,consumedHead.second);
            if(!ordinaryChild->support().supported || !consumedChild->support().supported) {
                lizardSupportFailures_.fetch_add(1);
                fastSupportFailures_.fetch_add(1);
                class RejectedPrepared final : public PreparedCombatTransition {
                    CombatRuntimeSupport support_;
                public:
                    explicit RejectedPrepared(CombatRuntimeSupport s):support_(std::move(s)){}
                    const CombatRuntimeSupport &support() const override{return support_;}
                    CombatRuntimeSample sample(std::mt19937_64 &) const override{return {};}
                };
                return std::make_unique<RejectedPrepared>(!ordinaryChild->support().supported?
                    ordinaryChild->support():consumedChild->support());
            }
            class LizardPrepared final : public PreparedCombatTransition {
                std::unique_ptr<PreparedCombatTransition> ordinaryChild_;
                std::unique_ptr<PreparedCombatTransition> consumedChild_;
                CombatRuntimeSupport support_{true,"supported"};
                CombatTransitionPersistentState original_;
                std::size_t tailPosition_;
                std::array<double,3> probabilities_;
                std::atomic<std::uint64_t> &fastSamples_;
                std::atomic<std::uint64_t> &lizardSamples_;
                std::atomic<std::uint64_t> &ordinaryWins_;
                std::atomic<std::uint64_t> &consumedWins_;
                std::atomic<std::uint64_t> &consumedLosses_;
                std::atomic<std::uint64_t> &supportFailures_;
            public:
                LizardPrepared(std::unique_ptr<PreparedCombatTransition> ordinaryChild,
                    std::unique_ptr<PreparedCombatTransition> consumedChild,
                    CombatTransitionPersistentState original,std::size_t tailPosition,
                    std::array<double,3> probabilities,
                    std::atomic<std::uint64_t> &fastSamples,
                    std::atomic<std::uint64_t> &lizardSamples,
                    std::atomic<std::uint64_t> &ordinaryWins,
                    std::atomic<std::uint64_t> &consumedWins,
                    std::atomic<std::uint64_t> &consumedLosses,
                    std::atomic<std::uint64_t> &supportFailures)
                    :ordinaryChild_(std::move(ordinaryChild)),
                     consumedChild_(std::move(consumedChild)),original_(std::move(original)),
                     tailPosition_(tailPosition),probabilities_(probabilities),
                     fastSamples_(fastSamples),lizardSamples_(lizardSamples),
                     ordinaryWins_(ordinaryWins),consumedWins_(consumedWins),
                     consumedLosses_(consumedLosses),supportFailures_(supportFailures){}
                const CombatRuntimeSupport &support() const override{return support_;}
                CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
                    lizardSamples_.fetch_add(1);
                    fastSamples_.fetch_add(1);
                    const double draw=std::generate_canonical<double,53>(rng);
                    double cumulative=0.0;int outcome=2;
                    for(int i=0;i<3;++i) { cumulative+=probabilities_[i];if(draw<cumulative){outcome=i;break;} }
                    if(outcome==2) {
                        consumedLosses_.fetch_add(1);
                        return {CombatRuntimeSample::Outcome::DEATH,{}};
                    }
                    auto result=(outcome==1?consumedChild_:ordinaryChild_)->sampleConditionedVictory(rng);
                    if(result.outcome!=CombatRuntimeSample::Outcome::VICTORY) {
                        supportFailures_.fetch_add(1);
                        return {};
                    }
                    restoreLizard(result.rawPost,original_,tailPosition_,outcome==0?1:0);
                    if(outcome==0) ordinaryWins_.fetch_add(1);
                    else consumedWins_.fetch_add(1);
                    return result;
                }
            };
            return std::make_unique<LizardPrepared>(std::move(ordinaryChild),
                std::move(consumedChild),original,stripped.second,
                prediction.classProbabilities,fastSamples_,lizardSamples_,lizardOrdinaryWins_,
                lizardConsumedWins_,lizardConsumedLosses_,lizardSupportFailures_);
        }
        lizardBoundaryExclusions_.fetch_add(1);
    }
    const bool fallback=useFallback(p);
    preparations_.fetch_add(1);
    (fallback?fallbackPreparations_:fastPreparations_).fetch_add(1);
    auto child=(fallback?standard_:fast_)->prepare(gc,p);
    if(!child->support().supported)
        (fallback?fallbackSupportFailures_:fastSupportFailures_).fetch_add(1);
    class HybridPrepared final : public PreparedCombatTransition {
        std::unique_ptr<PreparedCombatTransition> child_;
        std::atomic<std::uint64_t> &samples_;
    public:
        HybridPrepared(std::unique_ptr<PreparedCombatTransition> child,
            std::atomic<std::uint64_t> &samples):child_(std::move(child)),samples_(samples) {}
        const CombatRuntimeSupport &support() const override { return child_->support(); }
        CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
            samples_.fetch_add(1);
            return child_->sample(rng);
        }
    };
    return std::make_unique<HybridPrepared>(std::move(child),fallback?fallbackSamples_:fastSamples_);
}
ActiveLizardPrediction EntropicBrewFallbackCombatTransitionSampler::activeLizardPrediction(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p) const {
    return predictActiveLizard(captureCombatTransitionState(gc),p);
}
CombatRuntimeSample EntropicBrewFallbackCombatTransitionSampler::sampleActiveLizardClass(
    const sts::GameContext &gc,const CombatPredictorInputV1 &p,std::mt19937_64 &rng,
    int outcomeClass) const {
    if(outcomeClass<0 || outcomeClass>2)return {};
    const auto original=captureCombatTransitionState(gc);
    const auto prediction=predictActiveLizard(original,p);
    if(!prediction.supported)return {};
    if(outcomeClass==2)return {CombatRuntimeSample::Outcome::DEATH,{}};
    auto stripped=withoutLizard(original);
    auto ordinaryInput=withoutLizard(p);
    auto branch=outcomeClass==1?
        withHeadInputHp(stripped.first,ordinaryInput,prediction.t2HeadInputHp):
        std::make_pair(stripped.first,ordinaryInput);
    auto child=fast_->prepareState(branch.first,branch.second);
    if(!child->support().supported)return {};
    auto result=child->sampleConditionedVictory(rng);
    if(result.outcome!=CombatRuntimeSample::Outcome::VICTORY)return {};
    restoreLizard(result.rawPost,original,stripped.second,outcomeClass==0?1:0);
    return result;
}
EntropicBrewFallbackCombatTransitionSampler::Metrics
EntropicBrewFallbackCombatTransitionSampler::takeMetrics() const {
    Metrics result;
    result.preparations=preparations_.exchange(0);
    result.fastPreparations=fastPreparations_.exchange(0);
    result.fallbackPreparations=fallbackPreparations_.exchange(0);
    result.fastSamples=fastSamples_.exchange(0);
    result.fallbackSamples=fallbackSamples_.exchange(0);
    result.fastSupportFailures=fastSupportFailures_.exchange(0);
    result.fallbackSupportFailures=fallbackSupportFailures_.exchange(0);
    result.lizardPreparations=lizardPreparations_.exchange(0);
    result.lizardSamples=lizardSamples_.exchange(0);
    result.lizardOrdinaryWins=lizardOrdinaryWins_.exchange(0);
    result.lizardConsumedWins=lizardConsumedWins_.exchange(0);
    result.lizardConsumedLosses=lizardConsumedLosses_.exchange(0);
    result.lizardBoundaryExclusions=lizardBoundaryExclusions_.exchange(0);
    result.lizardSupportFailures=lizardSupportFailures_.exchange(0);
    {
        std::lock_guard<std::mutex> lock(brewStatesMutex_);
        result.uniqueBrewPredictorStates=brewStates_.size();
        brewStates_.clear();
    }
    result.fallbackRate=result.preparations?
        double(result.fallbackPreparations)/double(result.preparations):0.0;
    return result;
}

}
