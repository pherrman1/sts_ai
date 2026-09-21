package stsmodelinspector;

import com.google.gson.*;

public final class PotionOverlayTest {
    public static void main(String[] args) {
        JsonObject response = new JsonParser().parse("{\"session\":\"s\",\"sequence\":7,"
                + "\"observationHash\":\"h\",\"status\":\"OK\",\"evaluators\":[{"
                + "\"id\":\"silver_player_decision_v2\",\"status\":\"OK\","
                + "\"selectedLiveAction\":{\"kind\":\"potion\",\"potionSlot\":2,\"discard\":false,\"targetIndex\":2},"
                + "\"rootActionSummaries\":["
                + "{\"liveAction\":{\"kind\":\"end_turn\"}},"
                + "{\"liveAction\":{\"kind\":\"potion\",\"potionSlot\":2,\"discard\":false,\"targetIndex\":2},\"selectionQValid\":true,\"selectionQ\":3.5},"
                + "{\"liveAction\":{\"kind\":\"potion\",\"potionSlot\":2,\"discard\":true},\"selectionQValid\":true,\"selectionQ\":1.5},"
                + "{\"liveAction\":{\"kind\":\"potion\",\"potionSlot\":2,\"discard\":false,\"targetIndex\":1},\"selectionQValid\":false},"
                + "{\"liveAction\":null}]}]}").getAsJsonObject();
        PotionOverlay view = PotionOverlay.parse(response.toString());
        if (view.entries.size() != 3 || view.forSlot(1, false).size() != 0
                || view.forSlot(2, false).size() != 2 || view.forSlot(2, true).size() != 1)
            throw new AssertionError("physical slot or use/discard conflated");
        PotionOverlay.Entry best = view.forSlot(2, false).get(0);
        if (!best.selected || best.rank != 2 || best.target != 2 || best.q != 3.5
                || !best.text("Cultist").contains("→ Cultist")) throw new AssertionError("target/rank/selection lost");
        if (view.forSlot(2, false).get(1).q != null || view.forSlot(2, true).get(0).target != -1)
            throw new AssertionError("invented Q or discard target");
        if (!view.matches("s", 7, "h") || view.matches("s", 8, "h")
                || view.matches("other", 7, "h") || view.matches("s", 7, "other"))
            throw new AssertionError("stale potion ranking accepted");
        JsonObject evaluator = response.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        evaluator.addProperty("status", "UNSUPPORTED");
        if (!PotionOverlay.parse(response.toString()).entries.isEmpty()) throw new AssertionError("unsupported ranking shown");
        evaluator.addProperty("status", "OK"); response.addProperty("status", "ERROR");
        if (!PotionOverlay.parse(response.toString()).entries.isEmpty()) throw new AssertionError("error ranking shown");
        response.addProperty("status", "OK");
        evaluator.getAsJsonArray("rootActionSummaries").get(1).getAsJsonObject().addProperty("selectionQ", "NaN");
        boolean rejected = false;
        try { PotionOverlay.parse(response.toString()); } catch (IllegalArgumentException expected) { rejected = true; }
        if (!rejected) throw new AssertionError("nonfinite potion Q shown");
        System.out.println("PotionOverlayTest: slot, operation, target, rank, freshness, unsupported/error and nonfinite checks passed");
    }
}
