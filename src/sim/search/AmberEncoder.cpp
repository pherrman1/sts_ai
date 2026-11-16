// Native Amber-token combat encoder (stage 0, 2026-11-16); see AmberEncoder.h for the contract and id ranges.
//
// Float layout per token (index: value; "/k" = divided by k; flags are 0/1). Every slot past the listed ones is 0.
//
// RUN (1 token, ids none)
//   0 act/4  1 ascension/20  2 floorNum/50  3 turn/10  4 encounter (raw enum)/64  5 cardsDrawn/10
//   6 energyWasted/10  7 loopCount  8 monsterTurnIdx/5  9 monsterCount/5  10 monstersAlive/5
//   11 outcome victory  12 outcome loss  13 input PLAYER_NORMAL  14 input CARD_SELECT  15 inputState (raw)/16
//   16 endTurnQueued  17 turnHasEnded  18 skipMonsterTurn  19 intentsHidden  20 draw pile concrete (full order)
//   21 potionCount/5  22 potionCapacity/5  23 context omamoriCharged  24 actBossRoom  25 eliteRewards
//   26 actHealFollows  27 escapeForfeitsRun  28 miscBits bit 0  29 miscBits >> 1 (raw)
//   30 strikeCount/10  31 handNormalityCount  32 handPainCount  33 handBloodCardCount  34 drawPileBloodCardCount
//   35 discardPileBloodCardCount  36 cardsInHand/10  37 draw size/30  38 discard size/30  39 exhaust size/30
//   40 draw known top/10  41 draw known bottom/10
//   card select: 42 task (raw)/20  43 pickCount/10  44 canPickZero  45 canPickAnyNumber  46 data0
//   47 setCostToZero  48 drawAfter/10  49 damageAllBeforeBlocks/10  50 |drawsAfter|  51 sum(drawsAfter)/10
//   52 |blocksAfter|  53 sum(blocksAfter)/10
//   54 pending action queue length/10 (card-select states)  55 pending card queue length/10 (card-select states)
//   current card-queue item: 56 target/4  57 isEndTurn  58 triggerOnUse  59 ignoreEnergyTotal  60 energyOnUse/3
//   61 freeToPlay  62 randomTarget  63 autoplay
// PLAYER (1 token, ids none)
//   0 curHp/100  1 maxHp/100  2 curHp/maxHp  3 block/10  4 energy/3  5 energyPerTurn/3  6 cardDrawPerTurn/5
//   7 gold/100  8 stance (raw)  9 orbSlots  10 lastTargetedMonster/4  11 artifact  12 dexterity/10  13 focus/10
//   14 strength/10  15-21 relic counters (Happy Flower, Incense Burner, Ink Bottle, Inserter, Nunchaku, Pen Nib,
//   Sundial)/10  22 haveUsedNecronomiconThisTurn  23 combustHpLoss  24 devaFormEnergyPerTurn  25 echoFormCardsDoubled
//   26 panacheCounter  27 cardsPlayedThisTurn/10  28 attacksPlayedThisTurn/10  29 skillsPlayedThisTurn/10
//   30-32 orangePelletsCardTypesPlayed bits  33 cardsDiscardedThisTurn/10  34 lastAttackUnblockedDamage/10
//   35 timesDamagedThisCombat/10  36-38 bomb1..3/10  39 characterClass (raw)
// STATUS (one per player status present; ids[0] = status id)
//   0 amount/10 (0 for flag-only statuses)  1 justApplied  2 1
// MONSTER (one per occupied slot, wire rule: id or maxHp set; ids = monster, last move, move before, unique power)
//   0 curHp/100  1 maxHp/100  2 curHp/maxHp  3 block/10  4 curHp > 0  5 isEscapingB  6 halfDead  7 escapeNext
//   8 slot/4  9-19 artifact, blockReturn, choked, corpseExplosion, lockOn, mark, metallicize, platedArmor, poison,
//   regen, shackled (each /10)  20 strength/10  21 vulnerable/10  22 weak/10  23 uniquePower0/10
//   24 uniquePower1/10  25 miscInfo/10 (wire redaction under hidden intents)  26-28 INVINCIBLE, REACTIVE,
//   SHARP_HIDE  29-36 ASLEEP..STASIS flags  37 pendingMoveRolls  38 pendingDirectMoveChoice
//   39 popcount(latentDamageMask)  40 latentDamageMask/65536 (both 0 unless intents hidden)
//   41 extraRollMoveOnTurn bit  42 skipTurn bit  43-54 pendingRollInputs (curHp/100, maxHp/100, knightCurHp/100,
//   knightMaxHp/100, monsterTurnNumber/10, miscInfo/10, aliveCount, monstersAlive, knightAlive, playerConstricted,
//   asleep, halfDead)  55 |pendingAttackPredicates|  56 |pendingRollInputHistory|  57-60 the first two predicates
//   (value/10, flag)  61-63 last history entry (curHp/100, monsterTurnNumber/10, miscInfo/10)
// CARD (ids[0] = card id)
//   0-9 zone: hand, draw known bottom, draw unknown, draw known top, discard, exhaust, limbo, stasis,
//   current card-queue item, pending card queue  11 position/10 (hand index; known bottom: from the bottom; known
//   top / concrete pile: from the top, 0 = next draw; unknown, discard, exhaust: 0, as the wire's multisets)
//   12 upgraded  13 cost/3  14 costForTurn/3  15 freeToPlayOnce  16 retain  17 specialData/10
//   queue items: 20 target/4  21 isEndTurn  22 triggerOnUse  23 ignoreEnergyTotal  24 energyOnUse/3  25 freeToPlay
//   26 randomTarget  27 autoplay  28 regretCardCount  29 purgeOnUse  30 exhaustOnUse
// RELIC (ids[0] = relic id)   0 the relic's counter/10 (counter relics)  1 1
// POTION (one per filled slot; ids[0] = potion id)   0 slot/5  1 needs a target  2 1
// OPTION
//   card-select option cards (cardSelectInfo.cards, ids[0] = card id): 0 1  1 option index/3
//     2 live (card-select state with a Codex / Discovery task)
//   pending action queue items (card-select states; ids[0] = status / move / card id where the action has one):
//     4 1  5 CombatActionType (raw)/128  6 kind the wire exports  7 amount/10  8 status (raw)/64  9 monster/4
//     10 sourceMonster  11 queue position/10
#include "sim/search/AmberEncoder.h"

