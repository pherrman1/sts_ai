// Port of the Silver fork's SimpleAgent battle policy (production defaults
// only) to the main engine; see SilverRolloutAgent.h.

#include "sim/search/SilverRolloutAgent.h"

#include <algorithm>
#include <array>
#include <bitset>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "combat/BattleContext.h"
#include "data_structure/fixed_list.h"

using namespace sts;

namespace {

constexpr std::array<CardId,133> cardsPriorities = {
        CardId::APOTHEOSIS,
        CardId::GHOSTLY_ARMOR,
        CardId::PERFECTED_STRIKE,
        CardId::WHIRLWIND,
        CardId::BATTLE_TRANCE,
        CardId::DEMON_FORM,
        CardId::RAGE,
        CardId::OFFERING,
        CardId::IMPERVIOUS,
        CardId::IMMOLATE,
        CardId::LIMIT_BREAK,
        CardId::FLAME_BARRIER,
        CardId::MASTER_OF_STRATEGY,
        CardId::INFLAME,
        CardId::DISARM,
        CardId::SHRUG_IT_OFF,
        CardId::DOUBLE_TAP,
        CardId::THUNDERCLAP,
        CardId::METALLICIZE,
        CardId::POMMEL_STRIKE,
        CardId::SHOCKWAVE,
        CardId::UPPERCUT,
        CardId::JAX,
        CardId::PANIC_BUTTON,
        CardId::FLASH_OF_STEEL,
        CardId::FLEX,
        CardId::ANGER,
        CardId::SECRET_WEAPON,
        CardId::FINESSE,
        CardId::MAYHEM,
        CardId::PANACHE,
        CardId::SECRET_TECHNIQUE,
        CardId::METAMORPHOSIS,
        CardId::THINKING_AHEAD,
        CardId::MADNESS,
        CardId::DISCOVERY,
        CardId::CHRYSALIS,
        CardId::DEEP_BREATH,
        CardId::TRIP,
        CardId::ENLIGHTENMENT,
        CardId::HEAVY_BLADE,
        CardId::FEED,
        CardId::FIEND_FIRE,
        CardId::TWIN_STRIKE,
        CardId::HEADBUTT,
        CardId::SEEING_RED,
        CardId::COMBUST,
        CardId::CLASH,
        CardId::DARK_SHACKLES,
        CardId::SWORD_BOOMERANG,
        CardId::DRAMATIC_ENTRANCE,
        CardId::BLUDGEON,
        CardId::HAND_OF_GREED,
        CardId::EVOLVE,
        CardId::VIOLENCE,
        CardId::BITE,
        CardId::CARNAGE,
        CardId::CLOTHESLINE,
        CardId::BASH,
        CardId::BANDAGE_UP,
        CardId::PANACEA,
        CardId::RECKLESS_CHARGE,
        CardId::INFERNAL_BLADE,
        CardId::SPOT_WEAKNESS,
        CardId::STRIKE_RED,
        CardId::SHIV,
        CardId::HAVOC,
        CardId::RITUAL_DAGGER,
        CardId::DROPKICK,
        CardId::FEEL_NO_PAIN,
        CardId::SWIFT_STRIKE,
        CardId::CORRUPTION,
        CardId::MAGNETISM,
        CardId::BLOODLETTING,
        CardId::IRON_WAVE,
        CardId::ARMAMENTS,
        CardId::MIND_BLAST,
        CardId::ASCENDERS_BANE,
        CardId::DAZED,
        CardId::VOID,
        CardId::RAMPAGE,
        CardId::GHOSTLY_ARMOR,
        CardId::TRUE_GRIT,
        CardId::BLIND,
        CardId::GOOD_INSTINCTS,
        CardId::PUMMEL,
        CardId::HEMOKINESIS,
        CardId::EXHUME,
        CardId::REAPER,
        CardId::CLEAVE,
        CardId::WARCRY,
        CardId::PURITY,
        CardId::DUAL_WIELD,
        CardId::WILD_STRIKE,
        CardId::DEFEND_RED,
        CardId::BODY_SLAM,
        CardId::SEVER_SOUL,
        CardId::BURNING_PACT,
        CardId::BRUTALITY,
        CardId::BARRICADE,
        CardId::INTIMIDATE,
        CardId::JUGGERNAUT,
        CardId::SADISTIC_NATURE,
        CardId::DARK_EMBRACE,
        CardId::POWER_THROUGH,
        CardId::TRANSMUTATION,
        CardId::SENTINEL,
        CardId::RUPTURE,
        CardId::SLIMED,
        CardId::FIRE_BREATHING,
        CardId::SECOND_WIND,
        CardId::IMPATIENCE,
        CardId::THE_BOMB,
        CardId::JACK_OF_ALL_TRADES,
        CardId::SEARING_BLOW,
        CardId::BLOOD_FOR_BLOOD,
        CardId::BERSERK,
        CardId::ENTRENCH,
        CardId::FORETHOUGHT,
        CardId::CLUMSY,
        CardId::PARASITE,
        CardId::SHAME,
        CardId::INJURY,
        CardId::WOUND,
        CardId::WRITHE,
        CardId::DOUBT,
        CardId::BURN,
        CardId::DECAY,
        CardId::REGRET,
        CardId::NECRONOMICURSE,
        CardId::PAIN,
        CardId::NORMALITY,
        CardId::PRIDE,
};

constexpr std::array<CardId,133> cardPlayPriorities = {
        CardId::APOTHEOSIS,
        CardId::OFFERING,
        CardId::DEMON_FORM,
        CardId::INFLAME,
        CardId::METALLICIZE,
        CardId::DISARM,
        CardId::SHOCKWAVE,
        CardId::GHOSTLY_ARMOR,
        CardId::LIMIT_BREAK,
        CardId::DOUBLE_TAP,
        CardId::THUNDERCLAP,
        CardId::IMMOLATE,
        CardId::UPPERCUT,
        CardId::FLAME_BARRIER,
        CardId::SHRUG_IT_OFF,
        CardId::IMPERVIOUS,
        CardId::MADNESS,
        CardId::PERFECTED_STRIKE,
        CardId::BATTLE_TRANCE,
        CardId::RAGE,
        CardId::MASTER_OF_STRATEGY,
        CardId::POMMEL_STRIKE,
        CardId::JAX,
        CardId::FLASH_OF_STEEL,
        CardId::FLEX,
        CardId::ANGER,
        CardId::DEFEND_RED,
        CardId::BASH,
        CardId::WHIRLWIND,
        CardId::PANIC_BUTTON,
        CardId::SECRET_WEAPON,
        CardId::FINESSE,
        CardId::MAYHEM,
        CardId::PANACHE,
        CardId::SECRET_TECHNIQUE,
        CardId::METAMORPHOSIS,
        CardId::THINKING_AHEAD,
        CardId::DISCOVERY,
        CardId::CHRYSALIS,
        CardId::DEEP_BREATH,
        CardId::TRIP,
        CardId::ENLIGHTENMENT,
        CardId::HEAVY_BLADE,
        CardId::FEED,
        CardId::FIEND_FIRE,
        CardId::TWIN_STRIKE,
        CardId::HEADBUTT,
        CardId::SEEING_RED,
        CardId::COMBUST,
        CardId::CLASH,
        CardId::DARK_SHACKLES,
        CardId::SWORD_BOOMERANG,
        CardId::DRAMATIC_ENTRANCE,
        CardId::BLUDGEON,
        CardId::HAND_OF_GREED,
        CardId::EVOLVE,
        CardId::VIOLENCE,
        CardId::BITE,
        CardId::CARNAGE,
        CardId::CLOTHESLINE,
        CardId::BANDAGE_UP,
        CardId::PANACEA,
        CardId::RECKLESS_CHARGE,
        CardId::INFERNAL_BLADE,
        CardId::STRIKE_RED,
        CardId::SPOT_WEAKNESS,
        CardId::SHIV,
        CardId::HAVOC,
        CardId::RITUAL_DAGGER,
        CardId::DROPKICK,
        CardId::FEEL_NO_PAIN,
        CardId::SWIFT_STRIKE,
        CardId::CORRUPTION,
        CardId::MAGNETISM,
        CardId::BLOODLETTING,
        CardId::IRON_WAVE,
        CardId::ARMAMENTS,
        CardId::MIND_BLAST,
        CardId::ASCENDERS_BANE,
        CardId::DAZED,
        CardId::VOID,
        CardId::RAMPAGE,
        CardId::GHOSTLY_ARMOR,
        CardId::TRUE_GRIT,
        CardId::BLIND,
        CardId::GOOD_INSTINCTS,
        CardId::PUMMEL,
        CardId::HEMOKINESIS,
        CardId::EXHUME,
        CardId::REAPER,
        CardId::CLEAVE,
        CardId::WARCRY,
        CardId::PURITY,
        CardId::DUAL_WIELD,
        CardId::WILD_STRIKE,
        CardId::BODY_SLAM,
        CardId::SEVER_SOUL,
        CardId::BURNING_PACT,
        CardId::BRUTALITY,
        CardId::BARRICADE,
        CardId::INTIMIDATE,
        CardId::JUGGERNAUT,
        CardId::SADISTIC_NATURE,
        CardId::DARK_EMBRACE,
        CardId::POWER_THROUGH,
        CardId::TRANSMUTATION,
        CardId::SENTINEL,
        CardId::RUPTURE,
        CardId::SLIMED,
        CardId::FIRE_BREATHING,
        CardId::SECOND_WIND,
        CardId::IMPATIENCE,
        CardId::THE_BOMB,
        CardId::JACK_OF_ALL_TRADES,
        CardId::SEARING_BLOW,
        CardId::BLOOD_FOR_BLOOD,
        CardId::BERSERK,
        CardId::ENTRENCH,
        CardId::FORETHOUGHT,
        CardId::CLUMSY,
        CardId::PARASITE,
        CardId::SHAME,
        CardId::INJURY,
        CardId::WOUND,
        CardId::WRITHE,
        CardId::DOUBT,
        CardId::BURN,
        CardId::DECAY,
        CardId::REGRET,
        CardId::NECRONOMICURSE,
        CardId::PAIN,
        CardId::NORMALITY,
        CardId::PRIDE,
};

constexpr std::array<CardId,13>  defensiveCards = {
        CardId::POWER_THROUGH,
        CardId::TRUE_GRIT,
        CardId::IMPERVIOUS,
        CardId::SHRUG_IT_OFF,
        CardId::FLAME_BARRIER,
        CardId::ENTRENCH,
        CardId::DEFEND_RED,
        CardId::SENTINEL,
        CardId::SECOND_WIND,
        CardId::GHOSTLY_ARMOR,
        CardId::DARK_SHACKLES,
        CardId::PANIC_BUTTON,
        CardId::RAGE,
};


