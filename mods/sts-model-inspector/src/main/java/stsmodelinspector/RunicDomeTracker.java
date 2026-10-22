package stsmodelinspector;

import java.util.*;

/** Value-only public history for the audited stable-slot Runic Dome slice. */
final class RunicDomeTracker {
    private final Object monster;
    private final String id;
    private final long epoch;
    private final int ascension,act;
    private String failure;
    private boolean inRoll;
    private boolean pending;
    private boolean knownTurn, knownOverridePermitted, knownOverrideSeen;
    private int expectedKnownMove, knownNextMove;
    private Boolean attackPredicate;
    private int completed,damageExecutions;
    private int rollHp, rollMaxHp, publicMisc;
    private int firstHp, firstMaxHp, aliveCount;
    private boolean firstAlive, playerConstricted;
    private long generation;
    private int totalRolls,knownTransitions;
    private boolean shellPredecessor,hexPredecessor,lagaPredecessor;
    private boolean lagaAsleep=true; private int lagaSleeps;
    private boolean pendingDirect,hiddenSetterScope,hiddenSetterSeen;
    private int directChoices,pendingThefts;
    private boolean rebirthDuplicatePending;
    private int occupantGeneration,birthGlobalTurn,lastExecutionGlobalTurn=-1,globalTurn,rollGlobalTurn;
    private int birthParentSlot=-1,birthParentGeneration,latentDamageMask;
    private String birthKind="initial";
    private boolean publicDuplicatePending,darkInterveningRoll,torchConstructorPredecessor;
    void constructorTackle(Object source) {
        if(source!=monster || !"TorchHead".equals(id) || completed!=0 || totalRolls!=0 || knownNextMove!=0){invalidate("torch_constructor_lifecycle");return;}
        knownNextMove=1;torchConstructorPredecessor=true;++knownTransitions;++generation;
    }
    void bind(int generation,int birthTurn,String kind,int parentSlot,int parentGeneration) {
        if(occupantGeneration!=0 || generation<1 || birthTurn<0) invalidate("occupant_binding");
        occupantGeneration=generation;birthGlobalTurn=birthTurn;birthKind=kind;
        birthParentSlot=parentSlot;birthParentGeneration=parentGeneration;
    }
    void globalTurn(int turn) {globalTurn=turn;}
    int occupantGeneration() {return occupantGeneration;}
    int lastExecutedMove() {return executed.isEmpty()?-1:executed.get(executed.size()-1);}
    int latentDamageMask() {return latentDamageMask;}
    void filterLatentDamage(int mask) {
        if(mask==0 || (mask & ~latentDamageMask)!=0) invalidate("latent_damage_observation");
        else latentDamageMask=mask;
    }
    static boolean latent(String id) {return "FuzzyLouseNormal".equals(id)||"FuzzyLouseDefensive".equals(id)||"Darkling".equals(id);}
    static boolean split(String id) {return "AcidSlime_L".equals(id)||"SpikeSlime_L".equals(id)||"SlimeBoss".equals(id);}
    // Act 4: every turn ends in RollMoveAction, but only one roll per three is random
    // (CorruptHeart after Debilitate/Buff, SpireShield at moveCount%3==0, SpireSpear at %3==2).
    static boolean act4(String id) {return "CorruptHeart".equals(id)||"SpireShield".equals(id)||"SpireSpear".equals(id);}
    // The publicly determined result of the roll made after `done` executions, or 0 if it is random.
    static int act4Cycle(String id,int done,int last) {
        if("CorruptHeart".equals(id)) {
            if(done==0) return 3;
            int mc=(done-1)%3; return mc==1?(last==2?1:2):mc==2?4:0;
        }
        int mc=done%3;
        if("SpireShield".equals(id)) return mc==1?(last==1?2:1):mc==2?3:0;
        if("SpireSpear".equals(id)) return mc==0?(last==1?2:1):mc==1?3:0;
        return 0;
    }
    static boolean remaining(String id) {return latent(id)||split(id)||Arrays.asList("BronzeAutomaton","BronzeOrb","GremlinLeader","Reptomancer","Dagger","TheCollector","TorchHead").contains(id);}
    void publicOverride(Object source,int proposed,boolean threshold) {
        int expected="Darkling".equals(id)?4:3;
        if(source!=monster || (!split(id) && !"Darkling".equals(id)) || proposed!=expected || !threshold || inRoll || knownTurn) {invalidate("public_override_lifecycle");return;}
        pending=false;knownNextMove=0;rollHistory.clear();attackPredicates.clear();
        knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=expected;
        publicDuplicatePending=true;knownOverride(source,proposed);
    }

