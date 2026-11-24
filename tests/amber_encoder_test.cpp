// Native Amber-token combat encoder (sim/search/AmberEncoder.h; stage 0, 2026-11-16), on the wire states of
// tests/data/combat_net_wire_sample.jsonl:
//   - every state field the wire encoder reads (CombatTokNet's combatTokEncodeWire) reaches the encoding: one
//     mutator per field changes the state, and the encoding must change (each mutator in at least one state);
//   - determinism: two encodings of one state, into differently pre-filled outputs, have identical live slots;
//   - capacity: tokens past a segment's capacity and actions past kAmberMaxActions are counted in `cut`;
//   - every action's src / tgt names a live token, and play-card / potion actions name their card / potion
//     (and target monster when they need one);
//   - consequence features (amberAppendConsequences) touch only their own slots, match the engine and are inert
//     for the knowledge observer;
//   - amberHalf rounds as numpy's float32 -> float16 cast (CombatTokNet's combatTokRoundHalf).
// With --bench it also reports thread-CPU microseconds per position (no assertion) on states of a random walk
// from the sample states (std::mt19937_64(0) picks actions; no game seed is drawn), next to combatTokEncodeRoot.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <fstream>
#include <functional>
#include <iostream>
#include <random>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/Actions.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatTokNet.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

using namespace sts;
using namespace sts::search;

namespace {

    int failures = 0;
    void require(bool ok, const std::string &msg) {
        if (!ok && failures++ < 40) std::cerr << "FAIL: " << msg << '\n';
    }

    struct Root {
        BattleContext state;
        SilverSearchContext context;
    };

    bool sameLive(const AmberTokens &a, const AmberTokens &b) {
        if (a.n != b.n || a.nAct != b.nAct || a.cut != b.cut) return false;
        for (int s = 0; s < kAmberTokenTypes; ++s)
            for (int i = 0; i < a.n[s]; ++i) {
                const auto &x = a.tok[kAmberOff[s] + i], &y = b.tok[kAmberOff[s] + i];
                if (x.ids != y.ids || x.f != y.f) return false;
            }
        for (int i = 0; i < a.nAct; ++i) {
            const auto &x = a.act[i], &y = b.act[i];
            if (x.type != y.type || x.srcSeg != y.srcSeg || x.tgtSeg != y.tgtSeg || x.srcIdx != y.srcIdx
                || x.tgtIdx != y.tgtIdx || x.f != y.f)
                return false;
        }
        return true;
    }

    double cpuSeconds() {
        timespec ts{};
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
        return static_cast<double>(ts.tv_sec) + 1e-9 * static_cast<double>(ts.tv_nsec);
    }

    // A state field mutation: returns false when it does not apply to this state.
    struct Mut {
        std::string name;
        std::function<bool(BattleContext &, SilverSearchContext &)> f;
    };

    CardInstance someCard(CardId id = CardId::BASH) {
        CardInstance c(id);
        c.uniqueId = 77;
        return c;
    }

    bool anyMonster(const BattleContext &s, int &i) {
        for (i = 0; i < 5; ++i)
            if (s.monsters.arr[i].id != MonsterId::INVALID) return true;
        return false;
    }

