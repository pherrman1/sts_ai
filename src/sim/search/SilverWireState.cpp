#include "sim/search/SilverWireState.h"

#include <algorithm>
#include <sstream>
#include <stdexcept>

#include "constants/Potions.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SearchRng.h"

namespace sts::search {

    namespace {

        using silver_bridge::BattleStateWire;
        using silver_bridge::CardSource;
        using silver_bridge::CardWire;
        using silver_bridge::PileWire;
        using silver_bridge::SemanticAction;
        using silver_bridge::SemanticActionType;

        sts::Action pendingActionFromWire(const silver_bridge::PendingActionWire &in) {
            using K = silver_bridge::PendingActionKind;
            if (in.amount < 0 || in.amount > 999
                    || ((in.kind != K::BUFF_PLAYER && in.kind != K::DEBUFF_PLAYER && in.kind != K::DEBUFF_ALL_ENEMY)
                        && (in.status != 0 || in.sourceMonster))
                    || (in.kind == K::BUFF_PLAYER && in.sourceMonster)
                    || ((in.kind == K::GAMBLE || in.kind == K::UPGRADE_RANDOM || in.kind == K::USE_CARD
                        || in.kind == K::REMOVE_PEN_NIB || in.kind == K::REMOVE_PLAYER_DEBUFFS) && in.amount != 0))
                throw std::invalid_argument("invalid Silver pending action fields");
            switch (in.kind) {
                case K::DRAW: return Actions::DrawCards(in.amount);
                case K::GAIN_BLOCK: return Actions::GainBlock(in.amount);
                case K::GAIN_ENERGY: return Actions::GainEnergy(in.amount);
                case K::DAMAGE_ALL: return Actions::DamageAllEnemy(in.amount);
                case K::DAMAGE_RANDOM: return Actions::DamageRandomEnemy(in.amount);
                case K::GAMBLE: return Actions::GambleAction();
                case K::UPGRADE_RANDOM: return Actions::UpgradeRandomCardAction();
                case K::USE_CARD: return Actions::OnAfterCardUsed();
                case K::REMOVE_PEN_NIB: return Actions::RemoveStatus<PlayerStatus::PEN_NIB>();
                case K::REMOVE_PLAYER_DEBUFFS: return Actions::RemovePlayerDebuffs();
                case K::BUFF_PLAYER: {
                    const auto status = static_cast<PlayerStatus>(in.status);
                    switch (status) {
                        case PlayerStatus::PEN_NIB:
                            if(in.amount!=1)throw std::invalid_argument("invalid Silver pending Pen Nib amount");
                            [[fallthrough]];
                        case PlayerStatus::STRENGTH: case PlayerStatus::DEXTERITY:
                        case PlayerStatus::ARTIFACT: case PlayerStatus::BUFFER:
                        case PlayerStatus::PLATED_ARMOR: case PlayerStatus::THORNS:
                        case PlayerStatus::VIGOR: case PlayerStatus::INTANGIBLE:
                            if (in.status == static_cast<int>(status)) return makeAction(ActData_BuffPlayer{status,in.amount});
                            break;
                        default: break;
                    }
                    throw std::invalid_argument("unsupported Silver pending player buff");
                }
                case K::DEBUFF_PLAYER:
                    if ((in.status != static_cast<int>(PlayerStatus::LOSE_STRENGTH)
                            && !(in.status == static_cast<int>(PlayerStatus::WEAK) && in.amount == 1)) || in.sourceMonster)
                        throw std::invalid_argument("unsupported Silver pending player debuff");
                    return makeAction(ActData_DebuffPlayer{static_cast<PlayerStatus>(in.status),in.amount,false});
                case K::DEBUFF_ALL_ENEMY:
                    if ((in.status != static_cast<int>(MonsterStatus::WEAK)
                            && in.status != static_cast<int>(MonsterStatus::VULNERABLE)
                            && in.status != static_cast<int>(MonsterStatus::POISON)) || in.sourceMonster || in.amount == 0)
                        throw std::invalid_argument("unsupported Silver pending enemy debuff");
                    return makeAction(ActData_DebuffAllEnemy{static_cast<MonsterStatus>(in.status),in.amount,false});
                case K::SHUFFLE_WOUNDS:
                    if (in.amount != 2) throw std::invalid_argument("unsupported Silver pending Wound generation");
                    return Actions::MakeTempCardInDrawPile(CardInstance(CardId::WOUND),2,true);
                default: throw std::invalid_argument("unsupported Silver pending action kind");
            }
        }

        CardInstance fromWire(const CardWire &in) {
            CardInstance out;
            out.id = static_cast<CardId>(in.id);
            out.uniqueId = in.uniqueId;
            out.specialData = in.specialData;
            out.cost = static_cast<std::int8_t>(in.cost);
            out.costForTurn = static_cast<std::int8_t>(in.costForTurn);
            out.upgraded = in.upgraded;
            out.freeToPlayOnce = in.freeToPlayOnce;
            out.retain = in.retain;
            return out;
        }

        CardWire toWire(const CardInstance &in) {
            return {static_cast<std::int16_t>(in.id), in.uniqueId, in.specialData, in.cost,
                    in.costForTurn, in.upgraded, in.freeToPlayOnce, in.retain};
        }

        CardQueueItem fromWire(const silver_bridge::CardQueueItemWire &in) {
            CardQueueItem out;
            out.card = fromWire(in.card);
            out.target = in.target;
            out.isEndTurn = in.isEndTurn;
            out.triggerOnUse = in.triggerOnUse;
            out.ignoreEnergyTotal = in.ignoreEnergyTotal;
            out.energyOnUse = in.energyOnUse;
            out.freeToPlay = in.freeToPlay;
            out.randomTarget = in.randomTarget;
            out.autoplay = in.autoplay;
            out.regretCardCount = in.regretCardCount;
            out.purgeOnUse = in.purgeOnUse;
            out.exhaustOnUse = in.exhaustOnUse;
            return out;
        }