    int cardPriorityMap[372] {};
    int cardPlayMap[372] {};
    // Research (STS_SILVER_ROLLOUT_CARD_TABLE=<file>): learned play priority per (card id, upgraded),
    // replacing the cardPlayPriorities order; lower plays first. Default off.
    bool useLearnedPlayTable = false;
    int learnedPlayPriority[372 * 2] {};
    std::bitset<372> isAoeCard;
    std::bitset<372> isDefensiveCard;

    void initMaps() {
        static std::once_flag once;
        std::call_once(once, [] {
            for (int i = 0; i < static_cast<int>(cardPlayPriorities.size()); ++i) {
                cardPlayMap[static_cast<int>(cardPlayPriorities[i])] = i + 1;
            }
            for (int i = 0; i < static_cast<int>(cardsPriorities.size()); ++i) {
                cardPriorityMap[static_cast<int>(cardsPriorities[i])] = i + 1;
            }
            for (auto c : defensiveCards) {
                isDefensiveCard.set(static_cast<int>(c));
            }
            isAoeCard.set(static_cast<int>(CardId::CLEAVE));
            isAoeCard.set(static_cast<int>(CardId::IMMOLATE));
            isAoeCard.set(static_cast<int>(CardId::THUNDERCLAP));
            isAoeCard.set(static_cast<int>(CardId::WHIRLWIND));
            // File lines: "<card id> <upgraded 0|1> <score>"; higher score plays first, unlisted
            // cards score 0.
            if (const char *path = std::getenv("STS_SILVER_ROLLOUT_CARD_TABLE"); path && *path) {
                std::ifstream in(path);
                if (!in) throw std::runtime_error(std::string("STS_SILVER_ROLLOUT_CARD_TABLE: cannot open ") + path);
                int id = 0, upgraded = 0;
                double score = 0;
                while (in >> id >> upgraded >> score) {
                    if (id < 0 || id >= 372 || (upgraded != 0 && upgraded != 1))
                        throw std::runtime_error("STS_SILVER_ROLLOUT_CARD_TABLE: bad row");
                    learnedPlayPriority[id * 2 + upgraded] = static_cast<int>(-score * 1000.0);
                }
                useLearnedPlayTable = true;
            }
        });
    }

