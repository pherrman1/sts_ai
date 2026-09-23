package stsmodelinspector;

import java.util.HashMap;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/** Pure projection tests: no game, rendering context, RNG, or save is initialized. */
public final class LiveOocCaptureTest {
    private static Map<String,Object> obj(Object... values) {
        Map<String,Object> out = new HashMap<>();
        for (int i = 0; i < values.length; i += 2) out.put((String)values[i], values[i + 1]);
        return out;
    }
    private static void check(String id, int counter, boolean usedUp, int expected, String reason) {
        Map<String,Object> state = new HashMap<>();
        int actual = LiveOocCapture.nativeRelicData(id, counter, usedUp, state);
        if (actual != expected || (reason == null ? state.containsKey("unsupportedReason")
                : !reason.equals(state.get("unsupportedReason"))))
            throw new AssertionError(id + ": " + actual + " " + state);
    }
    public static void main(String[] args) throws Exception {
        if (LiveOocCapture.hasStrategicParentReward(Arrays.asList("CARD", "GOLD", "STOLEN_GOLD"))
                || !LiveOocCapture.hasStrategicParentReward(Arrays.asList("CARD", "SAPPHIRE_KEY"))
                || !LiveOocCapture.hasStrategicParentReward(Arrays.asList("RELIC"))
                || !LiveOocCapture.hasStrategicParentReward(Arrays.asList("POTION")))
            throw new AssertionError("opaque card reward boundary did not distinguish strategic parent rewards");
        check("MawBank", -1, false, 1, null);
        check("MawBank", -2, true, 0, null);
        check("Happy Flower", 2, false, 2, null);
        check("Pen Nib", 9, false, 9, null);
        check("Girya", 3, false, 3, null);
        check("Omamori", 2, false, 2, null);
        check("NeowsBlessing", -2, true, -2, null);
        check("Burning Blood", -1, false, -1, null);
        check("Lizard Tail", -1, false, -1, "RELIC_NATIVE_STATE_UNREPRESENTABLE:Lizard Tail:active");
        check("Lizard Tail", -2, true, 0, null);
        check("Matryoshka", 2, false, 2, "RELIC_NATIVE_STATE_UNREPRESENTABLE:Matryoshka:active");
        check("WingedGreaves", 3, false, 0, null);
        check("NlothsMask", 1, false, 1, "RELIC_NATIVE_STATE_UNREPRESENTABLE:NlothsMask:active");
        check("Matryoshka", -2, true, 0, null);
        check("UnqualifiedCounter", 3, false, 3, "RELIC_NATIVE_COUNTER_UNQUALIFIED:UnqualifiedCounter");
        if (!LiveOocCapture.bottlePromptMatches("Choose a card for Bottled Tornado.",
                    "Choose a card for ", "Bottled Tornado", ".")
                || LiveOocCapture.bottlePromptMatches("Choose a card to upgrade.",
                    "Choose a card for ", "Bottled Tornado", ".")
                || LiveOocCapture.bottlePromptMatches(null,
                    "Choose a card for ", "Bottled Tornado", "."))
            throw new AssertionError("bottle selector prompt identity widened");
        if (!"GAMBLE".equals(STSModelInspector.handSelectionTask("", true, true, 99)))
            throw new AssertionError("Gambler's Brew hand selector was not classified as GAMBLE");
        if (!"".equals(STSModelInspector.handSelectionTask("", false, true, 99)))
            throw new AssertionError("unknown fixed-size hand selector was over-promoted");
        if (LiveOocCapture.nativeEdgeDestination(14, 3, 16) != 3)
            throw new AssertionError("vanilla terminal boss edge lost");
        if (LiveOocCapture.nativeEdgeDestination(7, 6, 8) != 6)
            throw new AssertionError("ordinary visible edge changed");
        int[][] invalid = {{13, 3, 16}, {14, 2, 16}, {14, 3, 15}, {7, 7, 8}, {7, 3, 9}};
        for (int[] edge : invalid) {
            boolean rejected = false;
            try { LiveOocCapture.nativeEdgeDestination(edge[0], edge[1], edge[2]); }
            catch (IllegalArgumentException expected) { rejected = true; }
            if (!rejected) throw new AssertionError("invalid map edge accepted");
        }
        if (!"combat_reward".equals(LiveOocCapture.canonicalScreen("COMBAT_REWARD"))
                || !"selector".equals(LiveOocCapture.canonicalScreen("GRID"))
                || !"boss_relic".equals(LiveOocCapture.canonicalScreen("BOSS_REWARD")))
            throw new AssertionError("early canonical screen correlation lost");
        java.util.List<String> persistedPath = new java.util.ArrayList<>();
        for (int i = 0; i < 15; ++i) persistedPath.add("M");
        persistedPath.add("unknown-boss-marker");
        persistedPath.add("M");
        java.util.List<String> qualified = LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(16, 18));
        if (!"BOSS".equals(qualified.get(15)) || !"MONSTER".equals(qualified.get(16)))
            throw new AssertionError("completed public boss marker stayed incomplete in Act 2");
        java.util.List<String> act3Path = new java.util.ArrayList<>();
        for (int i = 0; i < 15; ++i) act3Path.add("M");
        act3Path.add("unknown-boss-marker");
        for (int i = 0; i < 15; ++i) act3Path.add("R");
        act3Path.add("unknown-boss-marker");
        java.util.List<String> act3Qualified = LiveOocCapture.canonicalPathHistory(
                act3Path, true, "", 3, java.util.Arrays.asList(16, 33));
        if (!"BOSS".equals(act3Qualified.get(31)))
            throw new AssertionError("completed Act 2 boss marker was lost at Act 3 map entry");
        java.util.List<String> sensoryLabels = java.util.Arrays.asList(
                "[Recall] Add 1 Colorless card to your deck.",
                "[Recall] Add 2 Colorless cards to your deck. Lose 5 HP.",
                "[Recall] Add 3 Colorless cards to your deck. Lose 10 HP.");
        java.util.List<Map<String,Object>> sensoryOptions = new java.util.ArrayList<>();
        for (int i = 0; i < 3; ++i) sensoryOptions.add(obj("index", i));
        if (!"Sensory Stone".equals(LiveOocCapture.canonicalEventId("SensoryStone"))
                || !LiveOocCapture.sensoryStoneInitialVisible(
                        "INTRO_2", sensoryLabels, sensoryOptions)
                || LiveOocCapture.sensoryStoneInitialVisible(
                        "OTHER", sensoryLabels, sensoryOptions))
            throw new AssertionError("Sensory Stone public Recall choices lost native indices or costs");
        java.util.List<String> priorEvents = new java.util.ArrayList<>();
        LiveOocCapture.addPriorEvent(priorEvents, "SensoryStone");
        LiveOocCapture.addPriorEvent(priorEvents, "Sensory Stone");
        if (priorEvents.size() != 1 || !"Sensory Stone".equals(priorEvents.get(0)))
            throw new AssertionError("Sensory Stone metric history retained its raw Java ID");
        java.util.List<Map<String,Object>> designerOptions = new java.util.ArrayList<>();
        for (int i = 0; i < 4; ++i) designerOptions.add(obj("index", i));
        java.util.List<String> designerLabels = java.util.Arrays.asList(
                "[Adjustments] Lose 40 Gold. Upgrade a card.",
                "[Clean Up] Lose 60 Gold. Transform 2 cards.",
                "[Full Service] Lose 90 Gold. Remove a card and upgrade a random card.",
                "[Punch] Lose 3 HP.");
        if (!java.util.Arrays.equals(new int[] {0, 3, 4, 5},
                LiveOocCapture.designerInitialNativeIndices("0", designerLabels,
                        designerOptions, true, false, 40, 60, 90, 3, 0))
                || LiveOocCapture.designerInitialNativeIndices("1", designerLabels,
                        designerOptions, true, false, 40, 60, 90, 3, 0) != null)
            throw new AssertionError("Designer visible services lost native option identities");
        designerLabels = java.util.Arrays.asList(
                "[Adjustments] Lose 50 Gold. Upgrade 2 random cards.",
                "[Clean Up] Lose 75 Gold. Remove a card.",
                "[Full Service] Lose 110 Gold. Remove a card and upgrade a random card.",
                "[Punch] Lose 5 HP.");
        if (!java.util.Arrays.equals(new int[] {1, 2, 4, 5},
                LiveOocCapture.designerInitialNativeIndices("0", designerLabels,
                        designerOptions, false, true, 50, 75, 110, 5, 20)))
            throw new AssertionError("Designer high-ascension services lost native option identities");
        java.util.List<Map<String,Object>> banditOptions = java.util.Arrays.asList(
                obj("index", 0), obj("index", 1));
        java.util.List<String> banditLabels = java.util.Arrays.asList(
                "[Pay] Lose ALL of your Gold.", "[Fight!]");
        if (!LiveOocCapture.maskedBanditsInitialVisible("INTRO", banditLabels, banditOptions)
                || LiveOocCapture.maskedBanditsInitialVisible("LEAVE", banditLabels, banditOptions))
            throw new AssertionError("Masked Bandits Pay/Fight event phase was misidentified");
        java.util.List<String> libraryLabels = java.util.Arrays.asList(
                "[Read] Choose 1 of 20 cards to add to your deck.", "[Sleep] Heal 26 HP.");
        if (!LiveOocCapture.libraryInitialVisible("0", libraryLabels, banditOptions, 26)
                || LiveOocCapture.libraryInitialVisible("1", libraryLabels, banditOptions, 26)
                || LiveOocCapture.libraryInitialVisible("0", libraryLabels, banditOptions, 25))
            throw new AssertionError("Library public Read/Sleep choice or heal was misidentified");
        java.util.List<Map<String,Object>> augmenterOptions = java.util.Arrays.asList(
                obj("index", 0), obj("index", 1), obj("index", 2));
        java.util.List<String> augmenterLabels = java.util.Arrays.asList(
                "[Test J.A.X.] Get JAXXED.",
                "[Become Test Subject] Transform 2 cards.",
                "[Ingest Mutagens] Obtain a special relic.");
        if (!LiveOocCapture.augmenterInitialVisible("0", augmenterLabels, augmenterOptions)
                || LiveOocCapture.augmenterInitialVisible("1", augmenterLabels, augmenterOptions)
                || LiveOocCapture.augmenterInitialVisible("0", augmenterLabels, banditOptions))
            throw new AssertionError("Augmenter initial options lost their native indices");
        java.util.List<String> writingLabels = java.util.Arrays.asList(
                "[Elegance] Remove a card from your deck.",
                "[Simplicity] Upgrade all Strikes and Defends.");
        if (!LiveOocCapture.ancientWritingInitialVisible("INTRO", writingLabels, banditOptions)
                || LiveOocCapture.ancientWritingInitialVisible("LEAVE", writingLabels, banditOptions)
                || LiveOocCapture.ancientWritingInitialVisible("INTRO", writingLabels, augmenterOptions))
            throw new AssertionError("Ancient Writing initial options lost their native indices");
        java.util.List<String> hallsLabels = java.util.Arrays.asList(
                "[Embrace Madness] Receive 2 Madness. Lose 11 HP.",
                "[Focus] Become Cursed - Writhe. Heal 22 HP.",
                "[Retrace Your Steps] Lose 4 Max HP.");
        if (!LiveOocCapture.windingHallsChoiceVisible("1", hallsLabels, augmenterOptions, 11, 22, 4)
                || LiveOocCapture.windingHallsChoiceVisible("0", hallsLabels, augmenterOptions, 11, 22, 4)
                || LiveOocCapture.windingHallsChoiceVisible("1", hallsLabels, augmenterOptions, 12, 22, 4))
            throw new AssertionError("Winding Halls public HP costs or options were misidentified");
        java.util.List<String> faceLabels = java.util.Arrays.asList(
                "[Touch] Lose 8 HP, gain 75 Gold.",
                "[Trade] 50%: Good Face. 50%: Bad Face.", "[Leave]");
        if (!LiveOocCapture.faceTraderChoiceVisible("MAIN", faceLabels, augmenterOptions, 8, 75, 0)
                || LiveOocCapture.faceTraderChoiceVisible("INTRO", faceLabels, augmenterOptions, 8, 75, 0)
                || LiveOocCapture.faceTraderChoiceVisible("MAIN", faceLabels, augmenterOptions, 9, 75, 0)
                || LiveOocCapture.faceTraderChoiceVisible("MAIN", faceLabels, augmenterOptions, 8, 75, 20))
            throw new AssertionError("Face Trader public Touch and Trade options were misidentified");
        java.util.List<String> addictLabels = java.util.Arrays.asList(
                "[Offer Gold] 85 Gold: Obtain a Relic.",
                "[Rob] Obtain a Relic. Become Cursed - Shame.", "[Leave]");
        if (!LiveOocCapture.addictInitialVisible("0", addictLabels, augmenterOptions, 85)
                || LiveOocCapture.addictInitialVisible("1", addictLabels, augmenterOptions, 85)
                || LiveOocCapture.addictInitialVisible("0", addictLabels, augmenterOptions, 84))
            throw new AssertionError("Addict initial public Pay/Rob/Leave options were misidentified");
        java.util.List<String> vampireLabels = java.util.Arrays.asList(
                "[Accept] Remove all Strikes. Receive 5 Bites. Lose 32 Max HP.", "[Refuse]");
        if (!LiveOocCapture.vampiresNoVialInitialVisible("0", vampireLabels, banditOptions, 32, false)
                || LiveOocCapture.vampiresNoVialInitialVisible("0", vampireLabels, banditOptions, 32, true)
                || LiveOocCapture.vampiresNoVialInitialVisible("0", vampireLabels, banditOptions, 31, false))
            throw new AssertionError("Vampires no-vial choices lost their native indices or HP cost");
        if (!"INVALID".equals(LiveOocCapture.canonicalPathHistory(
                act3Path, true, "", 3, java.util.Arrays.asList(16)).get(31)))
            throw new AssertionError("unconfirmed Act 2 boss marker was promoted");
        if (!"INVALID".equals(LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(18)).get(15)))
            throw new AssertionError("unknown path marker was promoted without a boss combat");
        persistedPath.remove(0);
        if (!"INVALID".equals(LiveOocCapture.canonicalPathHistory(
                persistedPath, false, "", 2, java.util.Arrays.asList(16, 18)).get(14)))
            throw new AssertionError("incomplete prior map history was promoted to a boss");
        Map<String,Object> openedChest = new HashMap<>();
        java.util.List<Map<String,Object>> openedChoices = new java.util.ArrayList<>();
        LiveOocCapture.captureOpenedTreasure(openedChest, openedChoices, true);
        if (openedChoices.size() != 1
                || !"proceed".equals(((Map<?,?>)openedChoices.get(0).get("liveAction")).get("kind"))
                || openedChest.containsKey("unsupportedReason"))
            throw new AssertionError("open boss chest lost its sole live Proceed action");
        openedChoices.clear();
        LiveOocCapture.captureOpenedTreasure(openedChest, openedChoices, false);
        if (!openedChoices.isEmpty()
                || !"CHEST_ALREADY_OPEN".equals(openedChest.get("unsupportedReason")))
            throw new AssertionError("open chest without Proceed exposed a false live action");
        Map<String,Object> phaseUnsupported = obj("publicState", obj("pathComplete", true,
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:Lizard Tail:active"),
                "unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE");
        LiveOocCapture.finalizeSupportReason(phaseUnsupported);
        if (!"EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE".equals(phaseUnsupported.get("unsupportedReason")))
            throw new AssertionError("relic warning hid the unsupported event outro phase");
        Map<String,Object> missingPath = obj("publicState", obj("pathComplete", false,
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:Lizard Tail:active"));
        LiveOocCapture.finalizeSupportReason(missingPath);
        if (!"PATH_HISTORY_UNAVAILABLE".equals(missingPath.get("unsupportedReason")))
            throw new AssertionError("relic warning hid incomplete public path history");
        Map<String,Object> failed = new HashMap<>();
        Map<String,Object> core = new HashMap<>();
        Map<String,Object> mcp = new HashMap<>();
        java.util.List<Object> choices = new java.util.ArrayList<>();
        failed.put("screen", "combat_reward"); failed.put("publicState", core);
        failed.put("mcpState", mcp); failed.put("liveChoices", choices);
        LiveOocCapture.recordCaptureError(failed, new IllegalArgumentException("choice occurrence unavailable"));
        if (!"IllegalArgumentException:choice occurrence unavailable".equals(failed.get("captureError"))
                || failed.containsKey("unsupportedReason") || failed.get("publicState") != core
                || failed.get("mcpState") != mcp || failed.get("liveChoices") != choices
                || !"combat_reward".equals(failed.get("screen")))
            throw new AssertionError("integrity failure became fallback or lost correlation");
        // An earlier support reason must not swallow a later integrity error;
        // the native importer gives captureError precedence over unsupported.
        failed.put("unsupportedReason", "CARD_GROUP_NOT_REVEALED");
        LiveOocCapture.recordCaptureError(failed, new NoSuchMethodException("read-only API missing"));
        if (!"NoSuchMethodException:read-only API missing".equals(failed.get("captureError")))
            throw new AssertionError("reflective integrity failure was hidden");
        if (!"Neow".equals(LiveOocCapture.canonicalEventId("NEOW"))
                || !"Big Fish".equals(LiveOocCapture.canonicalEventId("Big Fish")))
            throw new AssertionError("event canonical save identity mismatch");
        if (!LiveOocCapture.simpleInitialEventSupported("GoldenIdolEvent")
                || !LiveOocCapture.simpleInitialEventSupported("Beggar")
                || !LiveOocCapture.simpleInitialEventSupported("WomanInBlue")
                || !LiveOocCapture.simpleInitialEventSupported("ShiningLight")
                || !LiveOocCapture.simpleInitialEventSupported("WeMeetAgain")
                || !LiveOocCapture.simpleInitialEventSupported("Sssserpent")
                || !LiveOocCapture.simpleInitialEventSupported("ScrapOoze")
                || !LiveOocCapture.simpleInitialEventSupported("CursedTome")
                || LiveOocCapture.simpleInitialEventSupported("LiarsGame")
                || LiveOocCapture.simpleInitialEventSupported("WomanInBlueDialogue")
                || LiveOocCapture.simpleInitialEventSupported("Ghosts")
                || LiveOocCapture.simpleInitialEventSupported("WindingHalls")
                || LiveOocCapture.simpleInitialEventSupported("WorldOfGoop"))
            throw new AssertionError("Woman in Blue initial-phase support boundary mismatch");
        if (!"SMALL".equals(LiveOocCapture.visibleChestSize("SmallChest"))
                || !"MEDIUM".equals(LiveOocCapture.visibleChestSize("MediumChest"))
                || !"LARGE".equals(LiveOocCapture.visibleChestSize("LargeChest"))
                || !LiveOocCapture.visibleChestSize("BossChest").isEmpty())
            throw new AssertionError("public chest size mapping did not stay bounded");
        List<Object> nestOptions = Arrays.asList(obj("index", 0), obj("index", 1));
        List<String> nestLabels = Arrays.asList("[Smash and Grab] Obtain 99 Gold.",
                "[Stay in Line] Obtain Ritual Dagger. Lose 6 HP.");
        if (!LiveOocCapture.nestDecisionVisible("Nest", 1, nestLabels, nestOptions, 0)
                || LiveOocCapture.nestDecisionVisible("Nest", 0, nestLabels, nestOptions, 0)
                || LiveOocCapture.nestDecisionVisible("Nest", 1, nestLabels, nestOptions, 15))
            throw new AssertionError("Nest visible decision phase or ascension mismatch");
        if (!LiveOocCapture.goldenWingInitialVisible("INTRO", Arrays.asList(
                    "[Pray] Remove a card. Lose 7 HP.", "[Leave]"),
                    Arrays.asList(obj("index", 0), obj("index", 2)), false, 7)
                || LiveOocCapture.goldenWingInitialVisible("INTRO", Arrays.asList(
                    "[Pray] Remove a card. Lose 7 HP.", "[Leave]"),
                    Arrays.asList(obj("index", 0), obj("index", 1)), false, 7))
            throw new AssertionError("Golden Wing locked-option slot mismatch");
        if (LiveOocCapture.scrapOozeRetryCount(25, 3, 0) != 0
                || LiveOocCapture.scrapOozeRetryCount(35, 4, 0) != 1
                || LiveOocCapture.scrapOozeRetryCount(55, 8, 20) != 3
                || LiveOocCapture.scrapOozeRetryCount(105, 13, 20) != 8)
            throw new AssertionError("Scrap Ooze public chance lost native retry count");
        List<Object> goopOptions = Arrays.asList(obj("index", 0), obj("index", 1));
        List<String> goopLabels = Arrays.asList(
                "[Gather Gold] Gain 75 Gold. Lose 11 HP.", "[Leave It] Lose 41 Gold.");
        if (!LiveOocCapture.goopInitialVisible("INTRO", goopLabels, goopOptions, 11, 75, 41, 99)
                || LiveOocCapture.goopInitialVisible("RESULT", goopLabels, goopOptions, 11, 75, 41, 99)
                || LiveOocCapture.goopInitialVisible("INTRO", goopLabels, goopOptions, 11, 75, 42, 99)
                || LiveOocCapture.goopInitialVisible("INTRO", goopLabels, goopOptions, 11, 75, 41, 40))
            throw new AssertionError("World of Goop public loss or phase mismatch");
        List<Object> shrineOptions = Arrays.asList(obj("index", 0), obj("index", 1), obj("index", 2));
        List<String> shrineLabels = Arrays.asList("[Pray] Gain 100 Gold.",
                "[Desecrate] Gain 275 Gold. Become Cursed - Regret.", "[Leave]");
        if (!LiveOocCapture.goldShrineInitialVisible("INTRO", shrineLabels, shrineOptions, 100, 0)
                || LiveOocCapture.goldShrineInitialVisible("INTRO", shrineLabels, shrineOptions, 100, 20)
                || LiveOocCapture.goldShrineInitialVisible("RESULT", shrineLabels, shrineOptions, 100, 0)
                || LiveOocCapture.simpleInitialEventSupported("GoldenShrine"))
            throw new AssertionError("GoldShrine runtime class or public amount mismatch");
        List<String> clericLabels = Arrays.asList("[Heal] 35 Gold: Heal 20 HP.",
                "[Purify] 50 Gold: Remove a card from your deck.", "[Leave]");
        if (!LiveOocCapture.clericInitialVisible(0, clericLabels, shrineOptions, 20, 50, 80, 117, 0)
                || LiveOocCapture.clericInitialVisible(1, clericLabels, shrineOptions, 20, 50, 80, 117, 0)
                || LiveOocCapture.clericInitialVisible(0, clericLabels, shrineOptions, 19, 50, 80, 117, 0)
                || LiveOocCapture.clericInitialVisible(0, clericLabels, shrineOptions, 20, 50, 80, 49, 0)
                || LiveOocCapture.clericInitialVisible(0, clericLabels, shrineOptions, 20, 50, 80, 117, 20))
            throw new AssertionError("Cleric initial public options or amount mismatch");
        List<Object> deadOptions = Arrays.asList(obj("index", 0), obj("index", 1));
        List<String> deadLabels = Arrays.asList("[Search] Find Loot. 25%: monster returns.", "[Leave]");
        String[] deadDescriptions = {"", "", "start", "sentries", "nob", "lagavulin", "end"};
        if (LiveOocCapture.deadAdventurerPublicEncounter("INTRO", deadLabels, deadOptions,
                "startnobend", deadDescriptions, 0) != 1
                || LiveOocCapture.deadAdventurerPublicEncounter("RESULT", deadLabels, deadOptions,
                        "startnobend", deadDescriptions, 0) != -1
                || LiveOocCapture.deadAdventurerPublicEncounter("INTRO", deadLabels, deadOptions,
                        "startnobend", deadDescriptions, 20) != -1
                || LiveOocCapture.deadAdventurerPublicEncounter("INTRO", deadLabels, deadOptions,
                        "unknown", deadDescriptions, 0) != -1)
            throw new AssertionError("Dead Adventurer public encounter or phase mismatch");
        List<Object> altarOptions = Arrays.asList(obj("index", 1), obj("index", 2));
        List<String> altarLabels = Arrays.asList("[Sacrifice] Gain 5 Max HP. Lose 22 HP.",
                "[Desecrate] Become Cursed - Decay.");
        if (!LiveOocCapture.forgottenAltarInitialVisible(0, altarLabels, altarOptions, 22, 87, 0, false)
                || LiveOocCapture.forgottenAltarInitialVisible(1, altarLabels, altarOptions, 22, 87, 0, false)
                || LiveOocCapture.forgottenAltarInitialVisible(0, altarLabels, altarOptions, 21, 87, 0, false)
                || LiveOocCapture.forgottenAltarInitialVisible(0, altarLabels, altarOptions, 22, 87, 20, false)
                || LiveOocCapture.forgottenAltarInitialVisible(0, altarLabels,
                        Arrays.asList(obj("index", 0), obj("index", 2)), 22, 87, 0, false))
            throw new AssertionError("Forgotten Altar public options or loss mismatch");
        try {
            LiveOocCapture.scrapOozeRetryCount(30, 3, 0);
            throw new AssertionError("non-native Scrap Ooze chance was accepted");
        } catch (IllegalArgumentException expected) { /* fail closed */ }
        Object firstReward = new Object(), secondReward = new Object();
        String firstIdentity = LiveOocCapture.rewardIdentity(firstReward, null, null);
        if (!firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, null, null))
                || firstIdentity.equals(LiveOocCapture.rewardIdentity(secondReward, null, null)))
            throw new AssertionError("physical reward identity is unstable or ambiguous");
        if (firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, new Object(), null)))
            throw new AssertionError("reward identity reused after run boundary");
        String oldHome = System.getProperty("user.home");
        java.nio.file.Path home = java.nio.file.Files.createTempDirectory("live-ooc-history");
        System.setProperty("user.home", home.toString());
        LiveOocCapture.CardRewardVisits rewardVisits = new LiveOocCapture.CardRewardVisits();
        Object rewardPlayer = new Object(), rewardNode = new Object();
        rewardVisits.parent(rewardPlayer, rewardNode, java.util.Arrays.asList("card-a", "card-b"));
        if (rewardVisits.declined("card-a"))
            throw new AssertionError("unopened card was marked declined");
        rewardVisits.opened(rewardPlayer, rewardNode, "card-a");
        rewardVisits.parent(rewardPlayer, rewardNode, java.util.Arrays.asList("card-a", "card-b"));
        if (!rewardVisits.declined("card-a") || rewardVisits.declined("card-b"))
            throw new AssertionError("only the publicly skipped card should be declined");
        rewardVisits.parent(rewardPlayer, new Object(), java.util.Arrays.asList("card-a"));
        if (rewardVisits.declined("card-a"))
            throw new AssertionError("declined card leaked into another room");
        LiveOocCapture.QuestionHistory questions = new LiveOocCapture.QuestionHistory();
        questions.observe(222, 1, 0, 0, false, "NeowRoom");
        questions.observe(222, 1, 3, 1, true, "EventRoom");
        if (!questions.completeFor(1) || !"EVENT".equals(questions.snapshot().get(0).get("outcome")))
            throw new AssertionError("public question event outcome not captured");
        LiveOocCapture.QuestionHistory restoredQuestions = new LiveOocCapture.QuestionHistory();
        restoredQuestions.observe(222, 1, 3, 1, true, "EventRoom");
        if (!restoredQuestions.completeFor(1))
            throw new AssertionError("question outcome did not survive restart");
        restoredQuestions.observe(222, 1, 5, 2, true, "ShopRoom");
        if (!restoredQuestions.completeFor(2) || restoredQuestions.completeFor(3))
            throw new AssertionError("question outcome count did not gate completeness");
        LiveOocCapture.SeenRelicOffers seen = new LiveOocCapture.SeenRelicOffers();
        Object player = new Object();
        seen.observe(player, 10, 5, false, "shop", obj("relics",
                java.util.Arrays.asList(obj("id", "Anchor", "price", 120))));
        if (seen.complete()) throw new AssertionError("mid-run offer history became complete");
        player = new Object();
        seen.observe(player, 11, 0, true, "neow", obj());
        if (!seen.complete() || !seen.snapshot().isEmpty())
            throw new AssertionError("fresh-run offer history did not reset");
        seen.observe(player, 11, 1, false, "shop", obj("relics",
                java.util.Arrays.asList(obj("id", "Anchor", "price", 120))));
        seen.observe(player, 11, 1, false, "combat_reward", obj("relics",
                java.util.Arrays.asList("Vajra", "Anchor")));
        if (!seen.complete() || !seen.snapshot().equals(java.util.Arrays.asList("Anchor", "Vajra")))
            throw new AssertionError("visible offered relics were lost or duplicated");
        LiveOocCapture.SeenRelicOffers restartedSeen = new LiveOocCapture.SeenRelicOffers();
        restartedSeen.observe(new Object(), 11, 1, false, "map", obj());
        if (!restartedSeen.complete()
                || !restartedSeen.snapshot().equals(java.util.Arrays.asList("Anchor", "Vajra")))
            throw new AssertionError("persisted public relic offers did not restore after restart");
        LiveOocCapture.SeenRelicOffers menuThenSave = new LiveOocCapture.SeenRelicOffers();
        menuThenSave.observe(new Object(), 99, 0, true, "event", obj());
        menuThenSave.observe(new Object(), 11, 1, false, "map", obj());
        if (!menuThenSave.complete()
                || !menuThenSave.snapshot().equals(java.util.Arrays.asList("Anchor", "Vajra")))
            throw new AssertionError("saved offer ledger did not restore after a transient fresh player");
        seen.observe(player, 11, 3, false, "map", obj());
        if (seen.complete()) throw new AssertionError("missed floors retained complete history");
        LiveOocCapture.CombatClassHistory combats = new LiveOocCapture.CombatClassHistory();
        Object group = new Object();
        combats.observe(player, 12345, 1, 3, true, true, group, "FIXED_EVENT", "MUSHROOMS_EVENT");
        combats.observe(player, 12345, 1, 3, true, true, new Object(), "FIXED_EVENT", "MUSHROOMS_EVENT");
        combats.observe(player, 12345, 1, 3, false, false, null, null, "");
        combats.observe(player, 12345, 1, 5, false, true, new Object(), "NORMAL_QUEUE", "JAW_WORM");
        combats.observe(player, 12345, 1, 8, false, true, new Object(), "ELITE_QUEUE", "GREMLIN_NOB");
        if (!combats.completeFor(java.util.Arrays.asList(3, 5, 8))
                || combats.snapshot().size() != 3
                || !"FIXED_EVENT".equals(combats.snapshot().get(0).get("kind")))
            throw new AssertionError("complete combat-class ledger lost fixed-event distinction");
        if (combats.completeFor(java.util.Arrays.asList(3, 5, 9)))
            throw new AssertionError("wrong combat metric floor qualified the ledger");
        LiveOocCapture.CombatClassHistory restored = new LiveOocCapture.CombatClassHistory();
        restored.restoreFor(player, 12345, 1);
        if (!restored.completeFor(java.util.Arrays.asList(3, 5, 8)))
            throw new AssertionError("persisted combat history did not restore");
        restored.observe(player, 12345, 1, 8, false, true, new Object(), "ELITE_QUEUE", "");
        if (!restored.completeFor(java.util.Arrays.asList(3, 5, 8)))
            throw new AssertionError("empty encounter during reward reload invalidated saved combat");
        restored.observe(player, 12345, 1, 8, false, true, new Object(), "ELITE_QUEUE", "GREMLIN_NOB");
        if (restored.snapshot().size() != 3)
            throw new AssertionError("restart during combat duplicated the current floor");
        combats.observe(new Object(), 12345, 1, 9, false, true, new Object(), "NORMAL_QUEUE", "CULTIST");
        if (!combats.completeFor(java.util.Arrays.asList(3, 5, 8, 9)))
            throw new AssertionError("restored mid-act combat history did not remain complete");
        combats.observe(player, 12345, 2, 18, true, true, new Object(), "NORMAL_QUEUE", "CULTIST");
        if (!combats.completeFor(java.util.Arrays.asList(18)))
            throw new AssertionError("new act did not reset complete combat-class history");
        LiveOocCapture.CombatClassHistory sameSeed = new LiveOocCapture.CombatClassHistory();
        sameSeed.resetForFreshRun(player, 12345, 1);
        if (!sameSeed.snapshot().isEmpty() || !sameSeed.completeFor(java.util.Collections.emptyList()))
            throw new AssertionError("fresh run did not clear same-seed history");
        LiveOocCapture.CombatClassHistory staleAct = new LiveOocCapture.CombatClassHistory();
        staleAct.restoreFor(player, 12345, 2);
        if (!staleAct.snapshot().isEmpty() || staleAct.completeFor(java.util.Arrays.asList(18)))
            throw new AssertionError("fresh run retained same-seed Act-2 history");
        if (oldHome == null) System.clearProperty("user.home"); else System.setProperty("user.home", oldHome);
        if (!"RED_SLAVER".equals(STSModelInspector.singleEncounterName("SlaverRed", false))
                || !"RED_SLAVER".equals(STSModelInspector.singleEncounterName("RedSlaver", false))
                || !"BLUE_SLAVER".equals(STSModelInspector.singleEncounterName("SlaverBlue", false))
                || !"BLUE_SLAVER".equals(STSModelInspector.singleEncounterName("BlueSlaver", false)))
            throw new AssertionError("canonical Slaver runtime identity mismatch");
        System.out.println("LiveOocCaptureTest: 15 relic, 7 map edge, 5 screen, 3 path, 4 integrity, 4 event, 3 reward identity, 4 Slaver identity checks passed");
    }
}
