#include "sim/search/OocSemanticAction.h"

#include <algorithm>
#include <nlohmann/json.hpp>
#include <locale>
#include <optional>
#include <sstream>
#include <tuple>
#include <type_traits>
#include <utility>

#include "sim/search/GameAction.h"

namespace sts::search {
namespace {
using Effect = OocSemanticEffect;
using Source = OocSemanticSource;
using Select = CardSelectScreenType;
using RT = GameAction::RewardsActionType;

bool validCard(const Card &c) { return c.id > CardId::INVALID && c.id <= CardId::ZAP; }
bool validRelic(RelicId relic) { return relic < RelicId::INVALID; }
bool validEntity(const OocEntity &entity) {
    return std::visit([](const auto &v) {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, Card>) return validCard(v);
        else if constexpr (std::is_same_v<T, RelicId>) return validRelic(v);
        else if constexpr (std::is_same_v<T, Potion>) return v >= Potion::AMBROSIA && v <= Potion::WEAK_POTION;
        else if constexpr (std::is_same_v<T, Key>) return v == Key::SAPPHIRE_KEY || v == Key::EMERALD_KEY;
        else if constexpr (std::is_same_v<T, int>) return v >= 0;
        else return true;
    }, entity);
}

void writeCard(std::ostream &out, const Card &c) {
    out << static_cast<int>(c.id) << ',' << c.misc << ',' << c.upgraded;
}
void writeDeckTarget(std::ostream &out, const OocCardTarget &c) {
    out << ":card=" << static_cast<int>(c.id) << ":misc=" << c.misc
        << ":upgraded=" << (c.upgraded ? 1 : 0) << ":bottle=" << static_cast<int>(c.bottleSlot)
        << ":occurrence=" << c.occurrence;
}
void writeEntity(std::ostream &out, const OocEntity &entity) {
    std::visit([&](const auto &v) {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, OocNoTarget>) out << "none";
        else if constexpr (std::is_same_v<T, Card>) { out << "card,"; writeCard(out, v); }
        else if constexpr (std::is_same_v<T, RelicId>) out << "relic," << static_cast<int>(v);
        else if constexpr (std::is_same_v<T, Potion>) out << "potion," << static_cast<int>(v);
        else if constexpr (std::is_same_v<T, Key>) out << "key," << static_cast<int>(v);
        else out << "gold," << v;
    }, entity);
}

OocCardTarget targetForDeckIndex(const Deck &deck, int index) {
    const auto &c = deck.cards[index];
    int bottle = -1;
    for (int i = 0; i < 3; ++i) if (deck.bottleIdxs[i] == index) bottle = i;
    OocCardTarget target {c.id, c.misc, c.upgraded, static_cast<std::int8_t>(bottle), 0};
    for (int i = 0; i < index; ++i) {
        if (deck.cards[i] == c && !deck.isCardBottled(i) && bottle == -1) ++target.occurrence;
    }
    return target;
}

bool sameTarget(const OocCardTarget &a, const OocCardTarget &b) {
    return std::tie(a.id, a.misc, a.upgraded, a.bottleSlot, a.occurrence)
        == std::tie(b.id, b.misc, b.upgraded, b.bottleSlot, b.occurrence);
}

bool eligible(const Deck &deck, int index, Select type) {
    const auto &c = deck.cards[index];
    switch (type) {
        case Select::UPGRADE: return c.canUpgrade();
        case Select::REMOVE:
        case Select::TRANSFORM:
        case Select::BONFIRE_SPIRITS: return c.canTransform() && !deck.isCardBottled(index);
        case Select::TRANSFORM_UPGRADE: return c.canTransform();
        case Select::DUPLICATE: return true;
        default: return false;
    }
}

// Bindings exist only during this call. Nothing below is stored in semantic
// identity; in particular a compound's target is re-resolved after its source.
struct Binding {
    OocSemanticAction action;
    GameAction primitive;
    Select compound = Select::INVALID;
    ScreenState boundary = ScreenState::INVALID;
};
struct Bindings {
    bool supported = true;
    bool complete = true;
    std::string error;
    std::vector<Binding> values;

