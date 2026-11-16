// Research executable only: no production caller, reward, or search shortcut.
#include <algorithm>
#include <string_view>
#include <unordered_set>
#include <ctime>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include "combat/BattleContextBinary.h"
#include "game/RelicContainer.h"
#include "sim/search/CombatKnowledge.h"
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

// Natural-root mode (#1054, --snapshots): the same domain gate, but a quiet
// decision may also be a card selection (Headbutt, True Grit+, Burning Pact),
// whose choices the DFS enumerates. Only the caller's concrete live state is
// accepted: no information-set draw pile, no hidden intents.
bool quietNatural(const BattleContext &b, bool noPrismaticShard) {
    return noPrismaticShard && auditedDomain(b) && b.outcome == Outcome::UNDECIDED
        && (b.inputState == InputState::PLAYER_NORMAL || b.inputState == InputState::CARD_SELECT)
        && !b.endTurnQueued && !b.turnHasEnded && !b.skipMonsterTurn
        && !b.actionQueue.size && !b.cardQueue.size && !b.intentsHidden
        && b.cards.drawPile.isConcrete() && !b.undefinedBehaviorEvoked && b.loopCount < 900000
        && b.player.cardsPlayedThisTurn >= 0 && b.player.cardsPlayedThisTurn < 20000
        && b.player.attacksPlayedThisTurn >= 0 && b.player.attacksPlayedThisTurn < 20000
        && b.player.skillsPlayedThisTurn >= 0 && b.player.skillsPlayedThisTurn < 20000;
}

// The only RNG quotient in v0: two physical Dropkick/Flash of Steel cards,
// with no player powers or card hooks except Burning Blood/Sundial. At draw
// time the played card is out of the piles, so a shuffle has <=1 card. Its
// RNG advances but cannot affect the order. All other RNG streams stay exact.
bool singletonShuffles(const BattleContext &b) {
    Player allowed{};
    allowed.setHasRelic<RelicId::BURNING_BLOOD>(true);
    allowed.setHasRelic<RelicId::SUNDIAL>(true);
    if (b.player.statusBits0 || b.player.statusBits1 || !b.player.statusMap.empty()
        || (b.player.relicBits0 & ~allowed.relicBits0)
        || (b.player.relicBits1 & ~allowed.relicBits1)
        || !b.cards.exhaustPile.empty()) return false;
    int count=0; bool simple=true;
    eachCard(b,[&](const CardInstance &c) {
        if(c.id==CardId::INVALID) return;
        ++count;
        simple &= c.id==CardId::DROPKICK || c.id==CardId::FLASH_OF_STEEL;
    });
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
    // HP is the sole progress dimension. Preserve liveness and phase state.
    for (auto &m:b.monsters.arr) if (!m.isDeadOrEscaped() && !m.halfDead) m.curHp=1;
    if (singletonShuffles(b)) b.shuffleRng=Random(0);
    return b;
}

// Natural-root candidate key. It only proposes witnesses: a candidate is
// certified solely by replaying its actions on the untouched start state with
// the real RNG (below), so coarsening here cannot create a false certificate.
// On top of the v0 normalization it treats as progress (not identity) the
// player's HP, block, HP-loss counters, periodic relic counters, Strength and
// Dexterity, every monster's block and a positive Invincible cap (the Heart), and compares with equalForSearch: no RNG streams, the hand as a
// multiset. Ordered draw/discard piles, energy, powers, intents stay exact.
BattleContext controlStateNatural(BattleContext b) {
    b = controlState(b);
    if (b.player.curHp > 0) b.player.curHp = 1;
    b.player.block = 0;
    // HP-loss bookkeeping (Blood for Blood keeps its own per-card cost, which stays exact).
    b.player.timesDamagedThisCombat = 0; b.player.lastAttackUnblockedDamage = 0;
    // Periodic per-card relic/power counters (Pen Nib, Nunchaku, Ink Bottle, Panache; Kunai, Shuriken,
    // Ornamental Fan via the attack count, Letter Opener via the skill count) and the Strength and
    // Dexterity they feed: as exact identity they multiply a loop's period beyond the depth cap.
    // Art of War keeps its zero/nonzero attack test; Velvet Choker, Normality and Echo Form keep
    // the exact card count (v0 rule above).
    b.player.penNibCounter = 0; b.player.nunchakuCounter = 0; b.player.inkBottleCounter = 0;
    b.player.panacheCounter = 0;
    b.player.attacksPlayedThisTurn = std::min<int>(1, b.player.attacksPlayedThisTurn);
    b.player.skillsPlayedThisTurn = 0;
    b.player.strength = 0; b.player.dexterity = 0;
    for (auto &m:b.monsters.arr) {
        m.block = 0;
        if (m.hasStatus<MS::INVINCIBLE>() && m.getStatus<MS::INVINCIBLE>() > 0) m.setStatus<MS::INVINCIBLE>(1);
    }
    return b;
}

