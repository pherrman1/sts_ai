//
// Created by keega on 9/17/2021.
//

#include "sim/search/Action.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <set>

using namespace sts;

search::Action::Action(std::uint32_t bits) : bits(bits) {}
search::Action::Action(search::ActionType actionType) : bits(static_cast<int>(actionType) << 29) {}
search::Action::Action(search::ActionType actionType, int idx1) : bits((static_cast<int>(actionType) << 29) | (idx1 & 0xFFFF)) {}
search::Action::Action(search::ActionType actionType, int idx1, int idx2) : bits((static_cast<int>(actionType) << 29) | ((idx2 & 0x1FFF) << 16) | (idx1 & 0xFFFF)) {}
//
//search::Action::Action(search::ActionType actionType) : Action(actionType, 0, 0) {}
//
//search::Action::Action(search::ActionType actionType, int idx1) : Action(actionType, idx1, 0) {}
//
//search::Action::Action(search::ActionType actionType, int idx1, int idx2) : actionType(actionType), idx1(idx1),
//                                                                            idx2(idx2) {}

bool search::Action::operator==(const search::Action &rhs) const {
    return bits == rhs.bits;
//    return actionType == rhs.actionType && idx1 == rhs.idx1 && idx2 == rhs.idx2;
}

bool search::Action::operator!=(const search::Action &rhs) const {
    return !(rhs == *this);
}

search::ActionType search::Action::getActionType() const {
    return static_cast<ActionType>((bits >> 29) & 0xF);
//    return actionType;
}

int search::Action::getSourceIdx() const {
//    return idx1;
    return bits & 0xFFFF;
}

int search::Action::getTargetIdx() const {
//    return idx2;
    return (bits >> 16) & 0x1FFF;
}

int search::Action::getSelectIdx() const {
//    return idx1;
    return bits & 0xFFFF;
}

fixed_list<int, 10> search::Action::getSelectedIdxs() const {
    fixed_list<int,10> ret;
    int i = 0;
    int bitsCopy = bits & 0x3FF;
    while (bitsCopy) {
        if (bitsCopy & 0x1) {
            ret.push_back(i);
        }
        bitsCopy >>= 1;
        ++i;
    }
    return ret;
}

static bool hasPlayableAlchemizeForPotionDiscard(const BattleContext &bc) {
    if (bc.inputState != InputState::PLAYER_NORMAL || !bc.isCardPlayAllowed()) return false;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        const auto &card = bc.cards.hand[i];
        if (card.getId() == CardId::ALCHEMIZE && card.canUseOnAnyTarget(bc)) return true;
    }
    return false;
}

bool isValidPotionAction(const BattleContext &bc, const search::Action &a) {
    if (bc.inputState != InputState::PLAYER_NORMAL) {
        return false;
    }

    if (a.getSourceIdx() < 0 || a.getSourceIdx() > 5) {
        return false;
    }

    const auto p = bc.potions[a.getSourceIdx()];
    if (p == Potion::INVALID || p == Potion::EMPTY_POTION_SLOT) {
        return false;
    }

    if (a.getTargetIdx() > 5) {
        // discard action
        return hasPlayableAlchemizeForPotionDiscard(bc);

    } else {

        // Fairy in a Bottle is NOT usable in combat (auto-procs on lethal).
        if (p == sts::Potion::FAIRY_POTION) {
            return false;
        }

        if (p == sts::Potion::SMOKE_BOMB) {
            return !bc.smokeBombEscapeBlocked();
        }

        // Gambler's Brew is unusable when the hand is empty. Allowing it would
        // enqueue GAMBLE and enter CARD_SELECT with no legal actions because
        // the generic multi-select enumerator has no cards to enumerate.
        if (p == Potion::GAMBLERS_BREW && bc.cards.cardsInHand == 0) {
            return false;
        }

        if (!potionRequiresTarget(p)) {
            return true;
        }

        if (a.getTargetIdx() < 0) {
            return false;
        }

        return bc.monsters.arr[a.getTargetIdx()].isTargetable();
    }


}