    void fail(const std::string &why) { complete = false; if (error.empty()) error = why; }
    void add(const GameContext &gc, Effect effect, Source source, OocSemanticPayload target,
             GameAction primitive, Select compound = Select::INVALID,
             ScreenState boundary = ScreenState::INVALID) {
        if (!primitive.isValidAction(gc)) { fail("resolved source primitive is not legal"); return; }
        values.push_back({{effect, source, std::move(target)}, primitive, compound, boundary});
    }
};

void addCompound(Bindings &out, const GameContext &gc, Effect effect, Source source,
                 GameAction primitive, Select type, ScreenState boundary,
                 Event event = Event::INVALID, int option = -1, int cost = 0) {
    bool any = false;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!eligible(gc.deck, i, type)) continue;
        any = true;
        const auto card = targetForDeckIndex(gc.deck, i);
        OocSemanticPayload target = card;
        if (source != Source::CAMPFIRE_SMITH && source != Source::CAMPFIRE_PEACE_PIPE)
            target = OocTransactionTarget {card, event, option, cost};
        out.add(gc, effect, source, target, primitive, type, boundary);
    }
    if (!any) out.fail("legal source has no public eligible single-card targets");
}


std::vector<Card> cardGroup(const CardReward &cards) {
    std::vector<Card> result(cards.begin(), cards.end());
    std::sort(result.begin(), result.end(), [](const Card &a, const Card &b) {
        return std::tie(a.id, a.misc, a.upgraded) < std::tie(b.id, b.misc, b.upgraded);
    });
    return result;
}

std::string entityKey(const OocEntity &entity) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    writeEntity(out, entity);
    return out.str();
}

void addRewards(Bindings &out, const GameContext &gc) {
    const auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount < 0 || r.goldRewardCount > 2 || r.cardRewardCount < 0 || r.cardRewardCount > 5
            || r.relicCount < 0 || r.relicCount > 3 || r.potionCount < 0 || r.potionCount > 5
            || (r.sapphireKey && r.emeraldKey)) {
        out.fail("malformed reward container or mutually exclusive keys"); return;
    }
    auto item = [&](Effect effect, OocEntity entity, RT primitiveType, int idx, bool paired = false) {
        if (!validEntity(entity)) { out.fail("invalid active reward entity"); return; }
        OocRewardTarget target;
        target.entity = entity;
        target.sapphirePaired = paired;
        for (const auto &prior : out.values) {
            const auto *p = std::get_if<OocRewardTarget>(&prior.action.target);
            if (prior.action.effect == effect && p && p->sapphirePaired == paired
                    && entityKey(p->entity) == entityKey(entity)) ++target.occurrence;
        }
        out.add(gc, effect, Source::REWARDS, target, GameAction(primitiveType, idx));
    };
    for (int i = 0; i < r.goldRewardCount; ++i) item(Effect::TAKE_GOLD, r.gold[i], RT::GOLD, i);
    for (int i = 0; i < r.relicCount; ++i)
        item(Effect::TAKE_RELIC, r.relics[i], RT::RELIC, i, r.sapphireKey && i == r.relicCount-1);
    // The live MCP reward boundary has no discard-potion command.  Do not
    // present a potion take that cannot execute with a full inventory; leave
    // the reward available for another reward or the screen skip action.
    if (gc.potionCount < gc.potionCapacity) {
        for (int i = 0; i < r.potionCount; ++i)
            item(Effect::TAKE_POTION, r.potions[i], RT::POTION, i);
    }
    if (r.sapphireKey) item(Effect::TAKE_KEY, Key::SAPPHIRE_KEY, RT::KEY, 0, true);
    if (r.emeraldKey) item(Effect::TAKE_KEY, Key::EMERALD_KEY, RT::KEY, 0);
    for (int group = 0; group < r.cardRewardCount; ++group) {
        if (r.cardRewards[group].size() < 0 || r.cardRewards[group].size() > 4) {
            out.fail("invalid reward card group size"); return;
        }
        for (const auto &card : r.cardRewards[group]) {
            if (!validCard(card)) { out.fail("invalid active reward card"); return; }
        }
        OocRewardTarget target;
        target.cardGroup = cardGroup(r.cardRewards[group]);
        for (int j = 0; j < group; ++j)
            if (cardGroup(r.cardRewards[j]) == target.cardGroup) ++target.groupOccurrence;
        for (int i = 0; i < r.cardRewards[group].size(); ++i) {
            target.entity = r.cardRewards[group][i];
            target.occurrence = 0;
            for (int j = 0; j < i; ++j)
                if (r.cardRewards[group][j] == r.cardRewards[group][i]) ++target.occurrence;
            out.add(gc, Effect::TAKE_CARD, Source::REWARDS, target, GameAction(RT::CARD, group, i));
        }
        target.entity = OocNoTarget{};
        target.occurrence = 0;
        out.add(gc, gc.hasRelic(RelicId::SINGING_BOWL) ? Effect::SINGING_BOWL : Effect::SKIP_CARD_REWARD,
                Source::REWARDS, target, GameAction(RT::CARD, group, 5));
    }
    out.add(gc, Effect::LEAVE_REWARDS, Source::REWARDS, OocNoTarget{}, GameAction(RT::SKIP));
}