#include <cstring>

#include "combat/Actions.h"

namespace sts::search {

    std::uint16_t amberHalf(float x) {
        // F. Giesen, float_to_half_fast3_rtne (public domain).
        std::uint32_t u;
        std::memcpy(&u, &x, 4);
        const std::uint32_t sign = u & 0x80000000u;
        u ^= sign;
        std::uint16_t o;
        if (u >= 0x47800000u) {   // >= 65536 (incl. inf, nan): inf, nan stays nan
            o = u > 0x7f800000u ? 0x7e00 : 0x7c00;
            // 65520..65535 round to inf as well; [65504, 65520) handled below would need u < 0x477ff000.
        } else if (u < 0x38800000u) {   // below 2^-14: half subnormal or zero
            float f;
            std::memcpy(&f, &u, 4);
            constexpr std::uint32_t kMagicU = ((127 - 15) + (23 - 10) + 1) << 23;
            float magic;
            std::memcpy(&magic, &kMagicU, 4);
            f += magic;
            std::uint32_t r;
            std::memcpy(&r, &f, 4);
            o = static_cast<std::uint16_t>(r - kMagicU);
        } else {
            const std::uint32_t odd = (u >> 13) & 1u;
            u += 0xc8000fffu;   // ((15 - 127) << 23) + 0xfff, mod 2^32
            u += odd;
            o = static_cast<std::uint16_t>(u >> 13);
        }
        return static_cast<std::uint16_t>(o | (sign >> 16));
    }

    float amberHalfToFloat(std::uint16_t h) {
        const std::uint32_t sign = static_cast<std::uint32_t>(h & 0x8000u) << 16;
        const std::uint32_t exp = (h >> 10) & 0x1fu, man = h & 0x3ffu;
        std::uint32_t u;
        if (exp == 0x1f) {
            u = sign | 0x7f800000u | (man << 13);
        } else if (exp == 0) {
            const float v = static_cast<float>(man) * (1.0f / 16777216.0f);
            std::memcpy(&u, &v, 4);
            u |= sign;
        } else {
            u = sign | ((exp + 112u) << 23) | (man << 13);
        }
        float out;
        std::memcpy(&out, &u, 4);
        return out;
    }

    namespace {

        using T = AmberTokenType;
        constexpr std::uint8_t kNone = 0xff;
        constexpr int kCardCap = kAmberCap[static_cast<int>(T::CARD)];

        enum Zone { HAND, DRAW_BOTTOM, DRAW_UNKNOWN, DRAW_TOP, DISCARD, EXHAUST, LIMBO, STASIS, CUR_QUEUE, CARD_QUEUE };

        struct Enc {
            AmberTokens &out;
            std::uint8_t handTok[CardManager::MAX_HAND_SIZE];
            std::uint8_t drawTok[kCardCap], discardTok[kCardCap], exhaustTok[kCardCap];
            std::uint8_t monTok[5], potTok[5], optTok[3];

            explicit Enc(AmberTokens &o) : out(o) {
                std::memset(handTok, kNone, sizeof(handTok));
                std::memset(drawTok, kNone, sizeof(drawTok));
                std::memset(discardTok, kNone, sizeof(discardTok));
                std::memset(exhaustTok, kNone, sizeof(exhaustTok));
                std::memset(monTok, kNone, sizeof(monTok));
                std::memset(potTok, kNone, sizeof(potTok));
                std::memset(optTok, kNone, sizeof(optTok));
            }

            // A zeroed new token of segment s, or nullptr (counted in cut) when s is full; *idx = its index.
            AmberToken *push(T s, std::uint8_t *idx = nullptr) {
                const int si = static_cast<int>(s);
                if (out.n[si] >= kAmberCap[si]) {
                    ++out.cut;
                    return nullptr;
                }
                const int i = out.n[si]++;
                AmberToken &t = out.tok[kAmberOff[si] + i];
                std::memset(&t, 0, sizeof(t));
                if (idx) *idx = static_cast<std::uint8_t>(i);
                return &t;
            }
        };