bool isValidCardAction(const BattleContext &bc, const search::Action &a) {
    if (bc.inputState != InputState::PLAYER_NORMAL) {
        return false;
    }

    if (!bc.isCardPlayAllowed()) {
        return false;
    }

    if (a.getSourceIdx() < 0 || a.getSourceIdx() >= bc.cards.cardsInHand) {
        return false;
    }

    const auto &c = bc.cards.hand[a.getSourceIdx()];

    if (a.getTargetIdx() < 0 || a.getTargetIdx() >= 5) {
        return false;
    }

    return c.canUse(bc, a.getTargetIdx(), false);
}

bool isValidSingleCardSelectAction(const BattleContext &bc, const search::Action &a) {
    if (bc.inputState != InputState::CARD_SELECT) {
        return false;
    }

    switch (bc.cardSelectInfo.cardSelectTask) {
        case CardSelectTask::CODEX:
            return a.getSelectIdx() >= 0 && a.getSelectIdx() < 4;

        case CardSelectTask::DISCOVERY:
            return a.getSelectIdx() >= 0 && a.getSelectIdx() < 3;

        case CardSelectTask::HOLOGRAM:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
        case CardSelectTask::HEADBUTT:
        case CardSelectTask::MEDITATE:
            return a.getSelectIdx() >= 0 && a.getSelectIdx() < bc.cards.discardPile.size();

        case CardSelectTask::EXHUME:
            if (a.getSelectIdx() < 0 || a.getSelectIdx() >= bc.cards.exhaustPile.size()) {
                return false;
            }
            return bc.cards.exhaustPile[a.getSelectIdx()].id != sts::CardId::EXHUME;

        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::WARCRY:
            return a.getSelectIdx() >= 0 && a.getSelectIdx() < bc.cards.cardsInHand;

        case CardSelectTask::ARMAMENTS:
            if (a.getSelectIdx() < 0 || a.getSelectIdx() >= bc.cards.cardsInHand) {
                return false;
            }
            return bc.cards.hand[a.getSelectIdx()].canUpgrade();

        case CardSelectTask::DUAL_WIELD: {
            if (a.getSelectIdx() < 0 || a.getSelectIdx() >= bc.cards.cardsInHand) {
                return false;
            }
            const auto &c = bc.cards.hand[a.getSelectIdx()];
            return c.getType() == sts::CardType::POWER || c.getType() == sts::CardType::ATTACK;
        }

        case CardSelectTask::SECRET_TECHNIQUE: {
            if (a.getSelectIdx() < 0 || a.getSelectIdx() >= bc.cards.drawPile.size()) {
                return false;
            }
            return bc.cards.drawPile[a.getSelectIdx()].getType() == CardType::SKILL;
        }

        case CardSelectTask::SECRET_WEAPON: {
            if (a.getSelectIdx() < 0 || a.getSelectIdx() >= bc.cards.drawPile.size()) {
                return false;
            }
            return bc.cards.drawPile[a.getSelectIdx()].getType() == CardType::ATTACK;
        }

        case CardSelectTask::SEEK:
            return a.getSelectIdx() >= 0 && a.getSelectIdx() < bc.cards.drawPile.size();

        case CardSelectTask::EXHAUST_MANY:
        case CardSelectTask::GAMBLE:
        default:
            return false;
    }
}