        silver_bridge::CardQueueItemWire toWire(const CardQueueItem &in) {
            silver_bridge::CardQueueItemWire out;
            out.card = toWire(in.card); out.target = in.target; out.isEndTurn = in.isEndTurn;
            out.triggerOnUse = in.triggerOnUse; out.ignoreEnergyTotal = in.ignoreEnergyTotal;
            out.energyOnUse = in.energyOnUse; out.freeToPlay = in.freeToPlay; out.randomTarget = in.randomTarget;
            out.autoplay = in.autoplay; out.regretCardCount = in.regretCardCount;
            out.purgeOnUse = in.purgeOnUse; out.exhaustOnUse = in.exhaustOnUse;
            return out;
        }

        std::vector<CardInstance> fromWire(const std::vector<CardWire> &in) {
            std::vector<CardInstance> out;
            out.reserve(in.size());
            for (const auto &c : in) out.push_back(fromWire(c));
            return out;
        }

        std::vector<CardInstance> pileCards(const PileWire &in) {
            std::vector<CardInstance> out = fromWire(in.knownBottom);
            for (const auto &c : in.unknown) out.push_back(fromWire(c));
            for (const auto &c : in.knownTop) out.push_back(fromWire(c));
            return out;
        }

        void assignDrawPile(CardPile &out, const PileWire &in, bool fullOrderObserved) {
            if (!in.valid) throw std::invalid_argument("invalid Silver draw-pile observation");
            if (fullOrderObserved || in.fullOrderObserved) {
                out.assignConcrete(pileCards(in));
            } else {
                out.assignInformationState(fromWire(in.knownBottom), fromWire(in.unknown),
                                           fromWire(in.knownTop));
            }
        }

        template <typename Pile>
        PileWire pileWire(const Pile &in) {
            PileWire out;
            if (in.isConcrete()) {
                out.fullOrderObserved = true;
                for (const auto &c : in) out.knownTop.push_back(toWire(c));
                return out;
            }
            const int bottom = in.knownBottom();
            const int top = in.knownTop();
            for (int i = 0; i < bottom; ++i) out.knownBottom.push_back(toWire(in[i]));
            for (int i = bottom; i < in.size() - top; ++i) out.unknown.push_back(toWire(in[i]));
            for (int i = in.size() - top; i < in.size(); ++i) out.knownTop.push_back(toWire(in[i]));
            return out;
        }

        CardWire cardAt(const BattleContext &state, CardSource source, int idx) {
            const auto check = [idx](int size) {
                if (idx < 0 || idx >= size) {
                    throw std::runtime_error("Silver action index " + std::to_string(idx)
                                             + " out of range " + std::to_string(size));
                }
            };
            switch (source) {
                case CardSource::HAND:
                    check(state.cards.cardsInHand);
                    return toWire(state.cards.hand[idx]);
                case CardSource::DRAW:
                    check(state.cards.drawPile.size());
                    return toWire(state.cards.drawPile[idx]);
                case CardSource::DISCARD:
                    check(state.cards.discardPile.size());
                    return toWire(state.cards.discardPile[idx]);
                case CardSource::EXHAUST:
                    check(state.cards.exhaustPile.size());
                    return toWire(state.cards.exhaustPile[idx]);
                default:
                    throw std::runtime_error("unsupported Silver card source");
            }
        }

        bool cardIsInAnyPile(const BattleContext &bc, int uniqueId) {
            const auto same = [uniqueId](const CardInstance &c) { return c.uniqueId == uniqueId; };
            const auto &cards = bc.cards;
            return std::any_of(cards.hand.begin(), cards.hand.begin() + cards.cardsInHand, same)
                || std::any_of(cards.drawPile.begin(), cards.drawPile.end(), same)
                || std::any_of(cards.discardPile.begin(), cards.discardPile.end(), same)
                || std::any_of(cards.exhaustPile.begin(), cards.exhaustPile.end(), same);
        }

        template <int N>
        std::vector<sts::Action> queuedActions(const ActionQueue<N> &queue) {
            std::vector<sts::Action> out;
            for (int i = 0; i < queue.size; ++i) out.push_back(queue.arr[(queue.front + i) % N]);
            return out;
        }