        inline void put(AmberToken &t, int i, float v) { t.f[i] = amberHalf(v); }
        inline void flag(AmberToken &t, int i, bool v) { t.f[i] = v ? 0x3c00 : 0; }   // 1.0 in float16

        inline std::int16_t cardId(CardId id) { return static_cast<std::int16_t>(kAmberCardBase + static_cast<int>(id) - 1); }
        inline std::int16_t statusId(PlayerStatus s) {
            return static_cast<std::int16_t>(kAmberStatusBase + static_cast<int>(s) - 1);
        }
        inline std::int16_t moveId(MonsterMoveId m) {
            return m == MonsterMoveId::INVALID ? 0 : static_cast<std::int16_t>(kAmberMoveBase + static_cast<int>(m) - 1);
        }

        inline int popcount64(std::uint64_t v) { return __builtin_popcountll(v); }

        void queueFields(AmberToken &t, const CardQueueItem &q, int base) {
            put(t, base + 0, q.target / 4.0f);
            flag(t, base + 1, q.isEndTurn);
            flag(t, base + 2, q.triggerOnUse);
            flag(t, base + 3, q.ignoreEnergyTotal);
            put(t, base + 4, q.energyOnUse / 3.0f);
            flag(t, base + 5, q.freeToPlay);
            flag(t, base + 6, q.randomTarget);
            flag(t, base + 7, q.autoplay);
        }

        AmberToken *card(Enc &e, const CardInstance &c, int zone, int pos, std::uint8_t *idx = nullptr) {
            AmberToken *t = e.push(T::CARD, idx);
            if (!t) return nullptr;
            t->ids[0] = cardId(c.id);
            flag(*t, zone, true);
            put(*t, 11, pos / 10.0f);
            flag(*t, 12, c.upgraded);
            put(*t, 13, c.cost / 3.0f);
            put(*t, 14, c.costForTurn / 3.0f);
            flag(*t, 15, c.freeToPlayOnce);
            flag(*t, 16, c.retain);
            put(*t, 17, c.specialData / 10.0f);
            return t;
        }

        void queueCard(Enc &e, const CardQueueItem &q, int zone, int pos) {
            AmberToken *t = card(e, q.card, zone, pos);
            if (!t) return;
            queueFields(*t, q, 20);
            put(*t, 28, static_cast<float>(q.regretCardCount));
            flag(*t, 29, q.purgeOnUse);
            flag(*t, 30, q.exhaustOnUse);
        }

        int relicCounter(const Player &p, RelicId r, bool &has) {
            has = true;
            switch (r) {
                case RelicId::HAPPY_FLOWER: return p.happyFlowerCounter;
                case RelicId::INCENSE_BURNER: return p.incenseBurnerCounter;
                case RelicId::INK_BOTTLE: return p.inkBottleCounter;
                case RelicId::INSERTER: return p.inserterCounter;
                case RelicId::NUNCHAKU: return p.nunchakuCounter;
                case RelicId::PEN_NIB: return p.penNibCounter;
                case RelicId::SUNDIAL: return p.sundialCounter;
                default: has = false; return 0;
            }
        }

        void status(Enc &e, const Player &p, PlayerStatus s, int amount) {
            AmberToken *t = e.push(T::STATUS);
            if (!t) return;
            const int si = static_cast<int>(s);
            t->ids[0] = statusId(s);
            put(*t, 0, amount / 10.0f);
            flag(*t, 1, si < 32 && ((p.justAppliedBits >> si) & 1u));
            flag(*t, 2, true);
        }