bool isValidMultiCardSelectAction(const BattleContext &bc, const search::Action &a) { // this can be sped up using compiler intrinsics
    if (bc.inputState != InputState::CARD_SELECT) {
        return false;
    }

    switch (bc.cardSelectInfo.cardSelectTask) {
        case sts::CardSelectTask::EXHAUST_MANY: {
            const auto selected = a.getSelectedIdxs();
            if (selected.size() > bc.cardSelectInfo.pickCount) {
                return false;
            }
            for (auto x : selected) {
                if (x >= bc.cards.cardsInHand) {
                    return false;
                }
            }
            return true;
        }

        case sts::CardSelectTask::GAMBLE: {
            const auto selected = a.getSelectedIdxs();
            for (auto x : selected) {
                if (x >= bc.cards.cardsInHand) {
                    return false;
                }
            }
            return true;
        }

        default:
            return false;
    }
}

bool search::Action::isValidAction(const BattleContext &bc) const {
    if (bc.outcome != Outcome::UNDECIDED) {
        return false;
    }

    switch (getActionType()) {
        case ActionType::CARD:
            return isValidCardAction(bc, *this);

        case ActionType::POTION:
            return isValidPotionAction(bc, *this);

        case ActionType::SINGLE_CARD_SELECT:
            return isValidSingleCardSelectAction(bc, *this);

        case ActionType::MULTI_CARD_SELECT:
            return isValidMultiCardSelectAction(bc, *this);

        case ActionType::END_TURN:
            return bc.inputState == InputState::PLAYER_NORMAL;

        default:
            return false;
    }
}

std::ostream& printSingleCardSelectDescHelper(std::ostream &os, const BattleContext &bc, const search::Action &a) {
    // action is known to be valid here
    os << "{ " << cardSelectTaskStrings[static_cast<int>(bc.cardSelectInfo.cardSelectTask)];
    os << " (" << a.getSelectIdx() << ") ";
    // TODO we don't know if it's selecting from hand or discard
    // const auto &c = bc.cards.hand[a.getSelectIdx()];
    // c.printSimpleDesc(os);
    return os << " }";
}

std::ostream& printMultiCardSelectDescHelper(std::ostream &os, const BattleContext &bc, const search::Action &a) {
    // action is known to be valid here
    os << "{ " << cardSelectTaskStrings[static_cast<int>(bc.cardSelectInfo.cardSelectTask)];

    const auto selected = a.getSelectedIdxs();
    if (selected.empty()) {
        return os << " none";
    }

    for (int i = 0; i < selected.size(); ++i) {
        os << " (" << a.getSelectIdx() << ") ";
        const auto &c = bc.cards.hand[selected[i]];
        c.printSimpleDesc(os);
        if (i+1 < selected.size()) {
            os << ',';
        }
    }

    return os << " }";
}

std::ostream& search::Action::printDesc(std::ostream &os, const BattleContext &bc) const {
    if (!isValidAction(bc)) {
        return os << "{ INVALID ACTION }";
    }

    switch (getActionType()) {
        case ActionType::CARD: {
            const auto &c = bc.cards.hand[getSourceIdx()];
            os << "{ use card (" << getSourceIdx() << ") " << c;
            if (c.requiresTarget()) {
                const auto &m = bc.monsters.arr[getTargetIdx()];
                os << " -> (" << getTargetIdx() << ") " << m.getName();
            }
            return os << " }";
        }

        case ActionType::POTION: {
            const auto &p = bc.potions[getSourceIdx()];
            os << "{ ";
            if (getTargetIdx() == -1) {
                os << "discard potion ";
            } else {
                os << "drink potion ";
            }

            os << "(" << getSourceIdx() << ") " << getPotionName(p);

            if (potionRequiresTarget(p)) {
                const auto &m = bc.monsters.arr[getTargetIdx()];
                os << " -> (" << getTargetIdx() << ") " << m.getName();
            }
            return os << " }";
        }

        case ActionType::SINGLE_CARD_SELECT:
            return printSingleCardSelectDescHelper(os, bc, *this);

        case ActionType::MULTI_CARD_SELECT:
            return printMultiCardSelectDescHelper(os, bc, *this);

        case ActionType::END_TURN:
            return os << "{ end turn }";

        default:
            return os;
    }
}

