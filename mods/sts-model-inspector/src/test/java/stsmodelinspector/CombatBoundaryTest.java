package stsmodelinspector;

import com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon.CurrentScreen;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

/** Pure boundary and selection projection checks, without game/render initialization. */
public final class CombatBoundaryTest {
    public static void main(String[] args) {
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
