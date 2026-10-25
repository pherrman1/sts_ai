// Research executable only: no production caller, reward, or search shortcut.
#include <algorithm>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <openssl/evp.h>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include "combat/BattleContextBinary.h"
#include "game/RelicContainer.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

using namespace sts;
using namespace sts::search;
using json = nlohmann::json;
using SAction = sts::search::Action;

namespace {
constexpr int depthCap = 24, nodeCap = 2000, candidateCap = 16;
constexpr int repetitionCap = 128, replayCap = 1024, totalReplayCap = 4096;

// Like proveSilverUselessBlock: copied actions cannot mutate a live observer.
struct ObserverScope {
    CombatKnowledgeObserver *observer = g_combatKnowledgeObserver;
    BattleContext *debug = g_debug_bc;
    ObserverScope() { g_combatKnowledgeObserver = nullptr; }
    ~ObserverScope() { g_combatKnowledgeObserver = observer; g_debug_bc = debug; }
};

template<class F> void eachCard(const BattleContext &b, F f) {
    for (int i=0; i<b.cards.cardsInHand; ++i) f(b.cards.hand[i]);
    for (const auto &c:b.cards.drawPile) f(c);
    for (const auto &c:b.cards.discardPile) f(c);
    for (const auto &c:b.cards.exhaustPile) f(c);
    for (const auto &c:b.cards.stasisCards) f(c);
}

// Counter normalization is qualified only for the Ironclad card domain.
// Also reject foreign colored cards imported without their acquisition relic.
bool auditedDomain(const BattleContext &b) {
    if (b.player.cc != CharacterClass::IRONCLAD) return false;
    bool supported=true;
    eachCard(b,[&](const CardInstance &c) {
        if (c.id==CardId::INVALID) return;
        const auto color=getCardColor(c.id);
        supported &= color==CardColor::RED || color==CardColor::COLORLESS || color==CardColor::CURSE;
    });
    return supported;
}

// BattleContext omits RelicContainer's third bitset, including Prismatic
// Shard. Its absence must be proven by the caller, never guessed from Player.
bool quiet(const BattleContext &b, bool noPrismaticShard) {
    return noPrismaticShard && auditedDomain(b) && b.outcome == Outcome::UNDECIDED && b.inputState == InputState::PLAYER_NORMAL
        && !b.endTurnQueued && !b.turnHasEnded && !b.skipMonsterTurn
        && !b.actionQueue.size && !b.cardQueue.size && !b.intentsHidden
        && b.cards.drawPile.isConcrete() && !b.undefinedBehaviorEvoked
        && !b.haveUsedDiscoveryAction && b.loopCount < 900000
        && b.player.cardsPlayedThisTurn >= 0 && b.player.cardsPlayedThisTurn < 20000
        && b.player.attacksPlayedThisTurn >= 0 && b.player.attacksPlayedThisTurn < 20000
        && b.player.skillsPlayedThisTurn >= 0 && b.player.skillsPlayedThisTurn < 20000;
}

// The only RNG quotient in v0: two physical Dropkick/Flash of Steel cards,
// with no player powers or card hooks except Burning Blood/Sundial. Static
// exhaust stays exact in equality but cannot participate in this engine. At draw
// time the played card is out of the piles, so a shuffle has <=1 card. Its
// RNG advances but cannot affect the order. All other RNG streams stay exact.
bool singletonShuffles(const BattleContext &b) {
    Player allowed{};
    allowed.setHasRelic<RelicId::BURNING_BLOOD>(true);
    allowed.setHasRelic<RelicId::SUNDIAL>(true);
    if (b.player.statusBits0 || b.player.statusBits1 || !b.player.statusMap.empty()
        || (b.player.relicBits0 & ~allowed.relicBits0)
        || (b.player.relicBits1 & ~allowed.relicBits1)
        || std::any_of(b.cards.stasisCards.begin(),b.cards.stasisCards.end(),
            [](const CardInstance &c) { return c.id!=CardId::INVALID; })) return false;
    int count=0; bool simple=true;
    auto active=[&](const CardInstance &c) {
        if(c.id==CardId::INVALID) return;
        ++count;
        simple &= c.id==CardId::DROPKICK || c.id==CardId::FLASH_OF_STEEL;
    };
    for(int i=0;i<b.cards.cardsInHand;++i) active(b.cards.hand[i]);
    for(const auto &c:b.cards.drawPile) active(c);
    for(const auto &c:b.cards.discardPile) active(c);
    return simple && count==2 && b.cards.cardsInHand>0;
}

BattleContext controlState(BattleContext b) {
    // Existing equalForSearch's quiet-boundary history normalization. Use
    // operator== afterwards, keeping ordered cards and all omitted hash fields.
    b.curCardQueueItem = {};
    b.loopCount=0; b.energyWasted=0; b.cardsDrawn=0;
    // cardsPlayed: Choker, Normality and Echo Form need the exact count.
    // Otherwise only the <=3 Pocketwatch threshold consumes it in the engine.
    bool normality=false;
    eachCard(b,[&](const CardInstance &c) { normality |= c.id==CardId::NORMALITY; });
    if (!normality && !b.player.hasRelic<RelicId::VELVET_CHOKER>()
        && !b.player.hasStatus<PS::ECHO_FORM>())
        b.player.cardsPlayedThisTurn=std::min<int>(4,b.player.cardsPlayedThisTurn);
    // Attack consumers: first-attack check (Art of War), and
    // modulo-three relics. Keep exact for those relics; accept false negatives.
    if (!b.player.hasRelic<RelicId::KUNAI>() && !b.player.hasRelic<RelicId::SHURIKEN>()
        && !b.player.hasRelic<RelicId::ORNAMENTAL_FAN>())
        b.player.attacksPlayedThisTurn=std::min<int>(1,b.player.attacksPlayedThisTurn);
    if (!b.player.hasRelic<RelicId::LETTER_OPENER>()) b.player.skillsPlayedThisTurn=0;
    // Enemy HP and nondecreasing energy are progress coordinates. Preserve
    // player HP/block/powers, counters, liveness and phase state exactly.
    b.player.energy=0;
    for (auto &m:b.monsters.arr) if (!m.isDeadOrEscaped() && !m.halfDead) m.curHp=1;
    if (singletonShuffles(b)) b.shuffleRng=Random(0);
    return b;
}

// No Silver policy/prior/model initialization or pruning: enumerate legal
// physical card plays directly, through the existing Action legality API.
// Selections and potions are outside this first quiet-boundary oracle.
std::vector<SAction> actions(const BattleContext &b, bool noPrismaticShard) {
    std::vector<SAction> out;
    if (!quiet(b,noPrismaticShard)) return out;
    for (int i=0;i<b.cards.cardsInHand;++i) {
        const int targets=b.cards.hand[i].requiresTarget()?b.monsters.monsterCount:1;
        for(int t=0;t<targets;++t) {
            SAction a(ActionType::CARD,i,t);
            if(a.isValidAction(b)) out.push_back(a);
        }
    }
    return out;
}

json describe(const BattleContext &b,const SAction &a) {
    std::ostringstream s; a.printDesc(s,b);
    return {{"bits",a.bits},{"description",s.str()},
        {"semantic",semanticFingerprint(semanticFromSearchAction(b,a))}};
}

struct Oracle {
    int nodes=0,maxDepth=0,repeats=0,replayActions=0,rejections=0;
    bool stopped=false, noPrismaticShard=false;
    json candidates=json::array(), best={{"classification","NONE"}};
    std::vector<std::unique_ptr<BattleContext>> path, controls;
    std::vector<std::size_t> hashes;
    std::vector<json> steps;