        // One pending action-queue item as an OPTION token (the kinds capturePendingActionQueue exports carry their
        // parameters; any other action only its type).
        void pendingAction(Enc &e, const sts::Action &a, int pos) {
            AmberToken *t = e.push(T::OPTION);
            if (!t) return;
            flag(*t, 4, true);
            put(*t, 5, static_cast<float>(a.type) / 128.0f);
            put(*t, 11, pos / 10.0f);
            int amount = 0, statusRaw = 0, monster = 0;
            bool source = false, known = true;
            using C = CombatActionType;
            switch (a.type) {
                case C::DrawCards: amount = a.v_DrawCards.amount; break;
                case C::GainBlock: amount = a.v_GainBlock.amount; break;
                case C::GainEnergy: amount = a.v_GainEnergy.amount; break;
                case C::DamageAllEnemy: amount = a.v_DamageAllEnemy.damage; break;
                case C::DamageRandomEnemy: amount = a.v_DamageRandomEnemy.damage; break;
                case C::GambleAction:
                case C::UpgradeRandomCardAction:
                case C::OnAfterCardUsed:
                case C::RemovePlayerDebuffs:
                case C::ReactiveRollMove: break;
                case C::RemoveStatus:
                    statusRaw = static_cast<int>(a.v_RemoveStatus.s);
                    if (a.v_RemoveStatus.s != PlayerStatus::INVALID) t->ids[0] = statusId(a.v_RemoveStatus.s);
                    break;
                case C::HealPlayer: amount = a.v_HealPlayer.amount; break;
                case C::MonsterGainBlock:
                    monster = a.v_MonsterGainBlock.idx;
                    amount = a.v_MonsterGainBlock.amount;
                    break;
                case C::DamagePlayer: amount = a.v_DamagePlayer.damage; break;
                case C::SetMonsterMove:
                    monster = a.v_SetMonsterMove.monsterIdx;
                    amount = static_cast<int>(a.v_SetMonsterMove.move);
                    t->ids[0] = moveId(a.v_SetMonsterMove.move);
                    break;
                case C::BuffPlayer:
                    statusRaw = static_cast<int>(a.v_BuffPlayer.s);
                    amount = a.v_BuffPlayer.amount;
                    if (a.v_BuffPlayer.s != PlayerStatus::INVALID) t->ids[0] = statusId(a.v_BuffPlayer.s);
                    break;
                case C::DebuffPlayer:
                    statusRaw = static_cast<int>(a.v_DebuffPlayer.s);
                    amount = a.v_DebuffPlayer.amount;
                    source = a.v_DebuffPlayer.isSourceMonster;
                    if (a.v_DebuffPlayer.s != PlayerStatus::INVALID) t->ids[0] = statusId(a.v_DebuffPlayer.s);
                    break;
                case C::DebuffAllEnemy:
                    statusRaw = static_cast<int>(a.v_DebuffAllEnemy.s);
                    amount = a.v_DebuffAllEnemy.amount;
                    source = a.v_DebuffAllEnemy.isSourceMonster;
                    break;
                case C::DebuffEnemy:
                    statusRaw = static_cast<int>(a.v_DebuffEnemy.s);
                    monster = a.v_DebuffEnemy.idx;
                    amount = a.v_DebuffEnemy.amount;
                    source = a.v_DebuffEnemy.isSourceMonster;
                    break;
                case C::MakeTempCardInDrawPile:
                    amount = a.v_MakeTempCardInDrawPile.amount;
                    if (a.v_MakeTempCardInDrawPile.c.id != CardId::INVALID)
                        t->ids[0] = cardId(a.v_MakeTempCardInDrawPile.c.id);
                    break;
                default: known = false; break;
            }
            flag(*t, 6, known);
            put(*t, 7, amount / 10.0f);
            put(*t, 8, statusRaw / 64.0f);
            put(*t, 9, monster / 4.0f);
            flag(*t, 10, source);
        }

        void run(Enc &e, const BattleContext &s, const SilverSearchContext &ctx) {
            AmberToken &t = *e.push(T::RUN);
            const auto &cm = s.cards;
            const auto &sel = s.cardSelectInfo;
            put(t, 0, ctx.act / 4.0f);
            put(t, 1, s.ascension / 20.0f);
            put(t, 2, s.floorNum / 50.0f);
            put(t, 3, s.turn / 10.0f);
            put(t, 4, static_cast<float>(s.encounter) / 64.0f);
            put(t, 5, s.cardsDrawn / 10.0f);
            put(t, 6, s.energyWasted / 10.0f);
            put(t, 7, static_cast<float>(s.loopCount));
            put(t, 8, s.monsterTurnIdx / 5.0f);
            put(t, 9, s.monsters.monsterCount / 5.0f);
            put(t, 10, s.monsters.monstersAlive / 5.0f);
            flag(t, 11, s.outcome == Outcome::PLAYER_VICTORY);
            flag(t, 12, s.outcome == Outcome::PLAYER_LOSS);
            flag(t, 13, s.inputState == InputState::PLAYER_NORMAL);
            flag(t, 14, s.inputState == InputState::CARD_SELECT);
            put(t, 15, static_cast<float>(s.inputState) / 16.0f);
            flag(t, 16, s.endTurnQueued);
            flag(t, 17, s.turnHasEnded);
            flag(t, 18, s.skipMonsterTurn);
            flag(t, 19, s.intentsHidden);
            flag(t, 20, cm.drawPile.isConcrete());
            put(t, 21, s.potionCount / 5.0f);
            put(t, 22, s.potionCapacity / 5.0f);
            flag(t, 23, ctx.omamoriCharged);
            flag(t, 24, ctx.actBossRoom);
            flag(t, 25, ctx.eliteRewards);
            flag(t, 26, ctx.actHealFollows);
            flag(t, 27, ctx.escapeForfeitsRun);
            const auto misc = static_cast<std::uint32_t>(s.miscBits.to_ulong());
            flag(t, 28, misc & 1u);
            put(t, 29, static_cast<float>(misc >> 1));
            put(t, 30, cm.strikeCount / 10.0f);
            put(t, 31, static_cast<float>(cm.handNormalityCount));
            put(t, 32, static_cast<float>(cm.handPainCount));
            put(t, 33, static_cast<float>(cm.handBloodCardCount));
            put(t, 34, static_cast<float>(cm.drawPileBloodCardCount));
            put(t, 35, static_cast<float>(cm.discardPileBloodCardCount));
            put(t, 36, cm.cardsInHand / 10.0f);
            put(t, 37, cm.drawPile.size() / 30.0f);
            put(t, 38, static_cast<float>(cm.discardPile.size()) / 30.0f);
            put(t, 39, static_cast<float>(cm.exhaustPile.size()) / 30.0f);
            put(t, 40, cm.drawPile.knownTop() / 10.0f);
            put(t, 41, cm.drawPile.knownBottom() / 10.0f);
            put(t, 42, static_cast<float>(sel.cardSelectTask) / 20.0f);
            put(t, 43, sel.pickCount / 10.0f);
            flag(t, 44, sel.canPickZero);
            flag(t, 45, sel.canPickAnyNumber);
            put(t, 46, static_cast<float>(sel.data0));
            flag(t, 47, sel.setCostToZero);
            put(t, 48, sel.drawAfter / 10.0f);
            put(t, 49, sel.damageAllBeforeBlocks / 10.0f);
            int sum = 0;
            for (const int v : sel.drawsAfter) sum += v;
            put(t, 50, static_cast<float>(sel.drawsAfter.size()));
            put(t, 51, sum / 10.0f);
            sum = 0;
            for (const int v : sel.blocksAfter) sum += v;
            put(t, 52, static_cast<float>(sel.blocksAfter.size()));
            put(t, 53, sum / 10.0f);
            if (s.inputState == InputState::CARD_SELECT) {
                put(t, 54, s.actionQueue.size / 10.0f);
                put(t, 55, s.cardQueue.size / 10.0f);
            }
            queueFields(t, s.curCardQueueItem, 56);
        }

