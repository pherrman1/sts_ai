#include "live_silver_mapping.h"

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
    // The Java class names are color-independent: LouseNormal is the red
    // louse (Strengthen), while LouseDefensive is the green louse (Weaken).
    {"FuzzyLouseNormal", sts::MonsterId::RED_LOUSE}, {"FuzzyLouseDefensive", sts::MonsterId::GREEN_LOUSE},
    {"GremlinLeader", sts::MonsterId::GREMLIN_LEADER}, {"GremlinNob", sts::MonsterId::GREMLIN_NOB},
    {"GremlinFat", sts::MonsterId::FAT_GREMLIN}, {"GremlinThief", sts::MonsterId::SNEAKY_GREMLIN},
    {"GremlinTsundere", sts::MonsterId::SHIELD_GREMLIN}, {"GremlinWarrior", sts::MonsterId::MAD_GREMLIN},
    {"GremlinSneaky", sts::MonsterId::SNEAKY_GREMLIN}, {"GremlinShield", sts::MonsterId::SHIELD_GREMLIN},
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
    {"Hex", PlayerStatus::HEX}, {"Pen Nib", PlayerStatus::PEN_NIB},
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
    {"The Bomb", PlayerStatus::THE_BOMB}, {"TheBomb", PlayerStatus::THE_BOMB},
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
    // These are the move bytes established by the PR 248 live observer and
    // checked against the installed desktop-1.0.jar.  Do not infer the byte
    // from the order of native enum values: many vanilla monsters use sparse
    // or state-dependent byte constants.  Additional encounters stay
    // unsupported until their actual Java class constants are qualified.
    using M = sts::MonsterMoveId;
    switch (*monster) {
    case sts::MonsterId::CULTIST:
        return nextMove == 3 ? std::optional<M>{M::CULTIST_INCANTATION}
            : nextMove == 1 ? std::optional<M>{M::CULTIST_DARK_STRIKE} : std::nullopt;
    case sts::MonsterId::JAW_WORM:
        return nextMove == 1 ? std::optional<M>{M::JAW_WORM_CHOMP}
            : nextMove == 2 ? std::optional<M>{M::JAW_WORM_BELLOW}
            : nextMove == 3 ? std::optional<M>{M::JAW_WORM_THRASH} : std::nullopt;
    case sts::MonsterId::ACID_SLIME_L:
        return nextMove == 1 ? std::optional<M>{M::ACID_SLIME_L_CORROSIVE_SPIT}
            : nextMove == 2 ? std::optional<M>{M::ACID_SLIME_L_TACKLE}
            : nextMove == 3 ? std::optional<M>{M::ACID_SLIME_L_SPLIT}
            : nextMove == 4 ? std::optional<M>{M::ACID_SLIME_L_LICK} : std::nullopt;
    case sts::MonsterId::ACID_SLIME_M:
        return nextMove == 1 ? std::optional<M>{M::ACID_SLIME_M_CORROSIVE_SPIT}
            : nextMove == 2 ? std::optional<M>{M::ACID_SLIME_M_TACKLE}
            : nextMove == 4 ? std::optional<M>{M::ACID_SLIME_M_LICK} : std::nullopt;
    case sts::MonsterId::ACID_SLIME_S:
        return nextMove == 1 ? std::optional<M>{M::ACID_SLIME_S_TACKLE}
            : nextMove == 2 ? std::optional<M>{M::ACID_SLIME_S_LICK} : std::nullopt;
    case sts::MonsterId::FUNGI_BEAST:
        return nextMove == 1 ? std::optional<M>{M::FUNGI_BEAST_BITE}
            : nextMove == 2 ? std::optional<M>{M::FUNGI_BEAST_GROW} : std::nullopt;
    case sts::MonsterId::FAT_GREMLIN:
        return nextMove == 2 ? std::optional<M>{M::FAT_GREMLIN_SMASH} : std::nullopt;
    case sts::MonsterId::SNEAKY_GREMLIN:
        return nextMove == 1 ? std::optional<M>{M::SNEAKY_GREMLIN_PUNCTURE} : std::nullopt;
    case sts::MonsterId::SHIELD_GREMLIN:
        return nextMove == 1 ? std::optional<M>{M::SHIELD_GREMLIN_PROTECT}
            : nextMove == 2 ? std::optional<M>{M::SHIELD_GREMLIN_SHIELD_BASH} : std::nullopt;
    case sts::MonsterId::MAD_GREMLIN:
        return nextMove == 1 ? std::optional<M>{M::MAD_GREMLIN_SCRATCH} : std::nullopt;
    case sts::MonsterId::GREMLIN_WIZARD:
        return nextMove == 1 ? std::optional<M>{M::GREMLIN_WIZARD_ULTIMATE_BLAST}
            : nextMove == 2 ? std::optional<M>{M::GREMLIN_WIZARD_CHARGING} : std::nullopt;
    case sts::MonsterId::HEXAGHOST:
        return nextMove == 1 ? std::optional<M>{M::HEXAGHOST_DIVIDER}
            : nextMove == 2 ? std::optional<M>{M::HEXAGHOST_TACKLE}
            : nextMove == 3 ? std::optional<M>{M::HEXAGHOST_INFLAME}
            : nextMove == 4 ? std::optional<M>{M::HEXAGHOST_SEAR}
            : nextMove == 5 ? std::optional<M>{M::HEXAGHOST_ACTIVATE}
            : nextMove == 6 ? std::optional<M>{M::HEXAGHOST_INFERNO} : std::nullopt;
    case sts::MonsterId::LAGAVULIN:
        return nextMove == 1 ? std::optional<M>{M::LAGAVULIN_SIPHON_SOUL}
            : nextMove == 3 ? std::optional<M>{M::LAGAVULIN_ATTACK}
            : (nextMove == 4 || nextMove == 5 || nextMove == 6)
                ? std::optional<M>{M::LAGAVULIN_SLEEP} : std::nullopt;
    case sts::MonsterId::LOOTER:
        return nextMove == 1 ? std::optional<M>{M::LOOTER_MUG}
            : nextMove == 2 ? std::optional<M>{M::LOOTER_SMOKE_BOMB}
            : nextMove == 3 ? std::optional<M>{M::LOOTER_ESCAPE}
            : nextMove == 4 ? std::optional<M>{M::LOOTER_LUNGE} : std::nullopt;
    case sts::MonsterId::GREEN_LOUSE:
        return nextMove == 3 ? std::optional<M>{M::GREEN_LOUSE_BITE}
            : nextMove == 4 ? std::optional<M>{M::GREEN_LOUSE_SPIT_WEB} : std::nullopt;
    case sts::MonsterId::RED_LOUSE:
        return nextMove == 3 ? std::optional<M>{M::RED_LOUSE_BITE}
            : nextMove == 4 ? std::optional<M>{M::RED_LOUSE_GROW} : std::nullopt;
    case sts::MonsterId::SENTRY:
        return nextMove == 3 ? std::optional<M>{M::SENTRY_BOLT}
            : nextMove == 4 ? std::optional<M>{M::SENTRY_BEAM} : std::nullopt;
    case sts::MonsterId::BLUE_SLAVER:
        return nextMove == 1 ? std::optional<M>{M::BLUE_SLAVER_STAB}
            : nextMove == 4 ? std::optional<M>{M::BLUE_SLAVER_RAKE} : std::nullopt;
    case sts::MonsterId::RED_SLAVER:
        return nextMove == 1 ? std::optional<M>{M::RED_SLAVER_STAB}
            : nextMove == 2 ? std::optional<M>{M::RED_SLAVER_ENTANGLE}
            : nextMove == 3 ? std::optional<M>{M::RED_SLAVER_SCRAPE} : std::nullopt;
    case sts::MonsterId::SLIME_BOSS:
        return nextMove == 1 ? std::optional<M>{M::SLIME_BOSS_SLAM}
            : nextMove == 2 ? std::optional<M>{M::SLIME_BOSS_PREPARING}
            : nextMove == 3 ? std::optional<M>{M::SLIME_BOSS_SPLIT}
            : nextMove == 4 ? std::optional<M>{M::SLIME_BOSS_GOOP_SPRAY} : std::nullopt;
    case sts::MonsterId::SPIKE_SLIME_L:
        return nextMove == 1 ? std::optional<M>{M::SPIKE_SLIME_L_FLAME_TACKLE}
            : nextMove == 3 ? std::optional<M>{M::SPIKE_SLIME_L_SPLIT}
            : nextMove == 4 ? std::optional<M>{M::SPIKE_SLIME_L_LICK} : std::nullopt;
    case sts::MonsterId::SPIKE_SLIME_M:
        return nextMove == 1 ? std::optional<M>{M::SPIKE_SLIME_M_FLAME_TACKLE}
            : nextMove == 4 ? std::optional<M>{M::SPIKE_SLIME_M_LICK} : std::nullopt;
    case sts::MonsterId::SPIKE_SLIME_S:
        return nextMove == 1 ? std::optional<M>{M::SPIKE_SLIME_S_TACKLE} : std::nullopt;
    case sts::MonsterId::THE_GUARDIAN:
        return nextMove == 1 ? std::optional<M>{M::THE_GUARDIAN_DEFENSIVE_MODE}
            : nextMove == 2 ? std::optional<M>{M::THE_GUARDIAN_FIERCE_BASH}
            : nextMove == 3 ? std::optional<M>{M::THE_GUARDIAN_ROLL_ATTACK}
            : nextMove == 4 ? std::optional<M>{M::THE_GUARDIAN_TWIN_SLAM}
            : nextMove == 5 ? std::optional<M>{M::THE_GUARDIAN_WHIRLWIND}
            : nextMove == 6 ? std::optional<M>{M::THE_GUARDIAN_CHARGING_UP}
            : nextMove == 7 ? std::optional<M>{M::THE_GUARDIAN_VENT_STEAM} : std::nullopt;
    case sts::MonsterId::GREMLIN_NOB:
        return nextMove == 3 ? std::optional<M>{M::GREMLIN_NOB_BELLOW}
            : nextMove == 1 ? std::optional<M>{M::GREMLIN_NOB_RUSH}
            : nextMove == 2 ? std::optional<M>{M::GREMLIN_NOB_SKULL_BASH} : std::nullopt;
    default: return std::nullopt;
    }
}

} // namespace one_combat::advisor::live_silver
