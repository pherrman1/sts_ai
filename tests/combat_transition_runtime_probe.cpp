// Offline probability probe: reads captured fixtures, never executes gameplay.
#include "../apps/one_combat/combat_transition_runtime.h"
#include "../apps/one_combat/combat_transition_near_full.h"
#include <fstream>
#include <iostream>
#include <chrono>
#include <cmath>
using namespace one_combat;
using json=nlohmann::json;
CombatPredictorInputV1 predictor(const json &j) {
    CombatPredictorInputV1 p;auto &g=p.globals;const auto &v=j.at("globals");
#define FIELD(name) g.name=v.at(#name).get<decltype(g.name)>()
    FIELD(characterClass);FIELD(ascension);FIELD(act);FIELD(floor);FIELD(curHp);FIELD(maxHp);FIELD(gold);FIELD(encounter);FIELD(roomClass);FIELD(lastRoom);FIELD(potionCount);FIELD(potionCapacity);FIELD(potionKeepValue);FIELD(isBurningElite);
#undef FIELD
    for(const auto &c:j.at("cards"))p.cards.push_back({c.at("cardId"),c.at("upgraded"),c.at("misc"),c.at("bottleBinding")});
    for(const auto &r:j.at("relics"))p.relics.push_back({r.at("relicId"),r.at("data"),r.at("orderIndex")});
    for(const auto &v:j.at("potions"))p.potions.push_back({v.at("slot"),v.at("potionId")});return p;
}
CombatTransitionPersistentState persistent(const json &j) {
    CombatTransitionPersistentState s;
#define FIELD(name) s.name=j.at(#name).get<decltype(s.name)>()
    FIELD(curHp);FIELD(maxHp);FIELD(gold);FIELD(potionCount);FIELD(potionCapacity);FIELD(potions);FIELD(smokeBombUsed);FIELD(stolenGold);FIELD(relicBits);FIELD(cardTypeCounts);FIELD(bottleIdxs);FIELD(upgradeableCount);FIELD(transformableCount);
#undef FIELD
    for(const auto &r:j.at("relics"))s.relics.push_back({r.at("id"),r.at("data")});
    for(const auto &c:j.at("deck"))s.deck.push_back({c.at("id"),c.at("misc"),c.at("upgraded")});
    for(int i=0;i<6;++i){auto &r=s.combatRng[i];auto v=j.at("combatRng")[i];r.counter=v.at("counter");r.seed0=v.at("seed0");r.seed1=v.at("seed1");}return s;
}
int main(int argc,char **argv) {
    try {
        if(argc!=3 && argc!=4)throw std::runtime_error("usage: combat_transition_runtime_probe MODEL FIXTURES [smoke-and-parity]");
        NativeCombatTransitionSampler sampler(argv[1]);const auto &net=sampler.runtime();
        std::mt19937_64 rng(20260914);
        std::ifstream file(argv[2]);if(!file)throw std::runtime_error("fixture file");
        std::string line;int fixtureIndex=0;
        const bool supportOnly=argc==4&&std::string(argv[3])=="support-only";
        const bool full=argc==4&&std::string(argv[3])=="near-full";
        while(std::getline(file,line)) {
            auto j=json::parse(line);auto p=predictor(j.at("predictorInput"));auto pre=persistent(j.contains("pre")?j.at("pre"):j.at("transition").at("pre"));
            sts::GameContext gc;applyCombatTransitionState(gc,pre);
            auto support=sampler.support(gc,p);json out={{"supported",support.supported},{"reason",support.reason}};
            if(supportOnly){out["index"]=fixtureIndex++;std::cout<<out.dump()<<'\n';continue;}
            if(full){
                if(support.supported){int d=j.value("delta",0),ending=j.value("ending",pre.curHp),maximum=j.value("maximum",pre.maxHp),mask=j.value("mask",0);std::vector<int> consumed=j.value("consumed",std::vector<int>{}),dagger=j.value("dagger",std::vector<int>{});
                    out["survival"]=net.survival(p);out["maxHp"]=net.maxHp(p);out["hp"]=net.signedHp(net.hpEncoding(p),d,pre.curHp,maximum);out["diagnostics"]=nearFullDiagnostics(net,pre,p,d,ending,maximum,mask,consumed,j.value("escaped",false),dagger);
                    auto prepared=sampler.prepare(gc,p);json samples=json::array();
                    for(int draw=0;draw<j.value("draws",128);++draw){std::mt19937_64 random(20260921+draw),cached=random,tape=random;json words=json::array();for(int k=0;k<256;++k)words.push_back(tape());auto sample=sampler.sample(gc,p,random),other=prepared->sample(cached);if(sample.outcome!=other.outcome||combatTransitionStateJson(sample.rawPost)!=combatTransitionStateJson(other.rawPost)||random!=cached)throw std::runtime_error("near-full prepared/reference parity");
                        auto count=std::mt19937_64(20260921+draw);int used=0;while(count!=random&&used<256){count();++used;}if(count!=random)throw std::runtime_error("parity draw tape exhausted");samples.push_back({{"outcome",int(sample.outcome)},{"rawPost",combatTransitionStateJson(sample.rawPost)},{"words",words},{"wordsUsed",used}});
                    }out["samples"]=samples;
                }std::cout<<out.dump()<<'\n';continue;
            }
            if(argc==4) {
                using Clock=std::chrono::steady_clock;
                auto start=Clock::now();auto prepared=sampler.prepare(gc,p);
                double preparationNs=std::chrono::duration<double,std::nano>(Clock::now()-start).count();
                if(prepared->support().supported!=support.supported || prepared->support().reason!=support.reason)
                    throw std::runtime_error("prepared support mismatch");
                double referenceNs=0,preparedNs=0;int victories=0,deaths=0;
                constexpr int seeds=32,drawsPerSeed=4;
                for(int seed=0;seed<seeds;++seed) {
                    std::mt19937_64 oldRng(20260914+seed),newRng=oldRng;
                    for(int draw=0;draw<drawsPerSeed;++draw) {
                        start=Clock::now();auto reference=sampler.sample(gc,p,oldRng);
                        referenceNs+=std::chrono::duration<double,std::nano>(Clock::now()-start).count();
                        start=Clock::now();auto sample=prepared->sample(newRng);
                        preparedNs+=std::chrono::duration<double,std::nano>(Clock::now()-start).count();
                        if(reference.outcome!=sample.outcome ||
                            combatTransitionStateJson(reference.rawPost)!=combatTransitionStateJson(sample.rawPost) || oldRng!=newRng)
                            throw std::runtime_error("prepared sample/state/RNG parity mismatch");
                        victories+=reference.outcome==CombatRuntimeSample::Outcome::VICTORY;
                        deaths+=reference.outcome==CombatRuntimeSample::Outcome::DEATH;
                    }
                }
                const int draws=seeds*drawsPerSeed;
                out["preparedParity"]={{"seeds",seeds},{"drawsPerSeed",drawsPerSeed},{"draws",draws},
                    {"victory",victories},{"death",deaths},{"fullPersistentStateEqual",true},{"plannerRngPostEqual",true},
                    {"supportEqual",true},{"preparationNs",preparationNs},{"referenceSampleNs",referenceNs/draws},
                    {"preparedSampleNs",preparedNs/draws},{"preparedAmortizedNs",(preparationNs+preparedNs)/draws},
                    {"referenceEncoderCalls",support.supported?draws+3*victories:0},
                    {"preparedEncoderCalls",support.supported?4:0}};
            }
            if(support.supported) {
                out["survival"]=net.survival(p);out["max_hp"]=net.maxHp(p);auto z=net.hpEncoding(p);out["hp_encoding"]=z;
                int delta=j.value("delta",0),hpClass=j.value("hpClass",160),mask=j.value("mask",0);float fraction=j.value("fraction",.5f);
                int maximum=pre.maxHp+net.metadata().at("maxHpClasses")[delta].get<int>();
                out["hp"]=net.signedHp(z,delta,pre.curHp,maximum);
                std::vector<bool> hpLegal,potionLegal;for(int i=0;i<304;++i)hpLegal.push_back(pre.curHp+i-160>=1 && pre.curHp+i-160<=maximum);
                for(int m=0;m<32;++m){bool legal=true;for(int slot=0;slot<5;++slot)if((m&(1<<slot)) && (slot>=pre.potionCapacity || pre.potions[slot]<=1))legal=false;potionLegal.push_back(legal);}
                out["hpLegal"]=hpLegal;out["potionLegal"]=potionLegal;
                out["potion"]=net.potion(p,delta,fraction);out["relic"]=net.relic(z,hpClass,fraction,mask);
                if(argc==4) {
                    using Clock=std::chrono::steady_clock;
                    double supportNs=0,deathNs=0,victoryNs=0;int deaths=0,victories=0;
                    json invalid={{"illegal_hp",0},{"illegal_potion",0},{"illegal_relic",0},{"shared_residue",0},{"invalid_rng",0},{"duplicate_reward",0},{"copy_through",0}};
                    for(int draw=0;draw<32;++draw) {
                        auto start=Clock::now();sampler.support(gc,p);supportNs+=std::chrono::duration<double,std::nano>(Clock::now()-start).count();
                        start=Clock::now();auto sample=sampler.sample(gc,p,rng);double ns=std::chrono::duration<double,std::nano>(Clock::now()-start).count();
                        if(sample.outcome==CombatRuntimeSample::Outcome::DEATH){++deaths;deathNs+=ns;continue;}
                        if(sample.outcome!=CombatRuntimeSample::Outcome::VICTORY)throw std::runtime_error("supported smoke fallback");
                        ++victories;victoryNs+=ns;const auto &post=sample.rawPost;
                        if(post.curHp<1 || post.curHp>post.maxHp)invalid["illegal_hp"]=invalid["illegal_hp"].get<int>()+1;
                        int count=0;for(int slot=0;slot<5;++slot){count+=post.potions[slot]>1;if(post.potions[slot]!=pre.potions[slot] && !(slot<pre.potionCapacity && pre.potions[slot]>1 && post.potions[slot]==1))invalid["illegal_potion"]=invalid["illegal_potion"].get<int>()+1;}
                        if(count!=post.potionCount)invalid["illegal_potion"]=invalid["illegal_potion"].get<int>()+1;
                        auto expectedRng=replayNativeComposedMisc(pre.combatRng[2],p.globals.encounter);
                        if(post.combatRng[2].seed0!=expectedRng.seed0 || post.combatRng[2].seed1!=expectedRng.seed1 || post.combatRng[2].counter!=expectedRng.counter || post.combatRng[4].seed0!=pre.combatRng[4].seed0 || post.combatRng[4].seed1!=pre.combatRng[4].seed1 || post.combatRng[4].counter!=pre.combatRng[4].counter)invalid["invalid_rng"]=invalid["invalid_rng"].get<int>()+1;
                        bool coherent=false;for(int turns=0;turns<6 && !coherent;++turns)for(int attacks=0;attacks<10 && !coherent;++attacks)for(int cards=0;cards<10 && !coherent;++cards)for(int shuffles=0;shuffles<3 && !coherent;++shuffles) {
                            auto reconstructed=reconstructNativeComposedRelics(pre.relics,{{"turns",turns},{"attacks",attacks},{"cards",cards},{"shuffles",shuffles}},p.globals.encounter);
                            bool same=reconstructed.size()==post.relics.size();for(size_t i=0;i<reconstructed.size() && same;++i)same=reconstructed[i].id==post.relics[i].id && reconstructed[i].data==post.relics[i].data;coherent=same;
                        }
                        if(!coherent){invalid["illegal_relic"]=invalid["illegal_relic"].get<int>()+1;invalid["shared_residue"]=invalid["shared_residue"].get<int>()+1;}
                        auto mutableCopy=pre;mutableCopy.curHp=post.curHp;mutableCopy.maxHp=post.maxHp;mutableCopy.potions=post.potions;mutableCopy.potionCount=post.potionCount;mutableCopy.relics=post.relics;mutableCopy.combatRng[2]=post.combatRng[2];
                        if(combatTransitionStateJson(mutableCopy)!=combatTransitionStateJson(post))invalid["copy_through"]=invalid["copy_through"].get<int>()+1;
                        // Native reward construction is covered by adapter's exact oracle;
                        // this smoke checks that each sampled RAW state owns one continuation.
                        int continuationCalls=0;auto child=gc;child.regainControlAction=[&](sts::GameContext &){++continuationCalls;};applyCombatTransitionState(child,post);child.regainControl();if(continuationCalls!=1)invalid["duplicate_reward"]=invalid["duplicate_reward"].get<int>()+1;
                    }
                    json components;
                    auto timing=[&](const char *name,auto fn) {auto start=Clock::now();for(int i=0;i<10;++i)fn();components[name]=std::chrono::duration<double,std::nano>(Clock::now()-start).count()/10;};
                    timing("survival",[&]{net.survival(p);});timing("max_hp",[&]{net.maxHp(p);});timing("hp_encoding",[&]{net.hpEncoding(p);});
                    timing("hp_head",[&]{net.signedHp(z,delta,pre.curHp,maximum);});timing("potion",[&]{net.potion(p,delta,fraction);});timing("relic",[&]{net.relic(z,hpClass,fraction,mask);});
                    out["componentsNs"]=components;
                    out["smoke"]={{"draws",32},{"death",deaths},{"victory",victories},{"invalid",invalid},{"support_ns",supportNs/32},{"death_ns",deaths?deathNs/deaths:0},{"victory_ns",victories?victoryNs/victories:0}};
                }
            }
            std::cout<<out.dump()<<'\n';
        }
        return 0;
    }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
