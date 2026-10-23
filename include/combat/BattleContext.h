//
// Created by gamerpuppy on 7/4/2021.
//

#ifndef STS_LIGHTSPEED_BATTLECONTEXT_H
#define STS_LIGHTSPEED_BATTLECONTEXT_H

#include <cstdint>
#include <vector>
#include <array>
#include <functional>

#include "sts_common.h"

#include "data_structure/fixed_list.h"
#include "constants/Potions.h"
#include "constants/MonsterEncounters.h"
#include "combat/InputState.h"
#include "combat/Player.h"
#include "combat/Monster.h"
#include "combat/MonsterGroup.h"
#include "combat/ActionQueue.h"
#include "combat/CardQueue.h"
#include "combat/Actions.h"
#include "combat/CardManager.h"
#include "combat/CardSelectInfo.h"


namespace sts {



    enum class Outcome {
        UNDECIDED=0,
        PLAYER_VICTORY,
        PLAYER_LOSS,
    };

    static constexpr const char * battleOutcomeStrings[] {
            "UNDECIDED",
            "PLAYER_VICTORY",
            "PLAYER_LOSS",
    };

    class GameContext;

    extern thread_local std::function<void(const BattleContext &, GameContext &)> g_onBattleExitPersistent;

    // Optional instrumentation at the RAW persistent-transfer boundary.  The
    // callback runs after combat-owned persistent fields have been copied into
    // GameContext, but before GameContext::regainControl()/afterBattle.  It is
    // invoked for victory, loss, and unresolved exits so data producers can
    // quarantine the latter two without pretending they are successful fights.
    // It is null by default and has no gameplay effect.
    extern thread_local std::function<void(const BattleContext &, GameContext &)> g_onBattleExitRaw;

    extern thread_local BattleContext *g_debug_bc;

    // Engine fix flags (the *Fix() switches below and STS_ACTIVE_POWER_FEATURES)
    // are read from the environment once per epoch per thread. BattleContext::init
    // and search::battleContextFromWire call refreshEngineFlags(), so a flag set
    // before a combat starts takes effect in that combat. Code that changes a flag
    // with setenv at any other point (tests) must call refreshEngineFlags() itself.
    struct CachedFixFlag { std::uint32_t epoch = 0; bool value = false; };
    // Unset, empty or 1 = true, 0 = false, anything else throws "NAME must be 0 or 1".
    bool cachedFixFlag(CachedFixFlag &cache, const char *name);
    std::uint32_t engineFlagEpoch();
    void refreshEngineFlags();

    // STS_DEAD_TARGET_DEBUFF_FIX: unset or 1 = a debuff or buff on a dead,
    // half-dead or escaped monster does nothing, as in the game
    // (ApplyPowerAction.update returns first when target.isDeadOrEscaped();
    // combat parity canary 2026-10-18: Uppercut killing its target leaves it
    // without Weak or Vulnerable); 0 = the legacy engine applies it. Other
    // values are fatal. Read only when the target is already dead.
    bool deadTargetDebuffFix();

    // STS_CURL_UP_LETHAL_FIX: unset/1 (default) = Curl Up does not trigger on
    // a lethal hit, as in CurlUpPower.onAttacked (damageAmount <
    // currentHealth; combat parity canary 2 2026-10-18). The dead louse's
    // block and status bits are part of Silver's node identity, so this can
    // change search. 0 = the legacy engine curls anyway. Other values are
    // fatal. Read only on a lethal hit.
    bool curlUpLethalFix();

    // STS_ANGER_COPY_COST_FIX: unset/1 (default) = Anger's discard copy keeps
    // the played card's cost and costForTurn, as Java makeStatEquivalentCopy
    // does (live parity problem 43, seed 111200436: under Confusion the game's
    // copy is 1/1, the legacy native copy 0/0). 0 = the legacy base-cost copy.
    // Other values are fatal. Read only when Anger is played.
    bool angerCopyCostFix();