void addShop(Bindings &out, const GameContext &gc) {
    const auto &shop = gc.info.shop;
    for (const auto primitive : GameAction::getAllActionsInState(gc)) {
        const int i = primitive.getIdx1();
        Effect effect;
        OocShopTarget target;
        if (!isSupportedAutonomousOocAction(gc, primitive))
            continue;
        switch (primitive.getRewardsActionType()) {
            case RT::CARD: effect = Effect::BUY_CARD; target.entity = shop.cards[i]; target.expectedPrice = shop.cardPrice(i); break;
            case RT::RELIC: effect = Effect::BUY_RELIC; target.entity = shop.relics[i]; target.expectedPrice = shop.relicPrice(i); break;
            case RT::POTION: effect = Effect::BUY_POTION; target.entity = shop.potions[i]; target.expectedPrice = shop.potionPrice(i); break;
            case RT::CARD_REMOVE:
                if (shop.removeCost < 0) { out.fail("invalid shop removal price"); continue; }
                addCompound(out, gc, Effect::REMOVE_CARD, Source::SHOP_REMOVE, primitive,
                            Select::REMOVE, ScreenState::SHOP_ROOM, Event::INVALID, -1, shop.removeCost);
                continue;
            case RT::SKIP:
                out.add(gc, Effect::LEAVE_SHOP, Source::SHOP, OocNoTarget{}, primitive);
                continue;
            default: out.fail("unrecognized shop primitive"); continue;
        }
        if (target.expectedPrice < 0 || !validEntity(target.entity)) {
            out.fail("invalid active shop entity or price"); continue;
        }
        for (const auto &prior : out.values) {
            const auto *p = std::get_if<OocShopTarget>(&prior.action.target);
            if (prior.action.effect == effect && p && p->expectedPrice == target.expectedPrice
                    && entityKey(p->entity) == entityKey(target.entity)) ++target.occurrence;
        }
        out.add(gc, effect, Source::SHOP, target, primitive);
    }
}

void addCampsite(Bindings &out, const GameContext &gc) {
    for (const auto primitive : GameAction::getAllActionsInState(gc)) {
        switch (primitive.getIdx1()) {
            case 0: out.add(gc, Effect::REST, Source::CAMPFIRE, OocNoTarget{}, primitive); break;
            case 1: addCompound(out, gc, Effect::UPGRADE_CARD, Source::CAMPFIRE_SMITH,
                               primitive, Select::UPGRADE, ScreenState::MAP_SCREEN); break;
            case 2: out.add(gc, Effect::TAKE_RUBY_KEY, Source::CAMPFIRE, OocNoTarget{}, primitive); break;
            case 3: out.add(gc, Effect::LIFT, Source::CAMPFIRE, OocNoTarget{}, primitive); break;
            case 4: addCompound(out, gc, Effect::REMOVE_CARD, Source::CAMPFIRE_PEACE_PIPE,
                               primitive, Select::REMOVE, ScreenState::MAP_SCREEN); break;
            case 5: out.add(gc, Effect::DIG, Source::CAMPFIRE, OocNoTarget{}, primitive); break;
            case 6: out.add(gc, Effect::LEAVE_CAMPFIRE, Source::CAMPFIRE, OocNoTarget{}, primitive); break;
            default: out.fail("unrecognized campsite primitive"); break;
        }
    }
}


