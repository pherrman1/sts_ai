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
    private static final java.util.IdentityHashMap<AbstractMonster,Integer> slots=new java.util.IdentityHashMap<>();
    private static final AbstractMonster[] occupants=new AbstractMonster[5];
    private static final int[] occupantGenerations=new int[5];
    private static final java.util.Set<AbstractMonster> born=java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<AbstractMonster,Boolean>());
    private static final java.util.Set<AbstractMonster> initialized=java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<AbstractMonster,Boolean>());
    private static final java.util.Set<AbstractMonster> torchConstructed=java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<AbstractMonster,Boolean>());
    private static final java.util.Set<AbstractMonster> damageArmed=java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<AbstractMonster,Boolean>());
    private static final java.util.IdentityHashMap<AbstractMonster,java.util.List<java.util.Map<String,Object>>> damageObservations=new java.util.IdentityHashMap<>();
    private static AbstractMonster executingParent;
    private static int executingParentMove;
    private static boolean ready,constructingTorch;
    private static String bindingFailure;
    static String bindingFailure(){return bindingFailure;}
    static int occupantGeneration(AbstractMonster m){Integer slot=slots.get(m);return slot==null?0:occupantGenerations[slot];}
    private static int capacity;
    static java.util.IdentityHashMap<AbstractMonster,Integer> emittedSlots() {
        if(!ready || group!=AbstractDungeon.getMonsters())return null;
        java.util.IdentityHashMap<AbstractMonster,Integer> result=new java.util.IdentityHashMap<>();
        for(int slot=0;slot<capacity;++slot)if(occupants[slot]!=null && group.monsters.contains(occupants[slot]))result.put(occupants[slot],slot);
        for(AbstractMonster m:group.monsters)if(!slots.containsKey(m))invalidate("unregistered_occupant");
        return result;
    }
    static int declaredCapacity() {return ready?capacity:0;}
    static boolean publicLatentAttackActive(AbstractMonster m) {return active() && damageArmed.contains(m);}
    static void observePublicLatentDamage(AbstractMonster m,PublicLatentDamageCapture.Observation o) {
        if(!damageArmed.remove(m)){invalidate("latent_damage_source");return;}
        RunicDomeTracker t=tracker(m);if(t==null)return;
        t.filterLatentDamage(o.filterMask(t.latentDamageMask()));
        damageObservations.get(m).add(o.toMap());
    }
    static void beginParentTurn(AbstractMonster m) {if("SlimeBoss".equals(m.id))beginKnownTurn(m);else execute(m);if(ready){executingParent=m;executingParentMove=m.nextMove;}}
    static void endParentTurn(AbstractMonster m) {if(executingParent==m)executingParent=null;}
    static void torchConstructor(boolean before) {constructingTorch=before;}
    static void torchConstructorResult(AbstractMonster m) {if(ready && "TorchHead".equals(m.id))torchConstructed.add(m);}
    static void constructed(AbstractMonster child) {
        if(!ready)return;
        if(slots.containsKey(child))return;
        AbstractMonster parent=executingParent;
        if(parent==null || !slots.containsKey(parent)){invalidate("unqualified_birth_source");return;}
        int parentSlot=slots.get(parent),chosen=-1;String kind="summon";
        String id=parent.id;
        if(RunicDomeTracker.split(id)) {
            kind="split";int expected=3;
            RunicDomeTracker pt=tracker(parent);
            if(pt==null || executingParentMove!=expected || child.currentHealth!=parent.currentHealth || child.maxHealth!=parent.currentHealth){invalidate("split_birth_source");return;}
            if("SlimeBoss".equals(id)) chosen="SpikeSlime_L".equals(child.id)?0:"AcidSlime_L".equals(child.id)?2:-1;
            else if(child.id.equals("AcidSlime_L".equals(id)?"AcidSlime_M":"SpikeSlime_M")) chosen=occupants[parentSlot]==parent?parentSlot:parentSlot+1;
        } else {
            int[] order="BronzeAutomaton".equals(id)?new int[]{0,2}:"TheCollector".equals(id)?new int[]{1,0}:"GremlinLeader".equals(id)?new int[]{1,2,0}:"Reptomancer".equals(id)?new int[]{4,1,3,0}:new int[0];
            boolean family="BronzeAutomaton".equals(id)?"BronzeOrb".equals(child.id):"TheCollector".equals(id)?"TorchHead".equals(child.id):"Reptomancer".equals(id)?"Dagger".equals(child.id):"GremlinLeader".equals(id)&&java.util.Arrays.asList("GremlinFat","GremlinThief","GremlinWarrior","GremlinWizard","GremlinTsundere").contains(child.id);
            if(family)for(int slot:order)if(occupants[slot]==null || occupants[slot].isDeadOrEscaped()){chosen=slot;break;}
        }
        if(chosen<0 || chosen>=5){invalidate("birth_slot");return;}
        int parentGeneration=tracker(parent).occupantGeneration();
        slots.put(child,chosen);occupants[chosen]=child;++occupantGenerations[chosen];capacity=Math.max(capacity,chosen+1);
        identities.add(child);RunicDomeTracker t=new RunicDomeTracker(child,child.id,epoch,AbstractDungeon.actNum,capacity,AbstractDungeon.ascensionLevel);
        t.bind(occupantGenerations[chosen],com.megacrit.cardcrawl.actions.GameActionManager.turn,kind,parentSlot,parentGeneration);
        if("TorchHead".equals(child.id)){if(!torchConstructed.remove(child))t.invalidate("missing_torch_constructor");else t.constructorTackle(child);}
        trackers.add(t);born.add(child);damageObservations.put(child,new java.util.ArrayList<java.util.Map<String,Object>>());
    }
    static void beforeSpawnInit(AbstractMonster child) {
        if(!ready)return;
        if(!born.contains(child) || !initialized.add(child))invalidate("birth_initialization");
    }
    static void publicOverride(AbstractMonster m,int move) {
        if(!active() || group==null)return;RunicDomeTracker t=tracker(m);if(t==null)return;
        boolean threshold="Darkling".equals(m.id)?m.halfDead && m.currentHealth<=0:m.currentHealth<=m.maxHealth/2 || t.lastExecutedMove()==3;
        t.publicOverride(m,move,threshold);
    }

    private static long epoch;
    static boolean active() { return AbstractDungeon.player!=null && AbstractDungeon.player.hasRelic("Runic Dome"); }
    static void clear() { trackers.clear(); identities.clear(); group=null;ready=false;slots.clear();born.clear();torchConstructed.clear();initialized.clear();damageArmed.clear();damageObservations.clear();java.util.Arrays.fill(occupants,null);java.util.Arrays.fill(occupantGenerations,0);capacity=0;executingParent=null;bindingFailure=null; }
    static void begin(MonsterGroup current) {
        clear();
        java.util.IdentityHashMap<AbstractMonster,Integer> initial=STSModelInspector.emittedMonsterSlots(STSModelInspector.encounterName(AbstractDungeon.getCurrRoom()));
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
            Integer slot=initial.get(monster);if(slot==null || slot<0 || slot>=5){tracker.invalidate("initial_slot");slot=identities.size()-1;}
            slots.put(monster,slot);occupants[slot]=monster;occupantGenerations[slot]=1;capacity=Math.max(capacity,slot+1);
            tracker.bind(1,0,"initial",-1,0);initialized.add(monster);damageObservations.put(monster,new java.util.ArrayList<java.util.Map<String,Object>>());
            trackers.add(tracker);
        }
        if(current.monsters.size()==1 && "BronzeAutomaton".equals(current.monsters.get(0).id))capacity=3;
        ready=true;
    }
    static RunicDomeTracker tracker(AbstractMonster monster) {
        int slot=identities.indexOf(monster);
        if(slot<0) { invalidate("monster_replaced"); return null; }
        RunicDomeTracker t=trackers.get(slot);t.globalTurn(com.megacrit.cardcrawl.actions.GameActionManager.turn);return t;
    }
    static void invalidate(String reason) { if(bindingFailure==null)bindingFailure=reason; for(RunicDomeTracker t:trackers) t.invalidate(reason); }
    static void beginRoll(AbstractMonster monster) {
        if(!active() || group==null) return;
        RunicDomeTracker t=tracker(monster); if(t==null) return;
        if(damageArmed.contains(monster))t.invalidate("missing_latent_damage_observation");
        if(monster.isDeadOrEscaped() && !monster.halfDead) {t.beginTerminalRoll(monster);return;}
        AbstractMonster first=group.monsters.get(0);
        int alive=0; for(AbstractMonster m:group.monsters) if(!m.isDeadOrEscaped() && !m.halfDead) ++alive;
        t.beginRoll(monster,monster.currentHealth,monster.maxHealth,first.currentHealth,first.maxHealth,!first.isDeadOrEscaped() && !first.halfDead,alive,AbstractDungeon.player.hasPower("Constricted"));
    }
    static void endRoll(AbstractMonster monster) { if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.endRoll(monster); } }
    static void setMove(AbstractMonster monster) { if(constructingTorch && "TorchHead".equals(monster.id))return; if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.setMove(monster); } }
    static void execute(AbstractMonster monster) {
        // Only called at entry to the audited concrete takeTurn methods. The
        // move is public because it is now executing, never while queued.
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null){if(damageArmed.contains(monster))t.invalidate("missing_latent_damage_observation");t.execute(monster,monster.nextMove);if(RunicDomeTracker.latent(monster.id) && monster.nextMove==3)damageArmed.add(monster);} }
    }
    static void beginAcidTurn(AbstractMonster monster) {
        if(active() && group!=null) { RunicDomeTracker t=tracker(monster); if(t!=null)t.beginKnownTurn(monster,monster.nextMove); }
    }
    static void beginKnownTurn(AbstractMonster monster) {
        if(active() && group!=null) {
            RunicDomeTracker t=tracker(monster);int alive=0;
            for(AbstractMonster m:group.monsters) if(!m.isDeadOrEscaped() && !m.halfDead) ++alive;
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
        if(group!=AbstractDungeon.getMonsters()) invalidate("monster_replaced");
        emittedSlots();
        if(!damageArmed.isEmpty())invalidate("missing_latent_damage_observation");
        for(AbstractMonster monster:group.monsters)
            for(com.megacrit.cardcrawl.powers.AbstractPower power:monster.powers)
                if(!RunicDomeTracker.monsterPowerAllowed(power.ID,monster.id)) invalidate("unsupported_monster_power_domain");
        java.util.List<java.util.Map<String,Object>> rows=new java.util.ArrayList<>();
        boolean complete=true;
        for(int slot=0;slot<capacity;++slot) {
            AbstractMonster m=occupants[slot];
            if(m==null){java.util.Map<String,Object> absent=new java.util.LinkedHashMap<>();absent.put("slot",slot);absent.put("absent",true);absent.put("occupantGeneration",0);rows.add(absent);continue;}
            if(!initialized.contains(m) || !group.monsters.contains(m))invalidate("unsettled_birth");
            if((m.halfDead && !"AwakenedOne".equals(m.id) && !"Darkling".equals(m.id)) || (m.isEscaping && !"Looter".equals(m.id) && !"Mugger".equals(m.id))) invalidate("unsupported_monster_lifecycle");
            java.util.Map<String,Object> row=tracker(m).snapshot(m,
                    com.megacrit.cardcrawl.actions.GameActionManager.turn,slot,m.isDeadOrEscaped() && !m.halfDead);
            if(RunicDomeTracker.latent(m.id))row.put("latentDamageObservations",damageObservations.get(m));
            rows.add(row); complete &= Boolean.TRUE.equals(row.get("complete"));
        }
        java.util.Map<String,Object> out=new java.util.LinkedHashMap<>();
        out.put("schemaVersion",3);out.put("epoch",epoch);out.put("complete",complete);out.put("monsters",rows);
        return new Gson().toJson(out);
    }
}