    // STS_UPGRADE_COST_DELTA_FIX: unset/1 (default) = an in-combat upgrade
    // (Armaments, Apotheosis, ...) changes cost as Java upgradeBaseCost does:
    // Blood for Blood takes cost-1 from its current cost (keeping a
    // damage-taken reduction; live parity problem 59, seed 111200448), and a
    // cost-changing upgrade keeps the card's costForTurn - cost difference.
    // 0 = the legacy engine, which reset both costs to the upgraded base.
    // Other values are fatal. Read on every CardInstance::upgrade.
    bool upgradeCostDeltaFix();

    // STS_TRIP_COST_FIX: unset/1 (default) = Trip costs 0, as Java
    // cards.colorless.Trip does (live parity problem 110). 0 = the legacy engine
    // cost 1. Other values are fatal. Read when a Trip CardInstance is built.
    bool tripCostFix();

    // STS_BYRD_GROUNDED_FLIGHT_FIX: unset/1 (default) = the hit that takes a
    // Byrd's Flight from 1 to 0 removes the power, as Java ReducePowerAction
    // does (live parity problem 42, seed 111200436). The grounded Byrd takes
    // full damage and keeps no Flight at its next start of turn. 0 = the
    // legacy engine kept the status bit at amount 0, so damage stayed halved
    // and applyStartOfTurnPowers reset Flight to 3/4. Other values are fatal.
    bool byrdGroundedFlightFix();

    // STS_DEAD_MONSTER_BLOCK_FIX: unset/1 (default) = queued monster block
    // (Curl Up, Malleable, Guardian mode shift, block moves) does nothing once
    // the monster is dead, as in GainBlockAction.update (skips isDying or
    // isDead; overnight live play 2026-10-19: Fiend Fire curls a louse with an
    // early hit and kills it before the block lands). Dead-monster block is
    // part of Silver's node identity, so this can change search. 0 = the
    // legacy engine adds the block. Other values are fatal. Read only when
    // the monster is dead.
    bool deadMonsterBlockFix();

    // STS_DEAD_ALLY_BLOCK_FIX: unset/1 (default) = a monster move that adds
    // block to an ally directly skips a dead ally, as the queued
    // GainBlockAction/ApplyPowerAction do in Java (live problem 56, seed
    // 111200445: Deca's Square of Protection gave a dead Donu 16 block).
    // Covers Deca's Square of Protection (block and A19 Plated Armor) and
    // Spire Shield's Fortify. Dead-monster block is part of Silver's node
    // identity, so this can change search. 0 = the legacy engine adds them.
    // Other values are fatal. Read only when the ally is dead.
    bool deadAllyBlockFix();

    // STS_DEAD_ALLY_STRENGTH_FIX: unset/1 (default) = Donu's Circle of Power
    // and Spire Spear's Piercer skip a dead ally's Strength, as Java's queued
    // ApplyPowerAction skips a target that isDeadOrEscaped (dying, half-dead
    // or escaping; follow-up to live problem 56).
    // Dead monsters' powers are part of Silver's node identity, so this can
    // change search. 0 = the legacy engine buffs the dead ally. Other values
    // are fatal. Read only when the ally is dead.
    bool deadAllyStrengthFix();

    // STS_ENRAGE_ALL_MONSTERS_FIX: unset/1 (default) = Gremlin Nob's Anger
    // (Enrage) gains Strength on every played Skill whichever monster slot the
    // Nob is in, as Java's per-monster AngerPower.onUseCard (live problem 64b,
    // seed 111200459: Colosseum Nobs puts the Nob in slot 1 behind the
    // Taskmaster, and native only checked slot 0). A dead Nob gains nothing.
    // 0 = the legacy slot-0-only check. Other values are fatal.
    bool enrageAllMonstersFix();

    // STS_MUGGER_DEATH_RNG_FIX: unset/1 (default) = a dying Mugger draws
    // aiRng.random(2) for its death sound (Mugger.die calls playDeathSfx,
    // which uses aiRng; the Looter's uses MathUtils), as in the game (combat
    // parity canary 2 2026-10-18: aiRng counter 9 in Java vs 8 natively after
    // the kill). Later monster rolls in the fight change. 0 = the legacy
    // engine draws nothing. Other values are fatal.
    bool muggerDeathRngFix();

