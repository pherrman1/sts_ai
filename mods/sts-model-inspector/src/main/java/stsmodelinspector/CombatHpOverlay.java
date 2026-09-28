package stsmodelinspector;

import com.google.gson.*;
import java.util.*;

/**
 * Silver's end-of-combat HP samples at the current root, from one
 * identity-matched response. Display data only; never controls the game.
 */
final class CombatHpOverlay {
    static final String SCHEMA = "silver_final_hp_distribution_v1";

    /** Samples of one set of simulations; index 0 of the counts holds deaths. */
    static final class Layer {
        private final long[] counts;
        final long count, deaths, unresolved;
        Layer(JsonObject value, int bins) {
            JsonArray input = value.getAsJsonArray("hpCounts");
            if (input == null || input.size() != bins) throw new IllegalArgumentException("wrong HP axis");
            counts = new long[bins];
            long sum = 0;
            for (int i = 0; i < bins; ++i) {
                counts[i] = exactCount(input.get(i));
                sum = Math.addExact(sum, counts[i]);
            }
            count = exactCount(value.get("count"));
            deaths = exactCount(value.get("deaths"));
            unresolved = exactCount(value.get("unresolved"));
            if (sum != count || counts[0] != deaths) throw new IllegalArgumentException("inconsistent HP samples");
        }
        private Layer(long[] counts, long deaths, long unresolved) {
            this.counts = counts; this.deaths = deaths; this.unresolved = unresolved;
            long sum = 0;
            for (long value : counts) sum += value;
            count = sum;
        }
        int axisMaxHp() { return counts.length - 1; }
        long[] counts() { return counts.clone(); }
        /** Share of this layer's resolved samples with final HP in [fromHp, toHp]. */
        double share(int fromHp, int toHp) {
            if (count == 0) return 0;
            long sum = 0;
            for (int hp = Math.max(0, fromHp); hp <= Math.min(axisMaxHp(), toHp); ++hp) sum += counts[hp];
            return (double) sum / count;
        }
        double deathShare() { return count == 0 ? 0 : (double) deaths / count; }
        /** Mean final HP with deaths counted as 0, or NaN without samples. */
        double meanHp() {
            if (count == 0) return Double.NaN;
            double sum = 0;
            for (int hp = 1; hp < counts.length; ++hp) sum += (double) hp * counts[hp];
            return sum / count;
        }
        String hpLabel(int currentHp) {
            if (count == 0) return "no samples";
            double mean = meanHp();
            return String.format(Locale.ROOT, "≈%.0f HP (%+.0f)", mean, mean - currentHp);
        }
        String deathLabel() {
            return count == 0 ? "—" : String.format(Locale.ROOT, "%.1f%%", 100.0 * deathShare());
        }
        static Layer sum(List<Layer> layers, int bins) {
            long[] counts = new long[bins];
            long deaths = 0, unresolved = 0;
            for (Layer layer : layers) {
                for (int i = 0; i < bins; ++i) counts[i] += layer.counts[i];
                deaths += layer.deaths;
                unresolved += layer.unresolved;
            }
            return new Layer(counts, deaths, unresolved);
        }
    }

    /** One searched root action, bound to its physical live action. */
    static final class Action {
        final String label;
        final JsonObject liveAction;
        final long visits;
        final Layer layer;
        Action(String label, JsonObject liveAction, long visits, Layer layer) {
            this.label = label; this.liveAction = liveAction; this.visits = visits; this.layer = layer;
        }
        String kind() { return liveAction == null ? "" : text(liveAction, "kind"); }
        int targetIndex() {
            return liveAction != null && liveAction.has("targetIndex") ? liveAction.get("targetIndex").getAsInt() : -1;
        }
    }

    final String session, hash;
    final long sequence;
    final int currentHp, maxHp;
    final Layer root;
    final List<Action> actions;
    private final int bins;

    private CombatHpOverlay(JsonObject response, JsonObject distribution, Layer root, List<Action> actions,
                            int bins) {
        session = text(response, "session"); hash = text(response, "observationHash");
        sequence = response.get("sequence").getAsLong();
        currentHp = distribution.get("currentHp").getAsInt();
        maxHp = distribution.get("maxHp").getAsInt();
        this.root = root; this.actions = Collections.unmodifiableList(actions); this.bins = bins;
    }

    boolean matches(String session, long sequence, String hash) {
        return this.session.equals(session) && this.sequence == sequence && this.hash.equals(hash);
    }

    int axisMaxHp() { return bins - 1; }