struct EventTransaction {
    Event event;
    int option;
    Effect effect;
    Select selector;
    int goldBelow15 = 0;
    int goldAt15 = 0;
    int targetCount = 1;
    bool publicCandidates = true;
    ScreenState boundary = ScreenState::MAP_SCREEN;
};

// Metadata only: every effect (including Designer's automatic RNG upgrade)
// still runs through chooseEventOption + chooseSelectCardScreenOption.
constexpr EventTransaction eventTransactions[] = {
    {Event::OMINOUS_FORGE, 0, Effect::UPGRADE_CARD, Select::UPGRADE},
    {Event::ANCIENT_WRITING, 0, Effect::REMOVE_CARD, Select::REMOVE},
    {Event::OLD_BEGGAR, 0, Effect::REMOVE_CARD, Select::REMOVE, 75, 75},
    {Event::DESIGNER_IN_SPIRE, 0, Effect::UPGRADE_CARD, Select::UPGRADE, 40, 50},
    {Event::DESIGNER_IN_SPIRE, 2, Effect::REMOVE_CARD, Select::REMOVE, 60, 75},
    {Event::DESIGNER_IN_SPIRE, 4, Effect::REMOVE_CARD, Select::REMOVE, 90, 110},
    {Event::DUPLICATOR, 0, Effect::DUPLICATE_CARD, Select::DUPLICATE},
    {Event::LIVING_WALL, 0, Effect::REMOVE_CARD, Select::REMOVE},
    {Event::LIVING_WALL, 1, Effect::TRANSFORM_CARD, Select::TRANSFORM},
    {Event::LIVING_WALL, 2, Effect::UPGRADE_CARD, Select::UPGRADE},
    {Event::PURIFIER, 0, Effect::REMOVE_CARD, Select::REMOVE},
    {Event::THE_CLERIC, 1, Effect::REMOVE_CARD, Select::REMOVE, 50, 75},
    {Event::TRANSMORGRIFIER, 0, Effect::TRANSFORM_CARD, Select::TRANSFORM},
    {Event::UPGRADE_SHRINE, 0, Effect::UPGRADE_CARD, Select::UPGRADE},
    {Event::WING_STATUE, 0, Effect::REMOVE_CARD, Select::REMOVE},
};

void addEvents(Bindings &out, const GameContext &gc) {
    if (gc.curEvent == Event::MATCH_AND_KEEP) {
        out.supported = false; out.fail("disabled Match and Keep has no complete primitive enumeration"); return;
    }
    const auto primitives = GameAction::getAllActionsInState(gc);
    if (primitives.empty()) { out.fail("event has no enumerated legal options"); return; }
    for (const auto primitive : primitives) {
        const EventTransaction *mapping = nullptr;
        for (const auto &entry : eventTransactions) {
            if (entry.event == gc.curEvent && entry.option == primitive.getIdx1()) mapping = &entry;
        }
        // Seven damage precedes Wing Statue's selector. At low HP preserve the
        // source boundary rather than promise that the player can pick a card.
        if (gc.curEvent == Event::WING_STATUE && gc.curHp <= 7) mapping = nullptr;
        if (mapping && gc.gold < (gc.ascension < 15 ? mapping->goldBelow15 : mapping->goldAt15))
            mapping = nullptr;
        if (mapping && mapping->targetCount == 1 && mapping->publicCandidates) {
            addCompound(out, gc, mapping->effect, Source::EVENT, primitive, mapping->selector,
                        mapping->boundary, gc.curEvent, mapping->option,
                        gc.ascension < 15 ? mapping->goldBelow15 : mapping->goldAt15);
        } else {
            // Includes Note for Yourself: obtaining the offered card happens
            // before the removal candidates, and can have obtain-trigger effects.
            out.add(gc, Effect::EVENT_CHOICE, Source::EVENT,
                    OocEventTarget{gc.curEvent, primitive.getIdx1()}, primitive);
        }
    }
}

std::optional<Effect> selectorEffect(Select type) {
    switch (type) {
        case Select::UPGRADE: return Effect::UPGRADE_CARD;
        case Select::REMOVE: return Effect::REMOVE_CARD;
        case Select::TRANSFORM: return Effect::TRANSFORM_CARD;
        case Select::TRANSFORM_UPGRADE: return Effect::TRANSFORM_UPGRADE_CARD;
        case Select::DUPLICATE: return Effect::DUPLICATE_CARD;
        case Select::OBTAIN: return Effect::TAKE_CARD;
        case Select::BOTTLE: return Effect::BOTTLE_CARD;
        case Select::BONFIRE_SPIRITS: return Effect::SACRIFICE_CARD;
        default: return std::nullopt;
    }
}

