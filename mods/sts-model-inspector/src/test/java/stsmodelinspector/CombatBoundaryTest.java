package stsmodelinspector;

import com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon.CurrentScreen;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

/** Pure boundary and selection projection checks, without game/render initialization. */
public final class CombatBoundaryTest {
    public static void main(String[] args) {
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
        System.out.println("CombatBoundaryTest: 8 boundary, 2 selection and 12 entry-relic checks passed");
    }
}