    // STS_SPIRE_SURROUNDED_DEATH_FIX: unset/1 (default) = when Spire Shield
    // or Spire Spear dies with its partner alive, the player loses Surrounded,
    // as SpireShield/SpireSpear.die() queue RemoveSpecificPowerAction
    // (javap, live parity problem 40); this unblocks Smoke Bomb. 0 = the legacy
    // engine keeps Surrounded for the rest of the fight. Other values are fatal.
    bool spireSurroundedDeathFix();

    // STS_MUMMIFIED_HAND_PLAYED_CARD_FIX: unset/1 (default) = Mummified Hand
    // never picks the Power being played, which Java's cardQueue still holds
    // (live parity problem 48). 0 = the legacy pick. Other values are fatal.
    bool mummifiedHandPlayedCardFix();

    // STS_BLOOD_FOR_BLOOD_COPY_COST_FIX: unset/1 (default) = a Blood for Blood
    // generated in combat (Discovery, Infernal Blade, Dead Branch, Nilry's Codex) starts at 4
    // minus the times the player lost HP this combat, as Java's makeCopy does
    // (live parity problem 76). 0 = the legacy base cost. Other values are fatal.
    bool bloodForBloodCopyCostFix();
    // STS_TRUE_GRIT_SINGLE_CARD_RNG_FIX: unset/1 (default) = unupgraded True
    // Grit exhausts a lone hand card without a cardRandomRng draw, as Java's
    // ExhaustAction does (live parity problem 76). 0 = the legacy draw.
    // Other values are fatal.
    bool trueGritSingleCardRngFix();

    // STS_SLIME_SPLIT_RNG_FIX: unset/1 (default) = a large slime's split draws
    // aiRng for the two spawned medium slimes' first moves (SpawnMonsterAction
    // -> init -> rollMove) and, for Spike Slime (L) only, one more roll from
    // its queued RollMoveAction, as in the game; the split trigger of both
    // large slimes and the Slime Boss records the split move twice in the
    // move history (damage() calls setMove and queues a SetMoveAction).
    // Overnight live play 2026-10-19: aiRng counter 6 in Java vs 8 natively
    // after an Acid Slime (L) split. Later monster rolls in the fight change.
    // 0 = the legacy engine draws two extra rolls for either large slime and
    // keeps the previous move in moveHistory[1]. Other values are fatal.
    bool slimeSplitRngFix();

    // STS_SLIME_SPLIT_ROLL_ORDER_FIX: unset/1 (default) = a large slime or the
    // Slime Boss whose split is already pending ignores further hits (Java
    // damage() checks nextMove != SPLIT), and a RollMoveAction queued before the
    // split trigger (thorns or Flame Barrier during the slime's own turn) still
    // draws aiRng but leaves the split as the next move, because Java's
    // SetMoveAction(SPLIT) runs after it (history [SPLIT, rolled]). Live
    // problem 99 (seeds 111200568 and 111200594): native rolled over the split.
    // 0 = the legacy engine. Other values are fatal. Read only at a split
    // trigger or a queued roll of a split-pending slime.
    bool slimeSplitRollOrderFix();

    // STS_DYING_ATTACKER_FIX: unset/1 (default) = a queued monster attack
    // hit does nothing once its attacker is dead or half-dead, as in the game
    // (DamageAction.update cancels a non-THORNS hit when its owner isDying or
    // halfDead; overnight live parity 2026-10-19: Thorns killed a Byrd
    // mid-Peck and the game skipped its last two hits, HP 46 vs native 44).
    // 0 = the legacy engine lands every hit. Other values are fatal. Read
    // only when the attacker is dead or half-dead.
    bool dyingAttackerFix();

    // STS_BLOOD_POTION_HEAL_FIX: unset/1 (default) = a Blood Potion drunk in
    // combat heals 20% of max HP, 40% with Sacred Bark, as in the game and as
    // out of combat (combat parity canary 2 2026-10-18: 15 vs 31 HP at 79 max
    // HP). 0 = the legacy engine, which had the two swapped. Other values are
    // fatal. Read only when a Blood Potion is drunk in combat.
    bool bloodPotionHealFix();

