package stsmodelinspector;

import com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon.CurrentScreen;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

/** Pure boundary and selection projection checks, without game/render initialization. */
public final class CombatBoundaryTest {
    public static void main(String[] args) {
        java.util.Map<String, Integer> chosenByrd = new java.util.HashMap<>();
        chosenByrd.put("Chosen", 1);
        chosenByrd.put("Byrd", 1);
        if (!"CHOSEN_AND_BYRDS".equals(STSModelInspector.multiEncounterName(chosenByrd, false)))
            throw new AssertionError("live Chosen plus one Byrd lost its canonical encounter");
        chosenByrd.put("Byrd", 2);
        if ("CHOSEN_AND_BYRDS".equals(STSModelInspector.multiEncounterName(chosenByrd, false)))
            throw new AssertionError("unsupported two-Byrd shape was accepted as canonical");
        if (!"BOSS_TREASURE".equals(STSModelInspector.firstRoomAfterBossTreasure("", 3, 35, 0))
                || !"BOSS_TREASURE".equals(STSModelInspector.firstRoomAfterBossTreasure("", 2, 18, 0))
                || !"".equals(STSModelInspector.firstRoomAfterBossTreasure("", 3, 36, 1))
                || !"REST".equals(STSModelInspector.firstRoomAfterBossTreasure("REST", 3, 35, 0)))
            throw new AssertionError("first new-act combat previous room was guessed outside its boundary");
        STSModelInspector.HiddenIntentSnapshot chained = new STSModelInspector.HiddenIntentSnapshot();
        STSModelInspector.recordHiddenMoveHistory(chained, java.util.Arrays.asList((byte)41));
        STSModelInspector.recordHiddenMoveHistory(chained,
                java.util.Arrays.asList((byte)0, (byte)42));
        STSModelInspector.HiddenIntentSnapshot first = new STSModelInspector.HiddenIntentSnapshot();
        first.curHp = 97;
        first.monsterTurnNumber = 1;
        first = STSModelInspector.appendHiddenIntentRoll(null, first,
                java.util.Arrays.asList((byte)41));
        STSModelInspector.HiddenIntentSnapshot second = new STSModelInspector.HiddenIntentSnapshot();
        second.curHp = 62;
        second.monsterTurnNumber = 4;
        second = STSModelInspector.appendHiddenIntentRoll(first, second,
                java.util.Arrays.asList((byte)0, (byte)42));
        if (second.pendingMoveRolls != 2 || second.publicMoveHistoryCount != 1
                || second.publicMoveHistory[0] != 41
                || second.pendingRollInputHistory.size() != 2
                || second.pendingRollInputHistory.get(0).curHp != 97
                || second.pendingRollInputHistory.get(1).curHp != 62
                || second.pendingRollInputHistory.get(0).monsterTurnNumber != 1
                || second.pendingRollInputHistory.get(1).monsterTurnNumber != 4)
            throw new AssertionError("cross-turn Runic rolls lost distinct public inputs");
        if (chained.pendingMoveRolls != 2 || chained.publicMoveHistoryCount != 1
                || chained.publicMoveHistory[0] != 41)
            throw new AssertionError("chained hidden roll replaced its public pre-roll history");
        STSModelInspector.HiddenIntentSnapshot byteZero = new STSModelInspector.HiddenIntentSnapshot();
        STSModelInspector.recordHiddenMoveHistory(byteZero, java.util.Arrays.asList((byte)0));
        if (byteZero.pendingMoveRolls != 1 || byteZero.publicMoveHistoryCount != 1
                || byteZero.publicMoveHistory[0] != 0)
            throw new AssertionError("public move byte zero was confused with absent history");
        for (String id : new String[]{"FuzzyLouseNormal", "FuzzyLouseDefensive", "Darkling"})
            if (!STSModelInspector.runicPrivateMiscInfo(id))
                throw new AssertionError("Runic private randomized miscInfo was not rejected: " + id);
        if (STSModelInspector.runicPrivateMiscInfo("Donu"))
            throw new AssertionError("public Runic miscInfo was rejected");
        if (!STSModelInspector.nativeMiscZeroForId("GremlinWarrior")
                || !STSModelInspector.nativeMiscZeroForId("GremlinLeader")
                || STSModelInspector.nativeMiscZeroForId("GremlinWizard"))
            throw new AssertionError("Gremlin Leader summons lost their native miscInfo contract");
        java.util.Set<Integer> deadSlots = new java.util.HashSet<>(java.util.Arrays.asList(2));
        java.util.Set<Integer> liveSlots = new java.util.HashSet<>(java.util.Arrays.asList(1));
        if (STSModelInspector.gremlinReplacementSlot(deadSlots, liveSlots) != 2
                || STSModelInspector.gremlinReplacementSlot(
                        new java.util.HashSet<>(java.util.Arrays.asList(1, 2)),
                        new java.util.HashSet<Integer>()) != -1
                || STSModelInspector.gremlinReplacementSlot(
                        new java.util.HashSet<Integer>(), liveSlots) != -1)
            throw new AssertionError("summoned Gremlin Leader minion took an ambiguous or leader slot");
        java.util.Map<Integer,java.util.List<Integer>> deadOccupants = new java.util.HashMap<>();
        deadOccupants.put(1, java.util.Arrays.asList(1, 4));
        deadOccupants.put(2, java.util.Arrays.asList(2));
        java.util.Map<Integer,Integer> latestDead = STSModelInspector.latestDeadOrdinalBySlot(
                deadOccupants, new java.util.HashSet<>(java.util.Arrays.asList(2)));
        if (latestDead.size() != 1 || latestDead.get(1) != 4)
            throw new AssertionError("older dead Gremlin Leader slot occupant was retained");
        if (STSModelInspector.hiddenMiscMinimum("FuzzyLouseNormal", 0) != 5
                || STSModelInspector.hiddenMiscMinimum("FuzzyLouseDefensive", 20) != 6
                || STSModelInspector.hiddenMiscMinimum("Darkling", 20) != 11
                || STSModelInspector.hiddenMiscCount("Darkling") != 5
                || STSModelInspector.compatiblePrivateMiscMask(7, new int[]{5, 6, 7}, 6) != 2
                || STSModelInspector.compatiblePrivateMiscMask(2, new int[]{5, 6, 7}, 7) != 0)
            throw new AssertionError("Runic public damage posterior support is incorrect");
        if (STSModelInspector.guardianThresholdFromPublicPower(null, null) != null
                || STSModelInspector.guardianThresholdFromPublicPower(null, 30) != 30
                || STSModelInspector.guardianThresholdFromPublicPower(30, 12) != 30
                || STSModelInspector.guardianThresholdFromPublicPower(30, null) != 30
                || STSModelInspector.guardianThresholdFromPublicPower(30, 40) != 40)
            throw new AssertionError("Guardian public Mode Shift threshold history was lost");
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.HAND_SELECT, false, true)
                || !STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.GRID, false, true)
                || !STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.CARD_REWARD, false, true))
            throw new AssertionError("unknown selection must retain combat classification");
        // Event fights use this same phase-based gate; no room subclass is required.
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, true, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.EVENT, CurrentScreen.NONE, true, false))
            throw new AssertionError("event combat phase gate");
        if (STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.CARD_REWARD, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.GRID, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMPLETE, CurrentScreen.HAND_SELECT, false, true))
            throw new AssertionError("transitional or OOC modal misclassified");
        for (boolean canPickZero : new boolean[]{false, true}) {
            JsonObject selection = new Gson().fromJson(
                    STSModelInspector.selectionJson("", canPickZero, true, 99, null), JsonObject.class);
            if (!selection.get("task").getAsString().isEmpty()
                    || selection.get("canPickZero").getAsBoolean() != canPickZero
                    || !selection.get("canPickAnyNumber").getAsBoolean()
                    || selection.get("pickCount").getAsInt() != 99)
                throw new AssertionError("unknown selector or canPickZero lost");
        }
        JsonObject discovery = new Gson().fromJson(
                STSModelInspector.selectionJson("DISCOVERY", false, false, 1, 2, null), JsonObject.class);
        if (!"DISCOVERY".equals(discovery.get("task").getAsString())
                || discovery.get("data0").getAsInt() != 2
                || discovery.get("pickCount").getAsInt() != 1)
            throw new AssertionError("Discovery copy count was not preserved");
        JsonObject potionDiscovery = new Gson().fromJson(
                STSModelInspector.selectionJson("DISCOVERY", true, false, 1, 1, null), JsonObject.class);
        if (!STSModelInspector.qualifiedDiscoverySelection(true, true, 1, 3)
                || !STSModelInspector.qualifiedDiscoverySelection(true, false, 2, 3)
                || STSModelInspector.qualifiedDiscoverySelection(true, null, 1, 3)
                || STSModelInspector.qualifiedDiscoverySelection(true, true, 1, 2)
                || !potionDiscovery.get("canPickZero").getAsBoolean())
            throw new AssertionError("optional potion Discovery was not distinguished from mandatory Discovery");
        if (!STSModelInspector.zeroCostDiscardReturn(true, true, 0)
                || STSModelInspector.zeroCostDiscardReturn(true, false, 0)
                || STSModelInspector.zeroCostDiscardReturn(true, true, 1)
                || STSModelInspector.zeroCostDiscardReturn(false, true, 0))
            throw new AssertionError("Liquid Memories selector was confused with Hologram");
        for (String child : new String[]{"SpikeSlime_L", "AcidSlime_L", "SpikeSlime_M", "AcidSlime_M"})
            if (!STSModelInspector.slimeBossDescendant(child))
                throw new AssertionError("Slime Boss split child was not recognized: " + child);
        if (STSModelInspector.slimeBossDescendant("SlimeBoss")
                || STSModelInspector.slimeBossDescendant("SpikeSlime_S"))
            throw new AssertionError("unrelated slime replaced Slime Boss parent");
        for (int counter : new int[]{0, 1, 2, 3, -1, -2}) {
            if (STSModelInspector.combatEntryRelicData("NeowsBlessing", counter, false) != counter)
                throw new AssertionError("active/invalid Neow counter changed");
        }
        if (STSModelInspector.combatEntryRelicData("NeowsBlessing", -2, true) != 0
                || STSModelInspector.combatEntryRelicData("NeowsBlessing", -1, true) != -1
                || STSModelInspector.combatEntryRelicData("Omamori", -2, true) != -2)
            throw new AssertionError("spent Neow mapping is not exact and relic-specific");
        String forecast = STSModelInspector.ctmResponseJson(
                "{\"evaluators\":[{\"id\":\"silver_player_decision_v2\",\"status\":\"UNSUPPORTED\"},"
                + "{\"id\":\"ctm_combat_entry_v2\",\"status\":\"OK\",\"deathProbability\":0.2}]}");
        JsonObject ctm = new Gson().fromJson(forecast, JsonObject.class);
        if (!"OK".equals(ctm.get("status").getAsString()) || ctm.get("deathProbability").getAsDouble() != 0.2
                || !STSModelInspector.ctmResponseJson("{\"evaluators\":[]}").isEmpty())
            throw new AssertionError("another evaluator contaminated CTM forecast status");
        // A render previously found bucket 72, then read a shorter volatile
        // array after the advisor published its next forecast and crashed.
        double[] wide = new double[73];
        wide[72] = 1.0;
        STSModelInspector.HistogramSnapshot previous =
                new STSModelInspector.HistogramSnapshot(1, wide);
        STSModelInspector.HistogramSnapshot replacement =
                new STSModelInspector.HistogramSnapshot(20, new double[0]);
        STSModelInspector.HistogramSnapshot[] published = {previous};
        for (int i = 0; i < 1000; ++i) {
            STSModelInspector.HistogramSnapshot captured = published[0];
            published[0] = (i & 1) == 0 ? replacement : previous;
            int[] range = STSModelInspector.histogramNonzeroRange(captured);
            if (range[1] >= captured.values.length
                    || (captured == previous && (range[0] != 72 || range[1] != 72
                        || captured.min + range[1] != 73))
                    || (captured == replacement && (range[0] != -1 || range[1] != -1)))
                throw new AssertionError("histogram publication changed a captured render range");
        }
        System.out.println("CombatBoundaryTest: 8 boundary, 2 selection, 9 entry-relic, 2 CTM isolation and histogram snapshot checks passed");
    }
}