    json certify(const BattleContext &start,const std::vector<json> &w) {
        auto run=std::make_unique<BattleContext>(start);
        const auto expected=std::make_unique<BattleContext>(controlState(start));
        int used=0, previousEnergy=start.player.energy;
        for(int rep=1;rep<=repetitionCap;++rep) {
            for(const auto &step:w) {
                if(used>=replayCap || replayActions>=totalReplayCap)
                    return {{"reason","action_cap"},{"repetitions",rep-1},{"actions",used}};
                if(!quiet(*run,noPrismaticShard) || run->turn!=start.turn)
                    return {{"reason","control_boundary_changed"},{"repetitions",rep-1},{"actions",used}};
                const SAction a(step.at("bits").get<std::uint32_t>());
                if(!a.isValidAction(*run) || describe(*run,a).at("semantic")!=step.at("semantic"))
                    return {{"reason","witness_illegal_or_identity_changed"},{"repetitions",rep-1},{"actions",used}};
                a.execute(*run); ++used; ++replayActions;
                if(run->player.curHp<=0 || run->outcome==Outcome::PLAYER_LOSS)
                    return {{"reason","player_death"},{"repetitions",rep},{"actions",used}};
                if(run->outcome==Outcome::PLAYER_VICTORY && !run->smokeBombUsed && run->turn==start.turn)
                    return {{"reason","VICTORY"},{"repetitions",rep},{"actions",used}};
            }
            if(run->player.energy<previousEnergy)
                return {{"reason","energy_decreased"},{"repetitions",rep},{"actions",used}};
            if(!quiet(*run,noPrismaticShard) || run->turn!=start.turn || !(controlState(*run)==*expected))
                return {{"reason","control_state_changed"},{"repetitions",rep},{"actions",used}};
            previousEnergy=run->player.energy;
        }
        return {{"reason","repetition_cap"},{"repetitions",repetitionCap},{"actions",used}};
    }

    void candidate(int at,const BattleContext &end) {
        ++repeats;
        const auto &start=*path[at];
        std::vector<json> witness(steps.begin()+at,steps.end());
        json deltas=json::array(); bool damage=false;
        int total=0;
        for(int i=0;i<start.monsters.monsterCount;++i) {
            int d=end.monsters.arr[i].curHp-start.monsters.arr[i].curHp;
            damage |= !start.monsters.arr[i].isDeadOrEscaped() && d<0;
            total+=d; deltas.push_back(d);
        }
        json reach=json::array(); for(int i=0;i<at;++i) reach.push_back(steps[i]);
        json row={{"classification",damage?"PRODUCTIVE_CYCLE_CANDIDATE":"STALL_LOOP"},
            {"reach_depth",at},{"cycle_length",witness.size()}, {"reach_actions",reach},
            {"cycle_actions",witness},{"enemy_hp_deltas",deltas},{"enemy_hp_delta_per_cycle",total},
            {"player_hp_delta_per_cycle",end.player.curHp-start.player.curHp},
            {"energy_delta_per_cycle",end.player.energy-start.player.energy},
            {"cards_played_per_cycle",end.player.cardsPlayedThisTurn-start.player.cardsPlayedThisTurn},
            {"finite_resources_consumed",{{"potions",start.potionCount-end.potionCount},
                {"gold",start.player.gold-end.player.gold},{"new_exhausted_cards",end.cards.exhaustPile.size()-start.cards.exhaustPile.size()}}}};
        if(damage) {
            row["replay"]=certify(start,witness);
            if(row["replay"]["reason"]=="VICTORY") {
                row["classification"]="CERTIFIED_KILL";
                row["terminal"]="VICTORY";
                row["repetitions_to_terminal"]=row["replay"]["repetitions"];
            } else ++rejections;
        }
        auto rank=[](const json &r) {
            auto c=r.at("classification").get<std::string>();
            return c=="CERTIFIED_KILL"?3:c=="PRODUCTIVE_CYCLE_CANDIDATE"?2:c=="STALL_LOOP"?1:0;
        };
        if(rank(row)>rank(best)) best=row;
        candidates.push_back(row);
        if(rank(best)==3 || candidates.size()>=candidateCap || replayActions>=totalReplayCap) stopped=true;
    }

    void visit(std::unique_ptr<BattleContext> b) {
        if(stopped || nodes>=nodeCap) return;
        ++nodes;
        const int depth=steps.size(); maxDepth=std::max(maxDepth,depth);
        if(!quiet(*b,noPrismaticShard) || (!path.empty() && b->turn!=path.front()->turn)) return;
        auto control=std::make_unique<BattleContext>(controlState(*b));
        auto hash=hashBattleState(*control);
        for(int i=static_cast<int>(controls.size())-1;i>=0;--i)
            if(hash==hashes[i] && *control==*controls[i]
                && b->player.energy>=path[i]->player.energy) {
                candidate(i,*b); return; // never expand a repeated state
            }
        if(depth>=depthCap) return;
        auto legal=actions(*b,noPrismaticShard);
        path.push_back(std::move(b)); controls.push_back(std::move(control)); hashes.push_back(hash);
        for(const auto &a:legal) {
            if(stopped || nodes>=nodeCap) break;
            auto child=std::make_unique<BattleContext>(*path.back());
            steps.push_back(describe(*child,a));
            a.execute(*child);
            visit(std::move(child));
            steps.pop_back();
        }
        hashes.pop_back(); controls.pop_back(); path.pop_back();
    }