    // STS_HALF_DEAD_POWER_RESET_FIX: unset/1 (default) = a Darkling going
    // half-dead loses its power amounts as well as its status bits, as in
    // Darkling.damage (powers.clear(); overnight parity 2026-10-19: Vulnerable
    // and Weak left on killed Darklings). Without it a debuff on the revived
    // Darkling adds to the stale amount. 0 = the legacy engine. Other values
    // are fatal. Read only when a Darkling goes half-dead.
    bool halfDeadPowerResetFix();

    // STS_STRIKE_COUNT_FIX: unset/1 (default) = Perfected Strike counts Strikes
    // in hand, draw and discard only, as Java PerfectedStrike.countCards: a
    // Havoc/Mayhem-autoplayed Perfected Strike does not count itself, and the
    // live importer's recounted strikeCount skips the exhaust pile and Stasis
    // cards (overnight live play 2026-10-19, problem 10: 53 -> 26 natively vs
    // 29 in the game). 0 = the legacy counts. Other values are fatal. Read only
    // when an autoplayed Perfected Strike is used or the importer recounts.
    bool strikeCountFix();

    // STS_PILE_COST_RESET_FIX: unset/1 (default) = a card that lands in the
    // discard, draw or exhaust pile mid-turn gets costForTurn = cost, as in the
    // game (Soul.update calls clearPowers -> resetAttributes when the card
    // lands; ExhaustCardEffect.update calls resetAttributes; combat parity
    // canary 2 2026-10-19: a played 0-cost Discovery Power Through shows
    // costForTurn 1 in the discard pile). Cards created straight into a pile
    // (ShowCardAndAddToDiscardEffect etc.) keep their cost. 0 = the legacy
    // engine, which kept the turn cost until the end of turn. Other values are
    // fatal. Read only when a moved card's costForTurn differs from its cost.
    bool pileCostResetFix();

    // STS_CORRUPTION_HAND_COST_FIX: unset/1 (default) = a card made in hand
    // (MakeTempCardInHand: Dead Branch etc.; Discovery-style choices) under
    // Corruption runs the game's AbstractPlayer.onCardDrawOrDiscard pass first:
    // every SKILL in hand with costForTurn != 0 gets modifyCostForCombat(-9),
    // so a generated skill ends at cost 0 / costForTurn 0 for the rest of the
    // combat (ShowCardAndAddToHandEffect calls the pass before its own
    // setCostForTurn(-9); live parity problem 83, seed 111200508: Dead Branch
    // skills game 0/0, native base/0). 0 = the legacy engine, which zeroed only
    // costForTurn. Other values are fatal. Read only when a card is made in
    // hand while the player has Corruption.
    bool corruptionHandCostFix();

    // STS_HAND_UPGRADE_ALL_FIX: unset/1 (default) = upgrading every card in
    // hand (Armaments+, Blessing of the Forge) skips cards that cannot be
    // upgraded, as in the game (ArmamentsAction checks c.canUpgrade(); live
    // overnight 2026-10-19 seed 111194457: Ascender's Bane stayed unupgraded).
    // 0 = the legacy engine also upgrades curses and statuses (Burn+ deals 4).
    // Other values are fatal. Read only when such an upgrade resolves.
    bool handUpgradeAllFix();

    // STS_MAYHEM_AFTER_DRAW_FIX: unset/1 (default) = Mayhem plays the top
    // card after the start-of-turn draw, as in the game (MayhemPower queues a
    // wrapper action that queues PlayTopCardAction at the bottom when it
    // runs, behind DrawCardAction; overnight live play 2026-10-19 problem 13:
    // the played card opened a hand selection, Metallicize instead of a
    // pre-draw attack). 0 = the legacy engine, which played the pre-draw top
    // card. Other values are fatal. Read only at a Mayhem turn start.
    bool mayhemAfterDrawFix();