void addSelector(Bindings &out, const GameContext &gc) {
    const auto &info = gc.info;
    const auto effect = selectorEffect(info.selectScreenType);
    if (!effect) { out.supported = false; out.fail("unsupported selector semantics"); return; }
    const int completed = info.haveSelectedCards.size();
    const int remaining = info.toSelectCount - completed;
    if (completed < 0 || completed > 3 || info.toSelectCount < 1 || info.toSelectCount > 3 || remaining < 1
            || remaining > info.toSelectCards.size() || info.toSelectCards.size() > Deck::MAX_SIZE) {
        out.fail("malformed or exhausted selector cardinality"); return;
    }
    for (int i = 0; i < completed; ++i) {
        const auto &prior = info.haveSelectedCards[i];
        if (!validCard(prior.card)) { out.fail("invalid previously selected card"); return; }
        if (info.selectScreenType != Select::OBTAIN) {
            if (prior.deckIdx < 0 || prior.deckIdx >= gc.deck.size()
                    || prior.card != gc.deck.cards[prior.deckIdx]) {
                out.fail("previously selected card is stale or outside live deck"); return;
            }
            for (int j = 0; j < i; ++j) if (info.haveSelectedCards[j].deckIdx == prior.deckIdx) {
                out.fail("duplicate previously selected deck card"); return;
            }
        }
    }
    for (int i = 0; i < info.toSelectCards.size(); ++i) {
        const auto &candidate = info.toSelectCards[i];
        OocSelectorTarget target;
        target.type = info.selectScreenType;
        target.requiredPicks = info.toSelectCount;
        target.completedPicks = completed;
        if (info.selectScreenType == Select::OBTAIN) {
            OocCandidateTarget card {candidate.card, 0};
            if (!validCard(card.card)) { out.fail("invalid revealed card candidate"); continue; }
            for (int j = 0; j < i; ++j) if (info.toSelectCards[j].card == card.card) ++card.occurrence;
            target.card = card;
        } else {
            if (candidate.deckIdx < 0 || candidate.deckIdx >= gc.deck.size()
                    || candidate.card != gc.deck.cards[candidate.deckIdx]) {
                out.fail("selector candidate does not match current deck card"); continue;
            }
            bool alreadySelected = false;
            for (const auto &prior : info.haveSelectedCards)
                if (prior.deckIdx == candidate.deckIdx) alreadySelected = true;
            if (alreadySelected) { out.fail("selector offers an already selected deck card"); continue; }
            target.card = targetForDeckIndex(gc.deck, candidate.deckIdx);
        }
        out.add(gc, *effect, Source::SELECTOR, target, GameAction(i));
    }
}

void addBossRelics(Bindings &out, const GameContext &gc) {
    for (int i = 0; i < 3; ++i) {
        const auto relic = gc.info.bossRelics[i];
        if (!validRelic(relic)) { out.fail("invalid boss relic offer"); continue; }
        OocRelicTarget target {relic, 0};
        for (int j = 0; j < i; ++j) if (gc.info.bossRelics[j] == relic) ++target.occurrence;
        out.add(gc, Effect::TAKE_BOSS_RELIC, Source::BOSS_RELIC, target, GameAction(i));
    }
    out.add(gc, Effect::SKIP_BOSS_RELIC, Source::BOSS_RELIC, OocNoTarget{}, GameAction(3));
}

