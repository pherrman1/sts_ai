package stsmodelinspector;

import java.util.List;

/** Pure projection of committed vanilla card plays; does not predict future cards or targets. */
final class PendingCardQueueCapture {
    static final int CAPACITY = 10; // native CardQueue::capacity

    static final class Item {
        Object identity;
        String cardJson;
        String uuid;
        String cardId;
        boolean inHand;
        boolean vanillaEndTurnCard;
        Integer target;
        boolean hasMonster;
        boolean requiresTarget;
        boolean vanilla = true;
        boolean endTurnAutoPlay;
        int energyOnUse;
        boolean triggerOnUse = true;
        boolean ignoreEnergyTotal;
        boolean freeToPlay;
        boolean randomTarget;
        boolean autoplay;
        boolean purgeOnUse;
        boolean exhaustOnUse;
    }

    static final class Result {
        final String json;
        final String error;
        Result(String json, String error) { this.json = json; this.error = error; }
    }

    static Result capture(List<Item> items, Object processedItem) {
        return capture(items,processedItem,false,false);
    }

    static Result capture(List<Item> items, Object processedItem, boolean codexEndTurn, boolean unceasingTop) {
        if (items == null) return new Result(null, "queue_unavailable");
        if (items.size() > CAPACITY) return new Result(null, "queue_capacity");
        if(codexEndTurn && !items.isEmpty() && unceasingTop)
            return new Result(null,"end_turn_card_continuation");
        java.util.Set<String> endTurnCards = new java.util.HashSet<>();
        StringBuilder out = new StringBuilder("[");
        java.util.Set<Object> seen = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<Object,Boolean>());
        for (Item item : items) {
            if (item == null || item.identity == null || !item.vanilla) return new Result(null, "unknown_queue_item");
            // getNextAction removes the processed object before running the
            // actions that open a selector. Never drop a same-UUID copy.
            if (item.identity == processedItem || !seen.add(item.identity))
                return new Result(null, "queue_not_settled");
            boolean endTurn = item.cardJson == null;
            if (!endTurn && (item.uuid == null || item.uuid.isEmpty() || "null".equals(item.uuid)))
                return new Result(null, "card_identity");
            // This flag is Java's Unceasing Top hook, NOT a null-card marker.
            // Only an observed Codex end-turn owns this bounded status queue.
            if(codexEndTurn) {
                if(endTurn || item.triggerOnUse || !item.endTurnAutoPlay || !item.inHand
                        || !item.vanillaEndTurnCard || !("Burn".equals(item.cardId) || "Decay".equals(item.cardId))
                        || item.hasMonster || item.requiresTarget || item.target!=null || item.ignoreEnergyTotal
                        || item.freeToPlay || item.randomTarget || item.autoplay || item.purgeOnUse || item.exhaustOnUse
                        || !endTurnCards.add(item.uuid)) return new Result(null,"end_turn_card_continuation");
            } else if (item.endTurnAutoPlay || !item.triggerOnUse)
                return new Result(null, "end_turn_card_continuation");
            if (item.energyOnUse < 0 || item.energyOnUse > 999)
                return new Result(null, "queue_energy");
            if ((item.hasMonster && item.target == null)
                    || (!endTurn && item.requiresTarget && !item.randomTarget && !item.hasMonster)
                    || (item.target != null && (item.target < 0 || item.target > 4)))
                return new Result(null, "queue_target");
            if (endTurn && (item.hasMonster || item.energyOnUse != 0 || item.ignoreEnergyTotal
                    || item.freeToPlay || item.randomTarget || item.autoplay || item.purgeOnUse || item.exhaustOnUse))
                return new Result(null, "end_turn_marker");
            if (out.length() > 1) out.append(',');
            out.append("{\"card\":").append(endTurn ? "null" : item.cardJson)
                    .append(",\"target\":").append(item.target == null ? 0 : item.target)
                    .append(",\"energyOnUse\":").append(item.energyOnUse)
                    .append(",\"isEndTurn\":").append(endTurn)
                    .append(",\"triggerOnUse\":").append(item.triggerOnUse)
                    .append(",\"ignoreEnergyTotal\":").append(item.ignoreEnergyTotal)
                    .append(",\"freeToPlay\":").append(item.freeToPlay)
                    .append(",\"randomTarget\":").append(item.randomTarget)
                    .append(",\"autoplay\":").append(item.autoplay)
                    .append(",\"regretCardCount\":0")
                    .append(",\"endTurnAutoPlay\":").append(item.endTurnAutoPlay)
                    .append(",\"noTriggerOwner\":\"").append(codexEndTurn?"codex_end_turn":"").append("\"")
                    .append(",\"purgeOnUse\":").append(item.purgeOnUse)
                    .append(",\"exhaustOnUse\":").append(item.exhaustOnUse).append('}');
        }
        return new Result(out.append(']').toString(), null);
    }
}