    // STS_UNPLAYABLE_AUTOPLAY_FIX: unset/1 (default) = an autoplayed card
    // (Havoc, Mayhem) that fails canUse (Burn, Clash with a non-attack in
    // hand, Velvet Choker) is still routed like a played card, as in the game
    // (GameActionManager.getNextAction sets dontTriggerOnUseCard and queues
    // UseCardAction at the bottom: no use/onUseCard/onAfterUseCard hooks, but
    // Havoc's exhaust, Strange Spoon and the discard move still apply;
    // overnight live play 2026-10-20 problem 41). 0 = the legacy engine, where
    // the card vanished. Other values are fatal. Read only when an autoplayed
    // card cannot be played.
    bool unplayableAutoplayFix();

    // STS_AUTOPLAY_QUEUE_ORDER_FIX: unset/1 (default) = a card autoplayed from
    // the draw pile (Havoc, Mayhem, Distilled Chaos) joins the BACK of the card
    // queue, as in the game (PlayTopCardAction queues NewQueueCardAction(card,
    // target, false, true), whose addCardQueueItem(item, false) appends), so a
    // multi-card Distilled Chaos plays the top card first (overnight live play
    // 2026-10-20 problem 44). 0 = the legacy engine, which pushed it to the
    // front (reverse order). Other values are fatal. Read at each autoplay.
    bool autoplayQueueOrderFix();
    // STS_LAGAVULIN_WAKE_METALLICIZE_FIX: unset/1 (default) = a Lagavulin woken
    // by HP damage loses 8 Metallicize, as in the game (Lagavulin.damage queues
    // ChangeStateAction("OPEN"); changeState queues ReducePowerAction(
    // Metallicize, 8)), the same as the natural wake (overnight live play
    // 2026-10-20 problem 58: 12 -> 4). 0 = the legacy engine, which removed
    // Metallicize. Other values are fatal. Read only at a damage wake.
    bool lagavulinWakeMetallicizeFix();
    // STS_EXHAUST_EMPTY_HAND_FIX: unset/1 (default) = ExhaustMany (Purity,
    // Elixir) does nothing on an empty hand, as Java ExhaustAction.update
    // ends at once when the hand is empty (overnight live play 2026-10-20
    // problem 64(d): Purity as the last card left its selection open with
    // Letter Opener's damage queued behind it). 0 = the legacy engine, which
    // opened an empty CARD_SELECT. Other values are fatal.
    bool exhaustEmptyHandFix();

    // STS_PURGE_COPY_CAN_USE_FIX: unset/1 (default) = a purge-on-use replay copy
    // (Duplication, Double Tap, Burst, Echo Form, Necronomicon) must pass canUse
    // like any queued card, as in the game (getNextAction's canPlayCard is
    // canUse || dontTriggerOnUseCard, no purge exception), so Velvet Choker at
    // six cards stops it and it only poofs (overnight live play 2026-10-20
    // problem 55). 0 = the legacy engine, where purge copies skipped canUse.
    // Other values are fatal. Read for each purge copy.
    bool purgeCopyCanUseFix();

    // STS_MAGNETISM_FIX: unset/1 (default) = Magnetism adds its random
    // colorless card(s) to the hand at the start of each turn, as in the game
    // (MagnetismPower.atStartOfTurn rolls returnTrulyRandomColorlessCardInCombat
    // on cardRandomRng and queues MakeTempCardInHandAction; overnight live play
    // 2026-10-20 problem 39). 0 = the legacy engine, where Magnetism did
    // nothing. Other values are fatal. Read only at a Magnetism turn start.
    bool magnetismFix();

    // STS_SLIME_SPLIT_MONSTER_COUNT_FIX: unset/1 (default) = a large slime
    // split grows monsterCount only to cover the two child slots (max with
    // placeIdx+2), so a Spike Slime (L) splitting in slot 0 of the Slime Boss
    // layout (0,1,2) leaves monsterCount 3, as the live inspector reports
    // (overnight live play 2026-10-20 problem 62, seed 111200456 s217). Java
    // itself keeps dead parents in its list (raw size 5 there); the alive
    // monsters and their order are the same either way, so this only removes
    // an always-dead empty slot 3. 0 = the legacy engine (+1 per split, capped
    // at 4). Other values are fatal. Read only at a large slime split.
    bool slimeSplitMonsterCountFix();

