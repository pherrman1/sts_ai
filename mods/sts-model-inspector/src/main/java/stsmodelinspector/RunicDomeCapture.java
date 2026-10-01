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
    private static RunicDomeTracker tracker;
    private static MonsterGroup group;
    private static long epoch;
    static boolean active() { return AbstractDungeon.player!=null && AbstractDungeon.player.hasRelic("Runic Dome"); }
    static void clear() { tracker=null; group=null; }
    static void begin(MonsterGroup current) {
        clear(); if(!active()) return;
        group=current;
        AbstractMonster monster=current.monsters.size()==1?current.monsters.get(0):null;
        tracker=new RunicDomeTracker(monster,monster==null?"":monster.id,++epoch,AbstractDungeon.actNum,current.monsters.size());
    }
    static void beginRoll(AbstractMonster monster) {
        if(active() && tracker!=null) tracker.beginRoll(monster,monster.currentHealth,monster.maxHealth);
    }
    static void endRoll(AbstractMonster monster) { if(active() && tracker!=null) tracker.endRoll(monster); }
    static void setMove(AbstractMonster monster) { if(active() && tracker!=null) tracker.setMove(monster); }
    static void execute(AbstractMonster monster) {
        // Only called at entry to the audited concrete takeTurn methods. The
        // move is public because it is now executing, never while queued.
        if(active() && tracker!=null) tracker.execute(monster,monster.nextMove);
    }
    static String snapshot() {
        if(tracker==null) return "{\"schemaVersion\":1,\"complete\":false,\"reason\":\"missing_initialization\"}";
        if(group!=AbstractDungeon.getMonsters() || group.monsters.size()!=1) tracker.invalidate("monster_replaced");
        for(CardGroup pile:new CardGroup[]{AbstractDungeon.player.masterDeck,AbstractDungeon.player.hand,
                AbstractDungeon.player.drawPile,AbstractDungeon.player.discardPile,AbstractDungeon.player.exhaustPile,AbstractDungeon.player.limbo})
            for(AbstractCard card:pile.group) if(!RunicDomeTracker.cardAllowed(card.cardID)) tracker.invalidate("unsupported_card_domain");
        for(CardQueueItem item:AbstractDungeon.actionManager.cardQueue)
            if(item!=null && item.card!=null && !RunicDomeTracker.cardAllowed(item.card.cardID)) tracker.invalidate("unsupported_card_domain");
        for(com.megacrit.cardcrawl.powers.AbstractPower power:AbstractDungeon.player.powers)
            if(!RunicDomeTracker.playerPowerAllowed(power.ID)) tracker.invalidate("unsupported_player_power_domain");
        for(AbstractMonster monster:group.monsters)
            for(com.megacrit.cardcrawl.powers.AbstractPower power:monster.powers)
                if(!RunicDomeTracker.monsterPowerAllowed(power.ID,monster.id)) tracker.invalidate("unsupported_monster_power_domain");
        for(AbstractRelic relic:AbstractDungeon.player.relics)
            if(!RunicDomeTracker.relicAllowed(relic.relicId)) tracker.invalidate("unsupported_relic_domain");
        for(AbstractPotion potion:AbstractDungeon.player.potions)
            if(!RunicDomeTracker.potionAllowed(potion.ID)) tracker.invalidate("unsupported_potion_domain");
        return new Gson().toJson(tracker.snapshot(group.monsters.size()==1?group.monsters.get(0):null,
                com.megacrit.cardcrawl.actions.GameActionManager.turn));
    }
}