    private final List<Map<String,Object>> rollHistory=new ArrayList<>();
    private final Map<Integer,Boolean> attackPredicates=new TreeMap<>();
    private final List<Integer> executed = new ArrayList<>();

    RunicDomeTracker(Object monster, String id, long epoch, int act, int count) {
        this(monster,id,epoch,act,count,0);
    }
    RunicDomeTracker(Object monster, String id, long epoch, int act, int count,int ascension) {
        this.monster=monster; this.id=id; this.epoch=epoch; this.ascension=ascension;this.act=act;
        if(latent(id)) {int lo="Darkling".equals(id)?(ascension>=2?9:7):(ascension>=2?6:5);int hi=lo+("Darkling".equals(id)?4:2);for(int n=lo;n<=hi;++n)latentDamageMask|=1<<n;}
        if("BookOfStabbing".equals(id)) publicMisc=1;
        if("TheGuardian".equals(id)) publicMisc=ascension>=19?40:ascension>=9?35:30;
        if(monster==null || (act4(id)?act!=4:(act<1 || act>3)) || (count<1 || count>5) || !monsterAllowed(id))
            invalidate("unsupported_encounter");
    }
    static boolean monsterAllowed(String id) {
        return remaining(id) || Arrays.asList("JawWorm","Cultist","FungiBeast","SlaverBlue","SlaverRed",
                "AcidSlime_S","AcidSlime_M","SpikeSlime_M","SpikeSlime_S","Sentry","GremlinNob",
                "Centurion","Healer","Chosen","SnakePlant","Snecko","SphericGuardian",
                "Exploder","Repulsor","Maw","Nemesis","Orb Walker","GiantHead","Donu","Deca",
                "Spiker","Serpent","SlaverBoss","GremlinFat","BookOfStabbing","TimeEater","GremlinThief","GremlinWarrior","GremlinWizard",
                "GremlinTsundere","BanditBear","BanditLeader","BanditChild","Transient","WrithingMass","Champ","Byrd","Shelled Parasite","TheGuardian","Hexaghost","Lagavulin","Looter","Mugger","AwakenedOne").contains(id) || act4(id);
    }
    private boolean dynamic() { return remaining(id) || "Byrd".equals(id) || "Shelled Parasite".equals(id) || "TheGuardian".equals(id) || "Hexaghost".equals(id) || "Lagavulin".equals(id) || "AwakenedOne".equals(id) || thief() || act4(id); }
    private boolean thief() {return "Looter".equals(id) || "Mugger".equals(id);}
    void invalidate(String reason) { if(failure==null) failure=reason; }
    void beginRoll(Object source, int hp, int maxHp) {
        beginRoll(source,hp,maxHp,hp,maxHp,true,1);
    }
    void beginRoll(Object source,int hp,int maxHp,int firstHp,int firstMaxHp,boolean firstAlive,int aliveCount) {
        beginRoll(source,hp,maxHp,firstHp,firstMaxHp,firstAlive,aliveCount,false);
    }
    void beginRoll(Object source,int hp,int maxHp,int firstHp,int firstMaxHp,boolean firstAlive,int aliveCount,boolean constricted) {
        // A first-form Thorns death can leave an already queued roll before
        // the duplicate public Rebirth setter. Its result is overwritten;
        // count the observed roll without importing any hidden result/input.
        if("AwakenedOne".equals(id) && rebirthDuplicatePending && knownNextMove==3 && source==monster && !inRoll && !knownTurn && hp==0) {
            knownNextMove=0;pending=true;inRoll=true;++totalRolls;++generation;return;
        }
        if(publicDuplicatePending && (split(id) || "Darkling".equals(id)) && knownNextMove!=0 && !inRoll) {
            if("Darkling".equals(id))darkInterveningRoll=true;
            knownNextMove=0;pending=true;inRoll=true;++totalRolls;++generation;return;
        }
        if("TorchHead".equals(id) && torchConstructorPredecessor && totalRolls==0 && knownNextMove==1)knownNextMove=0;
        // AwakenedOne.changeState("REBIRTH") queues its HealAction behind takeTurn's
        // RollMoveAction, so the roll after Rebirth sees HP 0 (problem 91).
        boolean rebirthRoll="AwakenedOne".equals(id) && hp==0 && publicMisc==1
                && !executed.isEmpty() && executed.get(executed.size()-1)==3;
        if(("Shelled Parasite".equals(id) && knownNextMove==1 && shellPredecessor)
                || ("Hexaghost".equals(id) && knownNextMove==6 && hexPredecessor) || ("Lagavulin".equals(id) && lagaPredecessor)) knownNextMove=0;
        if(source!=monster || inRoll || (pending && !"WrithingMass".equals(id)) || rollHistory.size()>=255 || knownTurn || knownNextMove!=0
                || (knownLifecycle(id) && completed!=0) || (hp<=0 && !"Darkling".equals(id) && !rebirthRoll) || hp>maxHp || maxHp>999) {
            invalidate("roll_lifecycle"); return;
        }
        rollGlobalTurn=globalTurn; ++totalRolls; attackPredicate=null; inRoll=true; pending=true; rollHp=hp; rollMaxHp=maxHp; ++generation;
        this.firstHp=firstHp; this.firstMaxHp=firstMaxHp; this.firstAlive=firstAlive; this.aliveCount=aliveCount; this.playerConstricted=constricted;
        Map<String,Object> inputs=new LinkedHashMap<>();inputs.put("rollHp",hp);inputs.put("rollMaxHp",maxHp);
        inputs.put("firstHp",firstHp);inputs.put("firstMaxHp",firstMaxHp);inputs.put("firstAlive",firstAlive);
        if(occupantGeneration>0)inputs.put("rollGlobalTurn",globalTurn);
        inputs.put("aliveCount",aliveCount);inputs.put("playerConstricted",constricted);rollHistory.add(inputs);
        if(act4(id)) {
            if(totalRolls!=completed+1) {invalidate("act4_cycle_lifecycle");return;}
            int known=act4Cycle(id,completed,lastExecutedMove());
            if(known!=0) {pending=false;rollHistory.clear();knownNextMove=known;}
        }
    }
    // A queued vanilla roll may resolve after its source has publicly died.
    // It advances lifecycle/RNG accounting but cannot affect a future occupant.
    void beginTerminalRoll(Object source) {
        if(source!=monster || totalRolls<1 || completed<1 || inRoll || knownTurn || knownNextMove!=0
                || pendingDirect || hiddenSetterScope || publicDuplicatePending || rebirthDuplicatePending
                || pending || knownLifecycle(id)) {
            invalidate("terminal_roll_lifecycle");return;
        }
        ++totalRolls;++generation;inRoll=true;pending=false;rollHistory.clear();attackPredicates.clear();
    }
    void endRoll(Object source) {
        if(source!=monster || !inRoll) invalidate("roll_lifecycle");
        inRoll=false;
    }
    void setMove(Object source) {
        if(source!=monster) { invalidate("unobserved_move_override"); return; }
        if(inRoll) return;
        if(hiddenSetterScope) {hiddenSetterSeen=true;hiddenSetterScope=false;return;}
        if(!knownTurn || !knownOverridePermitted || knownOverrideSeen) invalidate("unobserved_move_override");
        else { knownOverrideSeen=true; knownOverridePermitted=false; }
    }
    void execute(Object source, int publicMove) {
        if(source!=monster || inRoll || knownTurn || (!pending && !pendingDirect && knownNextMove==0)
                || (knownNextMove!=0 && publicMove!=knownNextMove) || !legalExecuted(publicMove)) {
            invalidate("execution_lifecycle"); return;
        }
        if(occupantGeneration>0) {
            if(globalTurn<=lastExecutionGlobalTurn || globalTurn<birthGlobalTurn) invalidate("execution_global_turn");
            lastExecutionGlobalTurn=globalTurn;
        }
        if(latent(id) && publicMove==3)++damageExecutions;
        if("BronzeOrb".equals(id) && publicMove==3) publicMisc=1;
        if("BronzeAutomaton".equals(id)) {int residue=completed%6;publicMisc=residue==5?0:residue;}
        if("SlaverRed".equals(id) && publicMove==2) publicMisc=1;
        if("Spiker".equals(id) && publicMove==2) ++publicMisc;
        if("TimeEater".equals(id) && publicMove==5) publicMisc=1;
        if("BookOfStabbing".equals(id) && (publicMove==1 || ascension>=18)) ++publicMisc;
        if("WrithingMass".equals(id) && publicMove==4) publicMisc=1;
        if("AwakenedOne".equals(id) && publicMove==3) publicMisc=1;
        if("TheGuardian".equals(id) && publicMove==4) publicMisc+=10;
        if("Champ".equals(id)) { if(publicMove==2) ++publicMisc; if(publicMove==7) publicMisc|=4; }
        darkInterveningRoll=false;torchConstructorPredecessor=false;pending=false; pendingDirect=false;hiddenSetterSeen=false; knownNextMove=0; shellPredecessor=false; hexPredecessor=false; lagaPredecessor=false; attackPredicate=null;rollHistory.clear();attackPredicates.clear(); ++completed; ++generation;
        executed.add(publicMove); if(executed.size()>2) executed.remove(0);
    }
    static boolean knownLifecycle(String id) {
        return Arrays.asList("SlimeBoss","TorchHead","AcidSlime_S","GremlinThief","GremlinWarrior","GremlinWizard","GremlinTsundere",
                "BanditBear","BanditLeader","BanditChild","Transient","TheGuardian").contains(id);
    }
    void beginKnownTurn(Object source,int publicMove) { beginKnownTurn(source,publicMove,aliveCount); }
    void beginKnownTurn(Object source,int publicMove,int living) {
        if(!knownLifecycle(id) && !("Byrd".equals(id) && publicMove==5) && !("Shelled Parasite".equals(id) && publicMove==4)) { invalidate("known_transition_domain"); return; }
        execute(source,publicMove);
        if(failure!=null) return;
        knownTurn=true; knownOverridePermitted=false; knownOverrideSeen=false;
        aliveCount=living;
        if("GremlinWizard".equals(id)) publicMisc=publicMove==2?publicMisc+1:0;
        switch(id) {
            case "SlimeBoss": expectedKnownMove=publicMove==4?2:publicMove==2?1:publicMove==1?4:3;break;
            case "TorchHead": expectedKnownMove=1;break;
            case "AcidSlime_S": expectedKnownMove=3-publicMove;break;
            case "Byrd": expectedKnownMove=2;break;
            case "TheGuardian": expectedKnownMove=new int[]{0,3,7,4,5,6,2,5}[publicMove];break;
            case "Shelled Parasite": expectedKnownMove=1;shellPredecessor=true;break;
            case "BanditBear": expectedKnownMove=publicMove==3?1:3;break;
            case "BanditLeader": expectedKnownMove=publicMove==3?1:publicMove==1 && ascension>=17
                    && (executed.size()<2 || executed.get(0)!=1)?1:3;break;
            case "GremlinWizard": expectedKnownMove=publicMisc>=3 || (publicMove==1 && ascension>=17)?1:2;break;
            case "GremlinTsundere": expectedKnownMove=publicMove==2 || living<=1?2:1;break;
            default:expectedKnownMove=1;
        }
    }
    void beginRebirth(Object source,int proposed) {
        if(!"AwakenedOne".equals(id) || source!=monster || proposed!=3 || publicMisc!=0
                || (!pending && (completed==0 || executed.isEmpty() || (executed.get(executed.size()-1)!=1 && executed.get(executed.size()-1)!=2)))
                || inRoll || knownTurn || knownNextMove!=0 || rebirthDuplicatePending) {invalidate("public_rebirth_lifecycle");return;}
        pending=false;rollHistory.clear();attackPredicates.clear();attackPredicate=null;
        knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=3;
        rebirthDuplicatePending=true;knownOverride(source,proposed);
    }
    void beginThiefTurn(Object source,int move) {
        execute(source,move);if(failure!=null) return;
        if(move==1 || move==4) ++pendingThefts;
        if(move==1 && completed==2) {
            pendingDirect=true;hiddenSetterSeen=false;++directChoices;++generation;
        } else {
            expectedKnownMove=move==1?1:move==4?2:3;
            knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;
        }
    }
    boolean beginHiddenSetter(Object source) {
        if(!pendingDirect) return false;
        if(source!=monster || !thief() || completed!=2 || hiddenSetterScope || hiddenSetterSeen) {invalidate("hidden_choice_setter");return true;}
        hiddenSetterScope=true;return true;
    }
    void endHiddenSetter(Object source) {
        if(source!=monster || !pendingDirect || !hiddenSetterSeen || hiddenSetterScope) invalidate("hidden_choice_setter");
    }
    void recordTheft(Object source,int publicGold,int publicAmount) {
        if(source!=monster || !thief() || pendingThefts!=1 || publicGold<0 || publicAmount!=(ascension>=17?20:15)) {invalidate("public_theft_lifecycle");return;}
        publicMisc+=Math.min(publicGold,publicAmount);--pendingThefts;
    }
    void beginLagaTurn(Object source,int move) {
        execute(source,move);if(failure!=null) return;
        if(move==5 || move==6) {
            if(move==5) ++lagaSleeps;
            int next=move==6 || lagaSleeps>=3?3:5;
            if(next==3) lagaAsleep=false;
            lagaPredecessor=move==6 || lagaSleeps<3;
            knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=next;
        }
    }
    void lagaAwakePrebattle(Object source,int proposed) {
        if(!"Lagavulin".equals(id) || source!=monster || completed!=0 || proposed!=1 || !pending || inRoll || knownTurn) {invalidate("laga_prebattle");return;}
        lagaAsleep=false;pending=false;rollHistory.clear();attackPredicates.clear();
        knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=1;knownOverride(source,proposed);
    }
    void beginHexTurn(Object source,int publicMove,int publicPlayerHp) {
        execute(source,publicMove);if(failure!=null) return;
        if(publicMove==5) {
            if(publicPlayerHp<1 || publicPlayerHp>9999) {invalidate("public_player_hp");return;}
            publicMisc=publicPlayerHp/12+1;
            knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=1;
        }
    }
    void beginHexInferno(Object source,int proposed) {
        if(!"Hexaghost".equals(id) || source!=monster || proposed!=6 || completed<2 || (completed-2)%7!=6
                || inRoll || pending || knownTurn || knownNextMove!=0) {invalidate("hex_inferno_lifecycle");return;}
        hexPredecessor=true;knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=6;
        knownOverride(source,proposed);
    }
    void beginForcedStun(Object source,int proposed) {
        if(!dynamic() || source!=monster || proposed!=("TheGuardian".equals(id)?1:4) || inRoll || knownTurn || (!pending && knownNextMove==0)) {
            invalidate("unqualified_public_stun");return;
        }
        if("Lagavulin".equals(id)) lagaAsleep=false;
        pending=false;knownNextMove=0;shellPredecessor=false;rollHistory.clear();attackPredicates.clear();attackPredicate=null;
        knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=proposed;
        knownOverride(source,proposed);
    }
    // Called only at audited deterministic direct/action setter sites.
    // This validates a publicly determined override, not an unexecuted random roll.
    void knownOverride(Object source,int proposed) {
        if(publicDuplicatePending && !knownTurn && source==monster && proposed==("Darkling".equals(id)?4:3)) {
            publicDuplicatePending=false;pending=false;rollHistory.clear();attackPredicates.clear();knownNextMove=0;
            knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=proposed;
        }
        if("AwakenedOne".equals(id) && rebirthDuplicatePending && !knownTurn && (knownNextMove==3 || pending) && source==monster && proposed==3) {
            rebirthDuplicatePending=false;pending=false;rollHistory.clear();attackPredicates.clear();knownNextMove=0;knownTurn=true;knownOverridePermitted=false;knownOverrideSeen=false;expectedKnownMove=3;
        }
        if(source!=monster || !knownTurn || proposed!=expectedKnownMove
                || knownOverridePermitted || knownOverrideSeen) invalidate("known_transition_override");
        else knownOverridePermitted=true;
    }
    void endKnownTurn(Object source) {
        if(source!=monster || !knownTurn || !knownOverrideSeen || knownOverridePermitted)
            invalidate("known_transition_missing");
        if(failure==null) { knownNextMove=expectedKnownMove; ++knownTransitions; ++generation; }
        knownTurn=false; knownOverridePermitted=false;
    }
    void observeAttack(Object source,boolean attacking) {
        if(knownNextMove!=0) {
            if(source!=monster || knownTurn || attacking!=knownMoveAttacks()) invalidate("predicate_lifecycle");
            return;
        }
        if(source!=monster || inRoll || (!pending && !pendingDirect) || (attackPredicate!=null && attackPredicate!=attacking)) {
            invalidate("predicate_lifecycle");return;
        }
        attackPredicate=attacking;attackPredicates.put(pendingDirect?1:rollHistory.size(),attacking);
    }
    private boolean knownMoveAttacks() {
        if("AcidSlime_S".equals(id) || "GremlinWizard".equals(id)) return knownNextMove==1;
        if("GremlinTsundere".equals(id)) return knownNextMove==2;
        if("SlimeBoss".equals(id))return knownNextMove==1;
        if("AwakenedOne".equals(id) || split(id) || "Darkling".equals(id)) return false;
        if(thief()) return knownNextMove==1 || knownNextMove==4;
        if("Lagavulin".equals(id)) return knownNextMove==3;
        if("Hexaghost".equals(id)) return true;
        if("TheGuardian".equals(id)) return knownNextMove>=2 && knownNextMove<=5;
        if("Byrd".equals(id) || "Shelled Parasite".equals(id)) return knownNextMove!=4 && !("Byrd".equals(id) && knownNextMove==2);
        if("CorruptHeart".equals(id)) return knownNextMove==1 || knownNextMove==2;
        if("SpireShield".equals(id) || "SpireSpear".equals(id)) return knownNextMove!=2;
        return true;
    }
    private boolean legalExecuted(int move) {
        if("AcidSlime_S".equals(id)) return (move==1 || move==2)
                && (executed.isEmpty() || move!=executed.get(executed.size()-1));
        if("SpikeSlime_S".equals(id)) return move==1;
        if("Sentry".equals(id)) return (move==3 || move==4) && (executed.isEmpty() || move!=executed.get(executed.size()-1));
        if("Cultist".equals(id)) return move==(completed==0?3:1);
        if("JawWorm".equals(id)) return completed==0 && act==1 ? move==1 : move>=1 && move<=3;
        if("GremlinNob".equals(id)) return completed==0 ? move==3 : move==1 || move==2;
        if("SlaverRed".equals(id)) return completed==0 ? move==1 : move==1 || move==3 || (move==2 && publicMisc==0);
        if("SlaverBlue".equals(id) || "SpikeSlime_M".equals(id)) return move==1 || move==4;
        if("AcidSlime_M".equals(id)) return move==1 || move==2 || move==4;
        if("FungiBeast".equals(id)) return move==1 || move==2;
        switch(id) {
            case "FuzzyLouseNormal": case "FuzzyLouseDefensive": return move==3 || move==4;
            case "Darkling": return move>=1 && move<=5;
            case "AcidSlime_L": return move>=1 && move<=4;
            case "SpikeSlime_L": return move==1 || move==3 || move==4;
            case "SlimeBoss": return move>=1 && move<=4;
            case "BronzeAutomaton": return move>=1 && move<=5;
            case "BronzeOrb": return move>=1 && move<=3;
            case "GremlinLeader": return move>=2 && move<=4; // RALLY 2, ENCOURAGE 3, STAB 4
            case "Reptomancer": return move>=1 && move<=3;
            case "Dagger": return move==(completed==0?1:2);
            case "TheCollector": return move>=1 && move<=5;
            case "TorchHead": return move==1;
            case "Centurion": case "Healer": case "Serpent": return move>=1 && move<=3;
            case "Chosen": return completed==0?move==(ascension>=17?4:5):move>=1 && move<=5;
            case "SnakePlant": case "Repulsor": case "Orb Walker": case "Spiker": case "BookOfStabbing": return move==1 || move==2;
            case "Snecko": return completed==0?move==1:move==2 || move==3;
            case "SphericGuardian": return move==(completed==0?2:completed==1?4:completed%2==0?1:3);
            case "Exploder": return move==(completed<2?1:2);
            case "Maw": return completed==0?move==2:move>=3 && move<=5;
            case "Nemesis": return move>=2 && move<=4;
            case "GiantHead": return completed>=(ascension>=18?3:4)?move==2:move==1 || move==3;
            case "Donu": return move==(completed%2==0?2:0);
            case "Deca": return move==(completed%2==0?0:2);
            case "SlaverBoss": case "GremlinFat": return move==2;
            case "GremlinThief": case "GremlinWarrior": case "BanditChild": case "Transient": return move==1;
            case "GremlinWizard": return completed==0?move==2:move==1 || move==2;
            case "GremlinTsundere": return completed==0?move==1:move==1 || move==2;
            case "BanditBear": case "BanditLeader": return completed==0?move==2:move==1 || move==3;
            case "AwakenedOne": return publicMisc==0?(move==1 || move==2 || move==3):(move==5 || move==6 || move==8);
            case "Looter": case "Mugger": return completed<2?move==1:move>=2 && move<=4;
            case "Lagavulin": return move==1 || move==3 || move==4 || move==5 || move==6;
            case "Hexaghost": return move==(completed==0?5:completed==1?1:new int[]{4,2,4,3,2,4,6}[(completed-2)%7]);
            case "TheGuardian": return move>=1 && move<=7;
            case "Byrd": return move>=1 && move<=6;
            case "Shelled Parasite": return move>=1 && move<=4;
            case "Champ": return move>=1 && move<=7 && (move!=2 || (publicMisc & 3)<2) && (move!=7 || (publicMisc & 4)==0);
            case "WrithingMass": return move>=0 && move<=4 && (move!=4 || publicMisc==0);
            case "TimeEater": return move>=2 && move<=5 && (move!=5 || publicMisc==0);
            case "CorruptHeart": case "SpireShield": case "SpireSpear": {
                int known=act4Cycle(id,completed,lastExecutedMove());
                return known!=0?move==known:move==1 || move==2;
            }
            default:return false;
        }
    }
    Map<String,Object> snapshot(Object source, int playerTurn) {
        return snapshot(source,playerTurn,0,false);
    }
    Map<String,Object> snapshot(Object source, int playerTurn,int slot,boolean dead) {
        if(source!=monster || (occupantGeneration==0?(dead ? completed>=playerTurn : playerTurn!=completed+1):(birthGlobalTurn>=playerTurn || lastExecutionGlobalTurn>=playerTurn || (!dead && lastExecutionGlobalTurn!=playerTurn-1 && !(completed==0 && birthGlobalTurn==playerTurn-1))))) invalidate("history_gap");
        if("Sentry".equals(id)) for(int i=0;i<executed.size();++i)
            if(executed.get(i)!=((slot+completed-executed.size()+i)%2==0?3:4)) invalidate("history_gap");
        Map<String,Object> out=new LinkedHashMap<>();
        out.put("schemaVersion",dynamic()?3:"WrithingMass".equals(id)?2:1); out.put("epoch",epoch); out.put("generation",generation);
        // Between the first-form death and its queued duplicate SetMoveAction(3)
        // (a source card's grid, problem 90) Rebirth is already the known next
        // move; the row reports one known transition and the producer emits the
        // duplicate as a pending MONSTER_SET_MOVE.
        boolean rebirthWindow=rebirthDuplicatePending && knownNextMove==3 && !inRoll && !knownTurn;
        boolean complete=failure==null && !inRoll && !knownTurn && !hiddenSetterScope && (!rebirthDuplicatePending || rebirthWindow) && !publicDuplicatePending && pendingThefts==0 && (pending || (pendingDirect && hiddenSetterSeen) || knownNextMove!=0 || dead);
        out.put("complete",complete);
        if(!complete) { out.put("reason",failure==null?"roll_unsettled":failure); return out; }
        if(occupantGeneration>0) {
            out.put("historySchemaVersion",out.get("schemaVersion"));out.put("schemaVersion",4);
            out.put("occupantGeneration",occupantGeneration);out.put("birthGlobalTurn",birthGlobalTurn);
            out.put("birthKind",birthKind);out.put("birthParentSlot",birthParentSlot);out.put("birthParentGeneration",birthParentGeneration);
            out.put("lastExecutionGlobalTurn",lastExecutionGlobalTurn);out.put("rollGlobalTurn",rollGlobalTurn);
        }
        if(latent(id)){out.put("latentDamageMask",latentDamageMask);out.put("latentDamageExecutions",damageExecutions);}
        out.put("monsterId",id); out.put("slot",slot); out.put("completedTurns",completed);
        out.put("executedMoves",new ArrayList<Integer>(executed));
        List<List<Object>> predicates=new ArrayList<>();
        if(!dead) for(Map.Entry<Integer,Boolean> entry:attackPredicates.entrySet())
            predicates.add(Arrays.<Object>asList(entry.getKey(),entry.getValue()));
        out.put("pendingAttackPredicates",predicates);
        out.put("pendingMoveRolls",dead || knownNextMove!=0?0:rollHistory.size());
        if("WrithingMass".equals(id)) {
            out.put("totalRolls",totalRolls);
            out.put("pendingRollInputs",dead?Collections.emptyList():new ArrayList<Map<String,Object>>(rollHistory));
        } out.put("publicMisc",publicMisc);
        if(dynamic()) {
            out.put("totalRolls",totalRolls);out.put("knownTransitions",knownTransitions);
            out.put("knownRollPredecessor",!dead && torchConstructorPredecessor && pending?"torch_constructor_tackle":!dead && darkInterveningRoll && knownNextMove==4?"darkling_reincarnate_before_regrow":!dead && shellPredecessor?"shelled_stun_fell":!dead && hexPredecessor?"hexaghost_inferno_predecessor":!dead && lagaPredecessor?"lagavulin_sleep_predecessor":null);
        }
        if(thief()) {out.put("pendingDirectMoveChoice",!dead && pendingDirect?1:0);out.put("directChoices",directChoices);}
        if("Lagavulin".equals(id)) {out.put("publicAsleep",lagaAsleep);out.put("publicSleepTurns",lagaSleeps);}
        if(knownLifecycle(id) || dynamic()) {
            Map<String,Object> proof=null;
            if(!dead && knownNextMove!=0) {
                proof=new LinkedHashMap<>();proof.put("kind",act4(id)?"act4_public_cycle":remaining(id)?(split(id)?(knownNextMove==3?"public_split_override":"slime_boss_public_cycle"):"Darkling".equals(id)?"darkling_public_regrow":"public_deterministic_transition_v1"):"AwakenedOne".equals(id)?"awakened_public_rebirth":thief()?"thief_public_cycle":"Lagavulin".equals(id)?(knownNextMove==4?"public_stun_override":knownNextMove==1?"lagavulin_awake_event":"lagavulin_natural_wake"):"Hexaghost".equals(id)?"hexaghost_activate":"TheGuardian".equals(id)?(knownNextMove==1?"guardian_defensive_override":"guardian_public_cycle"):dynamic()?(knownNextMove==4?"public_stun_override":"byrd_headbutt_fly"):"AcidSlime_S".equals(id)?"acid_slime_s_alternation":"public_deterministic_transition_v1");proof.put("move",knownNextMove);
            }
            out.put("knownNextMove",proof);
        }
        out.put("firstHp",firstHp); out.put("firstMaxHp",firstMaxHp); out.put("firstAlive",firstAlive);
        out.put("playerConstricted",playerConstricted); out.put("aliveCount",aliveCount); out.put("rollHp",rollHp); out.put("rollMaxHp",rollMaxHp);
        return out;
    }