    // STS_CURIOSITY_FIX: unset/1 (default) = each Power play queues Strength
    // equal to Curiosity at the bottom for every monster holding it, as in the
    // game (CuriosityPower.onUseCard -> ApplyPowerAction; overnight live play
    // 2026-10-20 problems 45 and 65: the Awakened One's Strength stayed 2 lower
    // per Power natively). 0 = the legacy engine, where Curiosity did nothing.
    // Other values are fatal. Read only when a Power card is used.
    bool curiosityFix();

    // STS_DARK_SHACKLES_FIX: unset/1 (default) = Dark Shackles applies
    // Strength -9 (-15) and, when the target had no Artifact, Shackled 9 (15)
    // that restores it at the monster's end of turn, as in the game (live
    // problem 97, seed 111200587: the engine gave the monster +9 Strength and
    // Shackled only when it had Artifact). 0 = the legacy engine. Other values
    // are fatal. Read only when Dark Shackles is used.
    bool darkShacklesFix();

    // STS_IMPATIENCE_FIX: unset/1 (default) = Impatience draws only when the
    // hand holds no Attack, as in the game (live problem 98, seed 111200587:
    // the engine always drew because the Attack check never set its flag).
    // 0 = the legacy engine. Other values are fatal. Read only when Impatience
    // is used with an Attack in hand.
    bool impatienceFix();

    // STS_CORRUPTION_IMMEDIATE_COST_FIX: unset/1 (default) = playing Corruption
    // sets every Skill's cost to 0 at once, as Java's ApplyPowerAction
    // constructor does, so Mummified Hand (rolled in the UseCardAction
    // constructor) never picks a Skill (live problem 100, seed 111200621).
    // 0 = the legacy engine, which changed the costs when the queued power
    // resolved. Other values are fatal. Read only when Corruption is played.
    bool corruptionImmediateCostFix();

    // STS_NECRONOMICON_AUTOPLAY_FIX: unset/1 (default) = Necronomicon replays
    // an Attack with costForTurn >= 2 unless the card is freeToPlayOnce (or an
    // X-cost Attack with energyOnUse >= 2), as Java Necronomicon.onUseCard
    // does, including Havoc/Mayhem/Distilled Chaos autoplays and purge copies
    // (live problem 101, seed 111200627: Havoc's Immolate was replayed in the
    // game, not natively). 0 = the legacy engine, which skipped every
    // free-to-play queue item and purge copy. Other values are fatal.
    bool necronomiconAutoplayFix();

    struct BattleContext {

        // begin for debugging purposes
        inline static int sum = 0; // for preventing optimization in benchmarks
        bool haveUsedDiscoveryAction = false; // for tracking undefined behavior resulting from using the action
        bool undefinedBehaviorEvoked = false; // some cards cause inconsistent outcomes in games
        std::uint64_t seed = 0;
        int floorNum = 0;
        MonsterEncounter encounter = MonsterEncounter::INVALID;
        int loopCount = 0;
        int energyWasted = 0;
        int cardsDrawn = 0;
        // end for debugging purposes

        Random aiRng;
        Random cardRandomRng;
        Random miscRng;
        Random monsterHpRng;
        Random potionRng;
        Random shuffleRng;

        int ascension = 0;
        Outcome outcome = Outcome::UNDECIDED;
        bool smokeBombUsed = false;
        InputState inputState = InputState::EXECUTING_ACTIONS;
        CardSelectInfo cardSelectInfo;

        int monsterTurnIdx = 6;

        // Search only (Runic Dome): monster move rolls are deferred until the
        // move is used or queried (Monster::pendingMoveRolls), so a search
        // cannot see intents the player cannot. Always false in real play.
        bool intentsHidden = false;

        bool isBattleOver() const { return outcome != Outcome::UNDECIDED; }
        bool endTurnQueued = false;
        bool turnHasEnded = false;
        bool skipMonsterTurn = false;

        ActionQueue<128> actionQueue;
        CardQueue cardQueue;