    // Silver's rollout-policy constants at their production defaults.
    constexpr int kBlockOffset = 4;
    constexpr int kAoeMin = 2;

    int cardPriority(const CardInstance &c) {
        return 2 * cardPriorityMap[static_cast<int>(c.id)] + (c.isUpgraded() ? -1 : 0);
    }

    int getHighHpMonster(const BattleContext &bc, bool randomize, std::default_random_engine &rng) {
        int highHp = -1;
        fixed_list<int, 5> highIdxs;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (bc.monsters.arr[i].isTargetable()) {
                if (bc.monsters.arr[i].curHp > highHp) {
                    highHp = bc.monsters.arr[i].curHp;
                    highIdxs.clear();
                    highIdxs.push_back(i);
                } else if (randomize && bc.monsters.arr[i].curHp == highHp) {
                    highIdxs.push_back(i);
                }
            }
        }
        if (randomize && highIdxs.size() > 1) {
            std::uniform_int_distribution<int> dist(0, highIdxs.size() - 1);
            return highIdxs[dist(rng)];
        }
        return highIdxs.empty() ? -1 : highIdxs[0];
    }

    int getLowHpMonster(const BattleContext &bc, bool randomize, std::default_random_engine &rng) {
        int lowHp = 10000;
        fixed_list<int, 5> lowIdxs;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (bc.monsters.arr[i].isTargetable()) {
                if (bc.monsters.arr[i].curHp < lowHp) {
                    lowHp = bc.monsters.arr[i].curHp;
                    lowIdxs.clear();
                    lowIdxs.push_back(i);
                } else if (randomize && bc.monsters.arr[i].curHp == lowHp) {
                    lowIdxs.push_back(i);
                }
            }
        }
        if (randomize && lowIdxs.size() > 1) {
            std::uniform_int_distribution<int> dist(0, lowIdxs.size() - 1);
            return lowIdxs[dist(rng)];
        }
        return lowIdxs.empty() ? -1 : lowIdxs[0];
    }

    // Feed only grants its max HP on a kill, so the greedy policy plays it only when lethal.
    bool feedWouldKill(const BattleContext &bc, const CardInstance &feed) {
        int lowHp = 10000;
        int tgt = -1;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const auto &m = bc.monsters.arr[i];
            if (m.isTargetable() && m.curHp < lowHp) {
                lowHp = m.curHp;
                tgt = i;
            }
        }
        if (tgt < 0) {
            return false;
        }
        const int dmg = bc.calculateCardDamage(feed, tgt, feed.isUpgraded() ? 12 : 10);
        return dmg >= bc.monsters.arr[tgt].curHp + bc.monsters.arr[tgt].block;
    }

    int getBestCardToPlay(const BattleContext &bc, const fixed_list<int,10> &handIdxs, bool randomize,
                          std::default_random_engine &rng) {
        int bestPriority = 1 << 30;
        fixed_list<int,10> bestHandIdxs;
        for (int i = 0; i < handIdxs.size(); ++i) {
            const auto c = bc.cards.hand[handIdxs[i]];
            const int priority = useLearnedPlayTable
                    ? learnedPlayPriority[static_cast<int>(c.getId()) * 2 + (c.isUpgraded() ? 1 : 0)]
                    : 2 * cardPlayMap[static_cast<int>(c.getId())] + (c.isUpgraded() ? -1 : 0);
            if (priority < bestPriority) {
                bestPriority = priority;
                bestHandIdxs.clear();
                bestHandIdxs.push_back(handIdxs[i]);
            } else if (randomize && priority == bestPriority) {
                bestHandIdxs.push_back(handIdxs[i]);
            }
        }
        if (randomize && bestHandIdxs.size() > 1) {
            std::uniform_int_distribution<int> dist(0, bestHandIdxs.size() - 1);
            return bestHandIdxs[dist(rng)];
        }
        return bestHandIdxs[0];
    }

    template <typename Pile, typename Pred>
    void addSelectOptions(std::vector<std::pair<search::Action,CardInstance>> &actions,
                          const Pile &pile, int count, Pred pred) {
        for (int i = 0; i < count; ++i) {
            const auto &c = pile[i];
            if (pred(c)) {
                actions.emplace_back(search::Action(search::ActionType::SINGLE_CARD_SELECT, i), c);
            }
        }
    }

    constexpr auto anyCard = [](const CardInstance &) { return true; };

}