        void player(Enc &e, const Player &p) {
            AmberToken &t = *e.push(T::PLAYER);
            put(t, 0, p.curHp / 100.0f);
            put(t, 1, p.maxHp / 100.0f);
            put(t, 2, p.maxHp > 0 ? static_cast<float>(p.curHp) / static_cast<float>(p.maxHp) : 0.0f);
            put(t, 3, p.block / 10.0f);
            put(t, 4, p.energy / 3.0f);
            put(t, 5, p.energyPerTurn / 3.0f);
            put(t, 6, p.cardDrawPerTurn / 5.0f);
            put(t, 7, p.gold / 100.0f);
            put(t, 8, static_cast<float>(p.stance));
            put(t, 9, static_cast<float>(p.orbSlots));
            put(t, 10, p.lastTargetedMonster / 4.0f);
            put(t, 11, static_cast<float>(p.artifact));
            put(t, 12, p.dexterity / 10.0f);
            put(t, 13, p.focus / 10.0f);
            put(t, 14, p.strength / 10.0f);
            const int counters[7] = {p.happyFlowerCounter, p.incenseBurnerCounter, p.inkBottleCounter,
                                     p.inserterCounter, p.nunchakuCounter, p.penNibCounter, p.sundialCounter};
            for (int i = 0; i < 7; ++i) put(t, 15 + i, counters[i] / 10.0f);
            flag(t, 22, p.haveUsedNecronomiconThisTurn);
            put(t, 23, static_cast<float>(p.combustHpLoss));
            put(t, 24, static_cast<float>(p.devaFormEnergyPerTurn));
            put(t, 25, static_cast<float>(p.echoFormCardsDoubled));
            put(t, 26, static_cast<float>(p.panacheCounter));
            put(t, 27, p.cardsPlayedThisTurn / 10.0f);
            put(t, 28, p.attacksPlayedThisTurn / 10.0f);
            put(t, 29, p.skillsPlayedThisTurn / 10.0f);
            for (int i = 0; i < 3; ++i) flag(t, 30 + i, p.orangePelletsCardTypesPlayed[i]);
            put(t, 33, p.cardsDiscardedThisTurn / 10.0f);
            put(t, 34, p.lastAttackUnblockedDamage / 10.0f);
            put(t, 35, p.timesDamagedThisCombat / 10.0f);
            put(t, 36, p.bomb1 / 10.0f);
            put(t, 37, p.bomb2 / 10.0f);
            put(t, 38, p.bomb3 / 10.0f);
            put(t, 39, static_cast<float>(p.cc));
        }

        void statuses(Enc &e, const Player &p) {
            constexpr int kArt = static_cast<int>(PlayerStatus::ARTIFACT), kDex = static_cast<int>(PlayerStatus::DEXTERITY);
            constexpr int kFoc = static_cast<int>(PlayerStatus::FOCUS), kStr = static_cast<int>(PlayerStatus::STRENGTH);
            // The four field-backed statuses are present when nonzero (Player::hasStatusRuntime), not by their bit.
            std::uint64_t b0 = p.statusBits0 & ~1ULL;   // bit 0 = INVALID
            std::uint64_t b1 = p.statusBits1;
            for (const int k : {kArt, kDex, kFoc, kStr}) {
                if (k < 64) b0 &= ~(1ULL << k);
                else b1 &= ~(1ULL << (k - 64));
            }
            b1 &= (1ULL << (static_cast<int>(PlayerStatus::THE_BOMB) + 1 - 64)) - 1;
            auto mapped = [&](PlayerStatus s) {
                const auto it = p.statusMap.find(s);
                return it == p.statusMap.end() ? 0 : static_cast<int>(it->second);
            };
            while (b0) {
                const int k = __builtin_ctzll(b0);
                b0 &= b0 - 1;
                const auto s = static_cast<PlayerStatus>(k);
                status(e, p, s, mapped(s));
            }
            while (b1) {
                const int k = __builtin_ctzll(b1);
                b1 &= b1 - 1;
                const auto s = static_cast<PlayerStatus>(64 + k);
                status(e, p, s, mapped(s));
            }
            if (p.artifact) status(e, p, PlayerStatus::ARTIFACT, p.artifact);
            if (p.dexterity) status(e, p, PlayerStatus::DEXTERITY, p.dexterity);
            if (p.focus) status(e, p, PlayerStatus::FOCUS, p.focus);
            if (p.strength) status(e, p, PlayerStatus::STRENGTH, p.strength);
        }

