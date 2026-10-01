package stsmodelinspector;

import java.util.*;

/** Value-only public history for the audited stable-slot Runic Dome slice. */
final class RunicDomeTracker {
    private final Object monster;
    private final String id;
    private final long epoch;
    private String failure;
    private boolean inRoll;
    private boolean pending;
    private boolean knownTurn, knownOverridePermitted, knownOverrideSeen;
    private int expectedKnownMove, knownNextMove;
    private Boolean attackPredicate;
    private int completed;
    private int rollHp, rollMaxHp, publicMisc;
    private int firstHp, firstMaxHp, aliveCount;
    private boolean firstAlive;
    private long generation;
    private final List<Integer> executed = new ArrayList<>();

    RunicDomeTracker(Object monster, String id, long epoch, int act, int count) {
        this.monster=monster; this.id=id; this.epoch=epoch;
        if(monster==null || act!=1 || (count<1 || count>5) || !monsterAllowed(id))
            invalidate("unsupported_encounter");
    }
    static boolean monsterAllowed(String id) {
        return Arrays.asList("JawWorm","Cultist","FungiBeast","SlaverBlue","SlaverRed",
                "AcidSlime_S","AcidSlime_M","SpikeSlime_M","SpikeSlime_S","Sentry","GremlinNob").contains(id);
    }
    void invalidate(String reason) { if(failure==null) failure=reason; }
    void beginRoll(Object source, int hp, int maxHp) {
        beginRoll(source,hp,maxHp,hp,maxHp,true,1);
    }
    void beginRoll(Object source,int hp,int maxHp,int firstHp,int firstMaxHp,boolean firstAlive,int aliveCount) {
        if(source!=monster || inRoll || pending || knownTurn || knownNextMove!=0
                || ("AcidSlime_S".equals(id) && completed!=0) || hp<=0 || hp>maxHp || maxHp>999) {
            invalidate("roll_lifecycle"); return;
        }
        attackPredicate=null; inRoll=true; pending=true; rollHp=hp; rollMaxHp=maxHp; ++generation;
        this.firstHp=firstHp; this.firstMaxHp=firstMaxHp; this.firstAlive=firstAlive; this.aliveCount=aliveCount;
    }
    void endRoll(Object source) {
        if(source!=monster || !inRoll) invalidate("roll_lifecycle");
        inRoll=false;
    }
    void setMove(Object source) {
        if(source!=monster) { invalidate("unobserved_move_override"); return; }
        if(inRoll) return;
        if(!knownTurn || !knownOverridePermitted || knownOverrideSeen) invalidate("unobserved_move_override");
        else { knownOverrideSeen=true; knownOverridePermitted=false; }
    }
    void execute(Object source, int publicMove) {
        if(source!=monster || inRoll || knownTurn || (!pending && knownNextMove==0)
                || (knownNextMove!=0 && publicMove!=knownNextMove) || !legalExecuted(publicMove)) {
            invalidate("execution_lifecycle"); return;
        }
        if("SlaverRed".equals(id) && publicMove==2) publicMisc=1;
        pending=false; knownNextMove=0; attackPredicate=null; ++completed; ++generation;
        executed.add(publicMove); if(executed.size()>2) executed.remove(0);
    }
    void beginKnownTurn(Object source,int publicMove) {
        if(!"AcidSlime_S".equals(id)) { invalidate("known_transition_domain"); return; }
        execute(source,publicMove);
        if(failure!=null) return;
        knownTurn=true; knownOverridePermitted=false; knownOverrideSeen=false;
        expectedKnownMove=3-publicMove;
    }
    // Called only at the two audited direct setMove sites in AcidSlime_S.takeTurn.
    // This validates a publicly determined override, not an unexecuted random roll.
    void knownOverride(Object source,int proposed) {
        if(source!=monster || !knownTurn || proposed!=expectedKnownMove
                || knownOverridePermitted || knownOverrideSeen) invalidate("known_transition_override");
        else knownOverridePermitted=true;
    }
    void endKnownTurn(Object source) {
        if(source!=monster || !knownTurn || !knownOverrideSeen || knownOverridePermitted)
            invalidate("known_transition_missing");
        if(failure==null) { knownNextMove=expectedKnownMove; ++generation; }
        knownTurn=false; knownOverridePermitted=false;
    }
    void observeAttack(Object source,boolean attacking) {
        if(knownNextMove!=0) {
            if(source!=monster || knownTurn || attacking!=(knownNextMove==1)) invalidate("predicate_lifecycle");
            return;
        }
        if(source!=monster || inRoll || !pending || (attackPredicate!=null && attackPredicate!=attacking)) {
            invalidate("predicate_lifecycle");return;
        }
        attackPredicate=attacking;
    }
    private boolean legalExecuted(int move) {
        if("AcidSlime_S".equals(id)) return (move==1 || move==2)
                && (executed.isEmpty() || move!=executed.get(executed.size()-1));
        if("SpikeSlime_S".equals(id)) return move==1;
        if("Sentry".equals(id)) return (move==3 || move==4) && (executed.isEmpty() || move!=executed.get(executed.size()-1));
        if("Cultist".equals(id)) return move==(completed==0?3:1);
        if("JawWorm".equals(id)) return completed==0 ? move==1 : move>=1 && move<=3;
        if("GremlinNob".equals(id)) return completed==0 ? move==3 : move==1 || move==2;
        if("SlaverRed".equals(id)) return completed==0 ? move==1 : move==1 || move==3 || (move==2 && publicMisc==0);
        if("SlaverBlue".equals(id) || "SpikeSlime_M".equals(id)) return move==1 || move==4;
        if("AcidSlime_M".equals(id)) return move==1 || move==2 || move==4;
        return "FungiBeast".equals(id) && (move==1 || move==2);
    }
    Map<String,Object> snapshot(Object source, int playerTurn) {
        return snapshot(source,playerTurn,0,false);
    }
    Map<String,Object> snapshot(Object source, int playerTurn,int slot,boolean dead) {
        if(source!=monster || (dead ? completed>=playerTurn : playerTurn!=completed+1)) invalidate("history_gap");
        if("Sentry".equals(id)) for(int i=0;i<executed.size();++i)
            if(executed.get(i)!=((slot+completed-executed.size()+i)%2==0?3:4)) invalidate("history_gap");
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("schemaVersion",1); out.put("epoch",epoch); out.put("generation",generation);
        boolean complete=failure==null && !inRoll && !knownTurn && (pending || knownNextMove!=0 || dead);
        out.put("complete",complete);
        if(!complete) { out.put("reason",failure==null?"roll_unsettled":failure); return out; }
        out.put("monsterId",id); out.put("slot",slot); out.put("completedTurns",completed);
        out.put("executedMoves",new ArrayList<Integer>(executed));
        out.put("pendingAttackPredicates",!dead && attackPredicate!=null ? Arrays.asList(Arrays.asList(1,attackPredicate)) : Collections.emptyList());
        out.put("pendingMoveRolls",dead || knownNextMove!=0?0:1); out.put("publicMisc",publicMisc);
        if("AcidSlime_S".equals(id)) {
            Map<String,Object> proof=null;
            if(!dead && knownNextMove!=0) {
                proof=new LinkedHashMap<>();proof.put("kind","acid_slime_s_alternation");proof.put("move",knownNextMove);
            }
            out.put("knownNextMove",proof);
        }
        out.put("firstHp",firstHp); out.put("firstMaxHp",firstMaxHp); out.put("firstAlive",firstAlive);
        out.put("aliveCount",aliveCount); out.put("rollHp",rollHp); out.put("rollMaxHp",rollMaxHp);
        return out;
    }