        // Replays the interrupted card on a copy of `root` (card back in hand,
        // cost refunded, per-turn play counts and Ink Bottle/Nunchaku/Pen Nib
        // counters rolled back) and restores the
        // work still pending when its selection opens: the part of the queue
        // the play produced that the replay has not yet run. Actions the
        // replay adds while running are not copied, because the replay applies
        // the pre-selection effects a second time (a second hit can cross a
        // threshold such as the Guardian's Mode Shift). Effects the first play
        // already consumed (Vigor, the Pen Nib buff, Double Tap, Necronomicon)
        // are not rolled back, so triggers that depend on them may differ.
        bool restoreInterruptedPlayQueues(BattleContext &root) {
            const CardQueueItem item = root.curCardQueueItem;
            if (root.cards.cardsInHand >= CardManager::MAX_HAND_SIZE) return false;
            BattleContext replay = root;
            auto &p = replay.player;
            if (p.cardsPlayedThisTurn > 0) --p.cardsPlayedThisTurn;
            if (item.card.getType() == CardType::ATTACK && p.attacksPlayedThisTurn > 0) --p.attacksPlayedThisTurn;
            if (item.card.getType() == CardType::SKILL && p.skillsPlayedThisTurn > 0) --p.skillsPlayedThisTurn;
            if (item.card.costForTurn > 0 && !item.freeToPlay && !item.autoplay) p.energy += item.card.costForTurn;
            // Relic counters the play advanced (they wrap to 0 when they fire).
            if (p.hasRelic<RelicId::INK_BOTTLE>()) p.inkBottleCounter = p.inkBottleCounter == 0 ? 9 : p.inkBottleCounter - 1;
            if (item.card.getType() == CardType::ATTACK) {
                if (p.hasRelic<RelicId::NUNCHAKU>()) p.nunchakuCounter = p.nunchakuCounter == 0 ? 9 : p.nunchakuCounter - 1;
                if (p.hasRelic<RelicId::PEN_NIB>()) p.penNibCounter = p.penNibCounter == -1 ? 8 : p.penNibCounter - 1;
            }
            // The replay hits a second time: keep every monster alive so it
            // reaches the selection, and revive a target the real hit killed
            // so the card can be used again. Monster health does not enter
            // the actions the play queues.
            constexpr int kReplayMonsterHp = 1 << 20;
            if (item.card.requiresTarget() && item.target >= 0 && item.target < replay.monsters.monsterCount) {
                auto &target = replay.monsters.arr[item.target];
                if (target.isDying() && !target.isHalfDead() && !target.isEscaping()) {
                    target.curHp = 1;
                    ++replay.monsters.monstersAlive;
                }
            }
            for (int i = 0; i < replay.monsters.monsterCount; ++i) {
                auto &m = replay.monsters.arr[i];
                if (m.isTargetable()) m.curHp = m.maxHp = kReplayMonsterHp;
            }
            replay.cards.moveToHand(item.card);
            replay.inputState = InputState::EXECUTING_ACTIONS;
            replay.cardSelectInfo = CardSelectInfo{};
            replay.actionQueue.clear();
            replay.cardQueue.clear();
            CombatKnowledgeObserver *const observer = g_combatKnowledgeObserver;
            g_combatKnowledgeObserver = nullptr;   // the replay is not live play
            std::vector<sts::Action> played;
            try {
                replay.playCardQueueItem(item);
                played = queuedActions(replay.actionQueue);
                replay.executeActions();
            } catch (const std::exception &) {
                g_combatKnowledgeObserver = observer;
                return false;
            }
            g_combatKnowledgeObserver = observer;
            if (replay.inputState != InputState::CARD_SELECT
                    || replay.cardSelectInfo.cardSelectTask != root.cardSelectInfo.cardSelectTask
                    || replay.outcome != Outcome::UNDECIDED
                    || cardIsInAnyPile(replay, item.card.uniqueId)) {
                return false;
            }
            // The pending part of the play's queue is its longest suffix that
            // still appears, in order, in the replay's remaining queue.
            const auto remaining = queuedActions(replay.actionQueue);
            const auto pendingFrom = [&](std::size_t first) {
                std::size_t k = 0;
                for (std::size_t i = first; i < played.size(); ++i) {
                    while (k < remaining.size() && !(remaining[k] == played[i])) ++k;
                    if (k == remaining.size()) return false;
                    ++k;
                }
                return true;
            };
            std::size_t keep = played.size();
            while (keep > 0 && !pendingFrom(played.size() - keep)) --keep;
            if (keep == 0) return false;
            root.actionQueue.clear();
            for (std::size_t i = played.size() - keep; i < played.size(); ++i) root.actionQueue.pushBack(played[i]);
            root.cardQueue = replay.cardQueue;
            return true;
        }

        CardSource selectSource(CardSelectTask task) {
            switch (task) {
                case CardSelectTask::ARMAMENTS:
                case CardSelectTask::DUAL_WIELD:
                case CardSelectTask::EXHAUST_ONE:
                case CardSelectTask::EXHAUST_MANY:
                case CardSelectTask::FORETHOUGHT:
                case CardSelectTask::GAMBLE:
                case CardSelectTask::NIGHTMARE:
                case CardSelectTask::RECYCLE:
                case CardSelectTask::SETUP:
                case CardSelectTask::WARCRY:
                    return CardSource::HAND;
                case CardSelectTask::HEADBUTT:
                case CardSelectTask::HOLOGRAM:
                case CardSelectTask::LIQUID_MEMORIES_POTION:
                case CardSelectTask::MEDITATE:
                    return CardSource::DISCARD;
                case CardSelectTask::EXHUME:
                    return CardSource::EXHAUST;
                case CardSelectTask::SECRET_TECHNIQUE:
                case CardSelectTask::SECRET_WEAPON:
                case CardSelectTask::SEEK:
                    return CardSource::DRAW;
                default:
                    return CardSource::NONE;
            }
        }

        std::string cardFingerprint(const CardWire &card) {
            return std::to_string(card.id) + "_" + std::to_string(card.uniqueId) + "_"
                + std::to_string(card.specialData) + "_" + std::to_string(card.cost) + "_"
                + std::to_string(card.costForTurn) + "_" + std::to_string(card.upgraded ? 1 : 0) + "_"
                + std::to_string(card.freeToPlayOnce ? 1 : 0) + "_" + std::to_string(card.retain ? 1 : 0);
        }

    }