void executeSingleCardSelectActionHelper(BattleContext &bc, search::Action a) {
    // assumed to be valid action here

    const auto idx = a.getSelectIdx();

    switch (bc.cardSelectInfo.cardSelectTask) {

        case CardSelectTask::ARMAMENTS:
            bc.chooseArmamentsCard(idx);
            break;

        case CardSelectTask::CODEX:
            if (idx != 3) { // idx 3 means skip
                bc.chooseCodexCard(bc.cardSelectInfo.codexCards()[idx]);
            }
            break;

        case CardSelectTask::DISCOVERY:
            bc.chooseDiscoveryCard(bc.cardSelectInfo.discovery_Cards()[idx]);
            break;

        case CardSelectTask::DUAL_WIELD:
            bc.chooseDualWieldCard(idx);
            break;

        case CardSelectTask::EXHAUST_ONE:
            bc.chooseExhaustOneCard(idx);
            break;

        case CardSelectTask::EXHUME:
            bc.chooseExhumeCard(idx);
            break;

        case CardSelectTask::FORETHOUGHT:
            bc.chooseForethoughtCard(idx);
            break;

        case CardSelectTask::HEADBUTT:
            bc.chooseHeadbuttCard(idx);
            break;

        case CardSelectTask::HOLOGRAM:
            bc.chooseDiscardToHandCard(idx, false);
            break;

        case CardSelectTask::LIQUID_MEMORIES_POTION:
            bc.chooseDiscardToHandCard(idx, true);
            break;

        case CardSelectTask::SECRET_TECHNIQUE:
            bc.chooseDrawToHandCards(&idx, 1);
            break;

        case CardSelectTask::SECRET_WEAPON:
            bc.chooseDrawToHandCards(&idx, 1);
            break;

        case CardSelectTask::WARCRY:
            bc.chooseWarcryCard(idx);
            break;

        case CardSelectTask::MEDITATE:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::SEEK:
            // not implemented
        case CardSelectTask::INVALID:
        default:
            break;
    }
}

void executeMultiCardSelectActionHelper(BattleContext &bc, search::Action a) {
    // assumed to be valid action here
    switch (bc.cardSelectInfo.cardSelectTask) {

        case sts::CardSelectTask::EXHAUST_MANY:
            bc.chooseExhaustCards(a.getSelectedIdxs());
            break;

        case sts::CardSelectTask::GAMBLE:
            bc.chooseGambleCards(a.getSelectedIdxs());
            break;

        default:
            break;
    }
}

void search::Action::execute(BattleContext &bc) const {
#ifdef sts_asserts
    if (!isValidAction(bc)) {
        std::cerr << bc.seed << " " << static_cast<int>(getActionType()) << " " << getSourceIdx() << " " << getTargetIdx() << std::endl;
        std::cerr <<  cardSelectTaskStrings[static_cast<int>(bc.cardSelectInfo.cardSelectTask)] << std::endl;
        std::cerr << bc << std::endl;
        assert(false);
    }
#endif

    switch (getActionType()) {
        case ActionType::CARD: {
            const CardQueueItem item(bc.cards.hand[getSourceIdx()], getTargetIdx(), bc.player.energy);
            bc.addToBotCard(item);
            break;
        }

        case ActionType::POTION: {
            if (getTargetIdx() > 5) {
                bc.discardPotion(getSourceIdx());
            } else {
                bc.drinkPotion(getSourceIdx(), getTargetIdx());
            }
            break;
        }

        case ActionType::SINGLE_CARD_SELECT:
            executeSingleCardSelectActionHelper(bc, *this);
            break;

        case ActionType::MULTI_CARD_SELECT:
            executeMultiCardSelectActionHelper(bc, *this);
            break;

        case ActionType::END_TURN:
            bc.endTurn();
            break;

        default:
            break;
    }

    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
}