    static boolean playerPowerAllowed(String id) {
        return Arrays.asList("Strength","Dexterity","Artifact","Metallicize","Weak","Frail","Vulnerable","Entangled").contains(id);
    }
    static boolean monsterPowerAllowed(String id, String monster) {
        return Arrays.asList("Strength","Artifact","Weak","Vulnerable").contains(id)
                || ("Cultist".equals(monster) && "Ritual".equals(id))
                || ("FungiBeast".equals(monster) && "Spore Cloud".equals(id))
                || ("GremlinNob".equals(monster) && "Anger".equals(id));
    }
    static boolean cardAllowed(String id) {
        return Arrays.asList("Strike_R","Defend_R","Bash","Anger","Cleave","Clothesline","Headbutt",
                "Iron Wave","Pommel Strike","Shrug It Off","Thunderclap","Twin Strike","Perfected Strike",
                "Sword Boomerang","Heavy Blade","Body Slam","Inflame","Metallicize","Wound","Slimed","Dazed","Spot Weakness").contains(id);
    }
    static boolean relicAllowed(String id) {
        return Arrays.asList("Runic Dome","Burning Blood","Vajra","Anchor","Bag of Preparation","Orichalcum").contains(id);
    }
    static boolean potionAllowed(String id) {
        return Arrays.asList("Potion Slot","Fire Potion","Block Potion","Strength Potion","Dexterity Potion",
                "Weak Potion","FearPotion","Explosive Potion","Energy Potion").contains(id);
    }
}