Bindings bindings(const GameContext &gc) {
    Bindings out;
    if (gc.outcome != GameOutcome::UNDECIDED) {
        out.supported = false; out.fail("terminal game has no semantic OOC decisions"); return out;
    }
    if (gc.deck.size() < 0 || gc.deck.size() > Deck::MAX_SIZE) {
        out.fail("invalid live deck size"); return out;
    }
    for (const auto &card : gc.deck.cards) {
        if (!validCard(card)) { out.fail("invalid live deck card"); return out; }
    }
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN: addEvents(out, gc); break;
        case ScreenState::CARD_SELECT: addSelector(out, gc); break;
        case ScreenState::BOSS_RELIC_REWARDS: addBossRelics(out, gc); break;
        case ScreenState::REST_ROOM: addCampsite(out, gc); break;
        case ScreenState::SHOP_ROOM: addShop(out, gc); break;
        case ScreenState::REWARDS: addRewards(out, gc); break;
        case ScreenState::TREASURE_ROOM:
            out.add(gc, Effect::OPEN_CHEST, Source::TREASURE, OocNoTarget{}, GameAction(0));
            out.add(gc, Effect::LEAVE_TREASURE, Source::TREASURE, OocNoTarget{}, GameAction(1));
            break;
        default:
            out.supported = false;
            out.fail("unsupported semantic OOC screen");
            break;
    }
    std::sort(out.values.begin(), out.values.end(), [](const Binding &a, const Binding &b) {
        return canonicalOocSemanticActionKey(a.action) < canonicalOocSemanticActionKey(b.action);
    });
    for (std::size_t i = 1; i < out.values.size(); ++i) {
        if (canonicalOocSemanticActionKey(out.values[i-1].action)
                == canonicalOocSemanticActionKey(out.values[i].action))
            out.fail("ambiguous semantic identity in live candidates");
    }
    return out;
}

int liveDeckSelection(const GameContext &gc, const OocCardTarget &target, std::string &error) {
    int found = -1;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i) {
        const auto &candidate = gc.info.toSelectCards[i];
        const int deckIdx = candidate.deckIdx;
        if (deckIdx < 0 || deckIdx >= gc.deck.size()) continue;
        if (candidate.card != gc.deck.cards[deckIdx]) continue;
        if (!sameTarget(targetForDeckIndex(gc.deck, deckIdx), target)) continue;
        if (found != -1) { error = "semantic target is ambiguous in live selector"; return -1; }
        found = i;
    }
    if (found == -1) error = "semantic target is absent from live selector";
    return found;
}
} // namespace

bool isSupportedAutonomousOocAction(const GameContext &gc, const GameAction &action) {
    if (gc.screenState != ScreenState::SHOP_ROOM
        || action.getRewardsActionType() != GameAction::RewardsActionType::RELIC)
        return true;
    const int index = action.getIdx1();
    return index < 0 || index >= 3
        || gc.info.shop.relics[index] != RelicId::PRISMATIC_SHARD;
}

std::string canonicalOocSemanticActionKey(const OocSemanticAction &action) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << "ooc:v" << OocSemanticAction::kSchemaVersion
        << ":effect=" << static_cast<int>(action.effect)
        << ":source=" << static_cast<int>(action.source);
    std::visit([&](const auto &v) {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, OocNoTarget>) out << ":none";
        else if constexpr (std::is_same_v<T, OocCardTarget>) writeDeckTarget(out, v);
        else if constexpr (std::is_same_v<T, OocTransactionTarget>) {
            out << ":transaction:event=" << static_cast<int>(v.event)
                << ":option=" << v.option << ":cost=" << v.expectedGoldCost;
            writeDeckTarget(out, v.card);
        } else if constexpr (std::is_same_v<T, OocSelectorTarget>) {
            out << ":selector=" << static_cast<int>(v.type) << ":required=" << v.requiredPicks
                << ":completed=" << v.completedPicks;
            std::visit([&](const auto &c) {
                using C = std::decay_t<decltype(c)>;
                if constexpr (std::is_same_v<C, OocCardTarget>) writeDeckTarget(out, c);
                else { out << ":candidate="; writeCard(out, c.card); out << ":occurrence=" << c.occurrence; }
            }, v.card);
        } else if constexpr (std::is_same_v<T, OocRewardTarget>) {
            out << ":reward="; writeEntity(out, v.entity);
            out << ":group=[";
            for (const auto &c : v.cardGroup) { writeCard(out, c); out << ';'; }
            out << "]:groupOccurrence=" << v.groupOccurrence << ":occurrence=" << v.occurrence
                << ":sapphirePaired=" << v.sapphirePaired;
        } else if constexpr (std::is_same_v<T, OocShopTarget>) {
            out << ":shop="; writeEntity(out, v.entity);
            out << ":price=" << v.expectedPrice << ":occurrence=" << v.occurrence;
        } else if constexpr (std::is_same_v<T, OocEventTarget>) {
            out << ":event=" << static_cast<int>(v.event) << ":option=" << v.option;
        } else if constexpr (std::is_same_v<T, OocRelicTarget>) {
            out << ":relic=" << static_cast<int>(v.relic) << ":occurrence=" << v.occurrence;
        }
    }, action.target);
    return out.str();
}

