#include "sim/search/SilverPriorNet.h"
#include "sim/search/SilverWireJson.h"

#include <fstream>
#include <iostream>
#include <chrono>
#include <filesystem>
#include <numeric>
#include <cmath>
#include <set>

namespace {
using Json = nlohmann::json;
std::vector<Json> rows(const char *path) {
    std::ifstream in(path); if(!in) throw std::runtime_error(std::string("cannot open ")+path);
    std::vector<Json> out; std::string line;
    while(std::getline(in,line)) if(!line.empty()) out.push_back(Json::parse(line));
    return out;
}
}

int main(int argc,char **argv) {
    try {
        if(argc<4||argc>5) throw std::invalid_argument("usage: silver_prior_native_parity ARTIFACT ROOTS_JSONL PRIORS_JSONL [BENCH_REPEATS]");
        const auto loadStart=std::chrono::steady_clock::now();
        sts::search::SilverPriorNetV1 model(argv[1]);
        const auto loadEnd=std::chrono::steady_clock::now();
        const int repeats=argc==5?std::stoi(argv[4]):32;
        if(repeats<1||repeats>10000) throw std::invalid_argument("BENCH_REPEATS must be between 1 and 10000");
        const auto roots=rows(argv[2]), expected=rows(argv[3]);
        if(roots.size()!=64||expected.size()!=64) throw std::runtime_error("parity requires exactly 64 frozen roots and priors");
        std::map<std::string,Json> priorById;
        for(const auto &r:expected) if(!priorById.emplace(r.at("root_id").get<std::string>(),r).second) throw std::runtime_error("duplicate expected prior root");
        double maxPrior=0,maxLogit=0; std::size_t actionCount=0;
        std::set<std::string> ids;
        std::vector<std::pair<silver_bridge::BattleStateWire,std::vector<silver_bridge::SemanticAction>>> fixtures;
        std::size_t unknownPermutationCases=0, multiMonsterTargetRoots=0, potionTargetRoots=0, discardPotionRoots=0;
        std::size_t cardOccurrenceRoots=0, absentMonsterRoots=0, endTurnRoots=0;
        bool observedOrderSensitive=false;
        for(const auto &root:roots) {
            const auto id=root.at("root_id").get<std::string>(); if(!ids.insert(id).second) throw std::runtime_error("duplicate root id");
            const auto it=priorById.find(id); if(it==priorById.end()) throw std::runtime_error("missing prior row");
            const auto wire=silver_bridge::battleStateWireFromEnvelope(root.at("state"));
            auto actions=silver_bridge::enumerateSilverLegalActions(wire);
            std::vector<std::string> actual; for(const auto &a:actions) actual.push_back(silver_bridge::semanticActionFingerprint(a));
            if(actual!=root.at("native_order").get<std::vector<std::string>>()) throw std::runtime_error("native legal action order/fingerprint mismatch: "+id);
            if(actions.size()!=it->second.at("learned_prior").size()||actions.size()!=it->second.at("learned_logits").size()) throw std::runtime_error("expected action width mismatch");
            const auto logits=model.logits(wire,actions);const auto prior=model.prior(wire,actions);
            fixtures.emplace_back(wire,actions);
            std::set<int> targets;bool potionTarget=false,discardPotion=false,endTurn=false;
            for(const auto &a:actions){if(a.target>=0)targets.insert(a.target);potionTarget|=a.type==silver_bridge::SemanticActionType::POTION&&a.target>=0&&!a.discardPotion;discardPotion|=a.type==silver_bridge::SemanticActionType::POTION&&a.discardPotion;endTurn|=a.type==silver_bridge::SemanticActionType::END_TURN;}
            if(targets.size()>1)++multiMonsterTargetRoots;if(potionTarget)++potionTargetRoots;if(discardPotion)++discardPotionRoots;if(endTurn)++endTurnRoots;
            for(const auto &m:wire.monsters)if(m.idx<0){++absentMonsterRoots;break;}
            bool sameIdDifferentCost=false;for(std::size_t i=0;i<wire.hand.size();++i)for(std::size_t j=i+1;j<wire.hand.size();++j)if(wire.hand[i].id==wire.hand[j].id&&(wire.hand[i].cost!=wire.hand[j].cost||wire.hand[i].specialData!=wire.hand[j].specialData))sameIdDifferentCost=true;if(sameIdDifferentCost)++cardOccurrenceRoots;
            auto permuted=wire;bool hasUnknown=false;
            for(auto *pile:{&permuted.drawPile,&permuted.discardPile,&permuted.exhaustPile})if(pile->unknown.size()>1){std::reverse(pile->unknown.begin(),pile->unknown.end());hasUnknown=true;}
            if(hasUnknown){auto other=silver_bridge::enumerateSilverLegalActions(permuted);if(other.size()!=actions.size())throw std::runtime_error("unknown-pile permutation changed legal action count");for(std::size_t i=0;i<other.size();++i)if(silver_bridge::semanticActionFingerprint(other[i])!=actual[i])throw std::runtime_error("unknown-pile permutation changed legal action order");const auto q=model.prior(permuted,other);for(std::size_t i=0;i<q.size();++i)if(std::abs(q[i]-prior[i])>1e-6)throw std::runtime_error("unknown-pile permutation changed native prior");++unknownPermutationCases;}
            // Reclassify a multiset as an observed top segment, then reverse that
            // observed order. This synthetic input isolates position semantics.
            for(const auto &source:{wire.drawPile.unknown,wire.discardPile.unknown,wire.exhaustPile.unknown})if(source.size()>1){auto ordered=wire;ordered.drawPile.unknown.clear();ordered.drawPile.knownTop=source;auto reversed=ordered;std::reverse(reversed.drawPile.knownTop.begin(),reversed.drawPile.knownTop.end());const auto p0=model.prior(ordered,actions),p1=model.prior(reversed,actions);for(std::size_t i=0;i<p0.size();++i)if(std::abs(p0[i]-p1[i])>1e-7)observedOrderSensitive=true;break;}
            for(std::size_t i=0;i<actions.size();++i) {
                maxPrior=std::max(maxPrior,std::abs(prior[i]-it->second.at("learned_prior")[i].get<double>()));
                maxLogit=std::max(maxLogit,std::abs(logits[i]-it->second.at("learned_logits")[i].get<double>()));
            }
            if(maxPrior>1e-5) {
                double rootPriorError=0,rootLogitError=0;std::size_t worst=0;
                for(std::size_t i=0;i<actions.size();++i){double e=std::abs(prior[i]-it->second.at("learned_prior")[i].get<double>());if(e>rootPriorError){rootPriorError=e;worst=i;}rootLogitError=std::max(rootLogitError,std::abs(logits[i]-it->second.at("learned_logits")[i].get<double>()));}
                throw std::runtime_error("first parity mismatch root="+id+" action="+std::to_string(worst)+" native_logit="+std::to_string(logits[worst])+" python_logit="+std::to_string(it->second.at("learned_logits")[worst].get<double>())+" root_prior_error="+std::to_string(rootPriorError)+" root_logit_error="+std::to_string(rootLogitError));
            }
            actionCount+=actions.size();
        }
        if(maxLogit>1e-4) throw std::runtime_error("native logit parity exceeded 1e-4");
        if(cardOccurrenceRoots==0||potionTargetRoots==0||discardPotionRoots==0||multiMonsterTargetRoots==0||absentMonsterRoots==0||endTurnRoots!=64||unknownPermutationCases==0||!observedOrderSensitive)
            throw std::runtime_error("frozen-root/model edge-case coverage failed");
        std::vector<double> latency;latency.reserve(fixtures.size()*repeats);
        for(const auto &[wire,actions]:fixtures)(void)model.prior(wire,actions); // warm every root once
        for(const auto &[wire,actions]:fixtures)for(int r=0;r<repeats;++r){const auto t0=std::chrono::steady_clock::now();(void)model.prior(wire,actions);const auto t1=std::chrono::steady_clock::now();latency.push_back(std::chrono::duration<double,std::micro>(t1-t0).count());}
        std::sort(latency.begin(),latency.end());const double mean=std::accumulate(latency.begin(),latency.end(),0.0)/latency.size();
        auto percentile=[&](double q){return latency[static_cast<std::size_t>(std::ceil(q*latency.size()))-1];};
        Json result={{"schema","silver_prior_native_parity_v1"},{"roots",ids.size()},
            {"actions",actionCount},{"mean_legal_actions",double(actionCount)/ids.size()},
            {"max_abs_prior_error",maxPrior},{"max_abs_logit_error",maxLogit},
            {"prior_tolerance",1e-5},{"logit_tolerance",1e-4},{"passed",true},
            {"artifact_manifest_sha256",model.artifactSha256()},
            {"cases",{{"unknown_pile_permutation_invariant",unknownPermutationCases},
                {"observed_pile_order_sensitive",observedOrderSensitive},
                {"card_occurrence_cost_or_special_data",cardOccurrenceRoots},
                {"potion_target",potionTargetRoots},{"potion_discard",discardPotionRoots},
                {"multi_monster_targeting",multiMonsterTargetRoots},{"absent_monster",absentMonsterRoots},
                {"end_turn",endTurnRoots}}},
            {"latency",{{"warm_repeats_per_root",repeats},{"median_us_per_root",percentile(.5)},
                {"p95_us_per_root",percentile(.95)},{"mean_us_per_root",mean},
                {"median_us_per_action",percentile(.5)/(double(actionCount)/ids.size())},
                {"model_load_micros",std::chrono::duration<double,std::micro>(loadEnd-loadStart).count()},
                {"artifact_bytes",std::filesystem::file_size(argv[1])}}}};
        std::cout<<result.dump(2)<<'\n'; return 0;
    } catch(const std::exception &e) { std::cerr<<"silver_prior_native_parity: "<<e.what()<<'\n';return 2; }
}