    /**
     * Samples of every searched play of the card with this UUID. A positive
     * target restricts them to that monster (1-based live index); otherwise
     * every target is included. Null when Silver searched no such play.
     */
    Layer forCard(String uuid, int targetIndex) {
        List<Layer> matched = new ArrayList<>();
        for (Action action : actions) {
            if (!"card".equals(action.kind()) || !uuid.equals(text(action.liveAction, "cardUuid"))) continue;
            if (targetIndex > 0 && action.targetIndex() != targetIndex) continue;
            matched.add(action.layer);
        }
        return matched.isEmpty() ? null : Layer.sum(matched, bins);
    }

    /**
     * Samples of every searched use (or discard) of the potion in this 1-based
     * slot; a positive target restricts uses to that monster. Null when absent.
     */
    Layer forPotion(int slot, boolean discard, int targetIndex) {
        List<Layer> matched = new ArrayList<>();
        for (Action action : actions) {
            if (!"potion".equals(action.kind()) || action.liveAction.get("potionSlot").getAsInt() != slot
                    || action.liveAction.get("discard").getAsBoolean() != discard) continue;
            if (!discard && targetIndex > 0 && action.targetIndex() != targetIndex) continue;
            matched.add(action.layer);
        }
        return matched.isEmpty() ? null : Layer.sum(matched, bins);
    }

    Layer forEndTurn() {
        for (Action action : actions) if ("end_turn".equals(action.kind())) return action.layer;
        return null;
    }

    /** The shared HP axis over the root and every action layer. */
    HpAxis axis() {
        List<Layer> layers = new ArrayList<>();
        layers.add(root);
        for (Action action : actions) layers.add(action.layer);
        return new HpAxis(currentHp, maxHp, axisMaxHp(), layers);
    }

    /** Null when the response carries no OK Silver evaluator with final-HP samples. */
    static CombatHpOverlay parse(String json) {
        JsonObject response = new JsonParser().parse(json).getAsJsonObject();
        JsonArray evaluators = response.getAsJsonArray("evaluators");
        if (evaluators == null) return null;
        for (JsonElement element : evaluators) {
            JsonObject evaluator = element.getAsJsonObject();
            if (!"silver_player_decision_v2".equals(text(evaluator, "id"))
                    || !"OK".equals(text(evaluator, "status"))) continue;
            JsonElement value = evaluator.get("finalHpDistribution");
            if (value == null || !value.isJsonObject()) return null;
            JsonObject distribution = value.getAsJsonObject();
            if (!SCHEMA.equals(text(distribution, "schema")))
                throw new IllegalArgumentException("unknown final-HP distribution semantics");
            int axis = distribution.get("axisMaxHp").getAsInt();
            int maxHp = distribution.get("maxHp").getAsInt();
            int currentHp = distribution.get("currentHp").getAsInt();
            if (axis < 1 || axis < maxHp || currentHp < 0 || currentHp > axis)
                throw new IllegalArgumentException("invalid final-HP axis");
            int bins = axis + 1;
            Layer root = new Layer(distribution.getAsJsonObject("root"), bins);
            List<Action> actions = new ArrayList<>();
            long count = 0, deaths = 0, unresolved = 0;
            long[] columns = new long[bins];
            for (JsonElement rowElement : evaluator.getAsJsonArray("rootActionSummaries")) {
                JsonObject row = rowElement.getAsJsonObject();
                Layer layer = new Layer(row.getAsJsonObject("finalHp"), bins);
                count += layer.count; deaths += layer.deaths; unresolved += layer.unresolved;
                for (int i = 0; i < bins; ++i) columns[i] += layer.counts[i];
                JsonElement binding = row.get("liveAction");
                actions.add(new Action(text(row, "label"),
                        binding != null && binding.isJsonObject() ? binding.getAsJsonObject() : null,
                        row.get("edgeVisits").getAsLong(), layer));
            }
            if (count != root.count || deaths != root.deaths || unresolved != root.unresolved
                    || !Arrays.equals(columns, root.counts))
                throw new IllegalArgumentException("root actions do not partition the HP samples");
            return new CombatHpOverlay(response, distribution, root, actions, bins);
        }
        return null;
    }

    private static long exactCount(JsonElement value) {
        if (value == null || !value.isJsonPrimitive()) throw new IllegalArgumentException("missing count");
        long count = value.getAsLong();
        if (count < 0 || value.getAsDouble() != count) throw new IllegalArgumentException("invalid count");
        return count;
    }

    private static String text(JsonObject object, String key) {
        JsonElement value = object.get(key);
        return value == null || value.isJsonNull() ? "" : value.getAsString();
    }
}