    void capturePendingActionQueue(const BattleContext &state, BattleStateWire &wire) {
        using K = silver_bridge::PendingActionKind;
        wire.pendingActionQueueObserved = false;
        wire.pendingActionQueue.clear();
        if (state.inputState != InputState::CARD_SELECT) return;
        std::vector<silver_bridge::PendingActionWire> captured;
        for (const auto &action : queuedActions(state.actionQueue)) {
            silver_bridge::PendingActionWire item;
            switch (action.type) {
                case CombatActionType::DrawCards: item.kind=K::DRAW; item.amount=action.v_DrawCards.amount; break;
                case CombatActionType::GainBlock: item.kind=K::GAIN_BLOCK; item.amount=action.v_GainBlock.amount; break;
                case CombatActionType::GainEnergy: item.kind=K::GAIN_ENERGY; item.amount=action.v_GainEnergy.amount; break;
                case CombatActionType::DamageAllEnemy: item.kind=K::DAMAGE_ALL; item.amount=action.v_DamageAllEnemy.damage; break;
                case CombatActionType::DamageRandomEnemy: item.kind=K::DAMAGE_RANDOM; item.amount=action.v_DamageRandomEnemy.damage; break;
                case CombatActionType::GambleAction: item.kind=K::GAMBLE; break;
                case CombatActionType::UpgradeRandomCardAction: item.kind=K::UPGRADE_RANDOM; break;
                case CombatActionType::OnAfterCardUsed: item.kind=K::USE_CARD; break;
                case CombatActionType::RemoveStatus:
                    if(action.v_RemoveStatus.s!=PlayerStatus::PEN_NIB)return;
                    item.kind=K::REMOVE_PEN_NIB;break;
                case CombatActionType::RemovePlayerDebuffs: item.kind=K::REMOVE_PLAYER_DEBUFFS;break;
                case CombatActionType::BuffPlayer:
                    item.kind=K::BUFF_PLAYER; item.status=static_cast<int>(action.v_BuffPlayer.s); item.amount=action.v_BuffPlayer.amount; break;
                case CombatActionType::DebuffPlayer:
                    item.kind=K::DEBUFF_PLAYER; item.status=static_cast<int>(action.v_DebuffPlayer.s);
                    item.amount=action.v_DebuffPlayer.amount; item.sourceMonster=action.v_DebuffPlayer.isSourceMonster; break;
                case CombatActionType::DebuffAllEnemy:
                    item.kind=K::DEBUFF_ALL_ENEMY; item.status=static_cast<int>(action.v_DebuffAllEnemy.s);
                    item.amount=action.v_DebuffAllEnemy.amount; item.sourceMonster=action.v_DebuffAllEnemy.isSourceMonster; break;
                case CombatActionType::MakeTempCardInDrawPile:
                    item.kind=K::SHUFFLE_WOUNDS; item.amount=action.v_MakeTempCardInDrawPile.amount; break;
                default: return;
            }
            // Nondefault victory flags or unsupported parameterizations must
            // not silently become a different action through this wire.
            try { if (!(pendingActionFromWire(item) == action)) return; }
            catch (const std::invalid_argument &) { return; }
            captured.push_back(item);
        }
        wire.pendingActionQueueObserved = true;
        wire.pendingActionQueue = std::move(captured);
    }