// Some monster died, entered a half-dead phase, or lost HP+block since `a`.
bool progressed(const BattleContext &a,const BattleContext &b) {
    int before=0, after=0;
    for(int i=0;i<a.monsters.monsterCount;++i) {
        const auto &x=a.monsters.arr[i], &y=b.monsters.arr[i];
        if(!x.isDeadOrEscaped() && (y.isDeadOrEscaped() || (y.halfDead && !x.halfDead))) return true;
        if(!x.isDeadOrEscaped()) before+=x.curHp+x.block;
        if(!y.isDeadOrEscaped()) after+=y.curHp+y.block;
    }
    return after<before;
}

// Every living monster is capped for this turn: Invincible exhausted.
bool invincibleCapReached(const BattleContext &b) {
    bool any=false;
    for (int i=0;i<b.monsters.monsterCount;++i) {
        const auto &m=b.monsters.arr[i];
        if (m.isDeadOrEscaped() || m.halfDead) continue;
        if (!m.hasStatus<MS::INVINCIBLE>() || m.getStatus<MS::INVINCIBLE>() > 0) return false;
        any=true;
    }
    return any;
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

std::vector<SAction> actionsNatural(const BattleContext &b, bool noPrismaticShard) {
    if (!quietNatural(b,noPrismaticShard)) return {};
    if (b.inputState == InputState::CARD_SELECT) {
        std::vector<SAction> out;
        for (const auto &a:SAction::enumerateCardSelectActions(b)) if (a.isValidAction(b)) out.push_back(a);
        return out;
    }
    std::vector<SAction> out;
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
    int nodes=0,maxDepth=0,repeats=0,replayActions=0,rejections=0,directVictoryDepth=-1;
    bool stopped=false, noPrismaticShard=false;
    // v0 (fixtures, --roots): exact control states. natural (--snapshots): see controlStateNatural.
    bool natural=false; int nodeLimit=nodeCap, depthLimit=depthCap;
    std::unordered_set<std::size_t> expanded;   // natural: transposition pruning by hash (recall only)
    bool isQuiet(const BattleContext &b) const { return natural ? quietNatural(b,noPrismaticShard) : quiet(b,noPrismaticShard); }
    BattleContext key(const BattleContext &b) const { return natural ? controlStateNatural(b) : controlState(b); }
    bool sameKey(const BattleContext &a,const BattleContext &b) const { return natural ? a.equalForSearch(b) : a==b; }
    std::vector<SAction> legal(const BattleContext &b) const { return natural ? actionsNatural(b,noPrismaticShard) : actions(b,noPrismaticShard); }
    json candidates=json::array(), best={{"classification","NONE"}};
    std::vector<std::unique_ptr<BattleContext>> path, controls;
    std::vector<std::size_t> hashes;
    std::vector<json> steps;

    std::unique_ptr<BattleContext> lastRun;   // the replay's state where certify stopped
    int restarts=0;                            // natural: fresh searches after a broken period

    json certify(const BattleContext &start,const std::vector<json> &w) {
        lastRun=std::make_unique<BattleContext>(start);
        auto &run=lastRun;
        const auto expected=std::make_unique<BattleContext>(key(start));
        int used=0;
        for(int rep=1;rep<=repetitionCap;++rep) {
            for(const auto &step:w) {
                if(used>=replayCap || replayActions>=totalReplayCap)
                    return {{"reason","action_cap"},{"repetitions",rep-1},{"actions",used}};
                if(!isQuiet(*run) || run->turn!=start.turn)
                    return {{"reason","control_boundary_changed"},{"repetitions",rep-1},{"actions",used}};
                SAction a(step.at("bits").get<std::uint32_t>());
                if(natural) {
                    // Hand positions may move between periods: the same physical card and target.
                    bool found=false;
                    for(const auto &c:legal(*run)) if(describe(*run,c).at("semantic")==step.at("semantic")) { a=c; found=true; break; }
                    if(!found)
                        return {{"reason","witness_illegal_or_identity_changed"},{"repetitions",rep-1},{"actions",used}};
                } else if(!a.isValidAction(*run) || describe(*run,a).at("semantic")!=step.at("semantic"))
                    return {{"reason","witness_illegal_or_identity_changed"},{"repetitions",rep-1},{"actions",used}};
                a.execute(*run); ++used; ++replayActions;
                if(run->player.curHp<=0 || run->outcome==Outcome::PLAYER_LOSS)
                    return {{"reason","player_death"},{"repetitions",rep},{"actions",used}};
                if(run->outcome==Outcome::PLAYER_VICTORY && !run->smokeBombUsed && run->turn==start.turn)
                    return {{"reason","VICTORY"},{"repetitions",rep},{"actions",used},{"player_hp_lost",start.player.curHp-run->player.curHp}};
                if(natural && run->outcome==Outcome::UNDECIDED && run->turn==start.turn && invincibleCapReached(*run))
                    return {{"reason","INVINCIBLE_CAP"},{"repetitions",rep},{"actions",used},{"player_hp_lost",start.player.curHp-run->player.curHp}};
            }
            if(!isQuiet(*run) || run->turn!=start.turn || !sameKey(key(*run),*expected))
                return {{"reason","control_state_changed"},{"repetitions",rep},{"actions",used}};
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
            // Natural key: monster block is progress too (a loop first breaks Guardian's or a Spheric
            // Guardian's block); v0 keeps block exact, so this never fires there.
            damage |= natural && !start.monsters.arr[i].isDeadOrEscaped()
                && end.monsters.arr[i].block<start.monsters.arr[i].block;
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
            const auto why=row["replay"]["reason"].get<std::string>();
            if(natural && restarts>0 && (why=="control_state_changed" || why=="witness_illegal_or_identity_changed")
                    && lastRun->turn==start.turn && lastRun->player.curHp>0 && progressed(start,*lastRun)) {
                // The loop killed one monster or changed a phase (Darklings, Slavers, Awakened One):
                // search afresh from the replay's real state, same turn, same caps. Every action stays
                // a real simulator step from the untouched start, so a certificate stays sound.
                Oracle next; next.natural=true; next.nodeLimit=nodeLimit; next.depthLimit=depthLimit;
                next.restarts=restarts-1;
                auto tail=next.run(*lastRun,noPrismaticShard);
                nodes+=tail.at("nodes").get<int>(); replayActions+=tail.at("replay_actions").get<int>();
                const auto c=tail.at("classification").get<std::string>();
                row["replay"]["continuation"]={{"classification",c},{"nodes",tail.at("nodes")},
                    {"restarts_left",restarts-1}};
                if(c=="CERTIFIED_KILL" || c=="CERTIFIED_TURN_CAP") {
                    row["replay"]["reason"]=c=="CERTIFIED_KILL"?"VICTORY":"INVINCIBLE_CAP";
                    row["replay"]["continued"]=true;
                }
            }
            if(row["replay"]["reason"]=="VICTORY") {
                row["classification"]="CERTIFIED_KILL";
                row["terminal"]="VICTORY";
                row["repetitions_to_terminal"]=row["replay"]["repetitions"];
            } else if(row["replay"]["reason"]=="INVINCIBLE_CAP") {
                // Natural mode only: the loop exhausts this turn's damage cap (the Heart's Invincible).
                row["classification"]="CERTIFIED_TURN_CAP";
                row["terminal"]="INVINCIBLE_CAP";
                row["repetitions_to_terminal"]=row["replay"]["repetitions"];
            } else ++rejections;
        }
        auto rank=[](const json &r) {
            auto c=r.at("classification").get<std::string>();
            return c=="CERTIFIED_KILL"?4:c=="CERTIFIED_TURN_CAP"?3:c=="PRODUCTIVE_CYCLE_CANDIDATE"?2:c=="STALL_LOOP"?1:0;
        };
        if(rank(row)>rank(best)) best=row;
        candidates.push_back(row);
        if(rank(best)==4 || candidates.size()>=candidateCap || replayActions>=totalReplayCap) stopped=true;
    }

    void visit(std::unique_ptr<BattleContext> b) {
        if(stopped || nodes>=nodeLimit) return;
        ++nodes;
        const int depth=steps.size(); maxDepth=std::max(maxDepth,depth);
        if(b->outcome==Outcome::PLAYER_VICTORY && !b->smokeBombUsed && b->player.curHp>0
                && (path.empty() || b->turn==path.front()->turn)
                && (directVictoryDepth<0 || depth<directVictoryDepth))
            directVictoryDepth=depth;   // an ordinary same-turn lethal found by the DFS itself (no cycle)
        if(!isQuiet(*b) || (!path.empty() && b->turn!=path.front()->turn)) return;
        auto control=std::make_unique<BattleContext>(key(*b));
        auto hash=hashBattleState(*control);
        for(int i=static_cast<int>(controls.size())-1;i>=0;--i)
            if(hash==hashes[i] && sameKey(*control,*controls[i])) {
                candidate(i,*b); return; // never expand a repeated state
            }
        if(depth>=depthLimit) return;
        if(natural) {
            // Exact (v0 key) state already expanded off this path: same subtree. Keyed by a 64-bit
            // hash of its full binary snapshot, so a collision can lose recall but never certifies.
            const auto bytes=serializeBattleContext(controlState(*b));
            const auto exact=std::hash<std::string_view>{}(std::string_view(
                reinterpret_cast<const char*>(bytes.data()),bytes.size()));
            if(!expanded.insert(exact).second) return;
        }
        auto legal=this->legal(*b);
        path.push_back(std::move(b)); controls.push_back(std::move(control)); hashes.push_back(hash);
        for(const auto &a:legal) {
            if(stopped || nodes>=nodeLimit) break;
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
        if(isQuiet(root)) visit(std::make_unique<BattleContext>(root));
        best["supported"]=isQuiet(root);
        best["prismatic_shard_absence_proven"]=noPrismaticShard;
        best["reason"]=isQuiet(root)?"bounded_search":"requires_audited_ironclad_concrete_quiet_player_root";
        best["nodes"]=nodes; best["max_depth"]=maxDepth; best["dfs_victory_depth"]=directVictoryDepth;
        best["node_cap_hit"]=nodes>=nodeLimit; best["depth_cap_hit"]=maxDepth>=depthLimit; best["repeated_control_states"]=repeats;
        best["replay_actions"]=replayActions; best["replay_rejections"]=rejections;
        best["cpu_ms"]=1000.0*(std::clock()-begin)/CLOCKS_PER_SEC;
        best["candidates"]=candidates;
        best["mode"]=natural?"natural":"v0";
        best["caps"]={{"depth",depthLimit},{"cycle_length",depthLimit},{"nodes",nodeLimit},
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
        {"CERTIFIED_KILL",0},{"CERTIFIED_TURN_CAP",0},{"productive_candidates",0},{"replay_rejections",0},
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
    for(int field=0;field<8;++field) {
        auto changed=positive;
        switch(field) {
            case 0: ++changed.player.energy; break;
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
    // Natural-root mode (#1054): the same Dropkick loop with an unrelated relic and an
    // exhausted card is outside v0's shuffle quotient (RNG stays exact there).
    auto checkNatural=[&](const std::string &name,const BattleContext &b,const std::string &expected) {
        const BattleContext before=b;
        Oracle o; o.natural=true; o.restarts=4;
        auto row=o.run(b,true); row["fixture"]=name;
        std::cout<<row.dump()<<'\n'; rows.push_back(row);
        require(row.at("classification")==expected,name+": unexpected classification");
        require(b==before,name+": root mutated");
        return row;
    };
    auto natural=positive;
    natural.player.setHasRelic<RelicId::ANCHOR>(true);
    CardInstance gone(CardId::STRIKE_RED); gone.uniqueId=2; natural.cards.nextUniqueCardId=3;
    natural.cards.moveToExhaustPile(gone);
    check("natural_dropkick_v0",natural,"NONE");
    auto nk=checkNatural("natural_dropkick",natural,"CERTIFIED_KILL");
    require(nk.at("replay").at("reason")=="VICTORY","natural kill must be a replayed victory");
    // Two monsters: the first target's death breaks the period; a fresh search continues on the second.
    auto two=natural; two.monsters.arr[0].curHp=60; two.monsters.arr[0].maxHp=60;
    two.monsters.arr[1]=two.monsters.arr[0]; two.monsters.arr[1].idx=1;
    two.monsters.monsterCount=2; two.monsters.monstersAlive=2;
    auto both=checkNatural("natural_two_cultists",two,"CERTIFIED_KILL");
    require(both.at("replay").value("continued",false),"second monster must come from a continuation");
    // Kunai (+1 Dexterity per 3 attacks) and Pen Nib (every 10th attack doubled): period 30 in v0's key.
    auto periodic=natural; periodic.player.setHasRelic<RelicId::KUNAI>(true);
    periodic.player.setHasRelic<RelicId::PEN_NIB>(true); periodic.player.penNibCounter=3;
    check("natural_kunai_pen_nib_v0",periodic,"NONE");
    checkNatural("natural_kunai_pen_nib",periodic,"CERTIFIED_KILL");
    auto naturalBroken=natural; naturalBroken.monsters.arr[0].removeStatus<MS::VULNERABLE>();
    checkNatural("natural_dropkick_no_vulnerable",naturalBroken,"NONE");
    // A Heart-like per-turn damage cap: the loop reaches it, no same-turn kill.
    auto capped4=natural; capped4.monsters.arr[0].buff<MS::INVINCIBLE>(200);
    capped4.monsters.arr[0].curHp=800; capped4.monsters.arr[0].maxHp=800;
    auto turnCap=checkNatural("natural_invincible_cap",capped4,"CERTIFIED_TURN_CAP");
    require(turnCap.at("replay").at("reason")=="INVINCIBLE_CAP","cap must be reached in replay");
    // Beat of Death drains 1 HP per card: with 8 HP the loop recurs but dies before the kill.
    auto beat=natural; beat.monsters.arr[0].buff<MS::BEAT_OF_DEATH>(1); beat.player.curHp=8; beat.player.maxHp=80;
    auto death=checkNatural("natural_beat_of_death_low_hp",beat,"PRODUCTIVE_CYCLE_CANDIDATE");
    require(death.at("replay").at("reason")=="player_death","death must reject the candidate");
    auto beatOk=beat; beatOk.player.curHp=80;
    checkNatural("natural_beat_of_death",beatOk,"CERTIFIED_KILL");
    std::cout<<json({{"summary",summary(rows)},{"fixture_assertions","PASS"}}).dump()<<'\n';
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

std::vector<std::uint8_t> unhex(const std::string &h) {
    if(h.size()%2) throw std::runtime_error("odd hex snapshot");
    std::vector<std::uint8_t> out(h.size()/2);
    auto nib=[](char c)->int { return c<='9'?c-'0':c-'a'+10; };
    for(std::size_t i=0;i<out.size();++i) out[i]=std::uint8_t(nib(h[2*i])<<4 | nib(h[2*i+1]));
    return out;
}

// Recall check on real contexts ("plant"): the real turn-start state with its relics, powers,
// monsters and exhaust pile, but the card zones replaced by the 1-energy Dropkick loop of the
// fixtures (two Dropkicks in hand, empty draw and discard, every living monster Vulnerable 3).
// What the natural key misses here it would also miss in a real thinned deck of that run.
BattleContext plant(BattleContext b) {
    b.cards.cardsInHand=0;
    b.cards.drawPile.clear(); b.cards.discardPile.clear();
    b.cards.handNormalityCount=0; b.cards.handPainCount=0; b.cards.handBloodCardCount=0;
    b.cards.drawPileBloodCardCount=0; b.cards.discardPileBloodCardCount=0;
    for(int i=0;i<2;++i) { CardInstance c(CardId::DROPKICK); c.uniqueId=b.cards.nextUniqueCardId++; b.cards.moveToHand(c); }
    b.player.energy=std::max(1,b.player.energy);
    for(int i=0;i<b.monsters.monsterCount;++i) {
        auto &m=b.monsters.arr[i];
        if(m.isDeadOrEscaped()) continue;
        m.setHasStatus<MS::VULNERABLE>(true); m.setStatus<MS::VULNERABLE>(3);
    }
    return b;
}

// #1054 Stage 0: turn-start snapshots of real whole-run fights (one_combat
// STS_COMBAT_STATE_CAPTURE rows of kind "turn"; "-" reads stdin). One output row
// per snapshot, without the candidate list; the run's own Prismatic Shard flag
// is the provenance (the capture reads it from the run's RelicContainer).
void snapshots(const char *file,const std::string &mode,int nodeLimit,int depthLimit) {
    std::ifstream f; std::istream *in=&std::cin;
    if(std::string(file)!="-") { f.open(file); if(!f) throw std::runtime_error("cannot open snapshots"); in=&f; }
    std::vector<json> rows; std::string line;
    while(std::getline(*in,line)) {
        if(line.empty()) continue;
        auto source=json::parse(line);
        if(source.value("kind","")!="turn") continue;
        json row;
        if(!source.contains("state")) {
            row={{"classification","NONE"},{"supported",false},{"reason","no_concrete_snapshot"},{"nodes",0},
                 {"max_depth",0},{"cpu_ms",0.0},{"repeated_control_states",0},{"replay_rejections",0},{"candidates",json::array()}};
        } else {
            const auto bytes=unhex(source.at("state").get<std::string>());
            const auto real=deserializeBattleContext(bytes.data(),bytes.size());
            const auto b=mode=="plant"?plant(real):real;
            Oracle o; o.natural=mode!="v0"; o.nodeLimit=nodeLimit; o.depthLimit=depthLimit;
            o.restarts=o.natural?4:0;
            const bool noShard=source.at("prismatic_shard").is_boolean() && !source.at("prismatic_shard").get<bool>();
            const BattleContext before=b;
            row=o.run(b,noShard);
            require(b==before,"snapshot root mutated");
        }
        if(source.contains("state") && source.value("turn",-1)==0) {
            // Fight start: the combat deck and enabler relics, for the analysis's cheap proxies.
            const auto bytes=unhex(source.at("state").get<std::string>());
            const auto b=deserializeBattleContext(bytes.data(),bytes.size());
            json cards=json::object();
            eachCard(b,[&](const CardInstance &c) {
                if(c.id==CardId::INVALID) return;
                const std::string n=std::string(cardEnumStrings[static_cast<int>(c.id)])+(c.upgraded?"+":"");
                cards[n]=cards.value(n,0)+1;
            });
            json relics=json::array();
#define ORACLE_RELIC(R) if(b.player.hasRelic<RelicId::R>()) relics.push_back(#R);
            ORACLE_RELIC(DEAD_BRANCH) ORACLE_RELIC(UNCEASING_TOP) ORACLE_RELIC(SUNDIAL) ORACLE_RELIC(CHARONS_ASHES)
            ORACLE_RELIC(SNECKO_EYE) ORACLE_RELIC(RUNIC_PYRAMID) ORACLE_RELIC(ICE_CREAM) ORACLE_RELIC(ART_OF_WAR)
            ORACLE_RELIC(CHAMPION_BELT) ORACLE_RELIC(BIRD_FACED_URN) ORACLE_RELIC(MUMMIFIED_HAND) ORACLE_RELIC(NECRONOMICON)
#undef ORACLE_RELIC
            row["fight_start_cards"]=cards; row["enabler_relics"]=relics;
        }
        for(const char *k:{"seed","fight","act","floor","room","encounter","turn","hp","deck_size"})
            if(source.contains(k)) row[k]=source[k];
        json slim=row; slim.erase("candidates");
        slim["candidate_count"]=row["candidates"].size();
        std::cout<<slim.dump()<<'\n';
        rows.push_back(row);
    }
    std::cout<<json({{"summary",summary(rows)},{"mode",mode},{"node_cap",nodeLimit},{"depth_cap",depthLimit}}).dump()<<'\n';
}

int main(int argc,char **argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--fixtures") fixtures();
        else if(argc==3 && std::string(argv[1])=="--roots") roots(argv[2]);
        else if(argc>=3 && argc<=6 && std::string(argv[1])=="--snapshots") {
            const std::string mode=argc>=4?argv[3]:"natural";
            if(mode!="natural" && mode!="v0" && mode!="plant") throw std::runtime_error("mode must be natural, v0 or plant");
            snapshots(argv[2],mode,argc>=5?std::stoi(argv[4]):nodeCap,argc>=6?std::stoi(argv[5]):depthCap);
        }
        else { std::cerr<<"usage: combat_infinity_oracle --fixtures | --roots ROOTS.jsonl"
                          " | --snapshots FILE|- [natural|v0|plant [NODE_CAP [DEPTH_CAP]]]\n"; return 2; }
        return 0;
    } catch(const std::exception &e) { std::cerr<<"combat_infinity_oracle FAIL: "<<e.what()<<'\n'; return 1; }
}
