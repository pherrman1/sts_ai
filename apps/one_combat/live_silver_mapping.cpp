#include "live_silver_mapping.h"

#include <initializer_list>
#include <map>

namespace one_combat::advisor::live_silver {
namespace {

template <typename T>
std::optional<T> find(const std::map<std::string, T> &table, const std::string &key) {
    const auto it = table.find(key);
    return it == table.end() ? std::nullopt : std::optional<T>(it->second);
}

const std::map<std::string, sts::MonsterId> kMonsters = {
    {"AcidSlime_L", sts::MonsterId::ACID_SLIME_L}, {"AcidSlime_M", sts::MonsterId::ACID_SLIME_M},
    {"AcidSlime_S", sts::MonsterId::ACID_SLIME_S}, {"AwakenedOne", sts::MonsterId::AWAKENED_ONE},
    {"BlueSlaver", sts::MonsterId::BLUE_SLAVER}, {"SlaverBlue", sts::MonsterId::BLUE_SLAVER},
    {"BookOfStabbing", sts::MonsterId::BOOK_OF_STABBING},
    {"BronzeAutomaton", sts::MonsterId::BRONZE_AUTOMATON}, {"BronzeOrb", sts::MonsterId::BRONZE_ORB},
    {"Byrd", sts::MonsterId::BYRD}, {"Centurion", sts::MonsterId::CENTURION},
    {"Healer", sts::MonsterId::MYSTIC},
    {"Chosen", sts::MonsterId::CHOSEN}, {"CorruptHeart", sts::MonsterId::CORRUPT_HEART},
    {"Cultist", sts::MonsterId::CULTIST}, {"Dagger", sts::MonsterId::DAGGER},
    {"SnakeDagger", sts::MonsterId::DAGGER},
    {"Darkling", sts::MonsterId::DARKLING}, {"Deca", sts::MonsterId::DECA},
    {"Donu", sts::MonsterId::DONU}, {"Exploder", sts::MonsterId::EXPLODER},
    {"FungiBeast", sts::MonsterId::FUNGI_BEAST}, {"GiantHead", sts::MonsterId::GIANT_HEAD},
    {"FuzzyLouseNormal", sts::MonsterId::GREEN_LOUSE}, {"FuzzyLouseDefensive", sts::MonsterId::RED_LOUSE},
    {"GremlinLeader", sts::MonsterId::GREMLIN_LEADER}, {"GremlinNob", sts::MonsterId::GREMLIN_NOB},
    {"Gremlin Wizard", sts::MonsterId::GREMLIN_WIZARD}, {"GremlinWizard", sts::MonsterId::GREMLIN_WIZARD},
    {"Hexaghost", sts::MonsterId::HEXAGHOST}, {"JawWorm", sts::MonsterId::JAW_WORM},
    {"Lagavulin", sts::MonsterId::LAGAVULIN}, {"Looter", sts::MonsterId::LOOTER},
    {"MadGremlin", sts::MonsterId::MAD_GREMLIN}, {"Mugger", sts::MonsterId::MUGGER},
    {"Mystic", sts::MonsterId::MYSTIC}, {"Nemesis", sts::MonsterId::NEMESIS},
    {"Orb Walker", sts::MonsterId::ORB_WALKER}, {"OrbWalker", sts::MonsterId::ORB_WALKER},
    {"Pointy", sts::MonsterId::POINTY}, {"BanditPointy", sts::MonsterId::POINTY},
    {"BanditLeader", sts::MonsterId::MUGGER}, {"BanditBear", sts::MonsterId::BEAR},
    {"RedSlaver", sts::MonsterId::RED_SLAVER}, {"SlaverRed", sts::MonsterId::RED_SLAVER},
    {"Reptomancer", sts::MonsterId::REPTOMANCER}, {"Repulsor", sts::MonsterId::REPULSOR},
    {"Romeo", sts::MonsterId::ROMEO}, {"Sentry", sts::MonsterId::SENTRY},
    {"ShelledParasite", sts::MonsterId::SHELLED_PARASITE}, {"Shield Gremlin", sts::MonsterId::SHIELD_GREMLIN},
    {"ShieldGremlin", sts::MonsterId::SHIELD_GREMLIN}, {"SlimeBoss", sts::MonsterId::SLIME_BOSS},
    {"SnakePlant", sts::MonsterId::SNAKE_PLANT}, {"SneakyGremlin", sts::MonsterId::SNEAKY_GREMLIN},
    {"Snecko", sts::MonsterId::SNECKO}, {"SphericGuardian", sts::MonsterId::SPHERIC_GUARDIAN},
    {"Spiker", sts::MonsterId::SPIKER}, {"SpikeSlime_L", sts::MonsterId::SPIKE_SLIME_L},
    {"SpikeSlime_M", sts::MonsterId::SPIKE_SLIME_M}, {"SpikeSlime_S", sts::MonsterId::SPIKE_SLIME_S},
    {"Serpent", sts::MonsterId::SPIRE_GROWTH}, {"SpireGrowth", sts::MonsterId::SPIRE_GROWTH},
    {"SpireShield", sts::MonsterId::SPIRE_SHIELD}, {"SpireSpear", sts::MonsterId::SPIRE_SPEAR},
    {"Taskmaster", sts::MonsterId::TASKMASTER}, {"Champ", sts::MonsterId::THE_CHAMP},
    {"TheCollector", sts::MonsterId::THE_COLLECTOR}, {"TheGuardian", sts::MonsterId::THE_GUARDIAN},
    {"Maw", sts::MonsterId::THE_MAW}, {"TimeEater", sts::MonsterId::TIME_EATER},
    {"TorchHead", sts::MonsterId::TORCH_HEAD}, {"Transient", sts::MonsterId::TRANSIENT},
    {"WrithingMass", sts::MonsterId::WRITHING_MASS},
    // Runtime spelling used by old Java versions.
    {"Gremlin Nob", sts::MonsterId::GREMLIN_NOB},
};

const std::map<std::string, sts::MonsterEncounter> kEncounters = {
    {"CULTIST", sts::MonsterEncounter::CULTIST}, {"JAW_WORM", sts::MonsterEncounter::JAW_WORM},
    {"TWO_LOUSE", sts::MonsterEncounter::TWO_LOUSE}, {"SMALL_SLIMES", sts::MonsterEncounter::SMALL_SLIMES},
    {"BLUE_SLAVER", sts::MonsterEncounter::BLUE_SLAVER}, {"GREMLIN_GANG", sts::MonsterEncounter::GREMLIN_GANG},
    {"LOOTER", sts::MonsterEncounter::LOOTER}, {"LARGE_SLIME", sts::MonsterEncounter::LARGE_SLIME},
    {"LOTS_OF_SLIMES", sts::MonsterEncounter::LOTS_OF_SLIMES}, {"EXORDIUM_THUGS", sts::MonsterEncounter::EXORDIUM_THUGS},
    {"EXORDIUM_WILDLIFE", sts::MonsterEncounter::EXORDIUM_WILDLIFE}, {"RED_SLAVER", sts::MonsterEncounter::RED_SLAVER},
    {"THREE_LOUSE", sts::MonsterEncounter::THREE_LOUSE}, {"TWO_FUNGI_BEASTS", sts::MonsterEncounter::TWO_FUNGI_BEASTS},
    {"GREMLIN_NOB", sts::MonsterEncounter::GREMLIN_NOB}, {"LAGAVULIN", sts::MonsterEncounter::LAGAVULIN},
    {"THREE_SENTRIES", sts::MonsterEncounter::THREE_SENTRIES}, {"SLIME_BOSS", sts::MonsterEncounter::SLIME_BOSS},
    {"THE_GUARDIAN", sts::MonsterEncounter::THE_GUARDIAN}, {"HEXAGHOST", sts::MonsterEncounter::HEXAGHOST},
    {"SPHERIC_GUARDIAN", sts::MonsterEncounter::SPHERIC_GUARDIAN}, {"CHOSEN", sts::MonsterEncounter::CHOSEN},
    {"SHELL_PARASITE", sts::MonsterEncounter::SHELL_PARASITE}, {"THREE_BYRDS", sts::MonsterEncounter::THREE_BYRDS},
    {"TWO_THIEVES", sts::MonsterEncounter::TWO_THIEVES}, {"CHOSEN_AND_BYRDS", sts::MonsterEncounter::CHOSEN_AND_BYRDS},
    {"SENTRY_AND_SPHERE", sts::MonsterEncounter::SENTRY_AND_SPHERE}, {"SNAKE_PLANT", sts::MonsterEncounter::SNAKE_PLANT},
    {"SNECKO", sts::MonsterEncounter::SNECKO}, {"CENTURION_AND_HEALER", sts::MonsterEncounter::CENTURION_AND_HEALER},
    {"CULTIST_AND_CHOSEN", sts::MonsterEncounter::CULTIST_AND_CHOSEN}, {"THREE_CULTIST", sts::MonsterEncounter::THREE_CULTIST},
    {"SHELLED_PARASITE_AND_FUNGI", sts::MonsterEncounter::SHELLED_PARASITE_AND_FUNGI}, {"GREMLIN_LEADER", sts::MonsterEncounter::GREMLIN_LEADER},
    {"SLAVERS", sts::MonsterEncounter::SLAVERS}, {"BOOK_OF_STABBING", sts::MonsterEncounter::BOOK_OF_STABBING},
    {"AUTOMATON", sts::MonsterEncounter::AUTOMATON}, {"COLLECTOR", sts::MonsterEncounter::COLLECTOR},
    {"CHAMP", sts::MonsterEncounter::CHAMP}, {"THREE_DARKLINGS", sts::MonsterEncounter::THREE_DARKLINGS},
    {"ORB_WALKER", sts::MonsterEncounter::ORB_WALKER}, {"THREE_SHAPES", sts::MonsterEncounter::THREE_SHAPES},
    {"SPIRE_GROWTH", sts::MonsterEncounter::SPIRE_GROWTH}, {"TRANSIENT", sts::MonsterEncounter::TRANSIENT},
    {"FOUR_SHAPES", sts::MonsterEncounter::FOUR_SHAPES}, {"MAW", sts::MonsterEncounter::MAW},
    {"SPHERE_AND_TWO_SHAPES", sts::MonsterEncounter::SPHERE_AND_TWO_SHAPES}, {"JAW_WORM_HORDE", sts::MonsterEncounter::JAW_WORM_HORDE},
    {"WRITHING_MASS", sts::MonsterEncounter::WRITHING_MASS}, {"GIANT_HEAD", sts::MonsterEncounter::GIANT_HEAD},
    {"NEMESIS", sts::MonsterEncounter::NEMESIS}, {"REPTOMANCER", sts::MonsterEncounter::REPTOMANCER},
    {"AWAKENED_ONE", sts::MonsterEncounter::AWAKENED_ONE}, {"TIME_EATER", sts::MonsterEncounter::TIME_EATER},
    {"DONU_AND_DECA", sts::MonsterEncounter::DONU_AND_DECA}, {"SHIELD_AND_SPEAR", sts::MonsterEncounter::SHIELD_AND_SPEAR},
    {"THE_HEART", sts::MonsterEncounter::THE_HEART}, {"LAGAVULIN_EVENT", sts::MonsterEncounter::LAGAVULIN_EVENT},
    {"COLOSSEUM_EVENT_SLAVERS", sts::MonsterEncounter::COLOSSEUM_EVENT_SLAVERS}, {"COLOSSEUM_EVENT_NOBS", sts::MonsterEncounter::COLOSSEUM_EVENT_NOBS},
    {"MASKED_BANDITS_EVENT", sts::MonsterEncounter::MASKED_BANDITS_EVENT}, {"MUSHROOMS_EVENT", sts::MonsterEncounter::MUSHROOMS_EVENT},
    {"MYSTERIOUS_SPHERE_EVENT", sts::MonsterEncounter::MYSTERIOUS_SPHERE_EVENT},
};

const std::map<std::string, PlayerStatus> kPlayerStatuses = {
    {"ArtifactPower", PlayerStatus::ARTIFACT}, {"Artifact", PlayerStatus::ARTIFACT},
    {"Dexterity", PlayerStatus::DEXTERITY}, {"DexterityPower", PlayerStatus::DEXTERITY},
    {"Strength", PlayerStatus::STRENGTH}, {"StrengthPower", PlayerStatus::STRENGTH},
    {"Focus", PlayerStatus::FOCUS}, {"FocusPower", PlayerStatus::FOCUS},
    {"Weak", PlayerStatus::WEAK}, {"WeakPower", PlayerStatus::WEAK},
    {"Frail", PlayerStatus::FRAIL}, {"FrailPower", PlayerStatus::FRAIL},
    {"Vulnerable", PlayerStatus::VULNERABLE}, {"VulnerablePower", PlayerStatus::VULNERABLE},
    {"No Draw", PlayerStatus::NO_DRAW},
    {"NoDrawPower", PlayerStatus::NO_DRAW}, {"No Block", PlayerStatus::NO_BLOCK},
    {"NoBlockPower", PlayerStatus::NO_BLOCK}, {"Entangled", PlayerStatus::ENTANGLED}, {"EntanglePower", PlayerStatus::ENTANGLED},
    {"Intangible", PlayerStatus::INTANGIBLE}, {"IntangiblePlayerPower", PlayerStatus::INTANGIBLE}, {"Barricade", PlayerStatus::BARRICADE},
    {"Corruption", PlayerStatus::CORRUPTION}, {"Confused", PlayerStatus::CONFUSED},
    {"DoubleTapPower", PlayerStatus::DOUBLE_TAP}, {"Metallicize", PlayerStatus::METALLICIZE}, {"MetallicizePower", PlayerStatus::METALLICIZE},
    {"Plated Armor", PlayerStatus::PLATED_ARMOR}, {"PlatedArmorPower", PlayerStatus::PLATED_ARMOR}, {"Feel No Pain", PlayerStatus::FEEL_NO_PAIN}, {"FeelNoPain", PlayerStatus::FEEL_NO_PAIN},
    {"Dark Embrace", PlayerStatus::DARK_EMBRACE}, {"DarkEmbrace", PlayerStatus::DARK_EMBRACE}, {"Demon Form", PlayerStatus::DEMON_FORM}, {"DemonForm", PlayerStatus::DEMON_FORM},
    {"Combust", PlayerStatus::COMBUST}, {"Evolve", PlayerStatus::EVOLVE},
    {"Fire Breathing", PlayerStatus::FIRE_BREATHING}, {"FireBreathing", PlayerStatus::FIRE_BREATHING}, {"Juggernaut", PlayerStatus::JUGGERNAUT},
    {"Rage", PlayerStatus::RAGE}, {"Rupture", PlayerStatus::RUPTURE}, {"Thorns", PlayerStatus::THORNS},
    {"Vigor", PlayerStatus::VIGOR}, {"Buffer", PlayerStatus::BUFFER},
    {"RitualPower", PlayerStatus::RITUAL}, {"Wraith Form v2", PlayerStatus::WRAITH_FORM}, {"WraithForm", PlayerStatus::WRAITH_FORM}, {"Panache", PlayerStatus::PANACHE},
    // Vanilla power IDs with their Java Power suffixes.
    {"DoubleDamagePower", PlayerStatus::DOUBLE_DAMAGE}, {"DrawReductionPower", PlayerStatus::DRAW_REDUCTION},
    {"BiasPower", PlayerStatus::BIAS}, {"ConfusionPower", PlayerStatus::CONFUSED},
    {"ConstrictedPower", PlayerStatus::CONSTRICTED}, {"FastingPower", PlayerStatus::FASTING},
    {"HexPower", PlayerStatus::HEX}, {"LoseDexterityPower", PlayerStatus::LOSE_DEXTERITY},
    {"LoseStrengthPower", PlayerStatus::LOSE_STRENGTH}, {"BarricadePower", PlayerStatus::BARRICADE},
    {"BlasphemyPower", PlayerStatus::BLASPHEMER}, {"ElectrodynamicsPower", PlayerStatus::ELECTRO},
    {"SurroundedPower", PlayerStatus::SURROUNDED}, {"MasterRealityPower", PlayerStatus::MASTER_REALITY},
    {"WrathNextTurnPower", PlayerStatus::WRATH_NEXT_TURN}, {"AmplifyPower", PlayerStatus::AMPLIFY},
    {"BlurPower", PlayerStatus::BLUR}, {"BufferPower", PlayerStatus::BUFFER},
    {"CollectPower", PlayerStatus::COLLECT}, {"DuplicationPower", PlayerStatus::DUPLICATION},
    {"EchoFormPower", PlayerStatus::ECHO_FORM}, {"FreeAttackPowerPower", PlayerStatus::FREE_ATTACK_POWER},
    {"ReboundPower", PlayerStatus::REBOUND}, {"MantraPower", PlayerStatus::MANTRA},
    {"AccuracyPower", PlayerStatus::ACCURACY}, {"AfterImagePower", PlayerStatus::AFTER_IMAGE},
    {"BattleHymnPower", PlayerStatus::BATTLE_HYMN}, {"BrutalityPower", PlayerStatus::BRUTALITY},
    {"BurstPower", PlayerStatus::BURST}, {"CreativeAIPower", PlayerStatus::CREATIVE_AI},
    {"DevaFormPower", PlayerStatus::DEVA}, {"DevotionPower", PlayerStatus::DEVOTION},
    {"DrawCardNextTurnPower", PlayerStatus::DRAW_CARD_NEXT_TURN}, {"EnergizedPower", PlayerStatus::ENERGIZED},
    {"EnvenomPower", PlayerStatus::ENVENOM}, {"EstablishmentPower", PlayerStatus::ESTABLISHMENT},
    {"EvolvePower", PlayerStatus::EVOLVE}, {"FlameBarrierPower", PlayerStatus::FLAME_BARRIER},
    {"ForesightPower", PlayerStatus::FORESIGHT}, {"HelloWorldPower", PlayerStatus::HELLO_WORLD},
    {"InfiniteBladesPower", PlayerStatus::INFINITE_BLADES}, {"LikeWaterPower", PlayerStatus::LIKE_WATER},
    {"LoopPower", PlayerStatus::LOOP}, {"MagnetismPower", PlayerStatus::MAGNETISM},
    {"MayhemPower", PlayerStatus::MAYHEM}, {"NextTurnBlockPower", PlayerStatus::NEXT_TURN_BLOCK},
    {"NoxiousFumesPower", PlayerStatus::NOXIOUS_FUMES}, {"OmegaPower", PlayerStatus::OMEGA},
    {"PhantasmalKillerPower", PlayerStatus::PHANTASMAL}, {"SadisticNaturePower", PlayerStatus::SADISTIC},
    {"StaticDischargePower", PlayerStatus::STATIC_DISCHARGE}, {"ThousandCutsPower", PlayerStatus::THOUSAND_CUTS},
    {"ToolsOfTheTradePower", PlayerStatus::TOOLS_OF_THE_TRADE}, {"EquilibriumPower", PlayerStatus::EQUILIBRIUM},
};

const std::map<std::string, sts::MonsterStatus> kMonsterStatuses = {
    {"Artifact", sts::MonsterStatus::ARTIFACT}, {"ArtifactPower", sts::MonsterStatus::ARTIFACT}, {"Strength", sts::MonsterStatus::STRENGTH}, {"StrengthPower", sts::MonsterStatus::STRENGTH},
    {"Vulnerable", sts::MonsterStatus::VULNERABLE}, {"VulnerablePower", sts::MonsterStatus::VULNERABLE}, {"Weak", sts::MonsterStatus::WEAK}, {"WeakPower", sts::MonsterStatus::WEAK},
    {"Poison", sts::MonsterStatus::POISON}, {"PoisonPower", sts::MonsterStatus::POISON}, {"Metallicize", sts::MonsterStatus::METALLICIZE}, {"MetallicizePower", sts::MonsterStatus::METALLICIZE},
    {"Plated Armor", sts::MonsterStatus::PLATED_ARMOR}, {"PlatedArmorPower", sts::MonsterStatus::PLATED_ARMOR}, {"Regeneration", sts::MonsterStatus::REGEN},
    {"Regen", sts::MonsterStatus::REGEN}, {"Angry", sts::MonsterStatus::ANGRY},
    {"BeatOfDeath", sts::MonsterStatus::BEAT_OF_DEATH}, {"BeatOfDeathPower", sts::MonsterStatus::BEAT_OF_DEATH}, {"Curiosity", sts::MonsterStatus::CURIOSITY},
    {"Curl Up", sts::MonsterStatus::CURL_UP}, {"Enrage", sts::MonsterStatus::ENRAGE},
    {"Anger", sts::MonsterStatus::ENRAGE},
    {"Fading", sts::MonsterStatus::FADING}, {"Flight", sts::MonsterStatus::FLIGHT},
    {"GenericStrengthUp", sts::MonsterStatus::GENERIC_STRENGTH_UP}, {"Intangible", sts::MonsterStatus::INTANGIBLE},
    {"Malleable", sts::MonsterStatus::MALLEABLE}, {"Mode Shift", sts::MonsterStatus::MODE_SHIFT},
    {"Ritual", sts::MonsterStatus::RITUAL}, {"Slow", sts::MonsterStatus::SLOW},
    {"Spore Cloud", sts::MonsterStatus::SPORE_CLOUD}, {"Thievery", sts::MonsterStatus::THIEVERY},
    {"Thorns", sts::MonsterStatus::THORNS}, {"Time Warp", sts::MonsterStatus::TIME_WARP},
    {"Invincible", sts::MonsterStatus::INVINCIBLE}, {"InvinciblePower", sts::MonsterStatus::INVINCIBLE}, {"Reactive", sts::MonsterStatus::REACTIVE},
    {"Sharp Hide", sts::MonsterStatus::SHARP_HIDE}, {"Asleep", sts::MonsterStatus::ASLEEP},
    {"Barricade", sts::MonsterStatus::BARRICADE}, {"Minion", sts::MonsterStatus::MINION},
    {"MinionLeader", sts::MonsterStatus::MINION_LEADER}, {"PainfulStabs", sts::MonsterStatus::PAINFUL_STABS},
    {"Regrow", sts::MonsterStatus::REGROW}, {"Shifting", sts::MonsterStatus::SHIFTING},
    {"Stasis", sts::MonsterStatus::STASIS},
    {"BlockReturnPower", sts::MonsterStatus::BLOCK_RETURN}, {"ChokedPower", sts::MonsterStatus::CHOKED},
    {"CorpseExplosionPower", sts::MonsterStatus::CORPSE_EXPLOSION}, {"LockOnPower", sts::MonsterStatus::LOCK_ON},
    {"MarkPower", sts::MonsterStatus::MARK}, {"ShackledPower", sts::MonsterStatus::SHACKLED},
    {"RegenerateMonsterPower", sts::MonsterStatus::REGEN}, {"FadingPower", sts::MonsterStatus::FADING},
    {"FlightPower", sts::MonsterStatus::FLIGHT}, {"MalleablePower", sts::MonsterStatus::MALLEABLE},
    {"ModeShiftPower", sts::MonsterStatus::MODE_SHIFT}, {"SporeCloudPower", sts::MonsterStatus::SPORE_CLOUD},
    {"ThieveryPower", sts::MonsterStatus::THIEVERY}, {"SharpHidePower", sts::MonsterStatus::SHARP_HIDE},
    {"AsleepPower", sts::MonsterStatus::ASLEEP},
};

const std::map<std::string, sts::CardSelectTask> kSelectionTasks = {
    {"ARMAMENTS", sts::CardSelectTask::ARMAMENTS}, {"DUAL_WIELD", sts::CardSelectTask::DUAL_WIELD},
    {"EXHAUST_ONE", sts::CardSelectTask::EXHAUST_ONE}, {"EXHAUST_MANY", sts::CardSelectTask::EXHAUST_MANY},
    {"FORETHOUGHT", sts::CardSelectTask::FORETHOUGHT}, {"GAMBLE", sts::CardSelectTask::GAMBLE},
    {"HEADBUTT", sts::CardSelectTask::HEADBUTT}, {"EXHUME", sts::CardSelectTask::EXHUME},
    {"LIQUID_MEMORIES_POTION", sts::CardSelectTask::LIQUID_MEMORIES_POTION},
    {"SECRET_TECHNIQUE", sts::CardSelectTask::SECRET_TECHNIQUE}, {"SECRET_WEAPON", sts::CardSelectTask::SECRET_WEAPON},
    {"CODEX", sts::CardSelectTask::CODEX}, {"DISCOVERY", sts::CardSelectTask::DISCOVERY},
    {"HOLOGRAM", sts::CardSelectTask::HOLOGRAM}, {"MEDITATE", sts::CardSelectTask::MEDITATE},
    {"NIGHTMARE", sts::CardSelectTask::NIGHTMARE}, {"RECYCLE", sts::CardSelectTask::RECYCLE},
    {"SEEK", sts::CardSelectTask::SEEK}, {"SETUP", sts::CardSelectTask::SETUP}, {"WARCRY", sts::CardSelectTask::WARCRY},
};

} // namespace

std::optional<sts::MonsterId> monsterId(const std::string &id) { return find(kMonsters, id); }
std::optional<sts::MonsterEncounter> encounterId(const std::string &id) { return find(kEncounters, id); }
std::optional<sts::MonsterStatus> monsterStatus(const std::string &id) { return find(kMonsterStatuses, id); }
std::optional<PlayerStatus> playerStatus(const std::string &id) { return find(kPlayerStatuses, id); }
std::optional<sts::CardSelectTask> cardSelectTask(const std::string &id) { return find(kSelectionTasks, id); }

std::optional<sts::MonsterMoveId> monsterMove(const std::string &id, int nextMove) {
    const auto monster = monsterId(id);
    if (!monster || nextMove <= 0) return std::nullopt;
    // Vanilla AbstractMonster move slots are stable per encounter.  Keep the
    // table explicit: an unknown byte is a hard boundary, never an intent
    // guessed from localized text or damage.
    using M = sts::MonsterMoveId;
    const auto ordinal = [nextMove](std::initializer_list<M> moves) -> std::optional<M> {
        return nextMove >= 1 && static_cast<std::size_t>(nextMove) <= moves.size()
            ? std::optional<M>{*(moves.begin() + (nextMove - 1))} : std::nullopt;
    };
    switch (*monster) {
    case sts::MonsterId::ACID_SLIME_L: return ordinal({M::ACID_SLIME_L_CORROSIVE_SPIT, M::ACID_SLIME_L_LICK, M::ACID_SLIME_L_TACKLE, M::ACID_SLIME_L_SPLIT});
    case sts::MonsterId::ACID_SLIME_M: return ordinal({M::ACID_SLIME_M_CORROSIVE_SPIT, M::ACID_SLIME_M_LICK, M::ACID_SLIME_M_TACKLE});
    case sts::MonsterId::ACID_SLIME_S: return ordinal({M::ACID_SLIME_S_LICK, M::ACID_SLIME_S_TACKLE});
    case sts::MonsterId::AWAKENED_ONE: return ordinal({M::AWAKENED_ONE_SLASH, M::AWAKENED_ONE_SOUL_STRIKE, M::AWAKENED_ONE_REBIRTH, M::AWAKENED_ONE_DARK_ECHO, M::AWAKENED_ONE_SLUDGE, M::AWAKENED_ONE_TACKLE});
    case sts::MonsterId::BEAR: return ordinal({M::BEAR_BEAR_HUG, M::BEAR_LUNGE, M::BEAR_MAUL});
    case sts::MonsterId::BRONZE_AUTOMATON: return ordinal({M::BRONZE_AUTOMATON_BOOST, M::BRONZE_AUTOMATON_FLAIL, M::BRONZE_AUTOMATON_HYPER_BEAM, M::BRONZE_AUTOMATON_SPAWN_ORBS, M::BRONZE_AUTOMATON_STUNNED});
    case sts::MonsterId::BRONZE_ORB: return ordinal({M::BRONZE_ORB_BEAM, M::BRONZE_ORB_STASIS, M::BRONZE_ORB_SUPPORT_BEAM});
    case sts::MonsterId::BYRD: return ordinal({M::BYRD_CAW, M::BYRD_FLY, M::BYRD_HEADBUTT, M::BYRD_PECK, M::BYRD_STUNNED, M::BYRD_SWOOP});
    case sts::MonsterId::CENTURION: return ordinal({M::CENTURION_SLASH, M::CENTURION_FURY, M::CENTURION_DEFEND});
    case sts::MonsterId::CHOSEN: return ordinal({M::CHOSEN_POKE, M::CHOSEN_ZAP, M::CHOSEN_DEBILITATE, M::CHOSEN_DRAIN, M::CHOSEN_HEX});
    case sts::MonsterId::CORRUPT_HEART: return ordinal({M::CORRUPT_HEART_DEBILITATE, M::CORRUPT_HEART_BLOOD_SHOTS, M::CORRUPT_HEART_ECHO, M::CORRUPT_HEART_BUFF});
    case sts::MonsterId::DAGGER: return ordinal({M::DAGGER_STAB, M::DAGGER_EXPLODE});
    case sts::MonsterId::DARKLING: return ordinal({M::DARKLING_NIP, M::DARKLING_CHOMP, M::DARKLING_HARDEN, M::DARKLING_REINCARNATE, M::DARKLING_REGROW});
    case sts::MonsterId::DECA: return ordinal({M::DECA_SQUARE_OF_PROTECTION, M::DECA_BEAM});
    case sts::MonsterId::DONU: return ordinal({M::DONU_CIRCLE_OF_POWER, M::DONU_BEAM});
    case sts::MonsterId::EXPLODER: return ordinal({M::EXPLODER_SLAM, M::EXPLODER_EXPLODE});
    case sts::MonsterId::FAT_GREMLIN: return ordinal({M::FAT_GREMLIN_SMASH});
    case sts::MonsterId::FUNGI_BEAST: return ordinal({M::FUNGI_BEAST_BITE, M::FUNGI_BEAST_GROW});
    case sts::MonsterId::GREEN_LOUSE: return ordinal({M::GREEN_LOUSE_BITE, M::GREEN_LOUSE_SPIT_WEB});
    case sts::MonsterId::RED_LOUSE: return ordinal({M::RED_LOUSE_BITE, M::RED_LOUSE_GROW});
    case sts::MonsterId::GREMLIN_LEADER: return ordinal({M::GREMLIN_LEADER_ENCOURAGE, M::GREMLIN_LEADER_RALLY, M::GREMLIN_LEADER_STAB});
    case sts::MonsterId::GREMLIN_WIZARD: return ordinal({M::GREMLIN_WIZARD_CHARGING, M::GREMLIN_WIZARD_ULTIMATE_BLAST});
    case sts::MonsterId::HEXAGHOST: return ordinal({M::HEXAGHOST_ACTIVATE, M::HEXAGHOST_DIVIDER, M::HEXAGHOST_INFERNO, M::HEXAGHOST_SEAR, M::HEXAGHOST_TACKLE, M::HEXAGHOST_INFLAME});
    case sts::MonsterId::CULTIST: return nextMove == 3 ? M::CULTIST_INCANTATION : nextMove == 2 ? M::CULTIST_DARK_STRIKE : std::optional<M>{};
    case sts::MonsterId::JAW_WORM: return nextMove == 1 ? M::JAW_WORM_CHOMP : nextMove == 2 ? M::JAW_WORM_THRASH : nextMove == 3 ? M::JAW_WORM_BELLOW : std::optional<M>{};
    case sts::MonsterId::GREMLIN_NOB: return nextMove == 1 ? M::GREMLIN_NOB_RUSH : nextMove == 2 ? M::GREMLIN_NOB_SKULL_BASH : nextMove == 3 ? M::GREMLIN_NOB_BELLOW : std::optional<M>{};
    case sts::MonsterId::BLUE_SLAVER: return nextMove == 1 ? M::BLUE_SLAVER_STAB : nextMove == 2 ? M::BLUE_SLAVER_RAKE : std::optional<M>{};
    case sts::MonsterId::RED_SLAVER: return nextMove == 1 ? M::RED_SLAVER_STAB : nextMove == 2 ? M::RED_SLAVER_SCRAPE : nextMove == 3 ? M::RED_SLAVER_ENTANGLE : std::optional<M>{};
    case sts::MonsterId::LOOTER: return nextMove == 1 ? M::LOOTER_MUG : nextMove == 2 ? M::LOOTER_LUNGE : nextMove == 3 ? M::LOOTER_SMOKE_BOMB : nextMove == 4 ? M::LOOTER_ESCAPE : std::optional<M>{};
    case sts::MonsterId::MUGGER: return nextMove == 1 ? M::MUGGER_MUG : nextMove == 2 ? M::MUGGER_LUNGE : nextMove == 3 ? M::MUGGER_SMOKE_BOMB : nextMove == 4 ? M::MUGGER_ESCAPE : std::optional<M>{};
    case sts::MonsterId::LAGAVULIN: return nextMove == 1 ? M::LAGAVULIN_ATTACK : nextMove == 2 ? M::LAGAVULIN_SIPHON_SOUL : nextMove == 3 ? M::LAGAVULIN_SLEEP : std::optional<M>{};
    case sts::MonsterId::BOOK_OF_STABBING: return nextMove == 1 ? M::BOOK_OF_STABBING_MULTI_STAB : nextMove == 2 ? M::BOOK_OF_STABBING_SINGLE_STAB : std::optional<M>{};
    case sts::MonsterId::SNAKE_PLANT: return nextMove == 1 ? M::SNAKE_PLANT_CHOMP : nextMove == 2 ? M::SNAKE_PLANT_ENFEEBLING_SPORES : std::optional<M>{};
    case sts::MonsterId::SNECKO: return nextMove == 1 ? M::SNECKO_PERPLEXING_GLARE : nextMove == 2 ? M::SNECKO_TAIL_WHIP : nextMove == 3 ? M::SNECKO_BITE : std::optional<M>{};
    case sts::MonsterId::MAD_GREMLIN: return ordinal({M::MAD_GREMLIN_SCRATCH});
    case sts::MonsterId::MYSTIC: return ordinal({M::MYSTIC_HEAL, M::MYSTIC_BUFF, M::MYSTIC_ATTACK_DEBUFF});
    case sts::MonsterId::NEMESIS: return ordinal({M::NEMESIS_DEBUFF, M::NEMESIS_ATTACK, M::NEMESIS_SCYTHE});
    case sts::MonsterId::ORB_WALKER: return ordinal({M::ORB_WALKER_LASER, M::ORB_WALKER_CLAW});
    case sts::MonsterId::POINTY: return ordinal({M::POINTY_ATTACK});
    case sts::MonsterId::REPULSOR: return ordinal({M::REPULSOR_BASH, M::REPULSOR_REPULSE});
    case sts::MonsterId::REPTOMANCER: return ordinal({M::REPTOMANCER_SUMMON, M::REPTOMANCER_SNAKE_STRIKE, M::REPTOMANCER_BIG_BITE});
    case sts::MonsterId::ROMEO: return ordinal({M::ROMEO_MOCK, M::ROMEO_AGONIZING_SLASH, M::ROMEO_CROSS_SLASH});
    case sts::MonsterId::SENTRY: return ordinal({M::SENTRY_BEAM, M::SENTRY_BOLT});
    case sts::MonsterId::SHELLED_PARASITE: return ordinal({M::SHELLED_PARASITE_DOUBLE_STRIKE, M::SHELLED_PARASITE_FELL, M::SHELLED_PARASITE_STUNNED, M::SHELLED_PARASITE_SUCK});
    case sts::MonsterId::SHIELD_GREMLIN: return ordinal({M::SHIELD_GREMLIN_PROTECT, M::SHIELD_GREMLIN_SHIELD_BASH});
    case sts::MonsterId::SLIME_BOSS: return ordinal({M::SLIME_BOSS_GOOP_SPRAY, M::SLIME_BOSS_PREPARING, M::SLIME_BOSS_SLAM, M::SLIME_BOSS_SPLIT});
    case sts::MonsterId::SNEAKY_GREMLIN: return ordinal({M::SNEAKY_GREMLIN_PUNCTURE});
    case sts::MonsterId::SPHERIC_GUARDIAN: return ordinal({M::SPHERIC_GUARDIAN_SLAM, M::SPHERIC_GUARDIAN_ACTIVATE, M::SPHERIC_GUARDIAN_HARDEN, M::SPHERIC_GUARDIAN_ATTACK_DEBUFF});
    case sts::MonsterId::SPIKER: return ordinal({M::SPIKER_CUT, M::SPIKER_SPIKE});
    case sts::MonsterId::SPIKE_SLIME_L: return ordinal({M::SPIKE_SLIME_L_FLAME_TACKLE, M::SPIKE_SLIME_L_LICK, M::SPIKE_SLIME_L_SPLIT});
    case sts::MonsterId::SPIKE_SLIME_M: return ordinal({M::SPIKE_SLIME_M_FLAME_TACKLE, M::SPIKE_SLIME_M_LICK});
    case sts::MonsterId::SPIKE_SLIME_S: return ordinal({M::SPIKE_SLIME_S_TACKLE});
    case sts::MonsterId::SPIRE_GROWTH: return ordinal({M::SPIRE_GROWTH_QUICK_TACKLE, M::SPIRE_GROWTH_SMASH, M::SPIRE_GROWTH_CONSTRICT});
    case sts::MonsterId::SPIRE_SHIELD: return ordinal({M::SPIRE_SHIELD_BASH, M::SPIRE_SHIELD_FORTIFY, M::SPIRE_SHIELD_SMASH});
    case sts::MonsterId::SPIRE_SPEAR: return ordinal({M::SPIRE_SPEAR_BURN_STRIKE, M::SPIRE_SPEAR_PIERCER, M::SPIRE_SPEAR_SKEWER});
    case sts::MonsterId::TASKMASTER: return ordinal({M::TASKMASTER_SCOURING_WHIP});
    case sts::MonsterId::THE_CHAMP: return ordinal({M::THE_CHAMP_DEFENSIVE_STANCE, M::THE_CHAMP_FACE_SLAP, M::THE_CHAMP_TAUNT, M::THE_CHAMP_HEAVY_SLASH, M::THE_CHAMP_GLOAT, M::THE_CHAMP_EXECUTE, M::THE_CHAMP_ANGER});
    case sts::MonsterId::THE_COLLECTOR: return ordinal({M::THE_COLLECTOR_BUFF, M::THE_COLLECTOR_FIREBALL, M::THE_COLLECTOR_MEGA_DEBUFF, M::THE_COLLECTOR_SPAWN});
    case sts::MonsterId::THE_GUARDIAN: return ordinal({M::THE_GUARDIAN_CHARGING_UP, M::THE_GUARDIAN_FIERCE_BASH, M::THE_GUARDIAN_VENT_STEAM, M::THE_GUARDIAN_WHIRLWIND, M::THE_GUARDIAN_DEFENSIVE_MODE, M::THE_GUARDIAN_ROLL_ATTACK, M::THE_GUARDIAN_TWIN_SLAM});
    case sts::MonsterId::THE_MAW: return ordinal({M::THE_MAW_ROAR, M::THE_MAW_DROOL, M::THE_MAW_SLAM, M::THE_MAW_NOM});
    case sts::MonsterId::TORCH_HEAD: return ordinal({M::TORCH_HEAD_TACKLE});
    case sts::MonsterId::GIANT_HEAD: return nextMove == 1 ? M::GIANT_HEAD_COUNT : nextMove == 2 ? M::GIANT_HEAD_GLARE : nextMove == 3 ? M::GIANT_HEAD_IT_IS_TIME : std::optional<M>{};
    case sts::MonsterId::TIME_EATER: return nextMove == 1 ? M::TIME_EATER_REVERBERATE : nextMove == 2 ? M::TIME_EATER_HEAD_SLAM : nextMove == 3 ? M::TIME_EATER_RIPPLE : nextMove == 4 ? M::TIME_EATER_HASTE : std::optional<M>{};
    case sts::MonsterId::TRANSIENT: return nextMove == 1 ? M::TRANSIENT_ATTACK : std::optional<M>{};
    case sts::MonsterId::WRITHING_MASS: return nextMove == 1 ? M::WRITHING_MASS_IMPLANT : nextMove == 2 ? M::WRITHING_MASS_FLAIL : nextMove == 3 ? M::WRITHING_MASS_WITHER : nextMove == 4 ? M::WRITHING_MASS_MULTI_STRIKE : nextMove == 5 ? M::WRITHING_MASS_STRONG_STRIKE : std::optional<M>{};
    default: return std::nullopt;
    }
}

} // namespace one_combat::advisor::live_silver