search::SilverRolloutAgent::SilverRolloutAgent() {
    initMaps();
}

search::SilverRolloutAgent::SilverRolloutAgent(bool randomizeMode, std::uint64_t seed, int currentAct)
        : randomize(randomizeMode), act(currentAct) {
    initMaps();
    if (randomize) {
        rng.seed(seed);
    }
}

void search::SilverRolloutAgent::materializeHiddenIntents(BattleContext &bc) {
    for(int i=0;i<bc.monsters.monsterCount;++i) {
        auto &m=bc.monsters.arr[i];
        if((m.pendingMoveRolls>0 || m.pendingDirectMoveChoice!=0) && !m.isDeadOrEscaped()) m.materializePendingMove(bc);
    }
}

int search::SilverRolloutAgent::getIncomingDamage(const BattleContext &bc) const {
    int incomingDamage = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (m.isDeadOrEscaped() || m.isHalfDead()) {
            continue;
        }
        DamageInfo dInfo;
        if (m.pendingMoveRolls > 0 || m.pendingDirectMoveChoice != 0) {
            dInfo = {5 * act, 1};   // hidden intent: Silver's flat estimate
        } else {
            dInfo = {m.publicIncomingDamage(bc),1};
        }
        incomingDamage += dInfo.damage * dInfo.attackCount;
    }
    return incomingDamage;
}

