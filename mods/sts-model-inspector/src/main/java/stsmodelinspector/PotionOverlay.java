package stsmodelinspector;

import com.google.gson.*;
import java.util.*;

/** Typed potion rankings; slot, operation and target are never inferred from labels. */
final class PotionOverlay {
    static final class Entry {
        final int slot, target, rank;
        final long visits;   // root edge visits, -1 when not reported
        final boolean discard, selected;
        final Double q;
        Entry(JsonObject action, int rank, boolean selected, Double q, long visits) {
            slot = action.get("potionSlot").getAsInt();
            discard = action.get("discard").getAsBoolean();
            target = action.has("targetIndex") ? action.get("targetIndex").getAsInt() : -1;
            if (slot < 1 || (action.has("targetIndex") && (target < 1 || discard)))
                throw new IllegalArgumentException("invalid physical potion action");
            this.rank = rank; this.selected = selected; this.q = q; this.visits = visits;
        }
        /** Compact badge under the potion icon: operation, rank and visits. */
        String badge() {
            return (discard ? "Discard " : "") + "#" + rank + (visits >= 0 ? " · " + visits + "v" : "");
        }
    }
    final String session, hash;
    final long sequence;
    final List<Entry> entries;
    private PotionOverlay(JsonObject response, List<Entry> entries) {
        session = response.get("session").getAsString(); hash = response.get("observationHash").getAsString();
        sequence = response.get("sequence").getAsLong(); this.entries = Collections.unmodifiableList(entries);
    }
    boolean matches(String session, long sequence, String hash) {
        return this.session.equals(session) && this.sequence == sequence && this.hash.equals(hash);
    }
    /** The best-ranked use or discard action of this physical slot, or null. */
    Entry best(int slot) {
        Entry best = null;
        for (Entry entry : entries) if (entry.slot == slot && (best == null || entry.rank < best.rank)) best = entry;
        return best;
    }
    List<Entry> forSlot(int slot, boolean discard) {
        List<Entry> result = new ArrayList<>();
        for (Entry entry : entries) if (entry.slot == slot && entry.discard == discard) result.add(entry);
        return result;
    }
    static PotionOverlay parse(String json) {
        JsonObject response = new JsonParser().parse(json).getAsJsonObject();
        List<Entry> entries = new ArrayList<>();
        if (!"OK".equals(response.get("status").getAsString())) return new PotionOverlay(response, entries);
        for (JsonElement evaluatorElement : response.getAsJsonArray("evaluators")) {
            JsonObject evaluator = evaluatorElement.getAsJsonObject();
            if (!"silver_player_decision_v2".equals(evaluator.get("id").getAsString())
                    || !"OK".equals(evaluator.get("status").getAsString())) continue;
            int rank = 0;
            for (JsonElement element : evaluator.getAsJsonArray("rootActionSummaries")) {
                ++rank;
                JsonObject row = element.getAsJsonObject();
                JsonElement binding = row.get("liveAction");
                if (binding == null || !binding.isJsonObject()) continue;
                JsonObject action = binding.getAsJsonObject();
                if (!"potion".equals(action.get("kind").getAsString())) continue;
                Double q = row.has("selectionQValid") && row.get("selectionQValid").getAsBoolean()
                        ? row.get("selectionQ").getAsDouble() : null;
                if (q != null && !Double.isFinite(q)) throw new IllegalArgumentException("invalid potion score");
                long visits = row.has("edgeVisits") ? row.get("edgeVisits").getAsLong() : -1;
                entries.add(new Entry(action, rank, action.equals(evaluator.get("selectedLiveAction")), q, visits));
            }
        }
        return new PotionOverlay(response, entries);
    }
}
