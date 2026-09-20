package stsmodelinspector;

import com.google.gson.*;
import java.util.*;

/** Immutable display data from one identity-matched response; never controls the game. */
final class OocOverlay {
    static final class Choice {
        final String key, label, kind;
        final double q;
        final int index;
        final boolean selected;
        final JsonObject action;
        final JsonObject followUp;
        final String followUpUuid;
        Choice(String key, String label, String kind, double q, int index, boolean selected, JsonObject action,
               JsonObject followUp, String followUpUuid) {
            this.key = key; this.label = label; this.kind = kind;
            this.q = q; this.index = index; this.selected = selected; this.action = action;
            this.followUp = followUp; this.followUpUuid = followUpUuid;
        }
    }
    final String session, hash, status, reason, policy, screen;
    final long sequence;
    final List<Choice> choices;
    private OocOverlay(JsonObject response, String status, String reason, String policy,
                       String screen, List<Choice> choices) {
        session = text(response, "session"); hash = text(response, "observationHash");
        sequence = response.get("sequence").getAsLong();
        this.status = status; this.reason = reason; this.policy = policy; this.screen = screen;
        this.choices = Collections.unmodifiableList(choices);
    }
    boolean matches(String session, long sequence, String hash) {
        return this.session.equals(session) && this.sequence == sequence && this.hash.equals(hash);
    }
    Choice forAction(JsonObject action) {
        Choice first = null;
        for (Choice choice : choices) if (choice.action.equals(action)) {
            if (choice.selected) return choice;
            if (first == null) first = choice;
        }
        return first;
    }
    List<Choice> panelChoices() {
        if (!"card_reward".equals(screen) || choices.size() <= 2)
            return choices.subList(0, Math.min(6, choices.size()));
        // Card scores also appear below each physical card. Keep this panel
        // above the reward cards, including four-card Question Card layouts.
        Choice first = choices.get(0), second = choices.get(1);
        for (Choice choice : choices)
            if ("skip".equals(choice.kind) && choice != first) second = choice;
        return Arrays.asList(first, second);
    }
    static OocOverlay parse(String responseJson, String observationJson) {
        JsonObject response = new JsonParser().parse(responseJson).getAsJsonObject();
        JsonObject ooc = new JsonParser().parse(observationJson).getAsJsonObject().getAsJsonObject("ooc");
        String screen = text(ooc, "screen");
        JsonObject evaluator = null;
        if (response.has("evaluators")) for (JsonElement e : response.getAsJsonArray("evaluators")) {
            JsonObject candidate = e.getAsJsonObject();
            if ("live_ooc_decision_v1".equals(text(candidate, "id"))) {
                if (evaluator != null) throw new IllegalArgumentException("duplicate OOC evaluator");
                evaluator = candidate;
            }
        }
        if ("ERROR".equals(text(response, "status")) || evaluator == null)
            return new OocOverlay(response, "ERROR", text(response, "message"), "", screen, new ArrayList<Choice>());
        String status = text(evaluator, "status"), policy = text(evaluator, "policy");
        List<Choice> choices = new ArrayList<>();
        if ("OK".equals(status)) {
            String selected = text(evaluator, "selectedSemanticKey");
            Set<String> keys = new HashSet<>();
            int selectedCount = 0;
            for (JsonElement e : evaluator.getAsJsonArray("candidateSummaries")) {
                JsonObject c = e.getAsJsonObject(), action = c.getAsJsonObject("liveAction");
                String key = text(c, "semanticKey"), kind = text(action, "kind");
                double q = c.get("q").getAsDouble();
                if (!Double.isFinite(q) || key.isEmpty() || !keys.add(key))
                    throw new IllegalArgumentException("invalid OOC ranking");
                boolean best = key.equals(selected);
                if (best) {
                    ++selectedCount;
                    if (!action.equals(evaluator.get("selectedLiveAction")))
                        throw new IllegalArgumentException("selected OOC action mismatch");
                }
                int index = action.has("choiceIndex") ? action.get("choiceIndex").getAsInt() : -1;
                JsonObject preview = c.has("followUpPreview") ? c.getAsJsonObject("followUpPreview") : null;
                String previewUuid = "";
                if (preview != null && "OK".equals(text(preview, "status"))) {
                    if (!"v4_q".equals(text(preview, "policy")) || !"selector_preview".equals(text(preview, "scope"))
                            || !"upgrade".equals(text(preview, "selectorType")) || !Double.isFinite(preview.get("q").getAsDouble()))
                        throw new IllegalArgumentException("invalid next-choice preview");
                    JsonObject target = preview.getAsJsonObject("card");
                    JsonObject card = ooc.getAsJsonObject("publicState").getAsJsonArray("deck")
                            .get(target.get("deckIndex").getAsInt()).getAsJsonObject();
                    for (String field : new String[]{"id", "upgraded", "misc"})
                        if (!Objects.equals(target.get(field), card.get(field)))
                            throw new IllegalArgumentException("preview physical card mismatch");
                    previewUuid = text(card, "uuid");
                    if (previewUuid.isEmpty()) throw new IllegalArgumentException("preview physical card missing");
                }
                choices.add(new Choice(key, label(action, ooc), kind, q, index, best, action, preview, previewUuid));
            }
            if (selectedCount != 1) throw new IllegalArgumentException("missing selected OOC choice");
            choices.sort(Comparator.comparingDouble((Choice c) -> -c.q).thenComparing(c -> c.key));
        }
        return new OocOverlay(response, status, text(evaluator, "reason"), policy, screen, choices);
    }
    private static String label(JsonObject action, JsonObject ooc) {
        String kind = text(action, "kind");
        if (ooc.has("liveChoices")) for (JsonElement e : ooc.getAsJsonArray("liveChoices")) {
            JsonObject c = e.getAsJsonObject();
            boolean match = action.equals(c.get("liveAction"));
            if ("map".equals(kind)) match = Objects.equals(action.get("x"), c.get("x"))
                    && Objects.equals(action.get("y"), c.get("y"));
            if (match && !text(c, "mcpLabel").isEmpty()) return text(c, "mcpLabel");
        }
        if ("choose".equals(kind)) return "Choice " + text(action, "choiceIndex");
        if ("map".equals(kind)) return "Path (" + text(action, "x") + ", " + text(action, "y") + ")";
        return kind.isEmpty() ? "Choice" : Character.toUpperCase(kind.charAt(0)) + kind.substring(1).replace('_', ' ');
    }
    private static String text(JsonObject object, String field) {
        JsonElement e = object == null ? null : object.get(field);
        return e == null || e.isJsonNull() ? "" : e.getAsString();
    }
}