search::Action search::SilverRolloutAgent::chooseBattleCardPlay(const BattleContext &bc) {
    if (!bc.isCardPlayAllowed() || bc.player.cardsPlayedThisTurn > 1000) {
        return Action(ActionType::END_TURN);
    }

    // One pass over the hand: skip unplayable cards, categorize the rest.
    fixed_list<int,10> playableCardsIdxs;
    fixed_list<int,10> zeroCostAttacks;
    fixed_list<int,10> zeroCostNonAttacks;
    fixed_list<int,10> nonZeroCostCards;
    fixed_list<int,10> aoeCards;

    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        const auto &c = bc.cards.hand[i];
        if (!c.canUseOnAnyTarget(bc)) {
            continue;
        }
        playableCardsIdxs.push_back(i);
        // A non-lethal Feed is never the greedy pick (randomized mode still reaches it).
        if (c.getId() == CardId::FEED && !randomize && !feedWouldKill(bc, c)) {
            continue;
        }
        if (isAoeCard.test(static_cast<int>(c.getId()))) {
            aoeCards.push_back(i);
        }
        if (c.cost == 0 || c.costForTurn == 0) {
            if (c.getType() == CardType::ATTACK) {
                zeroCostAttacks.push_back(i);
            } else {
                zeroCostNonAttacks.push_back(i);
            }
        } else {
            nonZeroCostCards.push_back(i);
        }
    }

    if (playableCardsIdxs.empty()) {
        return Action(ActionType::END_TURN);
    }

    const int incomingDamage = getIncomingDamage(bc);
    if (bc.player.block > (incomingDamage - act - kBlockOffset)) {
        fixed_list<int,10> offensiveCards;
        for (auto handIdx : nonZeroCostCards) {
            const auto &c = bc.cards.hand[handIdx];
            if (!isDefensiveCard.test(static_cast<int>(c.getId()))) {
                offensiveCards.push_back(handIdx);
            }
        }
        if (offensiveCards.empty()) {
            for (int i = nonZeroCostCards.size()-1; i >= 0; --i) {
                const auto &c = bc.cards.hand[nonZeroCostCards[i]];
                if (c.doesExhaust()) {
                    nonZeroCostCards.remove(i);
                }
            }
        } else {
            nonZeroCostCards = offensiveCards;
        }
    }

    // Priority order: zero-cost non-attacks, non-zero-cost cards, zero-cost attacks. The AoE
    // override applies only when the pick came from the non-zero-cost cards.
    const fixed_list<int,10> *priority[3] = {&zeroCostNonAttacks, &nonZeroCostCards, &zeroCostAttacks};
    int bestCardIdx = -1;
    const fixed_list<int,10> *chosen = nullptr;
    for (auto *list : priority) {
        if (!list->empty()) {
            bestCardIdx = getBestCardToPlay(bc, *list, randomize, rng);
            chosen = list;
            break;
        }
    }
    if (bestCardIdx < 0) {
        return Action(ActionType::END_TURN);
    }
    if (chosen == &nonZeroCostCards && !aoeCards.empty()
            && bc.monsters.monstersAlive >= kAoeMin
            && bc.cards.hand[bestCardIdx].getType() == CardType::ATTACK) {
        bestCardIdx = getBestCardToPlay(bc, aoeCards, randomize, rng);
    }

    const auto &c = bc.cards.hand[bestCardIdx];
    if (!c.requiresTarget()) {
        return Action(ActionType::CARD, bestCardIdx);
    }
    const int targetIdx = c.getType() == CardType::ATTACK
            ? getLowHpMonster(bc, randomize, rng)
            : getHighHpMonster(bc, randomize, rng);
    return Action(ActionType::CARD, bestCardIdx, targetIdx);
}

