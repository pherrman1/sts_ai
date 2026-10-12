// Offline probability probe: reads captured fixtures, never executes gameplay.
#include "../apps/one_combat/combat_transition_runtime.h"
#include "../apps/one_combat/combat_transition_near_full.h"
#include <fstream>
#include <iostream>
#include <chrono>
#include <cmath>
#include <algorithm>
#include <map>
#include <array>
#include <cstring>
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
bool stateHasRelic(const CombatTransitionPersistentState &s,int id) {
    return std::any_of(s.relics.begin(),s.relics.end(),[&](const auto &r){return r.id==id;});
}
int stateRelicData(const CombatTransitionPersistentState &s,int id) {
    const auto it=std::find_if(s.relics.begin(),s.relics.end(),[&](const auto &r){return r.id==id;});
    return it==s.relics.end()?-1:it->data;
}
bool tailBit(const CombatTransitionPersistentState &s) {
    constexpr int id=static_cast<int>(sts::RelicId::LIZARD_TAIL);
    return (s.relicBits.at(id/64)&(std::uint64_t{1}<<(id%64)))!=0;
}
CombatPredictorInputV1 stripTail(CombatPredictorInputV1 p) {
    constexpr int id=static_cast<int>(sts::RelicId::LIZARD_TAIL);
    p.relics.erase(std::remove_if(p.relics.begin(),p.relics.end(),[](const auto &r){return r.relicId==id;}),p.relics.end());
    for(std::size_t i=0;i<p.relics.size();++i)p.relics[i].orderIndex=static_cast<int>(i);
    return p;
}
CombatTransitionPersistentState stripTail(CombatTransitionPersistentState s) {
    constexpr int id=static_cast<int>(sts::RelicId::LIZARD_TAIL);
    s.relics.erase(std::remove_if(s.relics.begin(),s.relics.end(),[](const auto &r){return r.id==id;}),s.relics.end());
    s.relicBits.at(id/64)&=~(std::uint64_t{1}<<(id%64));
    return s;
}
bool rngContract(const CombatTransitionPersistentState &pre,
    const CombatTransitionPersistentState &post,int encounter) {
    const auto expected=replayNativeComposedMisc(pre.combatRng[2],encounter);
    if(post.combatRng[2].counter!=expected.counter || post.combatRng[2].seed0!=expected.seed0 ||
        post.combatRng[2].seed1!=expected.seed1)return false;
    for(int i:{0,1,3,4,5})if(post.combatRng[i].counter!=pre.combatRng[i].counter ||
        post.combatRng[i].seed0!=pre.combatRng[i].seed0 ||
        post.combatRng[i].seed1!=pre.combatRng[i].seed1)return false;
    return true;
}
int main(int argc,char **argv) {
    try {
        if(argc==3 && std::string(argv[1])=="--require-standard-fallback") {
            CombatTransitionRuntime::requireCurrentStandardFallbackArtifact(argv[2]);
            std::cout << "pinned standard fallback SHA256 PASS\n";
            return 0;
        }
        // Loads one artifact, or a composed fast+standard pair, and names the identity it was checked against.
        auto identityName=[](const CombatTransitionRuntime &runtime) {
            return runtime.researchCandidate()?runtime.identity().at("candidateId").get<std::string>():std::string("production");
        };
        if(argc==3 && std::string(argv[1])=="--identity") {
            NativeCombatTransitionSampler sampler(argv[2]);
            std::cout << "identity=" << identityName(sampler.runtime()) << "\n";
            return 0;
        }
        if(argc==5 && std::string(argv[1])=="--pair-identity") {
            EntropicBrewFallbackCombatTransitionSampler hybrid(argv[2],argv[3],std::string(argv[4])=="1");
            std::cout << "identity=" << identityName(hybrid.fastRuntime())
                << " lizard_fairy=" << hybrid.fastRuntime().lizardFairyCapable()
                << " lizard_brew=" << hybrid.fastRuntime().lizardBrewCapable() << "\n";
            return 0;
        }
        if(argc==6 && std::string(argv[1])=="--lizard-parity") {
            EntropicBrewFallbackCombatTransitionSampler hybrid(argv[2],argv[3],true);
            NativeCombatTransitionSampler directSampler(argv[2]);
            std::ifstream pairs(argv[4]),selectionFile(argv[5]);
            if(!pairs || !selectionFile)throw std::runtime_error("Lizard parity input file");
            const auto selection=json::parse(selectionFile);
            std::map<std::pair<int,int>,json> targets;
            for(const auto &target:selection.at("targets"))
                targets.emplace(std::make_pair(target.at("sourceSeed").get<int>(),
                    target.at("fightIdx").get<int>()),target);
            std::string line;int rows=0;
            constexpr int tailId=static_cast<int>(sts::RelicId::LIZARD_TAIL);
            while(std::getline(pairs,line)) {
                const auto pair=json::parse(line);const auto &active=pair.at("activeTail");
                const int source=active.at("sourceSeed"),fight=active.at("fightIdx");
                const auto targetIt=targets.find({source,fight});
                if(targetIt==targets.end())throw std::runtime_error("Stage-C pair missing frozen selected target");
                auto p=predictor(active.at("predictorInput"));
                auto pre=persistent(active.at("transition").at("pre"));
                if(!stateHasRelic(pre,tailId) || stateRelicData(pre,tailId)!=1)
                    throw std::runtime_error("Stage-C active Tail state does not carry an active relic");
                sts::GameContext gc;applyCombatTransitionState(gc,pre);
                const auto prediction=hybrid.activeLizardPrediction(gc,p);
                if(!prediction.supported)
                    throw std::runtime_error("Stage-C active Lizard unsupported: "+prediction.reason);
                json branches=json::object();
                for(int outcomeClass=0;outcomeClass<3;++outcomeClass) {
                    const auto branchSeed=991000+std::uint64_t(rows)*3+outcomeClass;
                    std::mt19937_64 rng(branchSeed);
                    const auto result=hybrid.sampleActiveLizardClass(gc,p,rng,outcomeClass);
                    if(outcomeClass==2) {
                        if(result.outcome!=CombatRuntimeSample::Outcome::DEATH)
                            throw std::runtime_error("forced consumed-loss class did not end in death");
                        branches["consumedLoss"]={{"death",true}};
                        continue;
                    }
                    if(result.outcome!=CombatRuntimeSample::Outcome::VICTORY)
                        throw std::runtime_error("forced Lizard winning class did not produce a victory");
                    const auto &post=result.rawPost;
                    const bool consumed=outcomeClass==1;
                    const bool tailState=stateHasRelic(post,tailId) &&
                        stateRelicData(post,tailId)==(consumed?0:1) && tailBit(post) &&
                        post.relicBits==pre.relicBits;
                    const bool hpLegal=post.curHp>=1 && post.curHp<=post.maxHp;
                    const int hpDelta=consumed?post.curHp-prediction.t2HeadInputHp:0;
                    const bool t2HeadInput=prediction.t2HeadInputHp==p.globals.maxHp/2;
                    const auto &hpClasses=hybrid.fastRuntime().metadata().at("hpClasses");
                    const bool hpClassLegal=!consumed || (hpDelta>=hpClasses.front().get<int>() && hpDelta<=hpClasses.back().get<int>());
                    bool t2ConditionalIdentity=true;
                    if(consumed) {
                        auto directPre=stripTail(pre);
                        auto directInput=stripTail(p);
                        directPre.curHp=prediction.t2HeadInputHp;
                        directInput.globals.curHp=prediction.t2HeadInputHp;
                        auto directPrepared=directSampler.prepareState(directPre,directInput);
                        if(!directPrepared->support().supported)
                            throw std::runtime_error("direct frozen T2 conditional child became unsupported");
                        std::mt19937_64 directRng(branchSeed);
                        const auto direct=directPrepared->sampleConditionedVictory(directRng);
                        const auto withoutTail=stripTail(post);
                        t2ConditionalIdentity=direct.outcome==CombatRuntimeSample::Outcome::VICTORY &&
                            directRng==rng && combatTransitionStateJson(direct.rawPost)==
                                combatTransitionStateJson(withoutTail);
                    }
                    const bool correctRng=rngContract(pre,post,p.globals.encounter);
                    const int activeCount=static_cast<int>(std::count_if(post.potions.begin(),post.potions.end(),
                        [](int potion){return potion>1;}));
                    const bool potionCount=activeCount==post.potionCount;
                    if(!hpLegal || !correctRng || !potionCount || !tailState ||
                        (consumed&&(!t2HeadInput||!hpClassLegal||!t2ConditionalIdentity)))
                        throw std::runtime_error("forced Lizard branch violated HP/Tail/RNG/state invariants");
                    branches[consumed?"consumedWin":"ordinaryWin"]={{"victory",true},
                        {"tailPresent",stateHasRelic(post,tailId)},
                        {"tailData",stateRelicData(post,tailId)},
                        {"tailBit",tailBit(post)},
                        {"relicBitsPreserved",post.relicBits==pre.relicBits},
                        {"sampledMaxHp",consumed?post.maxHp:0},
                        {"t2HeadInputHp",consumed?prediction.t2HeadInputHp:0},
                        {"actualPostHp",consumed?post.curHp:0},
                        {"hpDelta",hpDelta},{"t2HeadInputApplied",!consumed||t2HeadInput},
                        {"t2ConditionalIdentity",t2ConditionalIdentity},
                        {"hpClassLegal",hpClassLegal},
                        {"hpLegal",hpLegal},{"rngContract",correctRng},{"potionCount",potionCount}};
                }
                std::cout<<json{{"sourceSeed",source},{"fightIdx",fight},
                    {"prediction",{{"supported",prediction.supported},{"reason",prediction.reason},
                        {"pOrdinaryWin",prediction.pOrdinaryWin},{"pReserveWin",prediction.pReserveWin},
                        {"qTailConsumed",prediction.qTailConsumed},
                        {"rWinGivenConsumed",prediction.rWinGivenConsumed},
                        {"classProbabilities",prediction.classProbabilities},
                        {"t2HeadInputHp",prediction.t2HeadInputHp}}},
                    {"branches",branches}}.dump()<<'\n';
                ++rows;
            }
            if(rows!=320 || static_cast<int>(targets.size())!=320)
                throw std::runtime_error("Lizard parity must cover the frozen 320-row selection");
            return 0;
        }
        if(argc==5 && std::string(argv[1])=="--lizard-dispatch") {
            EntropicBrewFallbackCombatTransitionSampler hybrid(argv[2],argv[3],true);
            std::ifstream file(argv[4]);if(!file)throw std::runtime_error("Lizard dispatch fixture file");
            std::string line;int rows=0;
            while(std::getline(file,line)) {
                const auto fixture=json::parse(line);auto p=predictor(fixture.at("predictorInput"));
                auto pre=persistent(fixture.at("preState"));sts::GameContext gc;
                applyCombatTransitionState(gc,pre);
                const auto support=hybrid.support(gc,p),forecast=hybrid.forecastSupport(p);
                const auto prepared=hybrid.prepare(gc,p);
                if(prepared->support().supported!=support.supported ||
                    prepared->support().reason!=support.reason)
                    throw std::runtime_error("Lizard dispatch prepare/support mismatch: "+
                        support.reason+" vs "+prepared->support().reason);
                int outcome=-1;
                if(support.supported) {
                    std::mt19937_64 rng(771100+rows);
                    outcome=static_cast<int>(prepared->sample(rng).outcome);
                }
                auto prediction=hybrid.activeLizardPrediction(gc,p);
                json out{{"name",fixture.at("name")},{"supported",support.supported},
                    {"reason",support.reason},{"forecastSupported",forecast.supported},
                    {"forecastReason",forecast.reason},{"preparedSupported",prepared->support().supported},
                    {"predictionSupported",prediction.supported},{"predictionReason",prediction.reason},
                    {"sampleOutcome",outcome}};
                if(prediction.supported) {
                    // The composed classes and one forced Tail-consumed victory per supported state.
                    std::mt19937_64 rng(881100+rows);
                    const auto consumed=hybrid.sampleActiveLizardClass(gc,p,rng,1);
                    out["prediction"]={{"brew",prediction.brew},{"fairy",prediction.fairy},
                        {"pOrdinaryWin",prediction.pOrdinaryWin},{"pReserveWin",prediction.pReserveWin},
                        {"rWinGivenConsumed",prediction.rWinGivenConsumed},
                        {"classProbabilities",prediction.classProbabilities},{"t2HeadInputHp",prediction.t2HeadInputHp}};
                    out["consumedOutcome"]=static_cast<int>(consumed.outcome);
                    if(consumed.outcome==CombatRuntimeSample::Outcome::VICTORY ||
                        consumed.outcome==CombatRuntimeSample::Outcome::ESCAPE)
                        out["consumedPost"]=combatTransitionStateJson(consumed.rawPost);
                    const auto expected=hybrid.expectation(gc,p),forecasted=hybrid.forecastExpectation(p);
                    out["expectation"]={{"supported",expected.supported},{"death",expected.death},
                        {"winningHpFraction",expected.winningHpFraction},{"forecastSupported",forecasted.supported},
                        {"forecastDeath",forecasted.death}};
                }
                std::cout<<out.dump()<<'\n';
                ++rows;
            }
            const auto metrics=hybrid.takeMetrics();
            std::cerr<<json{{"dispatchFixtures",rows},{"preparations",metrics.preparations},
                {"fastPreparations",metrics.fastPreparations},
                {"fallbackPreparations",metrics.fallbackPreparations},
                {"lizardPreparations",metrics.lizardPreparations},
                {"lizardSamples",metrics.lizardSamples},
                {"lizardBoundaryExclusions",metrics.lizardBoundaryExclusions},
                {"lizardSupportFailures",metrics.lizardSupportFailures},
                {"fastSupportFailures",metrics.fastSupportFailures},
                {"fallbackSupportFailures",metrics.fallbackSupportFailures}}.dump()<<'\n';
            return rows==8?0:1;
        }
        if(argc==6 && std::string(argv[1])=="--benchmark") {
            NativeCombatTransitionSampler fast(argv[2]),standard(argv[3]);
            EntropicBrewFallbackCombatTransitionSampler hybrid(argv[2],argv[3]);
            const int repetitions=std::stoi(argv[5]);if(repetitions<1)throw std::runtime_error("benchmark repetitions must be positive");
            std::ifstream file(argv[4]);if(!file)throw std::runtime_error("fixture file");
            struct Samples {std::vector<double> prepare,sample;std::uint64_t inputs=0,encoderCalls=0;};
            std::map<std::string,Samples> timings;
            auto append=[&](const std::string &name,double prepare,double sample,int encoders) {
                auto &values=timings[name];values.prepare.push_back(prepare);values.sample.push_back(sample);
                ++values.inputs;values.encoderCalls+=encoders;
            };
            std::string line;int index=0;std::uint64_t brewInputs=0,ordinaryInputs=0;
            while(std::getline(file,line)) {
                auto j=json::parse(line);auto p=predictor(j.at("predictorInput"));
                auto pre=persistent(j.contains("pre")?j.at("pre"):j.at("transition").at("pre"));
                sts::GameContext gc;applyCombatTransitionState(gc,pre);
                const bool brew=std::any_of(p.potions.begin(),p.potions.end(),[](const auto &x){return x.potionId==int(sts::Potion::ENTROPIC_BREW);});
                if(brew)++brewInputs;else ++ordinaryInputs;
                auto run=[&](const CombatTransitionSampler &sampler,const std::string &bucket,int encoders) {
                    if(bucket.empty())return false;
                    auto support=sampler.support(gc,p);if(!support.supported)return false;
                    auto prepared=sampler.prepare(gc,p);if(!prepared->support().supported)throw std::runtime_error("benchmark prepare lost support");
                    for(int warm=0;warm<10;++warm){std::mt19937_64 rng(776+warm);prepared->sample(rng);}
                    double prepareTotal=0,sampleTotal=0;
                    for(int rep=0;rep<repetitions;++rep) {
                        auto start=std::chrono::steady_clock::now();auto each=sampler.prepare(gc,p);
                        prepareTotal+=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
                        std::mt19937_64 rng(900000+index*repetitions+rep);start=std::chrono::steady_clock::now();
                        each->sample(rng);sampleTotal+=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
                    }
                    append(bucket,prepareTotal/repetitions,sampleTotal/repetitions,encoders);
                    return true;
                };
                run(standard,"standard_all_supported",4);
                if(brew) {
                    run(standard,"standard_brew",4);
                    run(hybrid,"hybrid_brew_fallback",4);
                } else if(run(fast,"fast_deepsets",3)) {
                    run(standard,"standard_ordinary_matched_fast",4);
                    run(hybrid,"hybrid_fast",3);
                }
                ++index;
            }
            json results=json::object();for(auto &[name,values]:timings) {
                auto prep=values.prepare,samples=values.sample;
                std::sort(prep.begin(),prep.end());std::sort(samples.begin(),samples.end());
                auto q=[](const std::vector<double> &v,double p){return v.empty()?0.0:v[std::size_t(p*double(v.size()-1))];};
                results[name]={{"supportedInputStates",values.inputs},{"encoderCallsPerPreparation",values.inputs?double(values.encoderCalls)/values.inputs:0},
                    {"preparationMedianUs",q(prep,.5)},{"preparationP25Us",q(prep,.25)},{"preparationP75Us",q(prep,.75)},
                    {"preparedSampleMedianUs",q(samples,.5)},{"preparedSampleP25Us",q(samples,.25)},{"preparedSampleP75Us",q(samples,.75)}};
            }
            const auto metrics=hybrid.takeMetrics();
            std::cout<<json{{"schema","combat_transition_hybrid_fixed_fixture_benchmark_v1"},
                {"fixtureCount",index},{"ordinaryInputs",ordinaryInputs},{"brewInputs",brewInputs},
                {"warmupsPerInput",10},{"repetitionsPerInput",repetitions},
                {"dispatchFraction",index?double(brewInputs)/index:0.0},{"timings",results},
                {"hybridMetrics",{{"preparations",metrics.preparations},
                    {"fastPreparations",metrics.fastPreparations},{"fallbackPreparations",metrics.fallbackPreparations},
                    {"fallbackRate",metrics.fallbackRate},{"uniqueBrewPredictorStates",metrics.uniqueBrewPredictorStates}}}}.dump(2)<<'\n';
            return index?0:1;
        }
        // Escape capability (#418 PR7): the escape head, both escape-conditioned HP heads, the
        // conditioned potion masks, and sampled escapes against their invariants.
        if(argc==5 && std::string(argv[1])=="--encoder-memo-parity") {
            // Two DeepSets artifacts with different weights, memoized and interleaved state by state
            // over two passes, against the unmemoized reference: every encoder output and the maxHP
            // head must match bit for bit. A memo shared across runtimes or encoder groups, or a key
            // missing a field, returns another token's floats.
            NativeCombatTransitionSampler first(argv[2]),second(argv[3]);
            std::ifstream file(argv[4]);if(!file)throw std::runtime_error("fixture file");
            std::vector<CombatPredictorInputV1> inputs;std::string line;
            while(std::getline(file,line)) {
                // Each state plus a variant that changes every memo key field but the ids.
                auto p=predictor(json::parse(line).at("predictorInput")),v=p;
                for(auto &c:v.cards){c.upgraded=!c.upgraded;c.misc+=3;c.bottleBinding=c.bottleBinding<0?0:-1;}
                for(auto &r:v.relics){++r.data;r.orderIndex=int(v.relics.size())-1-r.orderIndex;}
                for(size_t i=0;i<v.potions.size();++i)v.potions[i].potionId=p.potions[v.potions.size()-1-i].potionId;
                inputs.push_back(p);inputs.push_back(v);
            }
            if(inputs.empty())throw std::runtime_error("no fixture states");
            using Outputs=std::vector<std::vector<float>>;
            auto outputs=[](const CombatTransitionRuntime &net,const CombatPredictorInputV1 &p) {
                return Outputs{{net.survival(p)},net.hpEncoding(p),net.maxHpEncoding(p),net.potionEncoding(p),net.maxHp(p)};
            };
            auto same=[](const std::vector<float> &a,const std::vector<float> &b) {
                return a.size()==b.size() && std::memcmp(a.data(),b.data(),a.size()*sizeof(float))==0;
            };
            const std::array<const CombatTransitionRuntime*,2> nets{&first.runtime(),&second.runtime()};
            std::array<std::vector<Outputs>,2> reference;
            CombatTransitionRuntime::setEncoderMemoForTesting(false);
            for(int n=0;n<2;++n)for(const auto &p:inputs)reference[n].push_back(outputs(*nets[n],p));
            CombatTransitionRuntime::setEncoderMemoForTesting(true);
            bool differ=false;int comparisons=0;
            for(size_t k=0;k<inputs.size();++k)differ|=!same(reference[0][k][1],reference[1][k][1]);
            if(!differ)throw std::runtime_error("encoder memo parity needs artifacts with different encoders");
            for(int pass=0;pass<2;++pass)for(size_t i=0;i<inputs.size();++i)for(int n=0;n<2;++n) {
                const size_t k=pass?inputs.size()-1-i:i;const auto &net=*nets[n];
                const auto a=outputs(net,inputs[k]);
                for(size_t j=0;j<a.size();++j,++comparisons)
                    if(!same(a[j],reference[n][k][j]))throw std::runtime_error("encoder memo parity: artifact "+std::to_string(n)+
                        " output "+std::to_string(j)+" state "+std::to_string(k));
                if(net.sharedHpEncoder() && (!same(a[1],a[2]) || !same(net.maxHp(a[1]),a[4])))
                    throw std::runtime_error("shared HP encoder parity");
            }
            std::cout<<json{{"states",inputs.size()},{"comparisons",comparisons},
                {"sharedHpEncoder",{first.runtime().sharedHpEncoder(),second.runtime().sharedHpEncoder()}}}.dump()<<'\n';
            return 0;
        }
        if(argc==4 && std::string(argv[1])=="--escape") {
            NativeCombatTransitionSampler sampler(argv[2]);const auto &net=sampler.runtime();
            std::ifstream file(argv[3]);if(!file)throw std::runtime_error("fixture file");
            std::string line;int index=0;
            while(std::getline(file,line)) {
                auto j=json::parse(line);auto p=predictor(j.at("predictorInput"));auto pre=persistent(j.at("pre"));
                sts::GameContext gc;applyCombatTransitionState(gc,pre);
                const auto support=sampler.support(gc,p);
                json out={{"index",index++},{"escapeCapable",net.escapeCapable()},{"supported",support.supported},{"reason",support.reason}};
                if(support.supported && net.escapeCapable()) {
                    const bool boss=sts::isBossEncounter(static_cast<sts::MonsterEncounter>(p.globals.encounter));
                    const bool eligible=CombatTransitionRuntime::escapeEligible(pre.potions,pre.potionCapacity,boss);
                    const int d=j.value("delta",0),maximum=pre.maxHp+net.metadata().at("maxHpClasses")[d].get<int>();
                    const auto z=net.hpEncoding(p),zp=net.potionEncoding(p);
                    const float fraction=j.value("fraction",.5f);
                    out["eligible"]=eligible;out["boss"]=boss;out["z"]=z;out["escape"]=net.escapeProbability(z);out["maxHp"]=net.maxHp(p);
                    out["hp0"]=net.signedHp(z,d,pre.curHp,maximum,0);out["hp1"]=net.signedHp(z,d,pre.curHp,maximum,1);
                    json potion=json::object();
                    for(int e:{-1,0,1}) {
                        const bool smoke=std::any_of(pre.potions.begin(),pre.potions.begin()+std::min(pre.potionCapacity,5),[](int v){return v==int(sts::Potion::SMOKE_BOMB);});
                        if(e==1 && !smoke)continue;
                        potion[std::to_string(e)]=net.potionInventory(zp,pre.potions,pre.potionCapacity,d,fraction,boss,e);
                    }
                    out["potion"]=potion;
                    const auto expectation=sampler.expectation(gc,p);
                    out["expectation"]={{"death",expectation.death},{"winningHpFraction",expectation.winningHpFraction}};
                    auto prepared=sampler.prepare(gc,p);int escapes=0,victories=0,deaths=0;
                    for(int draw=0;draw<j.value("draws",64);++draw) {
                        std::mt19937_64 random(20261007+draw),cached=random;
                        auto sample=sampler.sample(gc,p,random),other=prepared->sample(cached);
                        if(sample.outcome!=other.outcome||combatTransitionStateJson(sample.rawPost)!=combatTransitionStateJson(other.rawPost)||random!=cached)
                            throw std::runtime_error("escape prepared/reference parity");
                        if(sample.outcome==CombatRuntimeSample::Outcome::DEATH){++deaths;continue;}
                        const auto &post=sample.rawPost;const bool escaped=sample.outcome==CombatRuntimeSample::Outcome::ESCAPE;
                        if(post.smokeBombUsed!=escaped || (escaped && !eligible) || post.curHp<1 || post.curHp>post.maxHp ||
                            post.potionCount!=static_cast<int>(std::count_if(post.potions.begin(),post.potions.end(),[](int v){return v>1;})))
                            throw std::runtime_error("sampled escape violates its invariants");
                        escapes+=escaped;victories+=!escaped;
                    }
                    out["samples"]={{"death",deaths},{"victory",victories},{"escape",escapes}};
                }
                std::cout<<out.dump()<<'\n';
            }
            return index?0:1;
        }
        if(argc==4 && std::string(argv[1])=="--potion-parity") {
            NativeCombatTransitionSampler sampler(argv[2]);const auto &net=sampler.runtime();
            std::ifstream file(argv[3]);if(!file)throw std::runtime_error("fixture file");
            std::string line;int index=0;
            while(std::getline(file,line)) {
                auto j=json::parse(line);auto p=predictor(j.at("predictorInput"));
                auto z=net.potionEncoding(p);const int delta=j.value("delta",0);
                const float fraction=j.value("fraction",.5f);auto probabilities=net.potion(z,p,delta,fraction);
                json legal=json::array();for(float probability:probabilities)legal.push_back(probability>0);
                std::cout<<json{{"index",index++},{"z",z},{"probabilities",probabilities},
                    {"legal",legal},{"delta",delta},{"fraction",fraction},
                    {"capacity",p.globals.potionCapacity},
                    {"boss",sts::isBossEncounter(static_cast<sts::MonsterEncounter>(p.globals.encounter))}}.dump()<<'\n';
            }
            return index?0:1;
        }
        if(argc==5 && std::string(argv[1])=="--hybrid") {
            NativeCombatTransitionSampler fast(argv[2]),standard(argv[3]);
            EntropicBrewFallbackCombatTransitionSampler hybrid(argv[2],argv[3]);
            std::ifstream file(argv[4]);if(!file)throw std::runtime_error("fixture file");
            std::string line;int index=0,brews=0,ordinary=0;
            while(std::getline(file,line)) {
                auto j=json::parse(line);auto p=predictor(j.at("predictorInput"));
                auto pre=persistent(j.contains("pre")?j.at("pre"):j.at("transition").at("pre"));
                sts::GameContext gc;applyCombatTransitionState(gc,pre);
                const bool brew=std::any_of(p.potions.begin(),p.potions.end(),[](const auto &x){return x.potionId==int(sts::Potion::ENTROPIC_BREW);});
                auto &expected=brew?static_cast<const CombatTransitionSampler&>(standard):static_cast<const CombatTransitionSampler&>(fast);
                auto expectedSupport=expected.support(gc,p),actualSupport=hybrid.support(gc,p);
                if(expectedSupport.supported!=actualSupport.supported||expectedSupport.reason!=actualSupport.reason)
                    throw std::runtime_error("hybrid support differs from selected child at fixture "+std::to_string(index));
                auto forecast=expected.forecastSupport(p),hybridForecast=hybrid.forecastSupport(p);
                if(forecast.supported!=hybridForecast.supported||forecast.reason!=hybridForecast.reason)
                    throw std::runtime_error("hybrid forecast support differs from selected child");
                auto expectedExpectation=expected.expectation(gc,p),actualExpectation=hybrid.expectation(gc,p);
                if(expectedExpectation.supported!=actualExpectation.supported ||
                    expectedExpectation.death!=actualExpectation.death ||
                    expectedExpectation.winningHpFraction!=actualExpectation.winningHpFraction ||
                    expectedExpectation.winningHpHistogram!=actualExpectation.winningHpHistogram)
                    throw std::runtime_error("hybrid expectation differs from selected child");
                auto expectedForecast=expected.forecastExpectation(p),actualForecast=hybrid.forecastExpectation(p);
                if(expectedForecast.supported!=actualForecast.supported || expectedForecast.death!=actualForecast.death ||
                    expectedForecast.winningHpFraction!=actualForecast.winningHpFraction ||
                    expectedForecast.winningHpHistogram!=actualForecast.winningHpHistogram)
                    throw std::runtime_error("hybrid forecast expectation differs from selected child");
                std::mt19937_64 left(20260924+index),right=left;
                auto expectedSample=expected.sample(gc,p,left),actualSample=hybrid.sample(gc,p,right);
                if(expectedSample.outcome!=actualSample.outcome || left!=right ||
                    combatTransitionStateJson(expectedSample.rawPost)!=combatTransitionStateJson(actualSample.rawPost))
                    throw std::runtime_error("hybrid scalar sample/RNG/RAW differs from selected child");
                auto expectedPrepared=expected.prepare(gc,p),actualPrepared=hybrid.prepare(gc,p);
                if(expectedPrepared->support().supported!=actualPrepared->support().supported ||
                    expectedPrepared->support().reason!=actualPrepared->support().reason)
                    throw std::runtime_error("hybrid prepared support differs from selected child");
                left.seed(80260924+index);right=left;
                expectedSample=expectedPrepared->sample(left);actualSample=actualPrepared->sample(right);
                if(expectedSample.outcome!=actualSample.outcome || left!=right ||
                    combatTransitionStateJson(expectedSample.rawPost)!=combatTransitionStateJson(actualSample.rawPost))
                    throw std::runtime_error("hybrid prepared sample/RNG/RAW differs from selected child");
                if(brew) {
                    ++brews;std::mt19937_64 directRng(99),before=directRng;
                    auto blocked=fast.sample(gc,p,directRng);
                    if(fast.support(gc,p).reason!="entropic_brew_requires_standard_ctm" ||
                        fast.forecastSupport(p).reason!="entropic_brew_requires_standard_ctm" ||
                        blocked.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED || directRng!=before)
                        throw std::runtime_error("direct specialist Brew misuse did not fail closed without RNG");
                } else ++ordinary;
                std::cout<<json{{"index",index},{"brewFallback",brew},{"support",actualSupport.supported},
                    {"reason",actualSupport.reason},{"scalarAndPreparedIdentity",true},
                    {"completeRawAndRngIdentity",true}}.dump()<<'\n';
                ++index;
            }
            const auto metrics=hybrid.takeMetrics();
            if(metrics.preparations!=static_cast<std::uint64_t>(index) ||
                metrics.fastPreparations!=static_cast<std::uint64_t>(ordinary) ||
                metrics.fallbackPreparations!=static_cast<std::uint64_t>(brews) ||
                metrics.fastSamples!=static_cast<std::uint64_t>(2*ordinary) ||
                metrics.fallbackSamples!=static_cast<std::uint64_t>(2*brews))
                throw std::runtime_error("hybrid metrics do not match fixture routes");
            std::cerr<<json{{"fixtures",index},{"ordinary",ordinary},{"brew",brews},
                {"preparations",metrics.preparations},{"fastPreparations",metrics.fastPreparations},
                {"fallbackPreparations",metrics.fallbackPreparations},{"fastSamples",metrics.fastSamples},
                {"fallbackSamples",metrics.fallbackSamples},{"fallbackRate",metrics.fallbackRate},
                {"uniqueBrewPredictorStates",metrics.uniqueBrewPredictorStates}}.dump()<<'\n';
            return index?0:1;
        }
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
            auto expectation=sampler.expectation(gc,p);
            out["expectation"]={{"supported",expectation.supported},{"death",expectation.death},
                {"winningHpFraction",expectation.winningHpFraction}};
            if(supportOnly){out["index"]=fixtureIndex++;std::cout<<out.dump()<<'\n';continue;}
            if(full){
                if(support.supported){int d=j.value("delta",0),ending=j.value("ending",pre.curHp),maximum=j.value("maximum",pre.maxHp),mask=j.value("mask",0);std::vector<int> consumed=j.value("consumed",std::vector<int>{}),dagger=j.value("dagger",std::vector<int>{});
                    out["survival"]=net.survival(p);out["maxHp"]=net.maxHp(p);out["maxHpEncoding"]=net.maxHpEncoding(p);out["hp"]=net.signedHp(net.hpEncoding(p),d,pre.curHp,maximum);out["diagnostics"]=nearFullDiagnostics(net,pre,p,d,ending,maximum,mask,consumed,j.value("escaped",false),dagger);
                    auto prepared=sampler.prepare(gc,p);json samples=json::array();
                    for(int draw=0;draw<j.value("draws",128);++draw){std::mt19937_64 random(20260921+draw),cached=random,tape=random;json words=json::array();for(int k=0;k<256;++k)words.push_back(tape());auto sample=sampler.sample(gc,p,random),other=prepared->sample(cached);if(sample.outcome!=other.outcome||combatTransitionStateJson(sample.rawPost)!=combatTransitionStateJson(other.rawPost)||random!=cached)throw std::runtime_error("near-full prepared/reference parity");
                        auto count=std::mt19937_64(20260921+draw);int used=0;while(count!=random&&used<256){count();++used;}if(count!=random)throw std::runtime_error("parity draw tape exhausted");samples.push_back({{"outcome",int(sample.outcome)},{"rawPost",combatTransitionStateJson(sample.rawPost)},{"words",words},{"wordsUsed",used}});
                    }out["samples"]=samples;
                }else{std::mt19937_64 random(123),before=random;auto sample=sampler.sample(gc,p,random);if(sample.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED||random!=before)throw std::runtime_error("unsupported sampling consumed RNG");out["unsupportedNoDraw"]=true;}std::cout<<out.dump()<<'\n';continue;
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
                    {"referenceEncoderCalls",support.supported?draws+3*victories:0}};
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