        int potionCount = 0;
        int potionCapacity = 3;
        std::array<Potion, 5> potions {Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT};

        int turn = 0;
        Player player;
        MonsterGroup monsters;
        CardManager cards;

        CardQueueItem curCardQueueItem;

        std::bitset<32> miscBits; // 0 stolen gold check,

        BattleContext() = default;
        BattleContext(const BattleContext &rhs) = default;

        // Exact equality of every field except the static benchmark `sum`.
        bool operator==(const BattleContext &rhs) const;

        // Equality for search transposition (the Silver fork's rule set):
        // operator== without the RNG streams and the debug/statistics fields
        // (loopCount, energyWasted, cardsDrawn, haveUsedDiscoveryAction,
        // undefinedBehaviorEvoked); curCardQueueItem is ignored when both
        // states are quiet player decisions; the hand is compared as a
        // multiset, and so are the discard and exhaust piles once the draw
        // pile is in information-set mode.
        [[nodiscard]] bool equalForSearch(const BattleContext &rhs) const;

// ****************************************

        void init(const GameContext &gc);
        void init(const GameContext &gc, MonsterEncounter encounterToInit);

        void initRelics(const GameContext &gc);

        void exitBattle(GameContext &g) const;
        void updateRelicsOnExit(GameContext &g) const;
        void updateCardsOnExit(Deck &d) const; // for cards like ritual dagger, and eventually lesson learned results

        [[nodiscard]] bool smokeBombEscapeBlocked() const {
            return isBossEncounter(encounter) || player.hasStatus<PS::SURROUNDED>();
        }

// ****************************************

        void setRequiresStolenGoldCheck(bool value);
        [[nodiscard]] bool requiresStolenGoldCheck() const;
        [[nodiscard]] int getMonsterTurnNumber() const;  // returns 1 for first turn, 2 for second, etc.

// ****************************************

        void executeActions();

        void playCardQueueItem(CardQueueItem);
        void useCard();
        void useNoTriggerCard();

        void useAttackCard();
        void useSkillCard();
        void usePowerCard();

        void onUseAttackCard();
        void onUseSkillCard();
        void onUsePowerCard();

        void onUseStatusOrCurseCard();
        void onAfterUseCard();

        void setState(InputState state);
        void addToTop(const Action &a);
        void addToBot(const Action &a);

        void addToTopCard(CardQueueItem item);
        void addToBotCard(CardQueueItem item);

        void checkCombat();
        void clearPostCombatActions();
        void cleanCardQueue();

        [[nodiscard]] bool isCardPlayAllowed() const;

        // **********************

        void endTurn(); // called when player clicks the end turn button
        void callEndOfTurnActions(); // GameActionManager.callEndTurnActions(), called when the end turn cardQueue item is reached.
        void onTurnEnding(); // AbstractRoom endTurn(), called when the turn actually ends.

        void callEndTurnEarlySequence(); // time eater

        void applyEndOfRoundPowers(); // game : MonsterGroup applyEndOfTurnPowers
        void afterMonsterTurns();

        void obtainPotion(Potion p);
        void discardPotion(int idx);
        void drinkPotion(int idx, int target=0);

        void drawCards(int count);
        void discardAtEndOfTurn();
        void discardAtEndOfTurnHelper();

        void playTopCardInDrawPile(int monsterTargetIdx, bool exhausts);

        void moveToHandHelper(CardInstance c);
        void corruptionHandCostPass(); // AbstractPlayer.onCardDrawOrDiscard's Corruption loop
        void exhaustSpecificCardInHand(int idx, std::int16_t uniqueId);
        void restoreRetainedCards(int count);
        void exhaustTopCardInHand();

        // this is
        void triggerOnEndOfTurnForPlayingCards();
        void triggerOnOtherCardPlayed(const CardInstance &usedCard);

        template <MonsterStatus s>
        void debuffEnemy(int idx, int amount, bool isSourceMonster=true);

        [[nodiscard]] int calculateCardDamage(const CardInstance &card, int targetIdx, int baseDamage) const;
        [[nodiscard]] int calculateCardBlock(int baseBlock) const;