        void monsters(Enc &e, const BattleContext &s) {
            for (int i = 0; i < 5; ++i) {
                const Monster &m = s.monsters.arr[i];
                if (m.id == MonsterId::INVALID && m.maxHp == 0) continue;   // empty slot (wire encoder rule)
                AmberToken *tp = e.push(T::MONSTER, &e.monTok[i]);
                if (!tp) continue;
                AmberToken &t = *tp;
                t.ids[0] = m.id == MonsterId::INVALID
                    ? 0 : static_cast<std::int16_t>(kAmberMonsterBase + static_cast<int>(m.id) - 1);
                t.ids[1] = moveId(m.moveHistory[0]);
                t.ids[2] = moveId(m.moveHistory[1]);
                for (int k = static_cast<int>(MonsterStatus::ANGRY); k <= static_cast<int>(MonsterStatus::TIME_WARP); ++k) {
                    if ((m.statusBits >> k) & 1ULL) {
                        t.ids[3] = static_cast<std::int16_t>(kAmberMonPowerBase + k - static_cast<int>(MonsterStatus::ANGRY));
                        break;
                    }
                }
                const std::uint16_t latent = s.intentsHidden ? m.latentDamageMask : 0;
                const int misc = s.intentsHidden && latent ? 0 : m.miscInfo;
                put(t, 0, m.curHp / 100.0f);
                put(t, 1, m.maxHp / 100.0f);
                put(t, 2, m.maxHp > 0 ? static_cast<float>(m.curHp) / static_cast<float>(m.maxHp) : 0.0f);
                put(t, 3, m.block / 10.0f);
                flag(t, 4, m.curHp > 0);
                flag(t, 5, m.isEscapingB);
                flag(t, 6, m.halfDead);
                flag(t, 7, m.escapeNext);
                put(t, 8, i / 4.0f);
                const int small[11] = {m.artifact, m.blockReturn, m.choked, m.corpseExplosion, m.lockOn, m.mark,
                                       m.metallicize, m.platedArmor, m.poison, m.regen, m.shackled};
                for (int k = 0; k < 11; ++k) put(t, 9 + k, small[k] / 10.0f);
                put(t, 20, m.strength / 10.0f);
                put(t, 21, m.vulnerable / 10.0f);
                put(t, 22, m.weak / 10.0f);
                put(t, 23, m.uniquePower0 / 10.0f);
                put(t, 24, m.uniquePower1 / 10.0f);
                put(t, 25, misc / 10.0f);
                for (int k = 0; k < 3; ++k)
                    flag(t, 26 + k, (m.statusBits >> (static_cast<int>(MonsterStatus::INVINCIBLE) + k)) & 1ULL);
                for (int k = 0; k < 8; ++k)
                    flag(t, 29 + k, (m.statusBits >> (static_cast<int>(MonsterStatus::ASLEEP) + k)) & 1ULL);
                put(t, 37, static_cast<float>(m.pendingMoveRolls));
                put(t, 38, static_cast<float>(m.pendingDirectMoveChoice));
                put(t, 39, static_cast<float>(popcount64(latent)));
                put(t, 40, latent / 65536.0f);
                flag(t, 41, s.monsters.extraRollMoveOnTurn[i]);
                flag(t, 42, s.monsters.skipTurn[i]);
                const auto &r = m.pendingRollInputs;
                put(t, 43, r.curHp / 100.0f);
                put(t, 44, r.maxHp / 100.0f);
                put(t, 45, r.knightCurHp / 100.0f);
                put(t, 46, r.knightMaxHp / 100.0f);
                put(t, 47, r.monsterTurnNumber / 10.0f);
                put(t, 48, r.miscInfo / 10.0f);
                put(t, 49, static_cast<float>(r.aliveCount));
                put(t, 50, static_cast<float>(r.monstersAlive));
                flag(t, 51, r.knightAlive);
                flag(t, 52, r.playerConstricted);
                flag(t, 53, r.asleep);
                flag(t, 54, r.halfDead);
                put(t, 55, static_cast<float>(m.pendingAttackPredicates.size()));
                put(t, 56, static_cast<float>(m.pendingRollInputHistory.size()));
                for (int k = 0; k < 2 && k < static_cast<int>(m.pendingAttackPredicates.size()); ++k) {
                    put(t, 57 + 2 * k, m.pendingAttackPredicates[k].first / 10.0f);
                    flag(t, 58 + 2 * k, m.pendingAttackPredicates[k].second);
                }
                if (!m.pendingRollInputHistory.empty()) {
                    const auto &h = m.pendingRollInputHistory.back();
                    put(t, 61, h.curHp / 100.0f);
                    put(t, 62, h.monsterTurnNumber / 10.0f);
                    put(t, 63, h.miscInfo / 10.0f);
                }
            }
        }

