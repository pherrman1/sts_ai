// Action-enumeration audit (2026-11-19): compares, at every decision of random-legal Ironclad runs, the actions the
// engine accepts (GameAction::isValidAction / search::Action::isValidAction over the whole encodable action space)
// with the actions the self-play driver offers the net:
//   out of combat: GameAction::getAllActionsInState(gc)        (az_run_driver oocActions)
//   in combat:     SilverSearcher::enumerateActions(bc)         (az_run_driver combatActions)
// Each difference is reported by category with an example (seed, floor). Equivalent duplicates that the combat
// enumerator collapses on purpose (identical hand cards / potions, canonical multi-select masks) count as covered.
// Also reported: enumerated actions the engine rejects, duplicate enumerations, and undecided states with no action.
//
// Report-only (exit 0). The reference is the engine's own isValidAction: options the engine itself lacks are not
// found. It checks the raw getAllActionsInState list; the driver's additions (az_run_driver.cpp oocActions: Singing
// Bowl, potion discards) are covered by their own unit tests.
// Usage: action_enumeration_audit_test [runs=200] [--combat] [--asc A] [--seed-base S]
// No gameplay evaluation: fixed test seeds, outcomes unused.
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/GameAction.h"
#include "sim/search/SilverSearcher.h"

using namespace sts;
using search::GameAction;
using RT = GameAction::RewardsActionType;

namespace {

    struct Finding {
        long count = 0;
        std::string example;
    };
    std::map<std::string, Finding> findings;
    std::map<std::string, long> coverage;

    void note(const std::string &cat, const std::string &where) {
        auto &f = findings[cat];
        if (f.count++ == 0) f.example = where;
    }

    const char *screenName(ScreenState s) {
        switch (s) {
            case ScreenState::EVENT_SCREEN: return "EVENT";
            case ScreenState::REWARDS: return "REWARDS";
            case ScreenState::BOSS_RELIC_REWARDS: return "BOSS_RELIC";
            case ScreenState::CARD_SELECT: return "CARD_SELECT";
            case ScreenState::MAP_SCREEN: return "MAP";
            case ScreenState::TREASURE_ROOM: return "TREASURE";
            case ScreenState::REST_ROOM: return "REST";
            case ScreenState::SHOP_ROOM: return "SHOP";
            case ScreenState::BATTLE: return "BATTLE";
            default: return "INVALID";
        }
    }
    const char *rtName(RT t) {
        switch (t) {
            case RT::CARD: return "CARD";
            case RT::GOLD: return "GOLD";
            case RT::KEY: return "KEY";
            case RT::POTION: return "POTION";
            case RT::RELIC: return "RELIC";
            case RT::CARD_REMOVE: return "CARD_REMOVE";
            case RT::SKIP: return "SKIP";
        }
        return "?";
    }

    std::string where(const GameContext &gc) {
        std::ostringstream o;
        o << "seed " << gc.seed << " floor " << gc.floorNum << " act " << gc.act;
        return o.str();
    }

    // Canonical form: the fields the engine reads for this screen; the rest zeroed (GameAction's idx2 only matters
    // for reward cards, KEY ignores idx1, non-reward screens read idx1 only).
    std::uint32_t canon(const GameContext &gc, GameAction a) {
        if (a.isPotionAction()) return a.bits & 0xC00000FFu;
        if (gc.screenState == ScreenState::REWARDS || gc.screenState == ScreenState::SHOP_ROOM) {
            const RT t = a.getRewardsActionType();
            int i1 = a.getIdx1(), i2 = a.getIdx2();
            if (t != RT::CARD || gc.screenState == ScreenState::SHOP_ROOM) i2 = 0;
            if (t == RT::KEY || t == RT::SKIP || t == RT::CARD_REMOVE) i1 = 0;
            if (gc.screenState == ScreenState::REWARDS && t == RT::GOLD) i1 = 0;   // the enumerator emits GOLD idx 0
            return GameAction(t, i1, i2).bits;
        }
        return GameAction(a.getIdx1()).bits;
    }