        void queuePurgeCard(const CardInstance &c, int target);
        void addPurgeCardToCardQueue(const CardQueueItem &item); // not really the front but hey
        void noOpRollMove(); // called by monsters to manipulate the aiRng counter when their rollMove function doesn't do anything

        void onManualDiscard(const CardInstance &c);
        void onShuffle();
        void triggerAndMoveToExhaustPile(CardInstance c);
        void unplayableAutoplayUseCard(CardInstance c, bool exhaust);
        void mummifiedHandOnUsePower();

        // card select screens
        void openDiscoveryScreen(std::array<CardId, 3> discoveryCards, int copyCount);
        void openSimpleCardSelectScreen(CardSelectTask task, int count);

        // single card select helpers
        void chooseArmamentsCard(int handIdx);
        void chooseCodexCard(CardId id);
        void chooseDiscardToHandCard(int discardIdx, bool forZeroCost);
        void chooseDiscoveryCard(CardId id);
        // A card Java creates with makeCopy() in combat (Discovery choices,
        // Infernal Blade, Dead Branch, Nilry's Codex): BloodForBlood.makeCopy() applies
        // updateCost(-damagedThisCombat) (STS_BLOOD_FOR_BLOOD_COPY_COST_FIX).
        CardInstance generatedCombatCard(CardId id) const;
        void chooseDualWieldCard(int handIdx);
        void chooseExhaustOneCard(int handIdx);
        void chooseExhumeCard(int exhaustIdx);
        void chooseForethoughtCard(int handIdx);
        void chooseForethoughtCards(const fixed_list<int,10> &idxs);
        void chooseHeadbuttCard(int discardIdx);
        void chooseRecycleCard(int handIdx);
        void chooseWarcryCard(int handIdx);

        // multi card helpers
        void chooseDrawToHandCards(const int *idxs, int cardCount);
        void chooseExhaustCards(const fixed_list<int,10> &idxs);
        void chooseGambleCards(const fixed_list<int,10> &idxs);

    };

    std::ostream& operator<<(std::ostream &os, const BattleContext &bc);

    template <PlayerStatus s>
    Action Actions::BuffPlayer(int amount) {
        return makeAction(ActData_BuffPlayer{s, amount});
    }

    template <PlayerStatus s>
    Action Actions::DebuffPlayer(int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffPlayer{s, amount, isSourceMonster});
    }

    template<PlayerStatus s>
    Action Actions::DecrementStatus(int amount) {
        return makeAction(ActData_DecrementStatus{s, amount});
    }

    template <PlayerStatus s>
    Action Actions::RemoveStatus() {
        return makeAction(ActData_RemoveStatus{s});
    }

    template<MonsterStatus s>
    Action Actions::BuffEnemy(int idx, int amount) {
        return makeAction(ActData_BuffEnemy{s, idx, amount});
    }

    template <MonsterStatus s>
    Action Actions::DebuffEnemy(int idx, int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffEnemy{s, idx, amount, isSourceMonster});
    }

    template <MonsterStatus s>
    Action Actions::DebuffAllEnemy(int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffAllEnemy{s, amount, isSourceMonster});
    }

    template <MonsterStatus s>
    void BattleContext::debuffEnemy(int idx, int amount, bool isSourceMonster) {
        // todo poison and snake skull
        Monster &e = monsters.arr[idx];
        if (e.isDeadOrEscaped() && deadTargetDebuffFix()) {
            return;
        }

        if (e.hasStatus<MS::ARTIFACT>()) {
            e.decrementStatus<MS::ARTIFACT>();
            return;
        }

        e.addDebuff<s>(amount, isSourceMonster);
        if (player.hasStatus<PS::SADISTIC>()) {
            addToBot( Actions::DamageEnemy(idx, player.getStatus<PS::SADISTIC>()) );
        }

        if (s == MS::VULNERABLE && player.hasRelic<RelicId::CHAMPION_BELT>()) {
            addToBot(Actions::DebuffEnemy<MS::WEAK>(idx, 1, false) );
        }
    }


}

#endif //STS_LIGHTSPEED_BATTLECONTEXT_H