template <typename ForwardIt>
void setupCardOptionsHelper(std::vector<search::Action> &actions, const ForwardIt begin, const ForwardIt end, const std::function<bool(const CardInstance &)> &p= nullptr) {
    for (int i = 0; begin+i != end; ++i) {
        const auto &c = begin[i];
        if (!p || (p(c))) {
            actions.emplace_back(search::ActionType::SINGLE_CARD_SELECT, i);
        }
    }
}

static int popcountInt(std::uint32_t x) {
    int n = 0;
    while (x) {
        n += static_cast<int>(x & 1u);
        x >>= 1;
    }
    return n;
}

// Multi-select enumeration mode (env STS_MULTISELECT_MODE):
//   all    - every subset of the hand (the full validity contract; can be
//            1023 actions at a 10-card Gambler's Brew state, which thins the
//            search dangerously at fixed simulation budgets);
//   single - empty + each single card + the whole hand (<= n+2 actions) --
//            the deployment mode: searchable, and still always valid;
//   none   - empty selection only (conservative no-op).
// The cardselect_parity test checks the `all` contract.
enum class MultiSelectMode { ALL, SINGLE, NONE };
static MultiSelectMode multiSelectMode() {
    static const MultiSelectMode m = [] {
        const char *e = std::getenv("STS_MULTISELECT_MODE");
        if (e && std::strcmp(e, "none") == 0) return MultiSelectMode::NONE;
        if (e && std::strcmp(e, "single") == 0) return MultiSelectMode::SINGLE;
        return MultiSelectMode::ALL;
    }();
    return m;
}

// Multi-select mask canonicalization (env STS_MULTISELECT_CANONICAL, default
// off): collapse bitmask choices that select the same multiset of identical
// hand cards (e.g. exhausting Strikes at hand positions {0,1} vs {0,2}).
static bool multiSelectCanonical() {
    static const bool c = [] {
        const char *e = std::getenv("STS_MULTISELECT_CANONICAL");
        return e && std::atoi(e) != 0;
    }();
    return c;
}

// Identity key for one hand card: (id, upgradeCount, costForTurn,
// freeToPlayOnce, specialData) -- the same equivalence the PLAYER_NORMAL
// duplicate collapse uses (playerNormalGroundTruth in apps/test.cpp), so only
// interchangeable copies collapse while upgraded/temporarily-modified copies
// stay distinct. Packed into 49 bits so a multiset key is a sortable vector.
static std::uint64_t cardIdentityKey(const CardInstance &c) {
    std::uint64_t k = static_cast<std::uint64_t>(static_cast<std::uint16_t>(c.getId()));
    k |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.getUpgradeCount())) << 16;
    k |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.costForTurn)) << 24;
    k |= static_cast<std::uint64_t>(c.freeToPlayOnce ? 1u : 0u) << 32;
    k |= static_cast<std::uint64_t>(static_cast<std::uint16_t>(c.specialData)) << 33;
    return k;
}