    BattleContext battleContextFromWire(const BattleStateWire &in) {
        if ((in.version != BattleStateWire::kVersion && !(in.version == 2 && !in.intentsHidden)) || !in.valid) {
            throw std::invalid_argument("invalid or incompatible Silver state wire");
        }
        if (in.hand.size() > static_cast<std::size_t>(CardManager::MAX_HAND_SIZE)) {
            throw std::invalid_argument("Silver hand exceeds capacity");
        }
        if (in.pendingActionQueue.size() > 128
                || (!in.pendingActionQueueObserved && !in.pendingActionQueue.empty())
                || (in.pendingActionQueueObserved && in.inputState != static_cast<int>(InputState::CARD_SELECT)))
            throw std::invalid_argument("invalid Silver pending action queue boundary or capacity");
        const auto cleanupCount=std::count_if(in.pendingActionQueue.begin(),in.pendingActionQueue.end(),[](const auto &item) {
            return item.kind==silver_bridge::PendingActionKind::USE_CARD;
        });
        if (cleanupCount>1 || (cleanupCount && (in.curCardQueueItem.card.id==static_cast<int>(CardId::INVALID)
                || in.curCardQueueItem.isEndTurn)))
            throw std::invalid_argument("invalid Silver pending card cleanup owner");
        BattleContext out;
        out.seed = in.isolatedSearchSeed;
        out.floorNum = in.floorNum;
        out.encounter = static_cast<MonsterEncounter>(in.encounter);
        out.loopCount = in.loopCount;
        out.energyWasted = in.energyWasted;
        out.cardsDrawn = in.cardsDrawn;
        out.ascension = in.ascension;
        out.outcome = static_cast<Outcome>(in.outcome);
        out.inputState = static_cast<InputState>(in.inputState);
        out.monsterTurnIdx = in.monsterTurnIdx;
        out.intentsHidden = in.intentsHidden;
        out.endTurnQueued = in.endTurnQueued;
        out.turnHasEnded = in.turnHasEnded;
        out.skipMonsterTurn = in.skipMonsterTurn;
        out.potionCount = in.potionCount;
        out.potionCapacity = in.potionCapacity;
        for (std::size_t i = 0; i < out.potions.size(); ++i) out.potions[i] = static_cast<Potion>(in.potions[i]);
        out.turn = in.turn;
        out.miscBits = std::bitset<32>(in.miscBits);

        const auto &wp = in.player;
        auto &p = out.player;
        p.cc = static_cast<CharacterClass>(wp.characterClass);
        p.gold = wp.gold; p.curHp = wp.curHp; p.maxHp = wp.maxHp; p.energy = wp.energy;
        p.energyPerTurn = wp.energyPerTurn; p.cardDrawPerTurn = wp.cardDrawPerTurn;
        p.stance = static_cast<Stance>(wp.stance); p.orbSlots = wp.orbSlots;
        p.lastTargetedMonster = wp.lastTargetedMonster; p.block = wp.block; p.artifact = wp.artifact;
        p.dexterity = wp.dexterity; p.focus = wp.focus; p.strength = wp.strength;
        p.justAppliedBits = wp.justAppliedBits; p.statusBits0 = wp.statusBits0; p.statusBits1 = wp.statusBits1;
        for (const auto &[status, amount] : wp.statusMap) p.statusMap.emplace(static_cast<PlayerStatus>(status), amount);
        p.relicBits0 = wp.relicBits0; p.relicBits1 = wp.relicBits1;
        p.happyFlowerCounter = wp.relicCounters[0]; p.incenseBurnerCounter = wp.relicCounters[1];
        p.inkBottleCounter = wp.relicCounters[2]; p.inserterCounter = wp.relicCounters[3];
        p.nunchakuCounter = wp.relicCounters[4]; p.penNibCounter = wp.relicCounters[5];
        p.sundialCounter = wp.relicCounters[6];
        p.haveUsedNecronomiconThisTurn = wp.haveUsedNecronomiconThisTurn;
        p.combustHpLoss = wp.combustHpLoss; p.devaFormEnergyPerTurn = wp.devaFormEnergyPerTurn;
        p.echoFormCardsDoubled = wp.echoFormCardsDoubled; p.panacheCounter = wp.panacheCounter;
        p.cardsPlayedThisTurn = wp.cardsPlayedThisTurn; p.attacksPlayedThisTurn = wp.attacksPlayedThisTurn;
        p.skillsPlayedThisTurn = wp.skillsPlayedThisTurn; p.cardsDiscardedThisTurn = wp.cardsDiscardedThisTurn;
        p.orangePelletsCardTypesPlayed = std::bitset<3>(wp.orangePelletsCardTypesPlayed);
        p.lastAttackUnblockedDamage = wp.lastAttackUnblockedDamage;
        p.timesDamagedThisCombat = wp.timesDamagedThisCombat;
        p.bomb1 = wp.bombs[0]; p.bomb2 = wp.bombs[1]; p.bomb3 = wp.bombs[2];

        out.monsters.monsterCount = in.monsterCount;
        out.monsters.monstersAlive = in.monstersAlive;
        out.monsters.extraRollMoveOnTurn = std::bitset<5>(in.extraRollMoveOnTurn);
        out.monsters.skipTurn = std::bitset<5>(in.skipMonsterTurnBits);
        for (std::size_t i = 0; i < out.monsters.arr.size(); ++i) {
            const auto &wm = in.monsters[i];
            auto &m = out.monsters.arr[i];
            m.occupantGeneration = wm.occupantGeneration;
            m.latentDamageMask = in.intentsHidden ? wm.latentDamageMask : 0; m.latentDamageMaterialized = false;
            m.idx = wm.idx; m.id = static_cast<MonsterId>(wm.id); m.curHp = wm.curHp;
            m.maxHp = wm.maxHp; m.block = wm.block; m.isEscapingB = wm.isEscapingB;
            m.halfDead = wm.halfDead; m.escapeNext = wm.escapeNext;
            m.moveHistory[0] = static_cast<MMID>(wm.moveHistory[0]);
            m.moveHistory[1] = static_cast<MMID>(wm.moveHistory[1]);
            m.statusBits = wm.statusBits;
            m.artifact = static_cast<std::int8_t>(wm.smallPowers[0]);
            m.blockReturn = static_cast<std::int8_t>(wm.smallPowers[1]);
            m.choked = static_cast<std::int8_t>(wm.smallPowers[2]);
            m.corpseExplosion = static_cast<std::int8_t>(wm.smallPowers[3]);
            m.lockOn = static_cast<std::int8_t>(wm.smallPowers[4]);
            m.mark = wm.smallPowers[5];
            m.metallicize = static_cast<std::int8_t>(wm.smallPowers[6]);
            m.platedArmor = static_cast<std::int8_t>(wm.smallPowers[7]);
            m.poison = static_cast<std::int8_t>(wm.smallPowers[8]);
            m.regen = static_cast<std::int8_t>(wm.smallPowers[9]);
            m.shackled = static_cast<std::int8_t>(wm.smallPowers[10]);
            m.strength = wm.strength; m.vulnerable = wm.vulnerable; m.weak = wm.weak;
            m.uniquePower0 = wm.uniquePower0; m.uniquePower1 = wm.uniquePower1; m.miscInfo = wm.miscInfo;
            const auto prior = Monster::latentDamagePrior(m.id, out.ascension);
            if ((wm.latentDamageMask && (!prior || (wm.latentDamageMask & ~prior) || (in.intentsHidden && wm.miscInfo != 0)
                    || (!in.intentsHidden && (wm.miscInfo<0 || wm.miscInfo>=16 || !(wm.latentDamageMask&(1u<<wm.miscInfo))))))
                    || (in.intentsHidden && m.idx>=0 && prior && !wm.latentDamageMask)) {
                throw std::runtime_error("invalid persistent damage posterior");
            }
            if (in.intentsHidden && wm.latentDamageMask) {
                if (wm.pendingRollInputs.miscInfo != 0) { throw std::runtime_error("private latent roll input"); }
                for (const auto &r:wm.pendingRollInputHistory) if(r.miscInfo!=0) { throw std::runtime_error("private latent roll history"); }
            }
            if (in.intentsHidden) {
                m.pendingMoveRolls = wm.pendingMoveRolls;
                m.pendingDirectMoveChoice = wm.pendingDirectMoveChoice;
                m.pendingAttackPredicates = wm.pendingAttackPredicates;
                const int steps = wm.pendingMoveRolls + (wm.pendingDirectMoveChoice != 0 ? 1 : 0);
                if (!wm.hasPredicateKnowledgeFields ||
                        ((!wm.pendingRollInputHistory.empty() || wm.pendingMoveRolls > 1)
                         && wm.pendingRollInputHistory.size() != wm.pendingMoveRolls)) {
                    throw std::runtime_error("hidden intent roll input history size mismatch");
                }
                int previousStep = 0;
                for (const auto &[step, attack] : wm.pendingAttackPredicates) {
                    if (step <= previousStep || step > steps) throw std::runtime_error("invalid hidden intent predicate step");
                    previousStep = step;
                }
                for (const auto &r : wm.pendingRollInputHistory) {
                    m.pendingRollInputHistory.push_back({r.curHp, r.maxHp, r.knightCurHp, r.knightMaxHp,
                        r.monsterTurnNumber, r.miscInfo, r.aliveCount, r.monstersAlive,
                        r.knightAlive, r.playerConstricted, r.asleep, r.halfDead});
                }
                const auto &r = wm.pendingRollInputs;
                m.pendingRollInputs = {r.curHp, r.maxHp, r.knightCurHp, r.knightMaxHp,
                                       r.monsterTurnNumber, r.miscInfo, r.aliveCount, r.monstersAlive,
                                       r.knightAlive, r.playerConstricted, r.asleep, r.halfDead};
            }
        }

        out.cards.nextUniqueCardId = in.nextUniqueCardId;
        out.cards.cardsInHand = static_cast<int>(in.hand.size());
        for (int i = 0; i < out.cards.cardsInHand; ++i) out.cards.hand[i] = fromWire(in.hand[i]);
        for (std::size_t i = 0; i < out.cards.limbo.size() && i < in.limbo.size(); ++i) {
            out.cards.limbo[i] = fromWire(in.limbo[i]);
        }
        for (std::size_t i = 0; i < out.cards.stasisCards.size(); ++i) {
            out.cards.stasisCards[i] = fromWire(in.stasisCards[i]);
        }
        out.cards.handNormalityCount = in.handNormalityCount;
        out.cards.handPainCount = in.handPainCount;
        out.cards.strikeCount = in.strikeCount;
        out.cards.handBloodCardCount = in.handBloodCardCount;
        out.cards.drawPileBloodCardCount = in.drawPileBloodCardCount;
        out.cards.discardPileBloodCardCount = in.discardPileBloodCardCount;
        assignDrawPile(out.cards.drawPile, in.drawPile, in.fullDrawOrderObserved);
        if (!in.discardPile.valid || !in.exhaustPile.valid) {
            throw std::invalid_argument("invalid Silver pile observation");
        }
        out.cards.discardPile = pileCards(in.discardPile);
        out.cards.exhaustPile = pileCards(in.exhaustPile);

        auto &select = out.cardSelectInfo;
        for (std::size_t i = 0; i < select.cards.size(); ++i) select.cards[i] = static_cast<CardId>(in.cardSelect.cards[i]);
        select.setCostToZero = in.cardSelect.setCostToZero;
        select.drawAfter = in.cardSelect.drawAfter;
        select.drawsAfter = in.cardSelect.drawsAfter;
        select.blocksAfter = in.cardSelect.blocksAfter;
        select.damageAllBeforeBlocks = in.cardSelect.damageAllBeforeBlocks;
        select.canPickZero = in.cardSelect.canPickZero;
        select.canPickAnyNumber = in.cardSelect.canPickAnyNumber;
        select.pickCount = in.cardSelect.pickCount;
        select.data0 = in.cardSelect.data0;
        select.cardSelectTask = static_cast<CardSelectTask>(in.cardSelect.task);

        out.curCardQueueItem = fromWire(in.curCardQueueItem);
        if (in.pendingCardQueue.size() > static_cast<std::size_t>(CardQueue::capacity)) {
            throw std::invalid_argument("Silver pending card queue exceeds capacity");
        }

        seedSearchRng(out, in.isolatedSearchSeed);

        // Vanilla defers the Guardian's Mode Shift: the hit that exhausts it
        // queues a state change, so a selection opened by the same card shows
        // Mode Shift at or below zero and the offensive move. The engine
        // shifts at the hit; settle it the same way, queueing the 20 block
        // behind the interrupted card's pending work.
        std::vector<int> shiftedGuardians;
        for (int i = 0; i < out.monsters.monsterCount; ++i) {
            auto &m = out.monsters.arr[i];
            if (m.id == MonsterId::THE_GUARDIAN && !m.isDeadOrEscaped()
                    && m.hasStatus<MonsterStatus::MODE_SHIFT>() && m.getStatus<MonsterStatus::MODE_SHIFT>() <= 0) {
                CombatKnowledgeObserver *const observer = g_combatKnowledgeObserver;
                g_combatKnowledgeObserver = nullptr;   // not a live event
                m.enterGuardianDefensiveMode();
                g_combatKnowledgeObserver = observer;
                shiftedGuardians.push_back(i);
            }
        }

        // A selection made while a card is being played (Headbutt, Warcry,
        // Burning Pact, ...) interrupts that play: the card is in no pile and
        // the rest of its work is still queued. Unless an exact action tail
        // was observed, rebuild it by replaying the card; if replay does not reach the
        // same selection, restore at least the OnAfterCardUsed that moves the
        // card to its destination.
        if (in.pendingActionQueueObserved) {
            out.actionQueue.clear();
            for (const auto &item : in.pendingActionQueue) out.addToBot(pendingActionFromWire(item));
        } else if (out.inputState == InputState::CARD_SELECT && out.curCardQueueItem.card.id != CardId::INVALID
                && !cardIsInAnyPile(out, out.curCardQueueItem.card.uniqueId)
                && !restoreInterruptedPlayQueues(out)) {
            out.addToBot(Actions::OnAfterCardUsed());
        }
        for (const int idx : shiftedGuardians) out.addToBot(Actions::MonsterGainBlock(idx, 20));
        // An observed card queue is exact; it replaces the replay's.
        if (in.pendingCardQueueObserved) {
            out.cardQueue.clear();
            for (const auto &item : in.pendingCardQueue) out.cardQueue.pushBack(fromWire(item));
        }
        return out;
    }