std::string oocSemanticActionPayloadJson(const OocSemanticAction &action) {
    using J = nlohmann::json;
    auto card = [](const Card &c) -> J { return {{"id", (int)c.id}, {"misc", c.misc}, {"upgraded", c.upgraded}}; };
    auto deck = [](const OocCardTarget &c) -> J { return {{"id", (int)c.id}, {"misc", c.misc}, {"upgraded", c.upgraded}, {"bottle", (int)c.bottleSlot}, {"occurrence", c.occurrence}}; };
    auto entity = [&](const OocEntity &e) -> J {
        return std::visit([&](const auto &v) -> J {
            using T = std::decay_t<decltype(v)>;
            if constexpr (std::is_same_v<T, OocNoTarget>) return {{"type", "none"}};
            else if constexpr (std::is_same_v<T, Card>) return {{"type", "card"}, {"value", card(v)}};
            else { const char *type = std::is_same_v<T, RelicId> ? "relic" : std::is_same_v<T, Potion> ? "potion" : std::is_same_v<T, Key> ? "key" : "gold"; return {{"type", type}, {"value", (int)v}}; }
        }, e);
    };
    return std::visit([&](const auto &v) -> J {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, OocNoTarget>) return {{"type", "none"}};
        else if constexpr (std::is_same_v<T, OocCardTarget>) return {{"type", "deck_card"}, {"card", deck(v)}};
        else if constexpr (std::is_same_v<T, OocTransactionTarget>) return {{"type", "transaction"}, {"card", deck(v.card)}, {"event", (int)v.event}, {"option", v.option}, {"expectedGoldCost", v.expectedGoldCost}};
        else if constexpr (std::is_same_v<T, OocSelectorTarget>) {
            J target = std::visit([&](const auto &c) -> J { using C = std::decay_t<decltype(c)>;
                if constexpr (std::is_same_v<C, OocCardTarget>) return {{"type", "deck_card"}, {"card", deck(c)}};
                else return {{"type", "candidate"}, {"card", card(c.card)}, {"occurrence", c.occurrence}};
            }, v.card);
            return {{"type", "selector"}, {"selectorType", (int)v.type}, {"requiredPicks", v.requiredPicks}, {"completedPicks", v.completedPicks}, {"target", target}};
        } else if constexpr (std::is_same_v<T, OocRewardTarget>) {
            J group = J::array(); for (const auto &c : v.cardGroup) group.push_back(card(c));
            return {{"type", "reward"}, {"entity", entity(v.entity)}, {"cardGroup", group}, {"groupOccurrence", v.groupOccurrence}, {"occurrence", v.occurrence}, {"sapphirePaired", v.sapphirePaired}};
        } else if constexpr (std::is_same_v<T, OocShopTarget>) return {{"type", "shop"}, {"entity", entity(v.entity)}, {"expectedPrice", v.expectedPrice}, {"occurrence", v.occurrence}};
        else if constexpr (std::is_same_v<T, OocEventTarget>) return {{"type", "event"}, {"event", (int)v.event}, {"option", v.option}};
        else return {{"type", "relic"}, {"relic", (int)v.relic}, {"occurrence", v.occurrence}};
    }, action.target).dump();
}

CardSelectScreenType oocSemanticPrimitiveCompoundSelector(const GameContext &gc, std::uint32_t bits) {
    const auto live = bindings(gc);
    if (!live.supported || !live.complete) return Select::INVALID;
    for (const auto &binding : live.values)
        if (binding.primitive.bits == bits && binding.compound != Select::INVALID) return binding.compound;
    return Select::INVALID;
}

OocSemanticPrimitiveBindings enumerateOocSemanticPrimitiveBindings(const GameContext &gc) {
    auto live = bindings(gc);
    OocSemanticPrimitiveBindings result {live.supported, live.complete, live.error, {}};
    for (auto &binding : live.values)
        result.bindings.push_back({std::move(binding.action), binding.primitive.bits, binding.compound});
    return result;
}

