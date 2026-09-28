package stsmodelinspector;

import com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon.CurrentScreen;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

/** Pure boundary and selection projection checks, without game/render initialization. */
public final class CombatBoundaryTest {
    public static void main(String[] args) {
        for (int initial : new int[]{30, 35, 40}) {
            for (int cycle = 0; cycle < 3; ++cycle) {
                int threshold = initial + 10 * cycle;
                if (STSModelInspector.guardianNativeThreshold(threshold, 10, true) != threshold
                        || STSModelInspector.guardianNativeThreshold(threshold + 10, 10, false) != threshold)
                    throw new AssertionError("Guardian threshold/cycle projection");
            }
        }
        if (STSModelInspector.guardianNativeThreshold(null, 10, true) != null
                || STSModelInspector.guardianNativeThreshold(30, null, true) != null
                || STSModelInspector.guardianNativeThreshold(30, 10, null) != null
                || STSModelInspector.guardianNativeThreshold(30, 11, true) != null
                || STSModelInspector.guardianNativeThreshold(10, 10, false) != null)
            throw new AssertionError("Guardian missing or invalid fields accepted");
        try {
            Class<?> guardian = Class.forName("com.megacrit.cardcrawl.monsters.exordium.TheGuardian", false,
                    CombatBoundaryTest.class.getClassLoader());
            if (guardian.getDeclaredField("dmgThreshold").getType() != int.class
                    || guardian.getDeclaredField("dmgThresholdIncrease").getType() != int.class
                    || guardian.getDeclaredField("isOpen").getType() != boolean.class)
                throw new AssertionError("Guardian JAR field types changed");
        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.HAND_SELECT, false, true)
                || !STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.GRID, false, true))
            throw new AssertionError("unknown selection must retain combat classification");
        // Event fights use this same phase-based gate; no room subclass is required.
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, true, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.EVENT, CurrentScreen.NONE, true, false))
            throw new AssertionError("event combat phase gate");
        if (STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.CARD_REWARD, false, true)
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
        for (int counter : new int[]{0, 1, 2, 3, -1, -2}) {
            if (STSModelInspector.combatEntryRelicData("NeowsBlessing", counter, false) != counter)
                throw new AssertionError("active/invalid Neow counter changed");
        }
        if (STSModelInspector.combatEntryRelicData("NeowsBlessing", -2, true) != 0
                || STSModelInspector.combatEntryRelicData("NeowsBlessing", -1, true) != -1
                || STSModelInspector.combatEntryRelicData("Omamori", -2, true) != 0
                || STSModelInspector.combatEntryRelicData("Omamori", 2, false) != 2
                || STSModelInspector.combatEntryRelicData("Omamori", -2, false) != -2
                || STSModelInspector.combatEntryRelicData("Pen Nib", -2, true) != -2)
            throw new AssertionError("spent charge mapping is not exact and relic-specific");
        String forecast = STSModelInspector.ctmResponseJson(
                "{\"evaluators\":[{\"id\":\"silver_player_decision_v2\",\"status\":\"UNSUPPORTED\"},"
                + "{\"id\":\"ctm_combat_entry_v2\",\"status\":\"OK\",\"deathProbability\":0.2}]}");
        JsonObject ctm = new Gson().fromJson(forecast, JsonObject.class);
        if (!"OK".equals(ctm.get("status").getAsString()) || ctm.get("deathProbability").getAsDouble() != 0.2
                || !STSModelInspector.ctmResponseJson("{\"evaluators\":[]}").isEmpty())
            throw new AssertionError("another evaluator contaminated CTM forecast status");
        System.out.println("CombatBoundaryTest: 8 boundary, 2 selection and 9 entry-relic and 2 CTM isolation checks passed");
    }
}