    SilverSearchContext searchContextFromWire(const BattleStateWire &wire) {
        SilverSearchContext context;
        context.act = wire.act;
        context.actBossRoom = isBossEncounter(static_cast<MonsterEncounter>(wire.encounter));
        context.omamoriCharged = wire.omamoriOwned && wire.omamoriValue > 0;
        return context;
    }

    BattleStateWire wireFromSearchState(const BattleContext &state, const SilverSearchContext &context) {
        BattleStateWire out;
        out.isolatedSearchSeed = state.seed;
        out.floorNum = state.floorNum;
        out.encounter = static_cast<int>(state.encounter);
        out.loopCount = state.loopCount;
        out.energyWasted = state.energyWasted;
        out.cardsDrawn = state.cardsDrawn;
        out.act = context.act;
        out.omamoriOwned = context.omamoriCharged;
        out.omamoriValue = context.omamoriCharged ? 1 : 0;
        out.ascension = state.ascension;
        out.outcome = static_cast<int>(state.outcome);
        out.inputState = static_cast<int>(state.inputState);
        out.monsterTurnIdx = state.monsterTurnIdx;
        out.endTurnQueued = state.endTurnQueued;
        out.turnHasEnded = state.turnHasEnded;
        out.skipMonsterTurn = state.skipMonsterTurn;
        out.potionCount = state.potionCount;
        out.potionCapacity = state.potionCapacity;
        for (std::size_t i = 0; i < out.potions.size(); ++i) out.potions[i] = static_cast<std::int16_t>(state.potions[i]);
        out.turn = state.turn;
        out.intentsHidden = state.intentsHidden;
        out.fullDrawOrderObserved = state.cards.drawPile.isConcrete();
        out.miscBits = static_cast<std::uint32_t>(state.miscBits.to_ulong());

        const auto &p = state.player;
        auto &wp = out.player;
        wp.characterClass = static_cast<std::int16_t>(p.cc);
        wp.gold = p.gold; wp.curHp = p.curHp; wp.maxHp = p.maxHp; wp.energy = p.energy;
        wp.energyPerTurn = p.energyPerTurn; wp.cardDrawPerTurn = p.cardDrawPerTurn;
        wp.stance = static_cast<std::int16_t>(p.stance); wp.orbSlots = p.orbSlots;
        wp.lastTargetedMonster = p.lastTargetedMonster; wp.block = p.block; wp.artifact = p.artifact;
        wp.dexterity = p.dexterity; wp.focus = p.focus; wp.strength = p.strength;
        wp.justAppliedBits = p.justAppliedBits; wp.statusBits0 = p.statusBits0; wp.statusBits1 = p.statusBits1;
        for (const auto &[status, amount] : p.statusMap) wp.statusMap.emplace_back(static_cast<std::int16_t>(status), amount);
        wp.relicBits0 = p.relicBits0; wp.relicBits1 = p.relicBits1;
        wp.relicCounters = {p.happyFlowerCounter, p.incenseBurnerCounter, p.inkBottleCounter,
                            p.inserterCounter, p.nunchakuCounter, p.penNibCounter, p.sundialCounter};
        wp.haveUsedNecronomiconThisTurn = p.haveUsedNecronomiconThisTurn;
        wp.combustHpLoss = p.combustHpLoss; wp.devaFormEnergyPerTurn = p.devaFormEnergyPerTurn;
        wp.echoFormCardsDoubled = p.echoFormCardsDoubled; wp.panacheCounter = p.panacheCounter;
        wp.cardsPlayedThisTurn = p.cardsPlayedThisTurn; wp.attacksPlayedThisTurn = p.attacksPlayedThisTurn;
        wp.skillsPlayedThisTurn = p.skillsPlayedThisTurn; wp.cardsDiscardedThisTurn = p.cardsDiscardedThisTurn;
        wp.orangePelletsCardTypesPlayed = static_cast<std::uint8_t>(p.orangePelletsCardTypesPlayed.to_ulong());
        wp.lastAttackUnblockedDamage = p.lastAttackUnblockedDamage;
        wp.timesDamagedThisCombat = p.timesDamagedThisCombat;
        wp.bombs = {p.bomb1, p.bomb2, p.bomb3};

        out.monsterCount = state.monsters.monsterCount;
        out.monstersAlive = state.monsters.monstersAlive;
        out.extraRollMoveOnTurn = static_cast<std::uint8_t>(state.monsters.extraRollMoveOnTurn.to_ulong());
        out.skipMonsterTurnBits = static_cast<std::uint8_t>(state.monsters.skipTurn.to_ulong());
        for (std::size_t i = 0; i < out.monsters.size(); ++i) {
            const auto &m = state.monsters.arr[i];
            auto &wm = out.monsters[i];
            wm.occupantGeneration = m.occupantGeneration;
            wm.latentDamageMask = state.intentsHidden ? m.latentDamageMask : 0;
            wm.idx = m.idx; wm.id = static_cast<std::int16_t>(m.id); wm.curHp = m.curHp;
            wm.maxHp = m.maxHp; wm.block = m.block; wm.isEscapingB = m.isEscapingB;
            wm.halfDead = m.halfDead; wm.escapeNext = m.escapeNext;
            wm.moveHistory = {static_cast<std::int16_t>(m.moveHistory[0]),
                              static_cast<std::int16_t>(m.moveHistory[1])};
            wm.statusBits = m.statusBits;
            wm.smallPowers = {m.artifact, m.blockReturn, m.choked, m.corpseExplosion, m.lockOn,
                              static_cast<std::int16_t>(m.mark), m.metallicize, m.platedArmor,
                              m.poison, m.regen, m.shackled};
            wm.strength = m.strength; wm.vulnerable = m.vulnerable; wm.weak = m.weak;
            wm.uniquePower0 = m.uniquePower0; wm.uniquePower1 = m.uniquePower1; wm.miscInfo = state.intentsHidden && wm.latentDamageMask ? 0 : m.miscInfo;
            wm.pendingMoveRolls = m.pendingMoveRolls;
            wm.pendingDirectMoveChoice = m.pendingDirectMoveChoice;
            wm.pendingAttackPredicates = m.pendingAttackPredicates;
            for (const auto &r : m.pendingRollInputHistory) {
                wm.pendingRollInputHistory.push_back({r.curHp, r.maxHp, r.knightCurHp, r.knightMaxHp,
                    r.monsterTurnNumber, r.miscInfo, r.aliveCount, r.monstersAlive,
                    r.knightAlive, r.playerConstricted, r.asleep, r.halfDead});
            }
            const auto &r = m.pendingRollInputs;
            wm.pendingRollInputs = {r.curHp, r.maxHp, r.knightCurHp, r.knightMaxHp, r.monsterTurnNumber,
                                    r.miscInfo, r.aliveCount, r.monstersAlive, r.knightAlive,
                                    r.playerConstricted, r.asleep, r.halfDead};
        }

        out.nextUniqueCardId = state.cards.nextUniqueCardId;
        out.handNormalityCount = state.cards.handNormalityCount;
        out.handPainCount = state.cards.handPainCount;
        out.strikeCount = state.cards.strikeCount;
        out.handBloodCardCount = state.cards.handBloodCardCount;
        out.drawPileBloodCardCount = state.cards.drawPileBloodCardCount;
        out.discardPileBloodCardCount = state.cards.discardPileBloodCardCount;
        for (int i = 0; i < state.cards.cardsInHand; ++i) out.hand.push_back(toWire(state.cards.hand[i]));
        for (const auto &card : state.cards.limbo) out.limbo.push_back(toWire(card));
        for (std::size_t i = 0; i < out.stasisCards.size(); ++i) out.stasisCards[i] = toWire(state.cards.stasisCards[i]);
        out.drawPile = pileWire(state.cards.drawPile);
        for (const auto &c : state.cards.discardPile) out.discardPile.unknown.push_back(toWire(c));
        for (const auto &c : state.cards.exhaustPile) out.exhaustPile.unknown.push_back(toWire(c));

        const auto &select = state.cardSelectInfo;
        for (std::size_t i = 0; i < out.cardSelect.cards.size(); ++i) {
            out.cardSelect.cards[i] = static_cast<std::int16_t>(select.cards[i]);
        }
        out.cardSelect.canPickZero = select.canPickZero;
        out.cardSelect.canPickAnyNumber = select.canPickAnyNumber;
        out.cardSelect.pickCount = select.pickCount;
        out.cardSelect.data0 = select.data0;
        out.cardSelect.task = static_cast<std::int16_t>(select.cardSelectTask);
        out.cardSelect.setCostToZero = select.setCostToZero;
        out.cardSelect.drawAfter = select.drawAfter;
    out.cardSelect.drawsAfter = select.drawsAfter;
    out.cardSelect.blocksAfter = select.blocksAfter;
    out.cardSelect.damageAllBeforeBlocks = select.damageAllBeforeBlocks;
        out.cardSelect.selectedBits = 0;

        out.curCardQueueItem = toWire(state.curCardQueueItem);
        capturePendingActionQueue(state,out);
        if (state.inputState == InputState::CARD_SELECT) {
            out.pendingCardQueueObserved = true;
            const auto &queue = state.cardQueue;
            for (int i = 0; i < queue.size; ++i) {
                out.pendingCardQueue.push_back(toWire(queue.arr[(queue.frontIdx + i) % CardQueue::capacity]));
            }
        }
        return out;
    }

