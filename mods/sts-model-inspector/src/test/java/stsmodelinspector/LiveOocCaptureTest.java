package stsmodelinspector;

import java.util.HashMap;
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
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"),
                "unsupportedReason", "EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE");
        LiveOocCapture.finalizeSupportReason(phaseUnsupported);
        if (!"EVENT_PHASE_UNREPRESENTABLE:Beggar:LEAVE".equals(phaseUnsupported.get("unsupportedReason")))
            throw new AssertionError("relic warning hid the unsupported event outro phase");
        Map<String,Object> missingPath = obj("publicState", obj("pathComplete", false,
                "unsupportedReason", "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"));
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
        if (!LiveOocCapture.simpleInitialEventSupported("WomanInBlue")
                || LiveOocCapture.simpleInitialEventSupported("WomanInBlueDialogue")
                || LiveOocCapture.simpleInitialEventSupported("ShiningLight")
                || LiveOocCapture.simpleInitialEventSupported("Ghosts")
                || LiveOocCapture.simpleInitialEventSupported("WindingHalls")
                || LiveOocCapture.simpleInitialEventSupported("WorldOfGoop"))
            throw new AssertionError("Woman in Blue initial-phase support boundary mismatch");
        Object firstReward = new Object(), secondReward = new Object();
        String firstIdentity = LiveOocCapture.rewardIdentity(firstReward, null, null);
        if (!firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, null, null))
                || firstIdentity.equals(LiveOocCapture.rewardIdentity(secondReward, null, null)))
            throw new AssertionError("physical reward identity is unstable or ambiguous");
        if (firstIdentity.equals(LiveOocCapture.rewardIdentity(firstReward, new Object(), null)))
            throw new AssertionError("reward identity reused after run boundary");
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
        seen.observe(player, 11, 3, false, "map", obj());
        if (seen.complete()) throw new AssertionError("missed floors retained complete history");
        LiveOocCapture.CombatClassHistory combats = new LiveOocCapture.CombatClassHistory();
        String oldHome = System.getProperty("user.home");
        java.nio.file.Path home = java.nio.file.Files.createTempDirectory("live-ooc-history");
        System.setProperty("user.home", home.toString());
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