        void cards(Enc &e, const BattleContext &s) {
            const auto &cm = s.cards;
            for (int i = 0; i < cm.cardsInHand; ++i) card(e, cm.hand[i], HAND, i, &e.handTok[i]);
            if (s.curCardQueueItem.card.id != CardId::INVALID) queueCard(e, s.curCardQueueItem, CUR_QUEUE, 0);
            if (s.inputState == InputState::CARD_SELECT) {
                const auto &q = s.cardQueue;
                for (int i = 0; i < q.size; ++i) queueCard(e, q.arr[(q.frontIdx + i) % CardQueue::capacity], CARD_QUEUE, i);
            }
            const auto &dp = cm.drawPile;
            const int n = dp.size(), bottom = dp.knownBottom(), top = dp.knownTop();
            const bool concrete = dp.isConcrete();
            for (int i = 0; i < n; ++i) {
                int zone, pos;
                if (concrete || i >= n - top) {
                    zone = DRAW_TOP;
                    pos = n - 1 - i;
                } else if (i < bottom) {
                    zone = DRAW_BOTTOM;
                    pos = i;
                } else {
                    zone = DRAW_UNKNOWN;
                    pos = 0;
                }
                card(e, dp[i], zone, pos, i < kCardCap ? &e.drawTok[i] : nullptr);
            }
            for (int i = 0; i < static_cast<int>(cm.discardPile.size()); ++i)
                card(e, cm.discardPile[i], DISCARD, 0, i < kCardCap ? &e.discardTok[i] : nullptr);
            for (int i = 0; i < static_cast<int>(cm.exhaustPile.size()); ++i)
                card(e, cm.exhaustPile[i], EXHAUST, 0, i < kCardCap ? &e.exhaustTok[i] : nullptr);
            for (int i = 0; i < CardManager::MAX_HAND_SIZE; ++i)
                if (cm.limbo[i].id != CardId::INVALID) card(e, cm.limbo[i], LIMBO, i);
            for (int i = 0; i < 2; ++i)
                if (cm.stasisCards[i].id != CardId::INVALID) card(e, cm.stasisCards[i], STASIS, i);
        }

        void relics(Enc &e, const Player &p) {
            for (int word = 0; word < 2; ++word) {
                std::uint64_t b = word == 0 ? p.relicBits0 : p.relicBits1;
                while (b) {
                    const int k = word * 64 + __builtin_ctzll(b);
                    b &= b - 1;
                    if (k >= static_cast<int>(RelicId::INVALID)) break;
                    AmberToken *t = e.push(T::RELIC);
                    if (!t) continue;
                    const auto r = static_cast<RelicId>(k);
                    t->ids[0] = static_cast<std::int16_t>(kAmberRelicBase + k);
                    bool has;
                    const int c = relicCounter(p, r, has);
                    if (has) put(*t, 0, c / 10.0f);
                    flag(*t, 1, true);
                }
            }
        }

        void potions(Enc &e, const BattleContext &s) {
            const int cap = s.potionCapacity < 5 ? s.potionCapacity : 5;
            for (int i = 0; i < cap; ++i) {
                const Potion p = s.potions[i];
                if (p == Potion::INVALID || p == Potion::EMPTY_POTION_SLOT) continue;
                AmberToken *t = e.push(T::POTION, &e.potTok[i]);
                if (!t) continue;
                t->ids[0] = static_cast<std::int16_t>(kAmberPotionBase + static_cast<int>(p) - 2);
                put(*t, 0, i / 5.0f);
                flag(*t, 1, potionRequiresTarget(p));
                flag(*t, 2, true);
            }
        }

        void options(Enc &e, const BattleContext &s) {
            const auto &sel = s.cardSelectInfo;
            const bool live = s.inputState == InputState::CARD_SELECT
                && (sel.cardSelectTask == CardSelectTask::CODEX || sel.cardSelectTask == CardSelectTask::DISCOVERY);
            for (int i = 0; i < 3; ++i) {
                if (sel.cards[i] == CardId::INVALID) continue;
                AmberToken *t = e.push(T::OPTION, &e.optTok[i]);
                if (!t) continue;
                t->ids[0] = cardId(sel.cards[i]);
                flag(*t, 0, true);
                put(*t, 1, i / 3.0f);
                flag(*t, 2, live);
            }
            if (s.inputState != InputState::CARD_SELECT) return;
            const auto &q = s.actionQueue;
            for (int i = 0, cur = q.front; i < q.size; ++i, ++cur) {
                if (cur >= q.getCapacity()) cur = 0;
                pendingAction(e, q.arr[cur], i);
            }
        }

        void setSrc(AmberAction &a, T seg, std::uint8_t idx) {
            if (idx == kNone) return;
            a.srcSeg = static_cast<std::uint8_t>(seg);
            a.srcIdx = idx;
        }
        void setTgt(AmberAction &a, T seg, std::uint8_t idx) {
            if (idx == kNone) return;
            a.tgtSeg = static_cast<std::uint8_t>(seg);
            a.tgtIdx = idx;
        }

        std::uint8_t tokAt(const std::uint8_t *map, int size, int idx) {
            return idx >= 0 && idx < size ? map[idx] : kNone;
        }