    std::vector<Mut> mutators() {
        std::vector<Mut> m;
        auto add = [&](const std::string &n, std::function<bool(BattleContext &, SilverSearchContext &)> f) {
            m.push_back({n, std::move(f)});
        };
#define G(name, expr) add(name, [](BattleContext &s, SilverSearchContext &c) { (void)c; expr; return true; })
        // global block (wire_encoder global scalars)
        G("act", c.act += 1);
        G("ascension", s.ascension -= 1);
        G("cardsDrawn", s.cardsDrawn += 1);
        G("encounter", s.encounter = static_cast<MonsterEncounter>(static_cast<int>(s.encounter) + 1));
        G("endTurnQueued", s.endTurnQueued = !s.endTurnQueued);
        G("energyWasted", s.energyWasted += 1);
        G("extraRollMoveOnTurn", int i = 0; anyMonster(s, i); s.monsters.extraRollMoveOnTurn.flip(i));
        G("floorNum", s.floorNum += 1);
        G("inputState", s.inputState = s.inputState == InputState::PLAYER_NORMAL ? InputState::EXECUTING_ACTIONS
                                                                                 : InputState::PLAYER_NORMAL);
        G("intentsHidden", s.intentsHidden = !s.intentsHidden);
        G("loopCount", s.loopCount += 1);
        G("miscBits0", s.miscBits.flip(0));
        G("miscBits5", s.miscBits.flip(5));
        G("monsterCount", s.monsters.monsterCount += 1);
        G("monsterTurnIdx", s.monsterTurnIdx -= 1);
        G("monstersAlive", s.monsters.monstersAlive += 1);
        G("omamori", c.omamoriCharged = !c.omamoriCharged);
        G("outcome", s.outcome = Outcome::PLAYER_LOSS);
        G("potionCapacity", s.potionCapacity += 1);
        G("potionCount", s.potionCount += 1);
        G("skipMonsterTurn", s.skipMonsterTurn = !s.skipMonsterTurn);
        G("skipMonsterTurnBits", int i = 0; anyMonster(s, i); s.monsters.skipTurn.flip(i));
        G("strikeCount", s.cards.strikeCount += 1);
        G("turn", s.turn += 1);
        G("turnHasEnded", s.turnHasEnded = !s.turnHasEnded);
        G("discardPileBloodCardCount", s.cards.discardPileBloodCardCount += 1);
        G("drawPileBloodCardCount", s.cards.drawPileBloodCardCount += 1);
        G("handBloodCardCount", s.cards.handBloodCardCount += 1);
        G("handNormalityCount", s.cards.handNormalityCount += 1);
        G("handPainCount", s.cards.handPainCount += 1);
        G("fullDrawOrderObserved", auto v = std::vector<CardInstance>(s.cards.drawPile.begin(), s.cards.drawPile.end());
          if (s.cards.drawPile.isConcrete()) s.cards.drawPile.assignInformationState({}, v, {});
          else s.cards.drawPile.assignConcrete(v));
        G("context actBossRoom", c.actBossRoom = !c.actBossRoom);
        // card select
        G("cardSelect.cards", s.cardSelectInfo.cards[0] = CardId::ANGER);
        G("cardSelect.canPickAnyNumber", s.cardSelectInfo.canPickAnyNumber = !s.cardSelectInfo.canPickAnyNumber);
        G("cardSelect.canPickZero", s.cardSelectInfo.canPickZero = !s.cardSelectInfo.canPickZero);
        G("cardSelect.damageAllBeforeBlocks", s.cardSelectInfo.damageAllBeforeBlocks += 1);
        G("cardSelect.data0", s.cardSelectInfo.data0 += 1);
        G("cardSelect.drawAfter", s.cardSelectInfo.drawAfter += 1);
        G("cardSelect.drawsAfter", s.cardSelectInfo.drawsAfter.push_back(2));
        G("cardSelect.blocksAfter", s.cardSelectInfo.blocksAfter.push_back(3));
        G("cardSelect.pickCount", s.cardSelectInfo.pickCount += 1);
        G("cardSelect.setCostToZero", s.cardSelectInfo.setCostToZero = !s.cardSelectInfo.setCostToZero);
        G("cardSelect.task", s.cardSelectInfo.cardSelectTask = CardSelectTask::SEEK);
        // current card-queue item (all fields, with and without a card)
        G("cq.card", s.curCardQueueItem.card = someCard());
        G("cq.target", s.curCardQueueItem.target += 1);
        G("cq.isEndTurn", s.curCardQueueItem.isEndTurn = !s.curCardQueueItem.isEndTurn);
        G("cq.triggerOnUse", s.curCardQueueItem.triggerOnUse = !s.curCardQueueItem.triggerOnUse);
        G("cq.ignoreEnergyTotal", s.curCardQueueItem.ignoreEnergyTotal = !s.curCardQueueItem.ignoreEnergyTotal);
        G("cq.energyOnUse", s.curCardQueueItem.energyOnUse += 1);
        G("cq.freeToPlay", s.curCardQueueItem.freeToPlay = !s.curCardQueueItem.freeToPlay);
        G("cq.randomTarget", s.curCardQueueItem.randomTarget = !s.curCardQueueItem.randomTarget);
        G("cq.autoplay", s.curCardQueueItem.autoplay = !s.curCardQueueItem.autoplay);
        G("cq.regretCardCount(card)", s.curCardQueueItem.card = someCard(); s.curCardQueueItem.regretCardCount += 1);
        G("cq.purgeOnUse(card)", s.curCardQueueItem.card = someCard(); s.curCardQueueItem.purgeOnUse = !s.curCardQueueItem.purgeOnUse);
        G("cq.exhaustOnUse(card)", s.curCardQueueItem.card = someCard(); s.curCardQueueItem.exhaustOnUse = !s.curCardQueueItem.exhaustOnUse);
        // player block
        G("p.artifact", s.player.artifact += 1);
        G("p.attacksPlayedThisTurn", s.player.attacksPlayedThisTurn += 1);
        G("p.block", s.player.block += 1);
        G("p.cardDrawPerTurn", s.player.cardDrawPerTurn += 1);
        G("p.cardsDiscardedThisTurn", s.player.cardsDiscardedThisTurn += 1);
        G("p.cardsPlayedThisTurn", s.player.cardsPlayedThisTurn += 1);
        G("p.characterClass", s.player.cc = CharacterClass::SILENT);
        G("p.combustHpLoss", s.player.combustHpLoss += 1);
        G("p.curHp", s.player.curHp -= 1);
        G("p.devaFormEnergyPerTurn", s.player.devaFormEnergyPerTurn += 1);
        G("p.dexterity", s.player.dexterity += 1);
        G("p.echoFormCardsDoubled", s.player.echoFormCardsDoubled += 1);
        G("p.energy", s.player.energy += 1);
        G("p.energyPerTurn", s.player.energyPerTurn += 1);
        G("p.focus", s.player.focus += 1);
        G("p.gold", s.player.gold += 1);
        G("p.haveUsedNecronomiconThisTurn", s.player.haveUsedNecronomiconThisTurn = !s.player.haveUsedNecronomiconThisTurn);
        G("p.justAppliedBits", s.player.statusBits0 |= 1ULL << 6; s.player.statusMap[PlayerStatus::WEAK] = 1;
          s.player.justAppliedBits ^= 1u << 6);
        G("p.lastAttackUnblockedDamage", s.player.lastAttackUnblockedDamage += 1);
        G("p.lastTargetedMonster", s.player.lastTargetedMonster += 1);
        G("p.maxHp", s.player.maxHp += 1);
        G("p.orangePelletsCardTypesPlayed", s.player.orangePelletsCardTypesPlayed.flip(1));
        G("p.orbSlots", s.player.orbSlots += 1);
        G("p.panacheCounter", s.player.panacheCounter += 1);
        G("p.skillsPlayedThisTurn", s.player.skillsPlayedThisTurn += 1);
        G("p.stance", s.player.stance = Stance::WRATH);
        G("p.strength", s.player.strength -= 1);
        G("p.timesDamagedThisCombat", s.player.timesDamagedThisCombat += 1);
        G("p.bomb1", s.player.bomb1 += 1);
        G("p.bomb2", s.player.bomb2 += 1);
        G("p.bomb3", s.player.bomb3 += 1);
        G("p.happyFlowerCounter", s.player.happyFlowerCounter += 1);
        G("p.incenseBurnerCounter", s.player.incenseBurnerCounter += 1);
        G("p.inkBottleCounter", s.player.inkBottleCounter += 1);
        G("p.inserterCounter", s.player.inserterCounter += 1);
        G("p.nunchakuCounter", s.player.nunchakuCounter += 1);
        G("p.penNibCounter", s.player.penNibCounter += 1);
        G("p.sundialCounter", s.player.sundialCounter += 1);
        G("p.relicBits0", s.player.relicBits0 ^= 1ULL << 5);
        G("p.relicBits1", s.player.relicBits1 ^= 1ULL << 7);
        G("p.statusBits0(flag)", s.player.statusBits0 ^= 1ULL << static_cast<int>(PlayerStatus::BARRICADE));
        G("p.statusBits1(flag)", s.player.statusBits1 ^= 1u << (static_cast<int>(PlayerStatus::RAGE) - 64));
        G("p.statusMap", s.player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::VULNERABLE);
          s.player.statusMap[PlayerStatus::VULNERABLE] += 1);
        // monsters (every scalar the wire encoder reads, small powers, roll inputs, predicates, history)
        auto mon = [&](const std::string &n, std::function<void(Monster &)> f) {
            add("m." + n, [f](BattleContext &s, SilverSearchContext &) {
                int i = 0;
                if (!anyMonster(s, i)) return false;
                f(s.monsters.arr[i]);
                return true;
            });
        };
#define M(name, expr) mon(name, [](Monster &x) { expr; })
        M("id", x.id = MonsterId::CULTIST == x.id ? MonsterId::JAW_WORM : MonsterId::CULTIST);
        M("idx", x.idx += 1);   // not encoded: the slot is (see below); the wire's idx equals the slot
        M("moveHistory0", x.moveHistory[0] = MMID::CULTIST_INCANTATION == x.moveHistory[0] ? MMID::CULTIST_DARK_STRIKE
                                                                                          : MMID::CULTIST_INCANTATION);
        M("moveHistory1", x.moveHistory[1] = MMID::CULTIST_INCANTATION == x.moveHistory[1] ? MMID::CULTIST_DARK_STRIKE
                                                                                          : MMID::CULTIST_INCANTATION);
        M("block", x.block += 1);
        M("curHp", x.curHp -= 1);
        M("escapeNext", x.escapeNext = !x.escapeNext);
        M("halfDead", x.halfDead = !x.halfDead);
        M("isEscapingB", x.isEscapingB = !x.isEscapingB);
        M("maxHp", x.maxHp += 1);
        M("miscInfo", x.miscInfo += 1);
        M("pendingDirectMoveChoice", x.pendingDirectMoveChoice += 1);
        M("pendingMoveRolls", x.pendingMoveRolls += 1);
        M("statusBits(unique)", x.statusBits ^= 1ULL << static_cast<int>(MS::RITUAL));
        M("statusBits(unique2)", x.statusBits ^= 1ULL << static_cast<int>(MS::REACTIVE));
        M("statusBits(bool)", x.statusBits ^= 1ULL << static_cast<int>(MS::MINION));
        M("strength", x.strength += 1);
        M("uniquePower0", x.uniquePower0 += 1);
        M("uniquePower1", x.uniquePower1 += 1);
        M("vulnerable", x.vulnerable += 1);
        M("weak", x.weak += 1);
        M("artifact", x.artifact += 1);
        M("blockReturn", x.blockReturn += 1);
        M("choked", x.choked += 1);
        M("corpseExplosion", x.corpseExplosion += 1);
        M("lockOn", x.lockOn += 1);
        M("mark", x.mark += 1);
        M("metallicize", x.metallicize += 1);
        M("platedArmor", x.platedArmor += 1);
        M("poison", x.poison += 1);
        M("regen", x.regen += 1);
        M("shackled", x.shackled += 1);
        M("roll.aliveCount", x.pendingRollInputs.aliveCount += 1);
        M("roll.asleep", x.pendingRollInputs.asleep = !x.pendingRollInputs.asleep);
        M("roll.curHp", x.pendingRollInputs.curHp += 1);
        M("roll.halfDead", x.pendingRollInputs.halfDead = !x.pendingRollInputs.halfDead);
        M("roll.knightAlive", x.pendingRollInputs.knightAlive = !x.pendingRollInputs.knightAlive);
        M("roll.knightCurHp", x.pendingRollInputs.knightCurHp += 1);
        M("roll.knightMaxHp", x.pendingRollInputs.knightMaxHp += 1);
        M("roll.maxHp", x.pendingRollInputs.maxHp += 1);
        M("roll.miscInfo", x.pendingRollInputs.miscInfo += 1);
        M("roll.monsterTurnNumber", x.pendingRollInputs.monsterTurnNumber += 1);
        M("roll.monstersAlive", x.pendingRollInputs.monstersAlive += 1);
        M("roll.playerConstricted", x.pendingRollInputs.playerConstricted = !x.pendingRollInputs.playerConstricted);
        M("pendingAttackPredicates", x.pendingAttackPredicates.push_back({7, true}));
        M("pendingRollInputHistory", x.pendingRollInputHistory.push_back(x.pendingRollInputs));
        // latentDamageMask is read only under hidden intents (as wireFromSearchState).
        add("m.latentDamageMask(hidden)", [](BattleContext &s, SilverSearchContext &) {
            int i = 0;
            if (!s.intentsHidden || !anyMonster(s, i)) return false;
            s.monsters.arr[i].latentDamageMask ^= 0x10;
            return true;
        });
        // cards in every zone, every card field
        auto hand = [&](const std::string &n, std::function<void(CardInstance &)> f) {
            add("hand." + n, [f](BattleContext &s, SilverSearchContext &) {
                if (s.cards.cardsInHand == 0) return false;
                f(s.cards.hand[0]);
                return true;
            });
        };
#define H(name, expr) hand(name, [](CardInstance &x) { expr; })
        H("id", x.id = x.id == CardId::ANGER ? CardId::CLASH : CardId::ANGER);
        H("upgraded", x.upgraded = !x.upgraded);
        H("cost", x.cost += 1);
        H("costForTurn", x.costForTurn += 1);
        H("freeToPlayOnce", x.freeToPlayOnce = !x.freeToPlayOnce);
        H("retain", x.retain = !x.retain);
        H("specialData", x.specialData += 1);
        add("hand.order", [](BattleContext &s, SilverSearchContext &) {
            auto &h = s.cards.hand;
            for (int i = 1; i < s.cards.cardsInHand; ++i)
                if (!(h[i].id == h[0].id && h[i].upgraded == h[0].upgraded)) {
                    std::swap(h[0], h[i]);
                    return true;
                }
            return false;
        });
        G("hand.add", if (s.cards.cardsInHand >= 10) return false; s.cards.hand[s.cards.cardsInHand++] = someCard());
        G("draw.top", s.cards.drawPile.addToTop(someCard()));
        G("draw.bottom", if (s.cards.drawPile.isConcrete()) return false; s.cards.drawPile.addToBottom(someCard()));
        G("discard.add", s.cards.discardPile.push_back(someCard()));
        G("exhaust.add", s.cards.exhaustPile.push_back(someCard()));
        G("limbo", s.cards.limbo[3] = someCard());
        G("stasis", s.cards.stasisCards[1] = someCard());
        // potions
        G("potions", s.potions[0] = s.potions[0] == Potion::FIRE_POTION ? Potion::BLOCK_POTION : Potion::FIRE_POTION);
        // card-select states: pending card queue and the pending action queue
        G("cardQueue(card select)", s.inputState = InputState::CARD_SELECT;
          s.cardQueue.pushBack(CardQueueItem(someCard(CardId::HAVOC), 0, 1)));
        G("actionQueue(card select)", s.inputState = InputState::CARD_SELECT;
          s.actionQueue.pushBack(Actions::DrawCards(2)));
#undef G
#undef M
#undef H
        return m;
    }

    // Fields the wire carries that the wire encoder does not read, or whose information is elsewhere: their
    // change may leave the encoding unchanged.
    bool exempt(const std::string &n) { return n == "m.idx"; }

    void checkActions(const BattleContext &s, const std::vector<search::Action> &acts, const AmberTokens &t,
                      const std::string &where) {
        for (int i = 0; i < t.nAct; ++i) {
            const auto &a = t.act[i];
            for (const auto [seg, idx] : {std::pair{a.srcSeg, a.srcIdx}, std::pair{a.tgtSeg, a.tgtIdx}}) {
                if (seg == kAmberNoSeg) continue;
                require(seg < kAmberTokenTypes && idx < t.n[seg], where + " action " + std::to_string(i)
                        + " points at a dead token");
            }
            const auto &in = acts[i];
            if (in.getActionType() == ActionType::CARD) {
                const int h = in.getSourceIdx();
                require(a.type == static_cast<int>(AmberActionType::PLAY_CARD) && a.srcSeg == static_cast<int>(AmberTokenType::CARD)
                        && t.at(AmberTokenType::CARD, a.srcIdx).ids[0] == kAmberCardBase - 1 + static_cast<int>(s.cards.hand[h].id),
                        where + " card action src is not its hand card");
                if (s.cards.hand[h].requiresTarget()) {
                    const int m = in.getTargetIdx();
                    require(a.tgtSeg == static_cast<int>(AmberTokenType::MONSTER)
                            && t.at(AmberTokenType::MONSTER, a.tgtIdx).f[8] == amberHalf(m / 4.0f),
                            where + " card action tgt is not its monster");
                }
            } else if (in.getActionType() == ActionType::POTION) {
                require(a.srcSeg == static_cast<int>(AmberTokenType::POTION)
                        && t.at(AmberTokenType::POTION, a.srcIdx).f[0] == amberHalf(in.getSourceIdx() / 5.0f),
                        where + " potion action src is not its slot");
            } else if (in.getActionType() == ActionType::END_TURN) {
                require(a.type == static_cast<int>(AmberActionType::END_TURN), where + " end turn type");
            }
            require(a.type != static_cast<int>(AmberActionType::UNKNOWN), where + " unresolved action");
        }
    }

}

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "usage: amber_encoder_test WIRES.jsonl [--bench]\n";
        return 2;
    }
    const bool bench = argc > 2 && std::string(argv[2]) == "--bench";
    std::vector<Root> roots;
    {
        std::ifstream f(argv[1]);
        std::string line;
        while (std::getline(f, line)) {
            if (line.empty()) continue;
            const auto wire = nlohmann::json::parse(line).at("wire").get<silver_bridge::BattleStateWire>();
            roots.push_back({battleContextFromWire(wire), searchContextFromWire(wire)});
        }
    }
    require(!roots.empty(), "no wire rows");
    SilverSearcher enumerator(roots[0].state, roots[0].context);
    auto enumerate = [&](const BattleContext &s) {
        return s.outcome == Outcome::UNDECIDED ? enumerator.enumerateActions(s) : std::vector<search::Action>{};
    };

    // float16 rounding
    {
        std::mt19937 rng(1);
        std::uniform_real_distribution<float> u(-8.0f, 8.0f);
        for (int i = 0; i < 200000; ++i) {
            const float x = std::ldexp(u(rng), static_cast<int>(rng() % 40) - 26);
            require(amberHalfToFloat(amberHalf(x)) == combatTokRoundHalf(x), "float16 rounding of " + std::to_string(x));
        }
        for (const float x : {0.0f, 1.0f, -1.0f, 65504.0f, 2047.0f, 1.0f / 3.0f, 6.0e-8f})
            require(amberHalfToFloat(amberHalf(x)) == combatTokRoundHalf(x), "float16 rounding of " + std::to_string(x));
        require(amberHalf(1.0f) == 0x3c00, "float16 one");
    }

    static AmberTokens a, b;
    int liveTokens = 0, states = 0;
    for (std::size_t r = 0; r < roots.size(); ++r) {
        const auto &root = roots[r];
        const auto acts = enumerate(root.state);
        const std::string where = "row " + std::to_string(r);
        // determinism, into differently pre-filled outputs
        std::memset(&a, 0x00, sizeof(a));
        std::memset(&b, 0x5a, sizeof(b));
        amberEncodeCombat(root.state, root.context, acts, a);
        amberEncodeCombat(root.state, root.context, acts, b);
        require(sameLive(a, b), where + " not deterministic");
        require(a.n[0] == 1 && a.n[1] == 1, where + " run / player token");
        require(a.nAct == static_cast<int>(acts.size()) && a.cut == 0, where + " actions or cut");
        require(a.n[static_cast<int>(AmberTokenType::CARD)] >= root.state.cards.cardsInHand, where + " hand cards");
        for (int s = 0; s < kAmberTokenTypes; ++s)
            for (int i = 0; i < a.n[s]; ++i)
                for (const auto id : a.tok[kAmberOff[s] + i].ids)
                    require(id >= 0 && id < kAmberIdEnd, where + " id out of range");
        checkActions(root.state, acts, a, where);
        for (int s = 0; s < kAmberTokenTypes; ++s) liveTokens += a.n[s];
        ++states;
    }

    // every mutator changes the encoding in at least one state where it applies
    const auto muts = mutators();
    for (const auto &mu : muts) {
        int applied = 0, changed = 0;
        for (const auto &root : roots) {
            BattleContext s = root.state;
            SilverSearchContext c = root.context;
            if (!mu.f(s, c)) continue;
            ++applied;
            amberEncodeCombat(root.state, root.context, {}, a);
            amberEncodeCombat(s, c, {}, b);
            if (!sameLive(a, b)) ++changed;
        }
        if (exempt(mu.name)) continue;
        require(applied > 0, "mutator " + mu.name + " applies to no sample state");
        require(changed > 0, "mutator " + mu.name + " does not reach the encoding");
    }

    // capacity cut counting: a discard pile larger than the CARD segment, and more actions than kAmberMaxActions
    {
        BattleContext s = roots[0].state;
        const int before = [&] {
            amberEncodeCombat(s, roots[0].context, {}, a);
            return static_cast<int>(a.n[static_cast<int>(AmberTokenType::CARD)]);
        }();
        const int extra = kAmberCap[static_cast<int>(AmberTokenType::CARD)] - before + 17;
        for (int i = 0; i < extra; ++i) s.cards.discardPile.push_back(someCard());
        std::vector<search::Action> many(kAmberMaxActions + 5, search::Action(ActionType::END_TURN));
        amberEncodeCombat(s, roots[0].context, many, a);
        require(a.n[static_cast<int>(AmberTokenType::CARD)] == kAmberCap[static_cast<int>(AmberTokenType::CARD)],
                "card segment not full");
        require(a.nAct == kAmberMaxActions, "actions not capped");
        require(a.cut == 17 + 5, "cut " + std::to_string(a.cut) + " != 22");
    }

    // consequence features (amberAppendConsequences): only their slots change (so with zero weights for them the
    // net computes what it did without them), those slots are 0 without the pass, deterministic, the live
    // knowledge observer sees nothing and the debug pointer is kept; the numbers match the engine.
    int conseqStates = 0, conseqPreviewed = 0, conseqKills = 0, conseqIntents = 0;
    {
        struct Counting : CombatKnowledgeObserver {
            int events = 0;
            void observeCombatKnowledgeEvent(const CombatKnowledgeEvent &) override { ++events; }
        } counting;
        auto newSlot = [](int seg, int j) {
            if (seg == static_cast<int>(AmberTokenType::PLAYER)) return j >= 40 && j <= 54;
            if (seg == static_cast<int>(AmberTokenType::CARD) || seg == static_cast<int>(AmberTokenType::POTION))
                return j >= 42 && j <= 60;
            return false;
        };
        static AmberTokens c;
        // the sample roots and states of a short random walk from them (std::mt19937_64(1); no game seed)
        std::vector<Root> cs(roots.begin(), roots.end());
        {
            std::mt19937_64 rng(1);
            for (int g = 0; cs.size() < roots.size() + 600 && g < 600; ++g) {
                const auto &r0 = roots[g % roots.size()];
                BattleContext s = r0.state;
                for (int step = 0; step < 60 && cs.size() < roots.size() + 600; ++step) {
                    auto acts = enumerate(s);
                    if (acts.empty()) break;
                    if (step) cs.push_back({s, r0.context});
                    acts[std::uniform_int_distribution<std::size_t>(0, acts.size() - 1)(rng)].execute(s);
                }
            }
        }
        for (std::size_t r = 0; r < cs.size(); ++r) {
            const auto &root = cs[r];
            const auto acts = enumerate(root.state);
            const std::string where = "consequences row " + std::to_string(r);
            amberEncodeCombat(root.state, root.context, acts, a);
            std::memcpy(&b, &a, sizeof(a));
            BattleContext *const debugBefore = g_debug_bc;
            g_combatKnowledgeObserver = &counting;
            amberAppendConsequences(root.state, acts, b);
            g_combatKnowledgeObserver = nullptr;
            require(counting.events == 0, where + " reached the knowledge observer");
            require(g_debug_bc == debugBefore, where + " debug pointer not restored");
            std::memset(&c, 0x5a, sizeof(c));
            amberEncodeCombat(root.state, root.context, acts, c);
            amberAppendConsequences(root.state, acts, c);
            require(sameLive(b, c), where + " not deterministic");
            require(a.n == b.n && a.nAct == b.nAct && a.cut == b.cut, where + " token / action counts changed");
            bool previewed = false;
            for (int s = 0; s < kAmberTokenTypes; ++s)
                for (int i = 0; i < a.n[s]; ++i) {
                    const auto &x = a.tok[kAmberOff[s] + i], &y = b.tok[kAmberOff[s] + i];
                    require(x.ids == y.ids, where + " ids changed");
                    for (int j = 0; j < kAmberFloat; ++j) {
                        if (newSlot(s, j)) {
                            require(x.f[j] == 0, where + " consequence slot used by the encoder: seg "
                                    + std::to_string(s) + " slot " + std::to_string(j));
                            if (j == 42 && y.f[j] != 0) previewed = true;
                        } else {
                            require(x.f[j] == y.f[j], where + " base slot changed: seg " + std::to_string(s)
                                    + " slot " + std::to_string(j));
                        }
                    }
                }
            for (int i = 0; i < a.nAct; ++i) {
                const auto &x = a.act[i], &y = b.act[i];
                require(x.f[3] == 0, where + " action f[3] used by the encoder");
                require(x.type == y.type && x.srcSeg == y.srcSeg && x.tgtSeg == y.tgtSeg && x.srcIdx == y.srcIdx
                        && x.tgtIdx == y.tgtIdx, where + " action changed");
                for (int j = 0; j < kAmberActFeat; ++j)
                    if (j != 3) require(x.f[j] == y.f[j], where + " action feature changed");
            }
            const BattleContext &st = root.state;
            const AmberToken &pl = b.at(AmberTokenType::PLAYER, 0);
            require(pl.f[54] == 0x3c00, where + " PLAYER 54");
            for (int k = 0; k < 5 && !st.intentsHidden; ++k) {
                const Monster &m = st.monsters.arr[k];
                if (m.id == MonsterId::INVALID || m.isDeadOrEscaped() || !m.isAttacking()) continue;
                const int hits = std::max(1, m.getMoveBaseDamage(st).attackCount);
                const float want = static_cast<float>(m.publicIncomingDamage(st)) / static_cast<float>(hits) / 10.0f;
                require(pl.f[40 + k] == amberHalf(want), where + " intent damage slot " + std::to_string(k));
                ++conseqIntents;
            }
            // every play's lethal flag and the card's per-target kill / damage = the engine's play on a copy
            const bool normal = st.inputState == InputState::PLAYER_NORMAL && st.outcome == Outcome::UNDECIDED;
            for (int i = 0; i < b.nAct && normal; ++i) {
                const auto &enc = b.act[i];
                if (enc.type != static_cast<std::uint8_t>(AmberActionType::PLAY_CARD)
                    || enc.srcSeg != static_cast<std::uint8_t>(AmberTokenType::CARD))
                    continue;
                BattleContext cp = st;
                acts[i].execute(cp);
                bool kill = false;
                for (int k = 0; k < 5; ++k) {
                    const Monster &m0 = st.monsters.arr[k], &m1 = cp.monsters.arr[k];
                    if (m0.id == MonsterId::INVALID || m0.isDeadOrEscaped()) continue;
                    kill |= (m1.isDying() || m1.isHalfDead()) && !m1.isEscaping();
                }
                require(enc.f[3] == (kill ? 0x3c00 : 0), where + " lethal flag of action " + std::to_string(i));
                conseqKills += kill;
                const AmberToken &ct = b.at(AmberTokenType::CARD, enc.srcIdx);
                require(ct.f[42] == 0x3c00, where + " played card not previewed");
                if (enc.tgtSeg == static_cast<std::uint8_t>(AmberTokenType::MONSTER)) {
                    const int k = acts[i].getTargetIdx();
                    const Monster &m0 = st.monsters.arr[k], &m1 = cp.monsters.arr[k];
                    const int dmg = std::max(0, (m0.curHp + m0.block) - (std::max(0, m1.curHp) + m1.block));
                    require(ct.f[43 + k] == amberHalf(dmg / 10.0f), where + " damage to the target");
                }
                require(ct.f[53] == amberHalf((cp.player.block - st.player.block) / 10.0f), where + " block");
            }
            if (previewed) ++conseqPreviewed;
            ++conseqStates;
        }
        require(conseqPreviewed > 0, "no sample state got a card / potion preview");
        require(conseqIntents > 0, "no sample state has an attack intent");
        // a 1-HP monster: some legal attack on it is lethal
        bool lethalSeen = false;
        for (const auto &root : roots) {
            BattleContext s = root.state;
            if (s.inputState != InputState::PLAYER_NORMAL || s.outcome != Outcome::UNDECIDED) continue;
            int k = 0;
            for (; k < 5; ++k) if (s.monsters.arr[k].id != MonsterId::INVALID && !s.monsters.arr[k].isDeadOrEscaped()) break;
            if (k == 5) continue;
            s.monsters.arr[k].curHp = 1;
            s.monsters.arr[k].block = 0;
            const auto acts = enumerate(s);
            amberEncodeCombat(s, root.context, acts, a);
            amberAppendConsequences(s, acts, a);
            for (int i = 0; i < a.nAct; ++i)
                if (a.act[i].f[3] == 0x3c00) lethalSeen = true;
            if (lethalSeen) break;
        }
        require(lethalSeen, "no lethal play found against a 1-HP monster");
    }

    nlohmann::json report = {{"states", states}, {"mutators", muts.size()},
                             {"consequence_states", conseqStates}, {"consequence_previewed", conseqPreviewed},
                             {"consequence_lethal_plays", conseqKills}, {"consequence_intents", conseqIntents},
                             {"live_tokens_per_state", states ? static_cast<double>(liveTokens) / states : 0.0}};

    if (bench) {
        // states of a random walk from the sample roots (as az-bench-producer's games)
        std::mt19937_64 rng(0);
        struct Pos { BattleContext state; int root; std::vector<search::Action> acts; };
        std::vector<Pos> walk;
        for (int g = 0; walk.size() < 4000 && g < 4000; ++g) {
            const int r = g % static_cast<int>(roots.size());
            BattleContext s = roots[r].state;
            for (int step = 0; step < 200 && walk.size() < 4000; ++step) {
                auto acts = enumerate(s);
                if (acts.empty()) break;
                walk.push_back({s, r, acts});
                acts[std::uniform_int_distribution<std::size_t>(0, acts.size() - 1)(rng)].execute(s);
            }
        }
        std::uint64_t sink = 0;
        long tokens = 0;
        const int reps = 20;
        const double t0 = cpuSeconds();
        for (int k = 0; k < reps; ++k)
            for (const auto &p : walk) {
                amberEncodeCombat(p.state, roots[p.root].context, p.acts, a);
                sink += a.tok[0].f[3] + a.nAct;
                if (k == 0) for (int s = 0; s < kAmberTokenTypes; ++s) tokens += a.n[s];
            }
        const double t1 = cpuSeconds();
        for (const auto &p : walk) {
            amberEncodeCombat(p.state, roots[p.root].context, p.acts, a);
            amberAppendConsequences(p.state, p.acts, a);
            sink += a.tok[1].f[52];
        }
        const double tc = cpuSeconds();
        CombatTokInputs in;
        std::vector<SilverSearcher::Edge> edges;
        int errs = 0;
        for (const auto &p : walk) {
            edges.assign(p.acts.size(), {});
            for (std::size_t k = 0; k < p.acts.size(); ++k) edges[k].action = p.acts[k];
            try {
                combatTokEncodeRoot(p.state, roots[p.root].context, edges, in);
            } catch (const std::exception &) {
                ++errs;
            }
            sink += in.cards.size();
        }
        const double t2 = cpuSeconds();
        const double n = static_cast<double>(walk.size());
        report["bench"] = {{"positions", walk.size()}, {"reps", reps},
                           {"amber_us_per_position", 1e6 * (t1 - t0) / (n * reps)},
                           {"amber_consequences_us_per_position", 1e6 * (tc - t1) / n},
                           {"wire_json_us_per_position", 1e6 * (t2 - tc) / n},
                           {"wire_json_errors", errs},
                           {"walk_live_tokens_per_state", static_cast<double>(tokens) / n},
                           {"sink", sink & 1}};
    }
    std::cout << report.dump() << std::endl;
    if (failures) {
        std::cerr << failures << " failure(s)\n";
        return 1;
    }
    return 0;
}