    SemanticAction semanticFromSearchAction(const BattleContext &state, const Action &action) {
        SemanticAction out;
        const auto task = state.cardSelectInfo.cardSelectTask;
        switch (action.getActionType()) {
            case ActionType::END_TURN:
                out.type = SemanticActionType::END_TURN;
                return out;

            case ActionType::CARD: {
                const int idx = action.getSourceIdx();
                out.type = SemanticActionType::CARD;
                out.source = CardSource::HAND;
                out.card = cardAt(state, CardSource::HAND, idx);
                // A card without a target leaves the packed target bits at
                // zero; that is not a target.
                out.target = state.cards.hand[idx].requiresTarget() ? action.getTargetIdx() : -1;
                return out;
            }

            case ActionType::POTION: {
                const int slot = action.getSourceIdx();
                if (slot < 0 || slot >= state.potionCapacity) {
                    throw std::runtime_error("Silver action names an invalid potion slot");
                }
                out.type = SemanticActionType::POTION;
                out.potionSlot = slot;
                out.potionId = static_cast<std::int16_t>(state.potions[slot]);
                out.discardPotion = action.getTargetIdx() > 5;
                out.target = !out.discardPotion && potionRequiresTarget(state.potions[slot])
                    ? action.getTargetIdx() : -1;
                return out;
            }

            case ActionType::MULTI_CARD_SELECT:
                out.type = SemanticActionType::MULTI_CARD_SELECT;
                out.source = CardSource::HAND;
                out.cardSelectTask = static_cast<std::int16_t>(task);
                for (const int idx : action.getSelectedIdxs()) {
                    out.selectedCards.push_back(cardAt(state, CardSource::HAND, idx));
                }
                return out;

            case ActionType::SINGLE_CARD_SELECT: {
                if (task == CardSelectTask::LIQUID_MEMORIES_POTION && state.cardSelectInfo.pickCount == 2) {
                    out.type = SemanticActionType::MULTI_CARD_SELECT;
                    out.source = CardSource::DISCARD;
                    out.cardSelectTask = static_cast<std::int16_t>(task);
                    out.selectedCards.push_back(cardAt(state,CardSource::DISCARD,action.getSelectIdx()));
                    out.selectedCards.push_back(cardAt(state,CardSource::DISCARD,action.getTargetIdx()-1));
                    return out;
                }
                const int idx = action.getSelectIdx();
                out.type = SemanticActionType::SINGLE_CARD_SELECT;
                out.cardSelectTask = static_cast<std::int16_t>(task);
                if (task == CardSelectTask::CODEX || task == CardSelectTask::DISCOVERY) {
                    out.source = CardSource::CARD_SELECT_OPTION;
                    if (idx == 3 && (task == CardSelectTask::CODEX || state.cardSelectInfo.canPickZero)) {
                        out.skipCardSelect = true;
                        return out;
                    }
                    if (idx < 0 || idx >= static_cast<int>(state.cardSelectInfo.cards.size())) {
                        throw std::runtime_error("Silver action names an invalid card option");
                    }
                    out.optionCardId = static_cast<std::int16_t>(state.cardSelectInfo.cards[idx]);
                    return out;
                }
                out.source = selectSource(task);
                if (out.source == CardSource::NONE) {
                    throw std::runtime_error("unsupported Silver card-select task="
                                             + std::to_string(static_cast<int>(task)));
                }
                out.card = cardAt(state, out.source, idx);
                return out;
            }
        }
        throw std::runtime_error("unsupported Silver action type");
    }

    std::string semanticFingerprint(const SemanticAction &action) {
        std::ostringstream out;
        out << "sa/t=" << static_cast<unsigned>(action.type)
            << "/s=" << static_cast<unsigned>(action.source)
            << "/c=" << cardFingerprint(action.card)
            << "/o=" << action.optionCardId
            << "/p=" << action.potionId << '_' << action.potionSlot
            << "/x=" << action.target
            << "/d=" << (action.discardPotion ? 1 : 0)
            << "/k=" << (action.skipCardSelect ? 1 : 0)
            << "/task=" << action.cardSelectTask
            << "/sel=";
        for (std::size_t i = 0; i < action.selectedCards.size(); ++i) {
            if (i != 0) out << '+';
            out << cardFingerprint(action.selectedCards[i]);
        }
        return out.str();
    }

}