        const std::uint8_t *selectPile(const Enc &e, CardSelectTask task, int &size, const BattleContext &s) {
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
                    size = s.cards.cardsInHand;
                    return e.handTok;
                case CardSelectTask::HEADBUTT:
                case CardSelectTask::HOLOGRAM:
                case CardSelectTask::LIQUID_MEMORIES_POTION:
                case CardSelectTask::MEDITATE:
                    size = std::min<int>(static_cast<int>(s.cards.discardPile.size()), kCardCap);
                    return e.discardTok;
                case CardSelectTask::EXHUME:
                    size = std::min<int>(static_cast<int>(s.cards.exhaustPile.size()), kCardCap);
                    return e.exhaustTok;
                case CardSelectTask::SECRET_TECHNIQUE:
                case CardSelectTask::SECRET_WEAPON:
                case CardSelectTask::SEEK:
                    size = std::min(s.cards.drawPile.size(), kCardCap);
                    return e.drawTok;
                default:
                    size = 0;
                    return nullptr;
            }
        }

        void action(const Enc &e, const BattleContext &s, const search::Action &in, AmberAction &a) {
            using AT = AmberActionType;
            a = AmberAction{};
            const auto &sel = s.cardSelectInfo;
            switch (in.getActionType()) {
                case ActionType::END_TURN:
                    a.type = static_cast<std::uint8_t>(AT::END_TURN);
                    return;
                case ActionType::CARD: {
                    const int idx = in.getSourceIdx();
                    a.type = static_cast<std::uint8_t>(AT::PLAY_CARD);
                    if (idx < 0 || idx >= s.cards.cardsInHand) break;
                    setSrc(a, T::CARD, e.handTok[idx]);
                    if (s.cards.hand[idx].requiresTarget()) {
                        const int tgt = in.getTargetIdx();
                        setTgt(a, T::MONSTER, tokAt(e.monTok, 5, tgt));
                        a.f[0] = 0x3c00;
                        a.f[1] = amberHalf(tgt / 4.0f);
                    }
                    return;
                }
                case ActionType::POTION: {
                    const int slot = in.getSourceIdx(), tgt = in.getTargetIdx();
                    const bool discard = tgt > 5;
                    a.type = static_cast<std::uint8_t>(discard ? AT::DISCARD_POTION : AT::USE_POTION);
                    if (slot < 0 || slot >= 5) break;
                    setSrc(a, T::POTION, e.potTok[slot]);
                    if (!discard && potionRequiresTarget(s.potions[slot])) {
                        setTgt(a, T::MONSTER, tokAt(e.monTok, 5, tgt));
                        a.f[0] = 0x3c00;
                        a.f[1] = amberHalf(tgt / 4.0f);
                    }
                    return;
                }
                case ActionType::SINGLE_CARD_SELECT: {
                    const int idx = in.getSelectIdx();
                    const auto task = sel.cardSelectTask;
                    a.f[2] = amberHalf(idx / 10.0f);
                    if (task == CardSelectTask::LIQUID_MEMORIES_POTION && sel.pickCount == 2) {
                        a.type = static_cast<std::uint8_t>(AT::SELECT_TWO);
                        const int n = std::min<int>(static_cast<int>(s.cards.discardPile.size()), kCardCap);
                        setSrc(a, T::CARD, tokAt(e.discardTok, n, idx));
                        setTgt(a, T::CARD, tokAt(e.discardTok, n, in.getTargetIdx() - 1));
                        return;
                    }
                    if (task == CardSelectTask::CODEX || task == CardSelectTask::DISCOVERY) {
                        if (idx == 3 && (task == CardSelectTask::CODEX || sel.canPickZero)) {
                            a.type = static_cast<std::uint8_t>(AT::SKIP_SELECT);
                            return;
                        }
                        a.type = static_cast<std::uint8_t>(AT::SELECT_OPTION);
                        setSrc(a, T::OPTION, tokAt(e.optTok, 3, idx));
                        return;
                    }
                    int size = 0;
                    const std::uint8_t *map = selectPile(e, task, size, s);
                    if (!map) break;
                    a.type = static_cast<std::uint8_t>(AT::SELECT_CARD);
                    setSrc(a, T::CARD, tokAt(map, size, idx));
                    return;
                }
                case ActionType::MULTI_CARD_SELECT: {
                    const unsigned mask = in.bits & 0x3ffu;
                    a.type = static_cast<std::uint8_t>(AT::SELECT_MANY);
                    a.f[0] = amberHalf(__builtin_popcount(mask) / 10.0f);
                    a.f[1] = amberHalf(static_cast<float>(mask));   // exact: integers below 2048
                    if (mask) {
                        setSrc(a, T::CARD, tokAt(e.handTok, s.cards.cardsInHand, __builtin_ctz(mask)));
                        setTgt(a, T::CARD, tokAt(e.handTok, s.cards.cardsInHand, 31 - __builtin_clz(mask)));
                    }
                    return;
                }
            }
            a = AmberAction{};
            a.type = static_cast<std::uint8_t>(AT::UNKNOWN);
        }

    }  // namespace

    void amberEncodeCombat(const BattleContext &state, const SilverSearchContext &context,
                           const std::vector<search::Action> &actions, AmberTokens &out) {
        out.clear();
        Enc e(out);
        run(e, state, context);
        player(e, state.player);
        statuses(e, state.player);
        monsters(e, state);
        cards(e, state);
        relics(e, state.player);
        potions(e, state);
        options(e, state);
        const int n = static_cast<int>(actions.size());
        const int keep = n < kAmberMaxActions ? n : kAmberMaxActions;
        for (int i = 0; i < keep; ++i) action(e, state, actions[i], out.act[i]);
        out.nAct = keep;
        out.cut += n - keep;
    }

}
