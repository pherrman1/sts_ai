package stsmodelinspector;

import com.google.gson.Gson;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.MonsterGroup;

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
            RunicDomeTracker tracker=new RunicDomeTracker(monster,monster.id,epoch,AbstractDungeon.actNum,current.monsters.size(),AbstractDungeon.ascensionLevel);
            // Both ordinary elite and installed Colosseum Taskmaster/Nob
            // construction use the public (float,float) canVuln=true overload.
            boolean colosseum=current.monsters.size()==2 && "SlaverBoss".equals(current.monsters.get(0).id)
                    && "GremlinNob".equals(current.monsters.get(1).id);
            if("GremlinNob".equals(monster.id) && !(AbstractDungeon.getCurrRoom() instanceof com.megacrit.cardcrawl.rooms.MonsterRoomElite)
                    && !colosseum) tracker.invalidate("unsupported_nob_variant");
            if("Healer".equals(monster.id) && (current.monsters.size()!=2
                    || !"Centurion".equals(current.monsters.get(0).id) || monster!=current.monsters.get(1)))
                tracker.invalidate("unsupported_mystic_group");
            if("JawWorm".equals(monster.id) && AbstractDungeon.actNum!=1) {
                boolean horde=AbstractDungeon.actNum==3 && current.monsters.size()==3;
                for(AbstractMonster member:current.monsters) horde &= "JawWorm".equals(member.id);
                if(!horde) tracker.invalidate("unsupported_jaw_variant");
            }
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
        t.beginRoll(monster,monster.currentHealth,monster.maxHealth,first.currentHealth,first.maxHealth,!first.isDeadOrEscaped(),alive,AbstractDungeon.player.hasPower("Constricted"));
    }
    static void endRoll(AbstractMonster monster) { if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.endRoll(monster); } }
    static void setMove(AbstractMonster monster) { if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.setMove(monster); } }
    static void execute(AbstractMonster monster) {
        // Only called at entry to the audited concrete takeTurn methods. The
        // move is public because it is now executing, never while queued.
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.execute(monster,monster.nextMove); }
    }
    static void beginAcidTurn(AbstractMonster monster) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.beginKnownTurn(monster,monster.nextMove); }
    }
    static void beginKnownTurn(AbstractMonster monster) {
        if(active() && group!=null) {
            RunicDomeTracker t=tracker(monster);int alive=0;
            for(AbstractMonster m:group.monsters) if(!m.isDeadOrEscaped()) ++alive;
            if(t!=null)t.beginKnownTurn(monster,monster.nextMove,alive);
        }
    }
    // Called at the actual source-qualified direct/action setter, after a
    // public execution has established the unique expected move.
    static void finishKnownOverride(AbstractMonster monster) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster);if(t!=null)t.endKnownTurn(monster); }
    }
    static void beginRebirth(AbstractMonster monster,int move) {
        if(active() && group!=null) {RunicDomeTracker t=tracker(monster);if(t!=null) {
            if(!monster.halfDead || monster.currentHealth>0) t.invalidate("unobserved_public_rebirth");
            t.beginRebirth(monster,move);
        }}
    }
    static void beginThiefTurn(AbstractMonster monster) {
        if(active() && group!=null) {RunicDomeTracker t=tracker(monster);if(t!=null)t.beginThiefTurn(monster,monster.nextMove);}
    }
    static boolean beginHiddenSetter(AbstractMonster monster) {
        if(!active() || group==null)return false;RunicDomeTracker t=tracker(monster);return t!=null && t.beginHiddenSetter(monster);
    }
    static void endHiddenSetter(AbstractMonster monster) {
        if(active() && group!=null) {RunicDomeTracker t=tracker(monster);if(t!=null)t.endHiddenSetter(monster);}
    }
    static void publicTheft(AbstractMonster monster) {
        if(active() && group!=null) {
            RunicDomeTracker t=tracker(monster);if(t==null)return;
            com.megacrit.cardcrawl.powers.AbstractPower p=monster.getPower("Thievery");
            t.recordTheft(monster,AbstractDungeon.player.gold,p==null?0:p.amount);
        }
    }
    static void beginLagaTurn(AbstractMonster monster) {
        if(active() && group!=null) {RunicDomeTracker t=tracker(monster);if(t!=null)t.beginLagaTurn(monster,monster.nextMove);}
    }
    static void lagaPrebattle(AbstractMonster monster,int move) {
        if(active() && group!=null) {
            RunicDomeTracker t=tracker(monster);if(t==null)return;
            if(!(AbstractDungeon.getCurrRoom().event instanceof com.megacrit.cardcrawl.events.exordium.DeadAdventurer)) t.invalidate("unsupported_laga_variant");
            t.lagaAwakePrebattle(monster,move);
        }
    }
    static void beginHexTurn(AbstractMonster monster) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster);if(t!=null)t.beginHexTurn(monster,monster.nextMove,AbstractDungeon.player.currentHealth); }
    }
    static void hexInferno(AbstractMonster monster,int move) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster);if(t!=null)t.beginHexInferno(monster,move); }
    }
    static void beginDynamicTurn(AbstractMonster monster) {
        if(("Byrd".equals(monster.id) && monster.nextMove==5) || ("Shelled Parasite".equals(monster.id) && monster.nextMove==4))
            beginKnownTurn(monster);
        else execute(monster);
    }
    static void publicStun(AbstractMonster monster,int proposed) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster);if(t!=null)t.beginForcedStun(monster,proposed); }
    }
    static void acidOverride(AbstractMonster monster,int proposed) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.knownOverride(monster,proposed); }
    }
    static void endAcidTurn(AbstractMonster monster) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.endKnownTurn(monster); }
    }
    static void observeAttack(AbstractMonster monster,boolean attacking) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.observeAttack(monster,attacking); }
    }
    static String snapshot() {
        if(trackers.isEmpty()) return "{\"schemaVersion\":1,\"complete\":false,\"reason\":\"missing_initialization\"}";
        if(group!=AbstractDungeon.getMonsters() || !group.monsters.equals(identities)) invalidate("monster_replaced");
        for(AbstractMonster monster:group.monsters)
            for(com.megacrit.cardcrawl.powers.AbstractPower power:monster.powers)
                if(!RunicDomeTracker.monsterPowerAllowed(power.ID,monster.id)) invalidate("unsupported_monster_power_domain");
        java.util.List<java.util.Map<String,Object>> rows=new java.util.ArrayList<>();
        boolean complete=true;
        for(int slot=0;slot<identities.size();++slot) {
            AbstractMonster m=identities.get(slot);
            if((m.halfDead && !"AwakenedOne".equals(m.id)) || (m.isEscaping && !"Looter".equals(m.id) && !"Mugger".equals(m.id))) invalidate("unsupported_monster_lifecycle");
            java.util.Map<String,Object> row=trackers.get(slot).snapshot(m,
                    com.megacrit.cardcrawl.actions.GameActionManager.turn,slot,m.isDeadOrEscaped() && !m.halfDead);
            rows.add(row); complete &= Boolean.TRUE.equals(row.get("complete"));
        }
        java.util.Map<String,Object> out=new java.util.LinkedHashMap<>();
        out.put("schemaVersion",2);out.put("epoch",epoch);out.put("complete",complete);out.put("monsters",rows);
        return new Gson().toJson(out);
    }
}