    static boolean monsterPowerAllowed(String id, String monster) {
        // Vanilla POWER_IDs (RunicDomeTrackerTest checks them against the jar): Block Return, Corpse Explosion and Mark
        // are "BlockReturnPower", "CorpseExplosionPower" and "PathToVictoryPower".
        return Arrays.asList("Strength","Artifact","Weak","Weakened","Vulnerable","BlockReturnPower","Choked","CorpseExplosionPower",
                "Lockon","PathToVictoryPower","Metallicize","Plated Armor","Poison","Regenerate","Shackled").contains(id)
                || (split(monster) && "Split".equals(id))
                || (("FuzzyLouseNormal".equals(monster)||"FuzzyLouseDefensive".equals(monster)) && "Curl Up".equals(id))
                || ("Darkling".equals(monster) && "Life Link".equals(id)) // RegrowPower.POWER_ID
                || (("Dagger".equals(monster)||"TorchHead".equals(monster)||"BronzeOrb".equals(monster)||monster.startsWith("Gremlin")) && "Minion".equals(id))
                || ("BronzeOrb".equals(monster) && "Stasis".equals(id))
                || ("Cultist".equals(monster) && "Ritual".equals(id))
                || ("FungiBeast".equals(monster) && "Spore Cloud".equals(id))
                || ("GremlinNob".equals(monster) && "Anger".equals(id))
                || ("SnakePlant".equals(monster) && "Malleable".equals(id))
                || ("SphericGuardian".equals(monster) && "Barricade".equals(id))
                || ("Exploder".equals(monster) && "Explosive".equals(id))
                || ("Orb Walker".equals(monster) && "Generic Strength Up Power".equals(id))
                || ("Nemesis".equals(monster) && "Intangible".equals(id))
                || ("GiantHead".equals(monster) && "Slow".equals(id))
                || (("Donu".equals(monster) || "Deca".equals(monster)) && "Plated Armor".equals(id))
                || ("Spiker".equals(monster) && "Thorns".equals(id))
                || ("BookOfStabbing".equals(monster) && "Painful Stabs".equals(id))
                || ("TimeEater".equals(monster) && "Time Warp".equals(id))
                || ("GremlinWarrior".equals(monster) && "Angry".equals(id))
                || ("Transient".equals(monster) && ("Shifting".equals(id) || "Fading".equals(id)))
                || ("WrithingMass".equals(monster) && ("Malleable".equals(id) || "Compulsive".equals(id)))
                || ("Byrd".equals(monster) && "Flight".equals(id))
                || ("AwakenedOne".equals(monster) && ("Curiosity".equals(id) || "Unawakened".equals(id)))
                || (("Looter".equals(monster) || "Mugger".equals(monster)) && "Thievery".equals(id))
                || ("TheGuardian".equals(monster) && ("Mode Shift".equals(id) || "Sharp Hide".equals(id)))
                || ("CorruptHeart".equals(monster) && ("Invincible".equals(id) || "BeatOfDeath".equals(id) || "Painful Stabs".equals(id)))
                || (("SpireShield".equals(monster) || "SpireSpear".equals(monster)) && "BackAttack".equals(id));
    }
}