static void pushMultiSelectActions(std::vector<search::Action> &actions,
                                   const BattleContext &bc, bool cappedByPickCount) {
    const int n = bc.cards.cardsInHand;
    if (n < 0 || n > 10) return;
    const int limit = bc.cardSelectInfo.pickCount;
    const MultiSelectMode m = multiSelectMode();
    const bool canonical = multiSelectCanonical();
    const std::uint32_t full = (1u << n) - 1;
    // Canonicalization bookkeeping: per multi-select task, keep only the first
    // mask whose selected-card multiset key was not seen before.
    std::set<std::vector<std::uint64_t>> seenKeys;
    const auto emit = [&](std::uint32_t mask) {
        const search::Action a(search::ActionType::MULTI_CARD_SELECT, (int)mask);
        if (canonical) {
            std::vector<std::uint64_t> key;
            for (int idx : a.getSelectedIdxs()) {
                key.push_back(cardIdentityKey(bc.cards.hand[idx]));
            }
            std::sort(key.begin(), key.end());
            if (!seenKeys.insert(std::move(key)).second) return;
        }
        actions.push_back({a});
    };

    if (m == MultiSelectMode::NONE) {
        if (!cappedByPickCount || 0 <= limit)
            actions.push_back({search::Action(search::ActionType::MULTI_CARD_SELECT, 0)});
        return;
    }
    if (m == MultiSelectMode::SINGLE) {
        if (!cappedByPickCount || 0 <= limit)
            actions.push_back({search::Action(search::ActionType::MULTI_CARD_SELECT, 0)});
        for (int i = 0; i < n; ++i)
            if (!cappedByPickCount || 1 <= limit)
                emit(1u << i);
        if (n > 1 && (!cappedByPickCount || n <= limit))
            actions.push_back({search::Action(search::ActionType::MULTI_CARD_SELECT, (int)full)});
        return;
    }
    for (std::uint32_t mask = 0; mask < (1u << n); ++mask) {
        if (!cappedByPickCount || popcountInt(mask) <= limit) {
            emit(mask);
        }
    }
}

std::vector<search::Action> search::Action::enumerateCardSelectActions(const BattleContext &bc) {
    std::vector<search::Action> actions;
    const auto &csi = bc.cardSelectInfo;

    switch (csi.cardSelectTask) {
        case CardSelectTask::ARMAMENTS:
            setupCardOptionsHelper( actions, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand,
                                    [] (const CardInstance &c) { return c.canUpgrade(); });
            break;

        case CardSelectTask::CODEX:
            for (int i = 0; i < 4; ++i) { // i -> 3 action means skip
                actions.push_back({Action(search::ActionType::SINGLE_CARD_SELECT, i)});
            }
            break;

        case CardSelectTask::DISCOVERY:
            for (int i = 0; i < 3; ++i) {
                actions.push_back({Action(search::ActionType::SINGLE_CARD_SELECT, i)});
            }
            break;

        case CardSelectTask::DUAL_WIELD:
            setupCardOptionsHelper( actions, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand,
                                    [] (const CardInstance &c) {
                                        return c.getType() == CardType::POWER || c.getType() == CardType::ATTACK;
                                    });
            break;

        case CardSelectTask::EXHUME:
            setupCardOptionsHelper(actions, bc.cards.exhaustPile.begin(), bc.cards.exhaustPile.end(),
                                   [](const auto &c) { return c.getId() != CardId::EXHUME; });
            break;

        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::WARCRY:
            setupCardOptionsHelper(actions, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand);
            break;

        case CardSelectTask::HEADBUTT:
        case CardSelectTask::HOLOGRAM:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
        case CardSelectTask::MEDITATE:
            setupCardOptionsHelper(actions, bc.cards.discardPile.begin(), bc.cards.discardPile.end());
            break;

        case CardSelectTask::SECRET_TECHNIQUE:
            setupCardOptionsHelper(actions, bc.cards.drawPile.begin(), bc.cards.drawPile.end(),
                                   [] (const CardInstance &c) {
                                       return c.getType() == CardType::SKILL;
                                   });
            break;

        case CardSelectTask::SECRET_WEAPON:
            setupCardOptionsHelper(actions, bc.cards.drawPile.begin(), bc.cards.drawPile.end(),
                                   [] (const CardInstance &c) {
                                       return c.getType() == CardType::ATTACK;
                                   });
            break;

        case CardSelectTask::SEEK:
            setupCardOptionsHelper(actions, bc.cards.drawPile.begin(), bc.cards.drawPile.end());
            break;

        case CardSelectTask::EXHAUST_MANY:
            pushMultiSelectActions(actions, bc, /*cappedByPickCount=*/true);
            break;

        case CardSelectTask::GAMBLE:
            pushMultiSelectActions(actions, bc, /*cappedByPickCount=*/false);
            break;

        default:
            break;
    }
    return actions;
}