    std::string kindOf(const GameContext &gc, GameAction a) {
        std::string s = screenName(gc.screenState);
        if (a.isPotionAction()) {
            const auto p = gc.potions[a.getIdx1()];
            if (a.isPotionDiscard()) return s + " potion-discard";
            return s + " potion-drink(" + std::to_string(static_cast<int>(p)) + ")";
        }
        if (gc.screenState == ScreenState::REWARDS || gc.screenState == ScreenState::SHOP_ROOM) {
            s += std::string(" ") + rtName(a.getRewardsActionType());
            if (a.getRewardsActionType() == RT::CARD && a.getIdx2() == 5 && gc.screenState == ScreenState::REWARDS)
                s += gc.hasRelic(RelicId::SINGING_BOWL) ? "(Singing Bowl +2 max HP)" : "(skip this card reward, no Bowl)";
            return s;
        }
        if (gc.screenState == ScreenState::EVENT_SCREEN) s += "/event" + std::to_string(static_cast<int>(gc.curEvent));
        if (gc.screenState == ScreenState::REST_ROOM) return s + " option" + std::to_string(a.getIdx1());
        if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS)
            return s + (a.getIdx1() < 3 && gc.info.bossRelics[a.getIdx1()] == RelicId::INVALID ? " empty-slot" : " idx")
                   + std::to_string(a.getIdx1());
        return s + " idx" + std::to_string(a.getIdx1());
    }

    // Whole encodable out-of-combat action space.
    std::vector<GameAction> oocSpace(const GameContext &gc) {
        std::vector<GameAction> v;
        for (int slot = 0; slot < 5; ++slot) {
            v.emplace_back(0x80000000u | static_cast<unsigned>(slot));
            v.emplace_back(0xC0000000u | static_cast<unsigned>(slot));
        }
        if (gc.screenState == ScreenState::REWARDS || gc.screenState == ScreenState::SHOP_ROOM) {
            for (int t = 0; t <= 6; ++t)
                for (int i1 = 0; i1 < 8; ++i1)
                    for (int i2 = 0; i2 < 8; ++i2) v.emplace_back(static_cast<RT>(t), i1, i2);
        } else {
            for (int i1 = 0; i1 < 40; ++i1) v.emplace_back(i1);
        }
        return v;
    }

    // ------------------------------------------------------------------ out of combat

    // Returns the actions the random walk may take: the enumeration plus the engine-valid extras of the classes found
    // missing (Bowl, out-of-combat drinks / discards), so states those actions reach are visited too.
    std::vector<GameAction> auditOoc(const GameContext &gc) {
        const auto en = GameAction::getAllActionsInState(gc);
        std::set<std::uint32_t> enC;
        std::map<std::uint32_t, int> dup;
        for (const auto &a : en) {
            ++dup[a.bits];
            enC.insert(canon(gc, a));
            if (!a.isValidAction(gc)) note("ENUMERATED BUT ENGINE-INVALID: " + kindOf(gc, a), where(gc));
        }
        for (const auto &[bits, n] : dup)
            if (n > 1) note("DUPLICATE ENUMERATION: " + kindOf(gc, GameAction(bits)), where(gc));
        if (en.empty()) note(std::string("NO ACTION (undecided): ") + screenName(gc.screenState)
                             + (gc.screenState == ScreenState::EVENT_SCREEN
                                ? "/event" + std::to_string(static_cast<int>(gc.curEvent)) : ""), where(gc));
        // Encoder view with exactly the driver's list (--sim-help takes reward gold before the net sees the screen):
        // a legal OPTION token that no action points at is a choice the net sees but can never make.
        if (!(gc.screenState == ScreenState::REWARDS && gc.info.rewardsContainer.goldRewardCount > 0)) {
            static const char *kinds[] = {"REWARD_GOLD", "REWARD_CARD", "REWARD_RELIC", "REWARD_POTION",
                "REWARD_EMERALD_KEY", "REWARD_SAPPHIRE_KEY", "SINGING_BOWL", "SHOP_CARD", "SHOP_RELIC",
                "SHOP_POTION", "SHOP_REMOVE", "BOSS_RELIC", "REST", "NEOW", "EVENT", "MATCH_SLOT", "CHEST"};
            static search::AmberTokens t;
            search::amberEncodeGame(gc, en, t);
            const int opt = static_cast<int>(search::AmberTokenType::OPTION);
            for (int i = 0; i < t.n[opt]; ++i) {
                const auto &tok = t.at(search::AmberTokenType::OPTION, i);
                if (tok.f[31] != 0x3c00) continue;   // not legal now
                bool used = false;
                for (int k = 0; k < t.nAct && !used; ++k)
                    used = t.act[k].srcSeg == opt && t.act[k].srcIdx == i;
                if (used) continue;
                std::string kind = "?";
                for (int q = 0; q < 17; ++q)
                    if (tok.f[12 + q] == 0x3c00) kind = kinds[q];
                if (kind == "SHOP_RELIC" && gc.screenState == ScreenState::SHOP_ROOM) {
                    // --sim-help bans Prismatic Shard; flag only other unreachable shop relics.
                }
                note(std::string("ENCODER LEGAL OPTION WITHOUT ACTION: ") + screenName(gc.screenState) + " " + kind,
                     where(gc));
            }
            for (int k = 0; k < t.nAct; ++k)
                if (t.act[k].type == static_cast<int>(search::AmberActionType::UNKNOWN))
                    note(std::string("ENCODER UNKNOWN ACTION: ") + kindOf(gc, en[k]), where(gc));
            if (t.cut > 0 && t.nAct < static_cast<int>(en.size()))
                note(std::string("ENCODER ACTIONS CUT: ") + screenName(gc.screenState), where(gc));
        }
        if (gc.screenState == ScreenState::REWARDS && gc.info.rewardsContainer.potionCount > 0
                && gc.potionCount >= gc.potionCapacity)
            note("CONTEXT: reward potion offered with full slots (taking it needs an out-of-combat discard)", where(gc));
        if (gc.screenState == ScreenState::SHOP_ROOM && gc.potionCount >= gc.potionCapacity)
            note("CONTEXT: shop visit with full slots (buying a potion needs an out-of-combat discard)", where(gc));
        std::vector<GameAction> walk = en;
        std::set<std::uint32_t> seen;
        for (const auto &a : oocSpace(gc)) {
            if (a.isPotionAction() && a.getIdx1() >= gc.potionCapacity) continue;
            if (!a.isValidAction(gc)) continue;
            const auto c = canon(gc, a);
            if (!seen.insert(c).second) continue;
            ++coverage[std::string("valid ") + screenName(gc.screenState)];
            if (enC.count(c)) continue;
            const auto k = kindOf(gc, a);
            note("VALID BUT NOT ENUMERATED: " + k, where(gc));
            const bool realExtra = a.isPotionAction()
                || (gc.screenState == ScreenState::REWARDS && a.getRewardsActionType() == RT::CARD && a.getIdx2() == 5
                    && gc.hasRelic(RelicId::SINGING_BOWL));
            if (realExtra && !(a.isPotionAction() && !a.isPotionDiscard() && gc.screenState == ScreenState::CARD_SELECT))
                walk.push_back(GameAction(c));
        }
        return walk;
    }

    // ------------------------------------------------------------------ combat

    bool sameCard(const CardInstance &l, const CardInstance &r) {   // SilverSearcher's cardsEquivalentForSearch
        if (l.id != r.id || l.upgraded != r.upgraded || l.specialData != r.specialData || l.cost != r.cost
            || l.costForTurn != r.costForTurn || l.freeToPlayOnce != r.freeToPlayOnce || l.retain != r.retain)
            return false;
        return l.uniqueId == r.uniqueId || (!l.usesSpecialData() && !r.usesSpecialData());
    }

    const CardInstance *selectPileCard(const BattleContext &bc, int idx) {   // SilverSearcher's selectableCard
        switch (bc.cardSelectInfo.cardSelectTask) {
            case CardSelectTask::ARMAMENTS:
            case CardSelectTask::EXHAUST_ONE:
            case CardSelectTask::FORETHOUGHT:
            case CardSelectTask::WARCRY:
                return idx < bc.cards.cardsInHand ? &bc.cards.hand[idx] : nullptr;
            case CardSelectTask::HEADBUTT:
            case CardSelectTask::LIQUID_MEMORIES_POTION:
                return idx < static_cast<int>(bc.cards.discardPile.size()) ? &bc.cards.discardPile[idx] : nullptr;
            case CardSelectTask::EXHUME:
                return idx < static_cast<int>(bc.cards.exhaustPile.size()) ? &bc.cards.exhaustPile[idx] : nullptr;
            default:
                return nullptr;
        }
    }

    std::string cwhere(const GameContext &gc, const BattleContext &bc) {
        std::ostringstream o;
        o << "seed " << gc.seed << " floor " << gc.floorNum << " turn " << bc.turn << " enc "
          << static_cast<int>(bc.encounter);
        return o.str();
    }

    // Whether enumerated action e covers valid action a (same effect up to the enumerator's intended collapsing).
    bool covers(const BattleContext &bc, search::Action a, search::Action e) {
        using search::ActionType;
        if (a.getActionType() != e.getActionType()) return false;
        switch (a.getActionType()) {
            case ActionType::END_TURN: return true;
            case ActionType::CARD: {
                const auto &ca = bc.cards.hand[a.getSourceIdx()];
                const auto &ce = bc.cards.hand[e.getSourceIdx()];
                if (!sameCard(ca, ce)) return false;
                return !ca.requiresTarget() || a.getTargetIdx() == e.getTargetIdx();
            }
            case ActionType::POTION: {
                const auto pa = bc.potions[a.getSourceIdx()], pe = bc.potions[e.getSourceIdx()];
                if (pa != pe) return false;
                const bool da = a.getTargetIdx() > 5, de = e.getTargetIdx() > 5;
                if (da != de) return false;
                return da || !potionRequiresTarget(pa) || a.getTargetIdx() == e.getTargetIdx();
            }
            case ActionType::SINGLE_CARD_SELECT: {
                if (a.bits == e.bits) return true;
                if (bc.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION
                    && bc.cardSelectInfo.pickCount == 2) return false;
                const auto *x = selectPileCard(bc, a.getSelectIdx()), *y = selectPileCard(bc, e.getSelectIdx());
                return x && y && a.getTargetIdx() == e.getTargetIdx() && sameCard(*x, *y);
            }
            case ActionType::MULTI_CARD_SELECT: {
                if (a.bits == e.bits) return true;
                auto ka = a.getSelectedIdxs(), ke = e.getSelectedIdxs();
                if (ka.size() != ke.size()) return false;
                std::vector<const CardInstance *> va, ve;
                for (int i : ka) va.push_back(&bc.cards.hand[i]);
                for (int i : ke) ve.push_back(&bc.cards.hand[i]);
                std::vector<bool> used(ve.size(), false);
                for (auto *c : va) {
                    bool hit = false;
                    for (std::size_t j = 0; j < ve.size() && !hit; ++j)
                        if (!used[j] && sameCard(*c, *ve[j])) used[j] = hit = true;
                    if (!hit) return false;
                }
                return true;
            }
        }
        return false;
    }

    std::string ckind(const BattleContext &bc, search::Action a) {
        using search::ActionType;
        switch (a.getActionType()) {
            case ActionType::END_TURN: return "END_TURN";
            case ActionType::CARD: {
                const auto &c = bc.cards.hand[a.getSourceIdx()];
                return std::string("CARD ") + c.getName() + (c.requiresTarget() ? " ->target" : "");
            }
            case ActionType::POTION: {
                const auto p = bc.potions[a.getSourceIdx()];
                return std::string(a.getTargetIdx() > 5 ? "POTION discard " : "POTION drink ") + getPotionName(p)
                       + (a.getTargetIdx() <= 5 && potionRequiresTarget(p) ? " ->target" : "");
            }
            case ActionType::SINGLE_CARD_SELECT:
                return std::string("SELECT ") + cardSelectTaskStrings[static_cast<int>(bc.cardSelectInfo.cardSelectTask)];
            case ActionType::MULTI_CARD_SELECT:
                return std::string("MULTI ") + cardSelectTaskStrings[static_cast<int>(bc.cardSelectInfo.cardSelectTask)];
        }
        return "?";
    }

    std::vector<search::Action> combatSpace(const BattleContext &bc) {
        using search::Action;
        using search::ActionType;
        std::vector<Action> v;
        v.emplace_back(ActionType::END_TURN);
        for (int s = 0; s < 10; ++s)
            for (int t = 0; t < 5; ++t) v.emplace_back(ActionType::CARD, s, t);
        for (int s = 0; s < 5; ++s) {
            for (int t = 0; t < 5; ++t) v.emplace_back(ActionType::POTION, s, t);
            v.emplace_back(ActionType::POTION, s, -1);
        }
        if (bc.inputState == InputState::CARD_SELECT) {
            const int piles = std::max({bc.cards.cardsInHand, static_cast<int>(bc.cards.discardPile.size()),
                                        static_cast<int>(bc.cards.drawPile.size()),
                                        static_cast<int>(bc.cards.exhaustPile.size()), 4});
            for (int i = 0; i < piles; ++i) {
                v.emplace_back(ActionType::SINGLE_CARD_SELECT, i, 0);
                if (bc.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION)
                    for (int j = 1; j <= piles; ++j) v.emplace_back(ActionType::SINGLE_CARD_SELECT, i, j);
            }
            for (int m = 0; m < 1024; ++m) v.emplace_back(ActionType::MULTI_CARD_SELECT, m);
        }
        return v;
    }

    void auditCombat(const GameContext &gc, const BattleContext &bc, search::SilverSearcher &en,
                     std::vector<search::Action> &out) {
        out = en.enumerateActions(bc);
        for (const auto &e : out)
            if (!e.isValidAction(bc)) note("COMBAT ENUMERATED BUT ENGINE-INVALID: " + ckind(bc, e), cwhere(gc, bc));
        if (out.empty()) note("COMBAT NO ACTION (undecided)", cwhere(gc, bc));
        for (const auto &a : combatSpace(bc)) {
            if (!a.isValidAction(bc)) continue;
            {
                std::string k = ckind(bc, a);
                if (a.getActionType() == search::ActionType::CARD) k = "CARD";
                if (a.getActionType() == search::ActionType::POTION) k = a.getTargetIdx() > 5 ? "POTION discard" : "POTION drink";
                ++coverage["valid combat " + k];
            }
            bool hit = false;
            for (const auto &e : out)
                if (covers(bc, a, e)) { hit = true; break; }
            if (!hit) note("COMBAT VALID BUT NOT ENUMERATED: " + ckind(bc, a), cwhere(gc, bc));
        }
    }

}  // namespace