search::Action search::SilverRolloutAgent::chooseBattleCardSelect(const BattleContext &bc) {
    if (bc.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION && bc.cardSelectInfo.pickCount == 2) {
        const auto pairs = search::Action::enumerateCardSelectActions(bc);
        return pairs.front();
    }

    std::vector<std::pair<search::Action,CardInstance>> actions;
    const auto &cards = bc.cards;
    const auto task = bc.cardSelectInfo.cardSelectTask;
    switch (task) {
        case CardSelectTask::ARMAMENTS:
            addSelectOptions(actions, cards.hand, cards.cardsInHand,
                             [](const CardInstance &c) { return c.canUpgrade(); });
            break;

        case CardSelectTask::CODEX:
        case CardSelectTask::DISCOVERY:
            for (int i = 0; i < 3; ++i) {
                actions.emplace_back(search::Action(search::ActionType::SINGLE_CARD_SELECT, i),
                                     CardInstance(bc.cardSelectInfo.cards[i]));
            }
            break;

        case CardSelectTask::DUAL_WIELD:
            addSelectOptions(actions, cards.hand, cards.cardsInHand, [](const CardInstance &c) {
                return c.getType() == CardType::POWER || c.getType() == CardType::ATTACK;
            });
            break;

        case CardSelectTask::EXHUME:
            addSelectOptions(actions, cards.exhaustPile, static_cast<int>(cards.exhaustPile.size()),
                             [](const CardInstance &c) { return c.getId() != CardId::EXHUME; });
            break;

        case CardSelectTask::FORETHOUGHT:
            if (bc.cardSelectInfo.canPickAnyNumber) return search::Action(search::ActionType::MULTI_CARD_SELECT, 0);
            addSelectOptions(actions, cards.hand, cards.cardsInHand, anyCard);
            break;

        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::WARCRY:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
            addSelectOptions(actions, cards.hand, cards.cardsInHand, anyCard);
            break;

        case CardSelectTask::HEADBUTT:
        case CardSelectTask::HOLOGRAM:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
        case CardSelectTask::MEDITATE:
            addSelectOptions(actions, cards.discardPile, static_cast<int>(cards.discardPile.size()), anyCard);
            break;

        case CardSelectTask::SECRET_TECHNIQUE:
            addSelectOptions(actions, cards.drawPile, cards.drawPile.size(),
                             [](const CardInstance &c) { return c.getType() == CardType::SKILL; });
            break;

        case CardSelectTask::SECRET_WEAPON:
            addSelectOptions(actions, cards.drawPile, cards.drawPile.size(),
                             [](const CardInstance &c) { return c.getType() == CardType::ATTACK; });
            break;

        case CardSelectTask::SEEK:
            addSelectOptions(actions, cards.drawPile, cards.drawPile.size(), anyCard);
            break;

        case CardSelectTask::EXHAUST_MANY:
        case CardSelectTask::GAMBLE:
            // Rollout policy: confirm without picking anything (Silver confirms the cards the
            // tree already picked; the main engine selects the whole subset at once).
            return search::Action(search::ActionType::MULTI_CARD_SELECT, 0);

        default:
            break;
    }

    if (actions.empty()) {
        return search::Action(search::ActionType::SINGLE_CARD_SELECT, 0);
    }

    std::stable_sort(actions.begin(), actions.end(), [](const auto &a, const auto &b) {
        return cardPriority(a.second) < cardPriority(b.second);
    });

    const bool pickWorst = task == CardSelectTask::EXHAUST_ONE || task == CardSelectTask::RECYCLE;
    if (!pickWorst) {
        if (randomize) {
            const int best = cardPriority(actions[0].second);
            int count = 1;
            while (count < static_cast<int>(actions.size()) && cardPriority(actions[count].second) == best) {
                ++count;
            }
            if (count > 1) {
                std::uniform_int_distribution<int> dist(0, count - 1);
                return actions[dist(rng)].first;
            }
        }
        return actions.front().first;
    }

    if (randomize) {
        const int worst = cardPriority(actions.back().second);
        int count = 1;
        for (int i = static_cast<int>(actions.size()) - 2; i >= 0 && cardPriority(actions[i].second) == worst; --i) {
            ++count;
        }
        if (count > 1) {
            std::uniform_int_distribution<int> dist(0, count - 1);
            return actions[actions.size() - 1 - dist(rng)].first;
        }
    }
    return actions.back().first;
}
