package stsmodelinspector;

import java.util.*;

/** Value-only public history for the audited single-monster Runic Dome slice. */
final class RunicDomeTracker {
    private final Object monster;
    private final String id;
    private final long epoch;
    private String failure;
    private boolean inRoll;
    private boolean pending;
    private int completed;
    private int rollHp, rollMaxHp;
    private long generation;
    private final List<Integer> executed = new ArrayList<>();

    RunicDomeTracker(Object monster, String id, long epoch, int act, int count) {
        this.monster=monster; this.id=id; this.epoch=epoch;
        if(monster==null || act!=1 || count!=1 || !("JawWorm".equals(id) || "Cultist".equals(id)))
            invalidate("unsupported_encounter");
    }
    void invalidate(String reason) { if(failure==null) failure=reason; }
    void beginRoll(Object source, int hp, int maxHp) {
        if(source!=monster || inRoll || pending || hp<=0 || hp>maxHp || maxHp>999) {
            invalidate("roll_lifecycle"); return;
        }
        inRoll=true; pending=true; rollHp=hp; rollMaxHp=maxHp; ++generation;
    }
    void endRoll(Object source) {
        if(source!=monster || !inRoll) invalidate("roll_lifecycle");
        inRoll=false;
    }
    void setMove(Object source) {
        if(source!=monster || !inRoll) invalidate("unobserved_move_override");
    }
    void execute(Object source, int publicMove) {
        if(source!=monster || inRoll || !pending || !legalExecuted(publicMove)) {
            invalidate("execution_lifecycle"); return;
        }
        pending=false; ++completed; ++generation;
        executed.add(publicMove); if(executed.size()>2) executed.remove(0);
    }
    private boolean legalExecuted(int move) {
        if("Cultist".equals(id)) return move==(completed==0?3:1);
        return completed==0 ? move==1 : move==1 || move==2 || move==3;
    }
    Map<String,Object> snapshot(Object source, int playerTurn) {
        if(source!=monster || playerTurn!=completed+1) invalidate("history_gap");
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("schemaVersion",1); out.put("epoch",epoch); out.put("generation",generation);
        boolean complete=failure==null && !inRoll && pending;
        out.put("complete",complete);
        if(!complete) { out.put("reason",failure==null?"roll_unsettled":failure); return out; }
        out.put("monsterId",id); out.put("slot",0); out.put("completedTurns",completed);
        out.put("executedMoves",new ArrayList<Integer>(executed));
        out.put("pendingMoveRolls",1); out.put("rollHp",rollHp); out.put("rollMaxHp",rollMaxHp);
        return out;
    }

    static boolean playerPowerAllowed(String id) {
        return Arrays.asList("Strength","Dexterity","Artifact","Metallicize").contains(id);
    }
    static boolean monsterPowerAllowed(String id, String monster) {
        return Arrays.asList("Strength","Artifact","Weak","Vulnerable").contains(id)
                || ("Cultist".equals(monster) && "Ritual".equals(id));
    }
    static boolean cardAllowed(String id) {
        return Arrays.asList("Strike_R","Defend_R","Bash","Anger","Cleave","Clothesline","Headbutt",
                "Iron Wave","Pommel Strike","Shrug It Off","Thunderclap","Twin Strike","Perfected Strike",
                "Sword Boomerang","Heavy Blade","Body Slam","Inflame","Metallicize","Wound").contains(id);
    }
    static boolean relicAllowed(String id) {
        return Arrays.asList("Runic Dome","Burning Blood","Vajra","Anchor","Bag of Preparation","Orichalcum").contains(id);
    }
    static boolean potionAllowed(String id) {
        return Arrays.asList("Potion Slot","Fire Potion","Block Potion","Strength Potion","Dexterity Potion",
                "Weak Potion","FearPotion","Explosive Potion","Energy Potion").contains(id);
    }
}