int main(int argc, char **argv) {
    int runs = 200, asc = 20;
    bool combat = false;
    std::uint64_t seedBase = 1;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--combat") combat = true;
        else if (a == "--asc" && i + 1 < argc) asc = std::atoi(argv[++i]);
        else if (a == "--seed-base" && i + 1 < argc) seedBase = std::strtoull(argv[++i], nullptr, 10);
        else runs = std::atoi(argv[i]);
    }
    long oocStates = 0, combatStates = 0, fights = 0, act4 = 0;
    std::map<std::string, long> screens;
    for (int run = 0; run < runs; ++run) {
        const std::uint64_t seed = seedBase + run;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        gc.skipBattles = !combat;
        std::mt19937 rng(static_cast<unsigned>(seed * 2654435761u));
        std::unique_ptr<search::SilverSearcher> enumerator;
        std::vector<search::Action> cacts;
        for (int step = 0; step < 6000 && gc.outcome == GameOutcome::UNDECIDED; ++step) {
            if (gc.screenState == ScreenState::BATTLE) {
                if (!combat) break;
                // Fuzzing only: a sturdy player reaches later acts; play is random over the enumeration.
                gc.maxHp = std::max(gc.maxHp, 900);
                gc.curHp = gc.maxHp;
                BattleContext bc;
                bc.init(gc);
                ++fights;
                if (!enumerator) enumerator = std::make_unique<search::SilverSearcher>(bc, search::SilverSearchContext{});
                for (int m = 0; m < 400 && bc.outcome == Outcome::UNDECIDED; ++m) {
                    ++combatStates;
                    auditCombat(gc, bc, *enumerator, cacts);
                    std::vector<search::Action> ok;
                    for (const auto &e : cacts)
                        if (e.isValidAction(bc)) ok.push_back(e);
                    if (ok.empty()) break;
                    // Bias toward card plays so fights end and later states (select screens, potions) appear.
                    search::Action pick = ok[std::uniform_int_distribution<std::size_t>(0, ok.size() - 1)(rng)];
                    if (pick.getActionType() == search::ActionType::END_TURN && ok.size() > 1 && rng() % 3)
                        pick = ok[std::uniform_int_distribution<std::size_t>(0, ok.size() - 2)(rng)];
                    pick.execute(bc);
                }
                if (bc.outcome == Outcome::UNDECIDED) { gc.outcome = GameOutcome::PLAYER_LOSS; break; }
                bc.exitBattle(gc);
                continue;
            }
            ++oocStates;
            ++screens[screenName(gc.screenState)];
            if (gc.act == 4) ++act4;
            auto walk = auditOoc(gc);
            std::vector<GameAction> ok;
            for (const auto &a : walk)
                if (a.isValidAction(gc)) ok.push_back(a);
            if (ok.empty()) break;
            ok[std::uniform_int_distribution<std::size_t>(0, ok.size() - 1)(rng)].execute(gc);
        }
    }
    std::cout << "runs " << runs << " asc " << asc << " mode " << (combat ? "combat" : "skip-battles")
              << " ooc_states " << oocStates << " combat_states " << combatStates << " fights " << fights
              << " act4_states " << act4 << "\nscreens:";
    for (const auto &[s, n] : screens) std::cout << ' ' << s << '=' << n;
    std::cout << "\nvalid actions checked:";
    for (const auto &[s, n] : coverage) std::cout << " [" << s << "]=" << n;
    std::cout << "\n\nFINDINGS (" << findings.size() << " categories)\n";
    for (const auto &[cat, f] : findings)
        std::cout << f.count << "\t" << cat << "\t(e.g. " << f.example << ")\n";
    return 0;
}