OocEnumerationResult enumerateOocSemanticActions(const GameContext &gc) {
    auto live = bindings(gc);
    OocEnumerationResult result {live.supported, live.complete, live.error, {}};
    for (auto &binding : live.values) result.actions.push_back(std::move(binding.action));
    return result;
}

std::vector<OocSemanticAction> enumerateCampfireUpgradeActions(const GameContext &gc) {
    auto all = enumerateOocSemanticActions(gc);
    std::vector<OocSemanticAction> result;
    for (auto &action : all.actions)
        if (action.source == Source::CAMPFIRE_SMITH) result.push_back(std::move(action));
    return result;
}

OocExecutionResult executeOocSemanticAction(GameContext &gc, const OocSemanticAction &action) {
    OocExecutionResult result;
    // The primitive hook can mutate external data before a transaction fails,
    // and existing observers bind the original context address. Do not silently
    // emit speculative observations or pretend those integrations see commits.
    if (g_onGameActionExecute) {
        result.error = "semantic execution requires the primitive GameAction observer to be detached";
        return result;
    }
    // Matching against freshly typed, legal candidates also rejects malformed
    // payload/effect/source combinations without trusting serialized input.
    auto live = bindings(gc);
    if (!live.supported || !live.complete) { result.error = live.error; return result; }
    const auto key = canonicalOocSemanticActionKey(action);
    const Binding *resolved = nullptr;
    for (const auto &binding : live.values) {
        if (canonicalOocSemanticActionKey(binding.action) != key) continue;
        if (resolved) { result.error = "ambiguous semantic action"; return result; }
        resolved = &binding;
    }
    if (!resolved) { result.error = "semantic action is stale, malformed, or unavailable in this source state"; return result; }

    GameContext next = gc;
    // Map is the only mutable shared object used by repository continuations.
    // Opaque caller-provided callbacks must themselves respect value semantics.
    if (gc.map) next.map = std::make_shared<Map>(*gc.map);
    try {
        if (!resolved->primitive.isValidAction(next)) { result.error = "source primitive became illegal"; return result; }
        resolved->primitive.execute(next);
        result.executedPrimitiveBits.push_back(resolved->primitive.bits);
        if (const auto *selection = std::get_if<OocSelectorTarget>(&action.target)) {
            const bool more = selection->completedPicks + 1 < selection->requiredPicks;
            if (more && (next.screenState != ScreenState::CARD_SELECT
                    || next.info.selectScreenType != selection->type
                    || next.info.haveSelectedCards.size() != selection->completedPicks + 1
                    || next.info.toSelectCards.size() != gc.info.toSelectCards.size() - 1)) {
                result.error = "selector pick did not reach expected next-pick boundary"; return result;
            }
            if (!more && next.screenState == ScreenState::CARD_SELECT
                    && next.info.selectScreenType == selection->type
                    && next.info.haveSelectedCards.size() == selection->requiredPicks) {
                result.error = "final selector pick did not leave completed selector"; return result;
            }
        }
        if (resolved->compound != Select::INVALID) {
            if (next.screenState != ScreenState::CARD_SELECT || next.info.selectScreenType != resolved->compound
                    || next.info.toSelectCount != 1 || !next.info.haveSelectedCards.empty()) {
                result.error = "source did not open expected single-target selector"; return result;
            }
            const auto *direct = std::get_if<OocCardTarget>(&action.target);
            const auto &target = direct ? *direct : std::get<OocTransactionTarget>(action.target).card;
            const int idx = liveDeckSelection(next, target, result.error);
            if (idx < 0) return result;
            const GameAction pick(idx);
            if (!pick.isValidAction(next)) { result.error = "resolved target primitive is illegal"; return result; }
            pick.execute(next);
            result.executedPrimitiveBits.push_back(pick.bits);
            if (next.screenState != resolved->boundary) {
                result.error = "compound did not reach expected completed boundary"; return result;
            }
        }
    } catch (const std::exception &e) {
        result.error = std::string("semantic primitive execution failed: ") + e.what(); return result;
    }
    gc = std::move(next);
    result.ok = true;
    return result;
}
} // namespace sts::search
