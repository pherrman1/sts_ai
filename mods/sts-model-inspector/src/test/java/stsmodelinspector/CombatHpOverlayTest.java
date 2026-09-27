package stsmodelinspector;

import com.google.gson.*;

/** Silver final-HP display contract: axis, partition, hover aggregation and freshness. */
public final class CombatHpOverlayTest {
    private static JsonObject layer(long... counts) {
        JsonObject value = new JsonObject();
        JsonArray bins = new JsonArray();
        long sum = 0;
        for (long count : counts) { bins.add(new JsonPrimitive(count)); sum += count; }
        value.add("hpCounts", bins);
        value.addProperty("count", sum);
        value.addProperty("deaths", counts[0]);
        value.addProperty("unresolved", 0);
        return value;
    }
    private static JsonObject row(String label, JsonObject liveAction, long visits, JsonObject finalHp) {
        JsonObject row = new JsonObject();
        row.addProperty("label", label);
        row.add("liveAction", liveAction);
        row.addProperty("edgeVisits", visits);
        row.add("finalHp", finalHp);
        return row;
    }
    private static JsonObject card(String uuid, int target) {
        JsonObject action = new JsonObject();
        action.addProperty("kind", "card");
        action.addProperty("cardUuid", uuid);
        if (target > 0) action.addProperty("targetIndex", target);
        return action;
    }
    private static void rejects(JsonObject response, String why) {
        try { CombatHpOverlay.parse(response.toString()); }
        catch (IllegalArgumentException expected) { return; }
        throw new AssertionError(why);
    }
    public static void main(String[] args) {
        // Axis 0..4 HP; index 0 = deaths.
        JsonObject endTurn = new JsonObject();
        endTurn.addProperty("kind", "end_turn");
        JsonArray rows = new JsonArray();
        rows.add(row("Strike -> Monster 1", card("strike", 1), 3, layer(1, 0, 0, 2, 0)));
        rows.add(row("Strike -> Monster 2", card("strike", 2), 2, layer(0, 0, 0, 0, 2)));
        rows.add(row("End Turn", endTurn, 1, layer(0, 1, 0, 0, 0)));
        JsonObject distribution = new JsonObject();
        distribution.addProperty("schema", CombatHpOverlay.SCHEMA);
        distribution.addProperty("currentHp", 4);
        distribution.addProperty("maxHp", 4);
        distribution.addProperty("axisMaxHp", 4);
        distribution.add("root", layer(1, 1, 0, 2, 2));
        JsonObject silver = new JsonObject();
        silver.addProperty("id", "silver_player_decision_v2");
        silver.addProperty("status", "OK");
        silver.add("finalHpDistribution", distribution);
        silver.add("rootActionSummaries", rows);
        JsonObject response = new JsonObject();
        response.addProperty("session", "s");
        response.addProperty("sequence", 7);
        response.addProperty("observationHash", "h");
        // The combat panel no longer depends on the CTM forecast's status.
        response.addProperty("status", "MODEL_UNAVAILABLE");
        JsonArray evaluators = new JsonArray();
        evaluators.add(silver);
        response.add("evaluators", evaluators);

        CombatHpOverlay view = CombatHpOverlay.parse(response.toString());
        if (view == null || view.root.count != 6 || view.root.deaths != 1 || view.axisMaxHp() != 4
                || Math.abs(view.root.meanHp() - (1 + 3 * 2 + 4 * 2) / 6.0) > 1e-12
                || !view.root.deathLabel().equals("16.7%") || !view.root.hpLabel(4).equals("≈3 HP (-2)"))
            throw new AssertionError("root samples or labels lost");
        CombatHpOverlay.Layer anyTarget = view.forCard("strike", -1);
        CombatHpOverlay.Layer second = view.forCard("strike", 2);
        if (anyTarget == null || anyTarget.count != 5 || anyTarget.deaths != 1
                || second == null || second.count != 2 || second.deathShare() != 0 || second.meanHp() != 4
                || view.forCard("strike", 3) != null || view.forCard("bash", -1) != null)
            throw new AssertionError("card hover aggregation or target restriction wrong");
        if (view.forEndTurn() == null || view.forEndTurn().meanHp() != 1)
            throw new AssertionError("end-turn layer lost");
        int[] deaths = view.bucketRange(0, view.buckets());
        int[] last = view.bucketRange(view.buckets(), view.buckets());
        if (view.buckets() != 4 || deaths[0] != 0 || deaths[1] != 0 || last[1] != 4
                || Math.abs(view.maxShare(view.buckets()) - 1.0) > 1e-12)
            throw new AssertionError("axis buckets or shared scale wrong");
        if (!view.matches("s", 7, "h") || view.matches("s", 8, "h"))
            throw new AssertionError("stale samples accepted");

        rows.get(2).getAsJsonObject().add("finalHp", layer(0, 0, 1, 0, 0));
        rejects(response, "non-partitioning root actions displayed");
        rows.get(2).getAsJsonObject().add("finalHp", layer(0, 1, 0, 0));
        rejects(response, "mismatched HP axis displayed");
        rows.get(2).getAsJsonObject().add("finalHp", layer(0, 1, 0, 0, 0));
        distribution.addProperty("schema", "other");
        rejects(response, "unknown semantics displayed");
        distribution.addProperty("schema", CombatHpOverlay.SCHEMA);
        silver.addProperty("status", "UNSUPPORTED");
        if (CombatHpOverlay.parse(response.toString()) != null) throw new AssertionError("unsupported samples shown");
        System.out.println("CombatHpOverlayTest: axis, partition, hover aggregation, labels and freshness checks passed");
    }
}