    json run(const BattleContext &root, bool shardAbsenceProven) {
        noPrismaticShard=shardAbsenceProven;
        ObserverScope scope;
        const auto begin=std::clock();
        if(quiet(root,noPrismaticShard)) visit(std::make_unique<BattleContext>(root));
        best["supported"]=quiet(root,noPrismaticShard);
        best["prismatic_shard_absence_proven"]=noPrismaticShard;
        best["reason"]=quiet(root,noPrismaticShard)?"bounded_search":"requires_audited_ironclad_concrete_quiet_player_root";
        best["nodes"]=nodes; best["max_depth"]=maxDepth;
        best["node_cap_hit"]=nodes>=nodeCap; best["depth_cap_hit"]=maxDepth>=depthCap; best["repeated_control_states"]=repeats;
        best["replay_actions"]=replayActions; best["replay_rejections"]=rejections;
        best["cpu_ms"]=1000.0*(std::clock()-begin)/CLOCKS_PER_SEC;
        best["candidates"]=candidates;
        best["caps"]={{"depth",depthCap},{"cycle_length",depthCap},{"nodes",nodeCap},
            {"candidates",candidateCap},{"repetitions",repetitionCap},{"actions_per_replay",replayCap},
            {"total_replay_actions",totalReplayCap}};
        return best;
    }
};

BattleContext fixture(CardId card=CardId::DROPKICK) {
    BattleContext b{};
    b.player.cc=CharacterClass::IRONCLAD;
    // Seeded initialization is confined to this tiny deterministic fixture.
    b.aiRng=Random(1); b.cardRandomRng=Random(2); b.miscRng=Random(3);
    b.monsterHpRng=Random(4); b.potionRng=Random(5); b.shuffleRng=Random(6);
    b.inputState=InputState::PLAYER_NORMAL; b.turn=1;
    b.player.energy=1;
    b.monsters.monsterCount=1; b.monsters.monstersAlive=1;
    auto &m=b.monsters.arr[0]; m.id=MonsterId::CULTIST; m.idx=0;
    m.setMove(MMID::CULTIST_INCANTATION);
    m.curHp=200; m.maxHp=200; m.addDebuff<MS::VULNERABLE>(2,false);
    CardInstance a(card), c(card); a.uniqueId=0; c.uniqueId=1;
    b.cards.nextUniqueCardId=2;
    b.cards.moveToHand(a); b.cards.moveToDrawPileTop(c);
    return b;
}

void require(bool ok,const std::string &why) { if(!ok) throw std::runtime_error(why); }

json summary(const std::vector<json> &rows) {
    json r={{"states",rows.size()},{"supported_states",0},{"NONE",0},{"repeated_states",0},{"STALL_LOOP",0},{"PRODUCTIVE_CYCLE_CANDIDATE",0},
        {"CERTIFIED_KILL",0},{"productive_candidates",0},{"replay_rejections",0},
        {"max_nodes",0},{"max_cpu_ms",0.0},{"max_depth",0}};
    double nodes=0,cpu=0;
    for(const auto &row:rows) {
        const auto c=row.at("classification").get<std::string>();
        r[c]=r[c].get<int>()+1;
        if(row.at("supported").get<bool>()) r["supported_states"]=r["supported_states"].get<int>()+1;
        if(row.at("repeated_control_states").get<int>()>0) r["repeated_states"]=r["repeated_states"].get<int>()+1;
        for(const auto &p:row.at("candidates"))
            if(p.at("classification")!="STALL_LOOP") r["productive_candidates"]=r["productive_candidates"].get<int>()+1;
        nodes+=row.at("nodes").get<int>(); cpu+=row.at("cpu_ms").get<double>();
        r["max_nodes"]=std::max(r["max_nodes"].get<int>(),row.at("nodes").get<int>());
        r["max_cpu_ms"]=std::max(r["max_cpu_ms"].get<double>(),row.at("cpu_ms").get<double>());
        r["max_depth"]=std::max(r["max_depth"].get<int>(),row.at("max_depth").get<int>());
        r["replay_rejections"]=r["replay_rejections"].get<int>()+row.at("replay_rejections").get<int>();
    }
    r["mean_nodes"]=rows.empty()?0:nodes/rows.size();
    r["mean_cpu_ms"]=rows.empty()?0:cpu/rows.size();
    return r;
}

void fixtures() {
    std::vector<json> rows;
    auto check=[&](const std::string &name,const BattleContext &b,const std::string &expected, bool noShard=true) {
        const BattleContext before=b;
        auto row=Oracle{}.run(b,noShard); row["fixture"]=name;
        std::cout<<row.dump()<<'\n'; rows.push_back(row);
        require(row.at("classification")==expected,name+": unexpected classification");
        require(b==before,name+": root mutated");
        return row;
    };
    auto positive=fixture();
    auto result=check("dropkick",positive,"CERTIFIED_KILL");
    require(result.at("enemy_hp_delta_per_cycle").get<int>()<0,"positive must be productive");
    auto broken=positive; broken.monsters.arr[0].removeStatus<MS::VULNERABLE>();
    check("dropkick_no_vulnerable",broken,"NONE");
    auto stall=fixture(CardId::FLASH_OF_STEEL);
    stall.monsters.arr[0].buff<MS::INVINCIBLE>(1);
    stall.monsters.arr[0].setStatus<MS::INVINCIBLE>(0);
    check("flash_invincible_stall_544_class",stall,"STALL_LOOP");
    auto phase=positive; phase.monsters.arr[0].id=MonsterId::AWAKENED_ONE;
    auto rejected=check("awakened_one_phase1",phase,"PRODUCTIVE_CYCLE_CANDIDATE");
    require(rejected.at("replay").at("reason")=="witness_illegal_or_identity_changed","phase must interrupt replay");
    auto time=positive; time.monsters.arr[0].buff<MS::TIME_WARP>(1);
    check("time_warp",time,"NONE");
    // A valid candidate whose lethal replay is beyond the conservative cap.
    auto capped=positive; capped.monsters.arr[0].curHp=100000; capped.monsters.arr[0].maxHp=100000;
    auto cap=check("repetition_cap",capped,"PRODUCTIVE_CYCLE_CANDIDATE");
    require(cap.at("replay").at("reason")=="repetition_cap","cap cannot certify");
    // Exercise both hard search bounds without a seed cohort. A third card
    // disables the audited singleton-shuffle quotient; RNG stays exact.
    auto branching=fixture(CardId::FLASH_OF_STEEL);
    CardInstance third(CardId::FLASH_OF_STEEL); third.uniqueId=2;
    branching.cards.moveToHand(third); branching.cards.nextUniqueCardId=3;
    branching.monsters.arr[0].curHp=100000; branching.monsters.arr[0].maxHp=100000;
    auto bounded=check("branching_budget",branching,"NONE");
    require(bounded.at("nodes")==nodeCap && bounded.at("max_depth")==depthCap,
        "search budget fixture did not reach both bounds");
    // The existing native binary replay restores this concrete combat root.
    const auto bytes=serializeBattleContext(positive);
    auto restored=deserializeBattleContext(bytes.data(),bytes.size());
    require(restored==positive,"existing binary snapshot round trip");
    auto info=positive; info.cards.drawPile.assignInformationState({},
        {CardInstance(CardId::STRIKE_RED),CardInstance(CardId::DEFEND_RED)},{});
    check("unsupported_information_set",info,"NONE");
    // Fail closed before any search outside the audited counter domain.
    for (const auto cc:{CharacterClass::SILENT,CharacterClass::DEFECT,CharacterClass::WATCHER}) {
        auto foreign=positive; foreign.player.cc=cc;
        auto row=check(std::string("unsupported_")+characterClassEnumNames[static_cast<int>(cc)],foreign,"NONE");
        require(!row.at("supported").get<bool>() && row.at("nodes")==0,"foreign character entered search");
    }
    RelicContainer shardRelics;
    shardRelics.add({RelicId::PRISMATIC_SHARD,0});
    require(shardRelics.has(RelicId::PRISMATIC_SHARD),"Shard fixture provenance");
    auto unsupported=check("unsupported_prismatic_shard",positive,"NONE",
        !shardRelics.has(RelicId::PRISMATIC_SHARD));
    require(!unsupported.at("supported").get<bool>() && unsupported.at("nodes")==0,"Shard entered search");
    auto finisher=positive; finisher.cards.hand[0]=CardInstance(CardId::FINISHER);
    unsupported=check("unsupported_foreign_finisher",finisher,"NONE");
    require(!unsupported.at("supported").get<bool>() && unsupported.at("nodes")==0,"foreign counter consumer entered search");
    // Key sensitivity: resources, dynamic cards, counters and enemy mechanics.
    auto key=controlState(positive);
    for(int field=1;field<8;++field) {
        auto changed=positive;
        switch(field) {
            case 1: ++changed.cards.hand[0].costForTurn; break;
            case 2: ++changed.player.sundialCounter; break;
            case 3: ++changed.monsters.arr[0].block; break;
            case 4: changed.monsters.arr[0].buff<MS::TIME_WARP>(1); break;
            case 5: ++changed.player.curHp; break;
            case 6: ++changed.cards.hand[0].uniqueId; break;
            case 7: changed.player.setHasRelic<RelicId::VELVET_CHOKER>(true); ++changed.player.cardsPlayedThisTurn; break;
        }
        require(!(controlState(changed)==key),"control field omitted");
    }
    auto higherEnergy=positive; ++higherEnergy.player.energy;
    require(controlState(higherEnergy)==key,"energy must be a progress coordinate");
    auto counted=positive;
    counted.player.setHasRelic<RelicId::VELVET_CHOKER>(true);
    auto countedMore=counted; ++countedMore.player.cardsPlayedThisTurn;
    require(!(controlState(counted)==controlState(countedMore)),"Choker count collapsed");
    counted=positive; counted.player.buff<PS::ECHO_FORM>(1);
    countedMore=counted; ++countedMore.player.cardsPlayedThisTurn;
    require(!(controlState(counted)==controlState(countedMore)),"Echo count collapsed");
    counted=positive; counted.player.setHasRelic<RelicId::LETTER_OPENER>(true);
    countedMore=counted; ++countedMore.player.skillsPlayedThisTurn;
    require(!(controlState(counted)==controlState(countedMore)),"Letter Opener count collapsed");
    std::cout<<json({{"summary",summary(rows)},{"fixture_assertions","PASS"}}).dump()<<'\n';
}

// Phase-2 fixtures use the same detector; --recall-probe records the ablation
// before interventions, while --recall-fixtures also checks final verdicts.
void staticExhaust(BattleContext &b) {
    for (auto id:{CardId::STRIKE_RED,CardId::STRIKE_RED,CardId::DEFEND_RED,
                 CardId::DEFEND_RED,CardId::BASH,CardId::ANGER,CardId::TRUE_GRIT}) {
        CardInstance c(id); c.uniqueId=b.cards.nextUniqueCardId++;
        b.cards.moveToExhaustPile(c);
    }
}

json scriptedTrace(BattleContext b, int cap) {
    const auto initial=std::make_unique<BattleContext>(b);
    json rows=json::array();
    for(int i=0;i<cap;++i) {
        auto legal=actions(b,true);
        if(legal.empty()) break;
        require(legal.size()==1,"script requires a single legal physical play");
        auto step=describe(b,legal[0]); legal[0].execute(b);
        step["action"]=i+1; step["energy"]=b.player.energy;
        step["player_hp"]=b.player.curHp; step["enemy_hp"]=b.monsters.arr[0].curHp;
        step["sundial_counter"]=b.player.sundialCounter;
        step["invincible"]=b.monsters.arr[0].getStatus<MS::INVINCIBLE>();
        rows.push_back(step);
        if(b.outcome!=Outcome::UNDECIDED || b.turn!=initial->turn) break;
    }
    return {{"trace",rows},{"actions",rows.size()},{"terminal_outcome",static_cast<int>(b.outcome)},
        {"turn_changed",b.turn!=initial->turn},{"energy_end",b.player.energy},
        {"player_hp_end",b.player.curHp},{"enemy_hp_end",b.monsters.arr[0].curHp},
        {"invincible_end",b.monsters.arr[0].getStatus<MS::INVINCIBLE>()},
        {"no_legal_card",actions(b,true).empty()}};
}

json periodEvidence(BattleContext b) {
    // Four plays saturate the existing bookkeeping normalization. Six further
    // plays restore both physical card positions and Sundial's modulo-3 count.
    for(int i=0;i<4;++i) {
        auto legal=actions(b,true); require(legal.size()==1,"period prefix"); legal[0].execute(b);
    }
    const auto start=std::make_unique<BattleContext>(b);
    for(int i=0;i<6;++i) {
        auto legal=actions(b,true); require(legal.size()==1,"full six-action period"); legal[0].execute(b);
    }
    auto a=std::make_unique<BattleContext>(controlState(*start));
    auto z=std::make_unique<BattleContext>(controlState(b));
    a->player.energy=z->player.energy=0;
    // Diagnostic only: the two active Dropkicks prove singleton shuffles;
    // static exhaust must remain exact even in this isolated comparison.
    a->shuffleRng=z->shuffleRng=Random(0);
    require(*a==*z,"period differs beyond energy and singleton shuffle RNG");
    require(start->player.sundialCounter==b.player.sundialCounter,"Sundial period");
    return {{"prefix_actions",4},{"period_actions",6},{"energy_start",start->player.energy},
        {"energy_end",b.player.energy},{"energy_delta",b.player.energy-start->player.energy},
        {"enemy_hp_delta",b.monsters.arr[0].curHp-start->monsters.arr[0].curHp},
        {"sundial_start",start->player.sundialCounter},{"sundial_end",b.player.sundialCounter},
        {"same_except_energy_and_singleton_rng",true}};
}

// Deliberately exercise the replay guard even when discovery correctly refuses
// a decreasing-energy or changing-HP/counter state as a cycle candidate.
json replayProbe(BattleContext b,int prefix,int period) {
    for(int i=0;i<prefix;++i) {
        auto legal=actions(b,true); require(legal.size()==1,"replay probe prefix"); legal[0].execute(b);
    }
    const auto start=std::make_unique<BattleContext>(b);
    std::vector<json> witness;
    for(int i=0;i<period;++i) {
        auto legal=actions(b,true); require(legal.size()==1,"replay probe period");
        witness.push_back(describe(b,legal[0])); legal[0].execute(b);
    }
    Oracle oracle; oracle.noPrismaticShard=true;
    return oracle.certify(*start,witness);
}

void recallFixtures(bool verify) {
    ObserverScope scope;
    std::vector<json> rows;
    auto check=[&](const std::string &name,const BattleContext &b,const std::string &expected,
                   const json &diagnostics=json::object()) {
        const auto before=std::make_unique<BattleContext>(b);
        auto row=Oracle{}.run(b,true); row["fixture"]=name; row["mechanics"]=diagnostics;
        std::cout<<row.dump()<<'\n'; rows.push_back(row);
        if(verify) require(row.at("classification")==expected,name+": recall classification");
        require(b==*before,name+": root mutated");
        return row;
    };
    auto base=std::make_unique<BattleContext>(fixture());
    check("minimal_dropkick",*base,"CERTIFIED_KILL");
    auto exhausted=std::make_unique<BattleContext>(*base); staticExhaust(*exhausted);
    check("static_exhaust_dropkick",*exhausted,"CERTIFIED_KILL");
    auto broken=std::make_unique<BattleContext>(*exhausted);
    broken->monsters.arr[0].removeStatus<MS::VULNERABLE>();
    check("broken_dropkick",*broken,"NONE",scriptedTrace(*broken,64));

    auto energy=std::make_unique<BattleContext>(*base);
    energy->player.energy=7; energy->player.setHasRelic<RelicId::SUNDIAL>(true);
    energy->cards.hand[0].cost=0; energy->cards.hand[0].setCostForTurn(0);
    auto measured=periodEvidence(*energy);
    require(measured.at("energy_delta").get<int>()>0,"positive energy economics");
    check("energy_positive_no_exhaust",*energy,"CERTIFIED_KILL",measured);
    staticExhaust(*energy);
    check("energy_positive_exhaust",*energy,"CERTIFIED_KILL",periodEvidence(*energy));
    auto negative=std::make_unique<BattleContext>(*energy);
    negative->cards.hand[0].cost=3; negative->cards.hand[0].setCostForTurn(3); // sole cost variable
    measured=periodEvidence(*negative);
    require(measured.at("energy_delta").get<int>()<0,"negative energy economics");
    measured["run_to_break"]=scriptedTrace(*negative,64);
    measured["forced_replay"]=replayProbe(*negative,4,6);
    require(measured["forced_replay"]["reason"]=="energy_decreased","decreasing replay must reject");
    require(measured["run_to_break"]["no_legal_card"].get<bool>() &&
        measured["run_to_break"]["enemy_hp_end"].get<int>()>0,"negative must run out before lethal");
    check("energy_negative_exhaust",*negative,"NONE",measured);

    auto time=std::make_unique<BattleContext>(*base);
    time->monsters.arr[0]=Monster{}; auto &tm=time->monsters.arr[0];
    tm.id=MonsterId::TIME_EATER; tm.idx=0; tm.initHp(time->monsterHpRng,0);
    tm.preBattleAction(*time); tm.setMove(MMID::TIME_EATER_HEAD_SLAM);
    tm.addDebuff<MS::VULNERABLE>(2,false); tm.setStatus<MS::TIME_WARP>(1);
    check("time_eater",*time,"NONE",scriptedTrace(*time,64));
    auto phase=std::make_unique<BattleContext>(*base);
    phase->monsters.arr[0].id=MonsterId::AWAKENED_ONE;
    check("awakened_one_phase1",*phase,"PRODUCTIVE_CYCLE_CANDIDATE");

    auto heart=std::make_unique<BattleContext>(*exhausted); heart->ascension=20;
    heart->monsters.arr[0]=Monster{}; auto &hm=heart->monsters.arr[0];
    hm.id=MonsterId::CORRUPT_HEART; hm.idx=0; hm.initHp(heart->monsterHpRng,20);
    hm.preBattleAction(*heart); hm.setMove(MMID::CORRUPT_HEART_DEBILITATE);
    hm.addDebuff<MS::VULNERABLE>(2,false);
    require(hm.curHp==800 && hm.getStatus<MS::BEAT_OF_DEATH>()==2 &&
        hm.getStatus<MS::INVINCIBLE>()==200,"real A20 Heart mechanics");
    auto trace=scriptedTrace(*heart,64);
    trace["forced_replay"]=replayProbe(*heart,4,2);
    require(trace["forced_replay"]["reason"]=="control_state_changed","Heart replay must reject");
    require(trace.at("enemy_hp_end")==600 && trace.at("player_hp_end")==0 &&
        trace.at("invincible_end")==0,"Heart cap and Beat of Death must prevent lethal");
    check("heart_invincible_and_beat",*heart,"NONE",trace);
    heart->player.curHp=12;
    check("heart_low_hp",*heart,"NONE",scriptedTrace(*heart,64));

    // Test the suggested alternative through actual simulator plays. Shrug's
    // accumulating block introduces a second progress dimension, so do not
    // extend the RNG quotient or block equality to accommodate this engine.
    auto suggested=std::make_unique<BattleContext>(fixture(CardId::POMMEL_STRIKE));
    suggested->cards.hand[0].upgrade(); suggested->cards.hand[0].cost=0;
    suggested->cards.hand[0].setCostForTurn(0);
    suggested->cards.drawPile.clear();
    CardInstance shrug(CardId::SHRUG_IT_OFF); shrug.uniqueId=1;
    suggested->cards.moveToDrawPileTop(shrug); suggested->player.energy=7;
    suggested->player.setHasRelic<RelicId::SUNDIAL>(true);
    for(int i=0;i<4;++i) {
        auto legal=actions(*suggested,true); require(legal.size()==1,"suggested prefix"); legal[0].execute(*suggested);
    }
    int initialBlock=suggested->player.block;
    auto suggestedTrace=scriptedTrace(*suggested,6);
    // Copy-play the same six actions to measure the extra state change.
    for(int i=0;i<6;++i) {
        auto legal=actions(*suggested,true); require(legal.size()==1,"suggested period"); legal[0].execute(*suggested);
    }
    int blockDelta=suggested->player.block-initialBlock;
    require(blockDelta==24,"Shrug must accumulate actual block");
    std::cout<<json({{"diagnostic","pommel_plus_shrug"},{"block_delta_per_six_plays",blockDelta},
        {"trace",suggestedTrace},{"reason","block_also_increases_outside_energy_only_scope"}}).dump()<<'\n';

    // A purported period with the same active cards but a changed exhaust
    // payload must fail full equality, including same-count mutations.
    auto periodStart=std::make_unique<BattleContext>(*exhausted);
    for(int i=0;i<4;++i) { auto legal=actions(*periodStart,true); legal[0].execute(*periodStart); }
    auto periodEnd=std::make_unique<BattleContext>(*periodStart);
    for(int i=0;i<2;++i) { auto legal=actions(*periodEnd,true); legal[0].execute(*periodEnd); }
    require(controlState(*periodStart)==controlState(*periodEnd),"static exhaust real period must match");
    auto changed=std::make_unique<BattleContext>(*periodEnd);
    changed->cards.exhaustPile[0].id=CardId::DEFEND_RED;
    require(!(controlState(*changed)==controlState(*periodStart)),"period exhaust mutation collapsed");
    require(!(controlState(*changed)==controlState(*exhausted)),"exhaust mutation collapsed");
    changed=std::make_unique<BattleContext>(*exhausted);
    ++changed->cards.exhaustPile[0].uniqueId;
    require(!(controlState(*changed)==controlState(*exhausted)),"exhaust physical ID collapsed");
    changed=std::make_unique<BattleContext>(*exhausted);
    changed->cards.exhaustPile.pop_back();
    require(!(controlState(*changed)==controlState(*exhausted)),"exhaust removal collapsed");
    auto stasis=std::make_unique<BattleContext>(*base);
    stasis->cards.stasisCards[0]=CardInstance(CardId::STRIKE_RED);
    require(!singletonShuffles(*stasis),"occupied stasis cannot qualify singleton shuffles");
    auto rngChanged=std::make_unique<BattleContext>(*exhausted);
    rngChanged->shuffleRng=Random(99);
    require(controlState(*rngChanged)==controlState(*exhausted),"qualified singleton shuffle RNG");
    rngChanged->cardRandomRng=Random(99);
    require(!(controlState(*rngChanged)==controlState(*exhausted)),"other RNG streams stay exact");
    std::cout<<json({{"summary",summary(rows)},{"exhaust_mutation_regressions","PASS"},
        {"recall_assertions",verify?"PASS":"PROBE"}}).dump()<<'\n';
}

// Research-only public-root adapter. Silver itself samples CardPile's unknown
// region lazily. Eagerly drawing a COPY with that same operation gives a
// public-conditioned concrete order; the root and its public facts stay intact.
constexpr int publicWorlds=4, publicRootCap=4;

std::string publicSha(const std::string &text) {
    unsigned char digest[EVP_MAX_MD_SIZE]{}; unsigned int length=0;
    if(EVP_Digest(text.data(),text.size(),digest,&length,EVP_sha256(),nullptr)!=1 || length!=32)
        throw std::runtime_error("public-root SHA256 failure");
    std::ostringstream out; out<<std::hex<<std::setfill('0');
    for(unsigned int i=0;i<length;++i) out<<std::setw(2)<<unsigned(digest[i]);
    return out.str();
}

struct PublicRoot {
    BattleContext state;
    std::string hash;
};

PublicRoot publicRoot(const json &row) {
    const auto &envelope=row.contains("public_wire")?row.at("public_wire"):row.at("state");
    auto wire=silver_bridge::battleStateWireFromEnvelope(envelope);
    require(wire.valid && wire.drawPile.valid,"invalid public root");
    require(!wire.fullDrawOrderObserved && !wire.drawPile.fullOrderObserved,
        "pilot requires information-set draw; never import private concrete order");
    require(!wire.intentsHidden,"hidden-intent roots outside pilot scope");
    // Ignore a source-provided RNG identity even when a historical wire has it.
    wire.isolatedSearchSeed=0;
    auto b=battleContextFromWire(wire);
    auto canonical=wireFromSearchState(b,searchContextFromWire(wire));
    canonical.isolatedSearchSeed=0; canonical.observedGeneration=0;
    return {std::move(b),publicSha(silver_bridge::battleStateWireEnvelope(canonical).dump())};
}

BattleContext publicWorld(const PublicRoot &root,int k) {
    require(k>=0 && k<publicWorlds,"world index outside frozen K=4");
    auto b=root.state;
    const auto digest=publicSha("combat-infinity-public-world-v1:"+root.hash+":"+std::to_string(k));
    const auto seed=std::stoull(digest.substr(0,16),nullptr,16);
    b.seed=seed; seedSearchRng(b,seed);
    auto pile=b.cards.drawPile;
    require(!pile.isConcrete(),"public sampling requires an information set");
    std::vector<CardInstance> drawn;
    while(!pile.empty()) drawn.push_back(pile.drawTop(b.shuffleRng));
    std::reverse(drawn.begin(),drawn.end()); // concrete representation is bottom-first
    b.cards.drawPile.assignConcrete(std::move(drawn));
    return b;
}

json annotatePublic(const json &source) {
    ObserverScope scope;
    auto root=std::make_unique<PublicRoot>(publicRoot(source));
    const auto before=std::make_unique<BattleContext>(root->state);
    const bool noShard=source.value("oracle_no_prismatic_shard",false);
    json result={{"schema","combat_infinity_public_sidecar_v1"},{"public_root_sha256",root->hash},
        {"K",publicWorlds},{"sampling","Silver_CardPile_drawTop_public_conditioned_v1"},
        {"candidate_fraction_definition","worlds_with_damaging_candidate_including_certified"},
        {"supported_worlds",0},{"certified_fraction",nullptr},{"candidate_fraction",nullptr},
        {"minimum_reach_depth",nullptr},{"worlds",json::array()}};
    if(!noShard) {
        result["status"]="UNSUPPORTED"; result["reason"]="missing_proven_no_prismatic_shard";
        return result;
    }
    int certified=0,candidates=0,minReach=depthCap+1;
    for(int k=0;k<publicWorlds;++k) {
        auto world=std::make_unique<BattleContext>(publicWorld(*root,k));
        auto verdict=Oracle{}.run(*world,true);
        json order=json::array();
        for(const auto &c:world->cards.drawPile)
            order.push_back({{"id",static_cast<int>(c.id)},{"physical_id",c.uniqueId}});
        result["worlds"].push_back({{"k",k},{"sample_seed",std::to_string(world->seed)},
            {"sampled_draw_bottom_first",order},{"oracle",verdict}});
        if(!verdict.at("supported").get<bool>()) continue;
        result["supported_worlds"]=result["supported_worlds"].get<int>()+1;
        certified+=verdict.at("classification")=="CERTIFIED_KILL";
        bool productive=false;
        for(const auto &c:verdict.at("candidates")) if(c.at("classification")!="STALL_LOOP") {
            productive=true; minReach=std::min(minReach,c.at("reach_depth").get<int>());
        }
        candidates+=productive;
    }
    require(root->state==*before,"public annotation mutated input root");
    if(result.at("supported_worlds")!=publicWorlds) {
        result["status"]="UNSUPPORTED"; result["reason"]="oracle_domain_or_quiet_boundary";
        return result; // missing worlds are never silently counted as negatives
    }
    result["status"]="ANNOTATED"; result["reason"]="bounded_K4_public_conditioned_worlds";
    result["certified_fraction"]=double(certified)/publicWorlds;
    result["candidate_fraction"]=double(candidates)/publicWorlds;
    if(minReach<=depthCap) result["minimum_reach_depth"]=minReach;
    return result;
}

json publicFixtureRow(BattleContext b) {
    // Explicit synthetic public knowledge: forget all draw order, retain the
    // multiset. No original concrete ordering is exported to the adapter.
    std::vector<CardInstance> unknown(b.cards.drawPile.begin(),b.cards.drawPile.end());
    b.cards.drawPile.assignInformationState({},unknown,{});
    auto wire=wireFromSearchState(b,SilverSearchContext{});
    wire.isolatedSearchSeed=0;
    return {{"public_wire",silver_bridge::battleStateWireEnvelope(wire)},
        {"oracle_no_prismatic_shard",true}};
}

void publicFixtures() {
    ObserverScope scope;
    std::vector<json> rows;
    auto check=[&](const std::string &name,const BattleContext &b,double expected) {
        auto input=publicFixtureRow(b); auto result=annotatePublic(input);
        require(result.at("status")=="ANNOTATED" && result.at("certified_fraction")==expected,
            name+": public fixture classification");
        result["fixture"]=name; rows.push_back(result); std::cout<<result.dump()<<'\n';
        return input;
    };
    auto positive=std::make_unique<BattleContext>(fixture()); staticExhaust(*positive);
    auto input=check("public_static_exhaust_dropkick",*positive,1.0);
    auto energy=std::make_unique<BattleContext>(*positive);
    energy->player.energy=7; energy->player.setHasRelic<RelicId::SUNDIAL>(true);
    energy->cards.hand[0].cost=0; energy->cards.hand[0].setCostForTurn(0);
    check("public_energy_positive",*energy,1.0);
    auto broken=std::make_unique<BattleContext>(*positive);
    broken->monsters.arr[0].removeStatus<MS::VULNERABLE>();
    check("public_broken_dropkick",*broken,0.0);
    auto phase=std::make_unique<BattleContext>(*positive); phase->monsters.arr[0].id=MonsterId::AWAKENED_ONE;
    check("public_phase_guard",*phase,0.0);
    require(rows[3].at("candidate_fraction")==1.0,"candidate fraction must include rejected damaging recurrences");
    require(rows[0].at("candidate_fraction")==1.0 && rows[0].at("minimum_reach_depth")==4,
        "positive public aggregate fields");
    require(rows[2].at("candidate_fraction")==0.0 && rows[2].at("minimum_reach_depth").is_null(),
        "no-candidate depth must be null");
    auto missing=input; missing.erase("oracle_no_prismatic_shard");
    auto unsupported=annotatePublic(missing);
    require(unsupported.at("status")=="UNSUPPORTED" && unsupported.at("certified_fraction").is_null()
        && unsupported.at("candidate_fraction").is_null() && unsupported.at("worlds").empty(),
        "missing provenance cannot produce negative labels");
    auto explicitFalse=input; explicitFalse["oracle_no_prismatic_shard"]=false;
    require(annotatePublic(explicitFalse).at("certified_fraction").is_null(),"false provenance cannot label");

    // Nontrivial information set: fixed top/bottom and three distinct unknowns.
    // Check exact draw-sequence parity with the existing lazy kernel for each
    // of the four frozen world seeds, with no card effects or game rollout.
    auto kernel=std::make_unique<BattleContext>(fixture());
    CardInstance bottom(CardId::STRIKE_RED),a(CardId::ANGER),c(CardId::DEFEND_RED),d(CardId::BASH),top(CardId::DROPKICK);
    bottom.uniqueId=5; a.uniqueId=2; c.uniqueId=3; d.uniqueId=4; top.uniqueId=1;
    kernel->cards.drawPile.assignInformationState({bottom},{a,c,d},{top});
    kernel->cards.nextUniqueCardId=6;
    auto wire=wireFromSearchState(*kernel,SilverSearchContext{});
    auto kernelInput=json{{"public_wire",silver_bridge::battleStateWireEnvelope(wire)}};
    auto root=std::make_unique<PublicRoot>(publicRoot(kernelInput));
    auto reversed=wire; std::reverse(reversed.drawPile.unknown.begin(),reversed.drawPile.unknown.end());
    reversed.isolatedSearchSeed=987654321;
    auto variant=std::make_unique<PublicRoot>(publicRoot({{"public_wire",silver_bridge::battleStateWireEnvelope(reversed)},
        {"private_draw_order","poisoned side channel must never be read"}}));
    require(root->hash==variant->hash,"source RNG/unknown order changed canonical public identity");
    json samples=json::array();
    for(int k=0;k<publicWorlds;++k) {
        auto world=std::make_unique<BattleContext>(publicWorld(*root,k));
        auto other=std::make_unique<BattleContext>(publicWorld(*variant,k));
        require(*world==*other,"unobserved source identity influenced sampled world");
        auto lazy=std::make_unique<BattleContext>(root->state); seedSearchRng(*lazy,world->seed);
        auto concrete=world->cards.drawPile;
        while(!concrete.empty()) require(concrete.drawTop(world->shuffleRng)==lazy->cards.drawPile.drawTop(lazy->shuffleRng),
            "materialized sequence differs from Silver lazy draw kernel");
        // Concrete draws consume no randomness; reset them before comparing
        // the sampler's post-materialization stream with the full lazy drain.
        auto fresh=std::make_unique<BattleContext>(publicWorld(*root,k));
        require(fresh->shuffleRng==lazy->shuffleRng,"sampler RNG continuation differs from lazy drain");
        require(fresh->cards.drawPile[0]==bottom && fresh->cards.drawPile[fresh->cards.drawPile.size()-1]==top,"known order facts changed");
        json ids=json::array(); for(const auto &card:fresh->cards.drawPile) ids.push_back(card.uniqueId);
        samples.push_back({{"k",k},{"draw_bottom_first",ids},{"seed",std::to_string(fresh->seed)}});
    }
    bool rejected=false;
    auto concreteWire=wire; concreteWire.fullDrawOrderObserved=true;
    try { (void)publicRoot({{"public_wire",silver_bridge::battleStateWireEnvelope(concreteWire)}}); }
    catch(const std::exception &) { rejected=true; }
    require(rejected,"private concrete order input must reject");
    auto hiddenWire=wire; hiddenWire.intentsHidden=true; rejected=false;
    try { (void)publicRoot({{"public_wire",silver_bridge::battleStateWireEnvelope(hiddenWire)}}); }
    catch(const std::exception &) { rejected=true; }
    require(rejected,"hidden intents outside pilot must reject");
    auto malformed=input; malformed["oracle_no_prismatic_shard"]="true"; rejected=false;
    try { (void)annotatePublic(malformed); } catch(const std::exception &) { rejected=true; }
    require(rejected,"nonboolean provenance must reject");
    auto foreign=std::make_unique<BattleContext>(*positive); foreign->player.cc=CharacterClass::SILENT;
    auto foreignResult=annotatePublic(publicFixtureRow(*foreign));
    require(foreignResult.at("status")=="UNSUPPORTED" && foreignResult.at("supported_worlds")==0
        && foreignResult.at("certified_fraction").is_null(),"unsupported worlds cannot become negatives");
    std::cout<<json({{"public_contract_assertions","PASS"},{"K",publicWorlds},{"control_roots",rows.size()},
        {"known_boundary_samples",samples},{"missing_provenance",unsupported}}).dump()<<'\n';
}

void publicRoots(const char *file) {
    std::ifstream in(file); require(bool(in),"cannot open public roots");
    std::string line; int count=0,supported=0;
    while(count<publicRootCap && std::getline(in,line)) {
        auto result=annotatePublic(json::parse(line)); result["root_index"]=count++;
        supported+=result.at("status")=="ANNOTATED";
        std::cout<<result.dump()<<'\n';
    }
    std::cout<<json({{"schema","combat_infinity_public_pilot_summary_v1"},{"roots",count},
        {"annotated_roots",supported},{"unsupported_roots",count-supported},{"K",publicWorlds},
        {"root_cap",publicRootCap}}).dump()<<'\n';
}

void roots(const char *file) {
    std::ifstream in(file); if(!in) throw std::runtime_error("cannot open roots");
    std::vector<json> rows; std::string line;
    // First eight rows, never outcome-dependent resampling or new collection.
    while(rows.size()<8 && std::getline(in,line)) {
        auto source=json::parse(line);
        auto wire=source.contains("wire")?source.at("wire").get<silver_bridge::BattleStateWire>()
            :silver_bridge::battleStateWireFromEnvelope(source.at("state"));
        auto b=battleContextFromWire(wire);
        // This explicit caller assertion must come from retained run relic
        // provenance. Legacy combat-only wires do not prove Shard absence.
        auto row=Oracle{}.run(b,source.value("oracle_no_prismatic_shard",false));
        row["root_index"]=rows.size(); row["wire_reconstructed"]=true;
        rows.push_back(row); std::cout<<row.dump()<<'\n';
    }
    std::cout<<json({{"summary",summary(rows)}}).dump()<<'\n';
}
}

int main(int argc,char **argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--fixtures") fixtures();
        else if(argc==2 && std::string(argv[1])=="--recall-probe") recallFixtures(false);
        else if(argc==2 && std::string(argv[1])=="--recall-fixtures") recallFixtures(true);
        else if(argc==2 && std::string(argv[1])=="--public-fixtures") publicFixtures();
        else if(argc==3 && std::string(argv[1])=="--public-roots") publicRoots(argv[2]);
        else if(argc==3 && std::string(argv[1])=="--roots") roots(argv[2]);
        else { std::cerr<<"usage: combat_infinity_oracle --fixtures | --recall-fixtures | --recall-probe | --public-fixtures | --public-roots ROOTS.jsonl | --roots ROOTS.jsonl\n"; return 2; }
        return 0;
    } catch(const std::exception &e) { std::cerr<<"combat_infinity_oracle FAIL: "<<e.what()<<'\n'; return 1; }
}
