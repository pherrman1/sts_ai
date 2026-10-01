package stsmodelinspector;

import com.google.gson.Gson;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.cards.CardGroup;
import com.megacrit.cardcrawl.cards.CardQueueItem;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.MonsterGroup;
import com.megacrit.cardcrawl.potions.AbstractPotion;
import com.megacrit.cardcrawl.relics.AbstractRelic;

/** Game-thread adapter. No hidden move/history, RNG or private misc field is sampled. */
final class RunicDomeCapture {
    private static final java.util.List<RunicDomeTracker> trackers=new java.util.ArrayList<>();
    private static final java.util.List<AbstractMonster> identities=new java.util.ArrayList<>();
    private static MonsterGroup group;
    private static long epoch;
    static boolean active() { return AbstractDungeon.player!=null && AbstractDungeon.player.hasRelic("Runic Dome"); }
    static void clear() { trackers.clear(); identities.clear(); group=null; }
    static void begin(MonsterGroup current) {
        clear(); if(!active()) return;
        group=current;
        ++epoch;
        for(AbstractMonster monster:current.monsters) {
            identities.add(monster);
            RunicDomeTracker tracker=new RunicDomeTracker(monster,monster.id,epoch,AbstractDungeon.actNum,current.monsters.size());
            // The ordinary elite constructor fixes canVuln=true. Event Nobs
            // use a different constructor; never infer that private flag.
            if("GremlinNob".equals(monster.id) && !(AbstractDungeon.getCurrRoom() instanceof com.megacrit.cardcrawl.rooms.MonsterRoomElite))
                tracker.invalidate("unsupported_nob_variant");
            trackers.add(tracker);
        }
    }
    static RunicDomeTracker tracker(AbstractMonster monster) {
        int slot=identities.indexOf(monster);
        if(slot<0) { invalidate("monster_replaced"); return null; }
        return trackers.get(slot);
    }
    static void invalidate(String reason) { for(RunicDomeTracker t:trackers) t.invalidate(reason); }
    static void beginRoll(AbstractMonster monster) {
        if(!active() || group==null) return;
        RunicDomeTracker t=tracker(monster); if(t==null) return;
        AbstractMonster first=group.monsters.get(0);
        int alive=0; for(AbstractMonster m:group.monsters) if(!m.isDeadOrEscaped()) ++alive;
        t.beginRoll(monster,monster.currentHealth,monster.maxHealth,first.currentHealth,first.maxHealth,!first.isDeadOrEscaped(),alive);
    }
    static void endRoll(AbstractMonster monster) { if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.endRoll(monster); } }
    static void setMove(AbstractMonster monster) { if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.setMove(monster); } }
    static void execute(AbstractMonster monster) {
        // Only called at entry to the audited concrete takeTurn methods. The
        // move is public because it is now executing, never while queued.
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.execute(monster,monster.nextMove); }
    }
    static void observeAttack(AbstractMonster monster,boolean attacking) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.observeAttack(monster,attacking); }
    }
    static String snapshot() {
        if(trackers.isEmpty()) return "{\"schemaVersion\":1,\"complete\":false,\"reason\":\"missing_initialization\"}";
        if(group!=AbstractDungeon.getMonsters() || !group.monsters.equals(identities)) invalidate("monster_replaced");
        for(CardGroup pile:new CardGroup[]{AbstractDungeon.player.masterDeck,AbstractDungeon.player.hand,
                AbstractDungeon.player.drawPile,AbstractDungeon.player.discardPile,AbstractDungeon.player.exhaustPile,AbstractDungeon.player.limbo})
            for(AbstractCard card:pile.group) if(!RunicDomeTracker.cardAllowed(card.cardID)) invalidate("unsupported_card_domain");
        for(CardQueueItem item:AbstractDungeon.actionManager.cardQueue)
            if(item!=null && item.card!=null && !RunicDomeTracker.cardAllowed(item.card.cardID)) invalidate("unsupported_card_domain");
        for(com.megacrit.cardcrawl.powers.AbstractPower power:AbstractDungeon.player.powers)
            if(!RunicDomeTracker.playerPowerAllowed(power.ID)) invalidate("unsupported_player_power_domain");
        for(AbstractMonster monster:group.monsters)
            for(com.megacrit.cardcrawl.powers.AbstractPower power:monster.powers)
                if(!RunicDomeTracker.monsterPowerAllowed(power.ID,monster.id)) invalidate("unsupported_monster_power_domain");
        for(AbstractRelic relic:AbstractDungeon.player.relics)
            if(!RunicDomeTracker.relicAllowed(relic.relicId)) invalidate("unsupported_relic_domain");
        for(AbstractPotion potion:AbstractDungeon.player.potions)
            if(!RunicDomeTracker.potionAllowed(potion.ID)) invalidate("unsupported_potion_domain");
        java.util.List<java.util.Map<String,Object>> rows=new java.util.ArrayList<>();
        boolean complete=true;
        for(int slot=0;slot<identities.size();++slot) {
            AbstractMonster m=identities.get(slot);
            if(m.halfDead || m.isEscaping) invalidate("unsupported_monster_lifecycle");
            java.util.Map<String,Object> row=trackers.get(slot).snapshot(m,
                    com.megacrit.cardcrawl.actions.GameActionManager.turn,slot,m.isDeadOrEscaped());
            rows.add(row); complete &= Boolean.TRUE.equals(row.get("complete"));
        }
        java.util.Map<String,Object> out=new java.util.LinkedHashMap<>();
        out.put("schemaVersion",2);out.put("epoch",epoch);out.put("complete",complete);out.put("monsters",rows);
        return new Gson().toJson(out);
    }
}
