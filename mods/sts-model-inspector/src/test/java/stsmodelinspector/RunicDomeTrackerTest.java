package stsmodelinspector;

import java.util.*;

public final class RunicDomeTrackerTest {
    private static void applyConstructorPatch(javassist.CtBehavior constructor,Class<?> patchClass) throws Exception {
        javassist.CtClass patch=constructor.getDeclaringClass().getClassPool().get(patchClass.getName());
        com.evacipated.cardcrawl.modthespire.lib.SpirePatch annotation=
                (com.evacipated.cardcrawl.modthespire.lib.SpirePatch)patch.getAnnotation(com.evacipated.cardcrawl.modthespire.lib.SpirePatch.class);
        if(!com.evacipated.cardcrawl.modthespire.lib.SpirePatch.CONSTRUCTOR.equals(annotation.method()))
            throw new AssertionError("expected constructor patch "+patchClass.getName());
        int applied=0;
        for(javassist.CtMethod method:patch.getDeclaredMethods()) {
            com.evacipated.cardcrawl.modthespire.patcher.PatchInfo info;
            if(method.hasAnnotation(com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch.class))
                info=new com.evacipated.cardcrawl.modthespire.patcher.PostfixPatchInfo(constructor,method);
            else if(method.hasAnnotation(com.evacipated.cardcrawl.modthespire.lib.SpireRawPatch.class))
                info=new com.evacipated.cardcrawl.modthespire.patcher.RawPatchInfo(constructor,patchClass.getDeclaredMethod(method.getName(),javassist.CtBehavior.class));
            else continue;
            info.setSpirePatch(annotation).doPatch();++applied;
        }
        if(applied!=1)throw new AssertionError("constructor patch coverage drift "+patchClass.getName());
    }
    private static void rejectLegacySpawnBinding(javassist.ClassPool pool) throws Exception {
        javassist.CtClass spawn=pool.get("com.megacrit.cardcrawl.actions.common.SpawnMonsterAction");
        javassist.CtConstructor constructor=spawn.getDeclaredConstructor(new javassist.CtClass[]{pool.get("com.megacrit.cardcrawl.monsters.AbstractMonster"),javassist.CtClass.booleanType,javassist.CtClass.intType});
        javassist.CtClass legacy=pool.makeClass("stsmodelinspector.LegacySpawnConstructorPatch");
        javassist.CtMethod postfix=javassist.CtNewMethod.make("public static void postfix(com.megacrit.cardcrawl.monsters.AbstractMonster m) {}",legacy);
        legacy.addMethod(postfix);
        try {
            new com.evacipated.cardcrawl.modthespire.patcher.PostfixPatchInfo(constructor,postfix).doPatch();
            throw new AssertionError("ModTheSpire accepted the broken receiver-less Spawn postfix");
        } catch(com.evacipated.cardcrawl.modthespire.patcher.PatchingException expected) {
            if(!expected.toString().contains("postfix(com.megacrit.cardcrawl.actions.common.SpawnMonsterAction)"))throw expected;
        } finally { spawn.detach();legacy.detach(); }
    }
    // Plays `moves` through a bound Act-4 tracker; expected[i] is the public move proven before move i (0 = random roll).
    private static RunicDomeTracker act4Run(String id,int[] moves,int[] expected,int hp) {
        Object m=new Object();RunicDomeTracker t=new RunicDomeTracker(m,id,23,4,"CorruptHeart".equals(id)?1:2,20);
        t.bind(1,0,"initial",-1,0);t.globalTurn(0);t.beginRoll(m,hp,hp,hp,hp,true,1);t.setMove(m);t.endRoll(m);
        for(int i=0;i<moves.length;++i) {
            Map<String,Object> row=t.snapshot(m,i+1,0,false);complete(row);
            Object proof=row.get("knownNextMove");
            if(expected[i]==0?(proof!=null || !row.get("pendingMoveRolls").equals(1))
                    :(!row.get("pendingMoveRolls").equals(0) || !(proof instanceof Map) || !"act4_public_cycle".equals(((Map<?,?>)proof).get("kind"))
                        || !Integer.valueOf(expected[i]).equals(((Map<?,?>)proof).get("move"))))
                throw new AssertionError(id+" move "+i+" proof "+row);
            t.globalTurn(i+1);t.execute(m,moves[i]);t.beginRoll(m,hp,hp,hp,hp,true,1);t.setMove(m);t.endRoll(m);
        }
        return t;
    }
    private static void complete(Map<String,Object> snapshot) {
        if(!Boolean.TRUE.equals(snapshot.get("complete"))) throw new AssertionError(snapshot);
    }
    private static void rejected(Map<String,Object> snapshot) {
        if(!Boolean.FALSE.equals(snapshot.get("complete"))) throw new AssertionError("unproven Dome accepted: "+snapshot);
    }
    public static void main(String[] args) throws Exception {
        // Source-shaped second-generation split/summon: the Java list keeps
        // an old corpse, while the observed native slot belongs to its child.
        Object retired=new Object(), replacement=new Object(), unboundOccupant=new Object();
        java.util.Map<Object,Integer> retiredSlots=new java.util.IdentityHashMap<>();retiredSlots.put(retired,2);
        Object[] current=new Object[5];current[2]=replacement;
        if(!RunicDomeCapture.retiredDeadOccupant(retired,true,false,true,retiredSlots,current)
                || RunicDomeCapture.retiredDeadOccupant(retired,false,false,true,retiredSlots,current)
                || RunicDomeCapture.retiredDeadOccupant(retired,true,true,true,retiredSlots,current)
                || RunicDomeCapture.retiredDeadOccupant(retired,true,false,false,retiredSlots,current)
                || RunicDomeCapture.retiredDeadOccupant(unboundOccupant,true,false,true,retiredSlots,current))
            throw new AssertionError("retired dead occupant lost exact replacement proof");
        current[2]=retired;
        if(RunicDomeCapture.retiredDeadOccupant(retired,true,false,true,retiredSlots,current))
            throw new AssertionError("current native corpse was hidden");
        current[2]=null;
        if(RunicDomeCapture.retiredDeadOccupant(retired,true,false,true,retiredSlots,current))
            throw new AssertionError("empty slot fabricated a replacement");
        Object monster=new Object();
        for(String id:Arrays.asList("JawWorm","Cultist")) {
            RunicDomeTracker a=new RunicDomeTracker(monster,id,1,1,1);
            RunicDomeTracker b=new RunicDomeTracker(monster,id,1,1,1);
            for(RunicDomeTracker tracker:Arrays.asList(a,b)) {
                tracker.beginRoll(monster,42,42); tracker.setMove(monster); tracker.endRoll(monster);
            }
            Map<String,Object> first=a.snapshot(monster,1); complete(first);
            // No API accepts a private roll result, history, damage, or RNG.
            // Different unexecuted realizations cannot change the projection.
            if(!first.equals(b.snapshot(monster,1)) || first.containsKey("nextMove") || first.containsKey("miscInfo"))
                throw new AssertionError("hidden result leaked");
            a.execute(monster,id.equals("JawWorm")?1:3);
            a.beginRoll(monster,30,42); a.setMove(monster); a.endRoll(monster);
            Map<String,Object> second=a.snapshot(monster,2); complete(second);
            if(!second.get("completedTurns").equals(1) || !second.get("generation").equals(3L)
                    || !second.get("rollHp").equals(30) || second.equals(first)) throw new AssertionError("executed public history lost");
            a.execute(monster,id.equals("JawWorm")?2:1);
            a.beginRoll(monster,20,42); a.setMove(monster); a.endRoll(monster);
            complete(a.snapshot(monster,3));
            a.execute(monster,id.equals("JawWorm")?3:1);
            a.beginRoll(monster,18,42); a.setMove(monster); a.endRoll(monster);
            Map<String,Object> fourth=a.snapshot(monster,4); complete(fourth);
            if(!fourth.get("executedMoves").equals(Arrays.asList(id.equals("JawWorm")?2:1,id.equals("JawWorm")?3:1)))
                throw new AssertionError("executed history order");
        }
        RunicDomeTracker t=new RunicDomeTracker(monster,"JawWorm",1,1,1);
        rejected(t.snapshot(monster,1)); // never rolled / hot attachment
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.beginRoll(monster,42,42);
        rejected(t.snapshot(monster,1)); // hook exception / unresolved scope
        t.endRoll(monster); t.beginRoll(monster,42,42); rejected(t.snapshot(monster,1)); // hidden reroll
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.setMove(monster); rejected(t.snapshot(monster,1));
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.beginRoll(monster,42,42);t.endRoll(monster);
        rejected(t.snapshot(new Object(),1)); // spawn/replacement cannot inherit history
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1);t.beginRoll(monster,42,42);t.endRoll(monster);
        rejected(t.snapshot(monster,2)); // missing public turn hook
        for(String id:Arrays.asList("AcidSlime_L","Darkling"))
            rejected(new RunicDomeTracker(monster,id,1,1,1).snapshot(monster,1));
        rejected(new RunicDomeTracker(monster,"JawWorm",1,4,1).snapshot(monster,1));
        rejected(new RunicDomeTracker(monster,"JawWorm",1,1,6).snapshot(monster,1));
        // Every audited concrete takeTurn has one trailing RollMoveAction.
        for(String id:Arrays.asList("FungiBeast","SlaverBlue","SlaverRed","AcidSlime_M","SpikeSlime_M","GremlinNob")) {
            RunicDomeTracker multi=new RunicDomeTracker(monster,id,7,1,2);
            multi.beginRoll(monster,35,35,44,44,true,2);multi.endRoll(monster);
            complete(multi.snapshot(monster,1,1,false));
            multi.execute(monster,"GremlinNob".equals(id)?3:1);
            multi.beginRoll(monster,30,35,0,44,false,1);multi.endRoll(monster);
            Map<String,Object> state=multi.snapshot(monster,2,1,false);complete(state);
            if(!state.get("slot").equals(1) || !state.get("firstHp").equals(0)
                    || !state.get("aliveCount").equals(1)) throw new AssertionError("roll group inputs lost");
            Map<String,Object> corpse=multi.snapshot(monster,3,1,true);complete(corpse);
            if(!corpse.get("pendingMoveRolls").equals(0)) throw new AssertionError("dead slot retained private move");
        }
        for(int slot=0;slot<3;++slot) {
            RunicDomeTracker sentry=new RunicDomeTracker(monster,"Sentry",11,1,3);
            for(int completed=0;completed<4;++completed) {
                sentry.beginRoll(monster,35,40,35,40,true,3);sentry.endRoll(monster);
                complete(sentry.snapshot(monster,completed+1,slot,false));
                sentry.execute(monster,(slot+completed)%2==0?3:4);
            }
        }
        RunicDomeTracker spike=new RunicDomeTracker(monster,"SpikeSlime_S",12,1,5);
        spike.beginRoll(monster,10,10);spike.endRoll(monster);spike.execute(monster,1);
        spike.beginRoll(monster,8,10);spike.endRoll(monster);complete(spike.snapshot(monster,2,4,false));
        // Small Acid Slime's only RNG is its initial roll. Later moves are
        // proven by the scoped vanilla takeTurn override, never a queued read.
        for(int opening:new int[]{1,2}) {
            RunicDomeTracker acid=new RunicDomeTracker(monster,"AcidSlime_S",13,1,2);
            acid.beginRoll(monster,10,10);acid.setMove(monster);acid.endRoll(monster);
            Map<String,Object> initial=acid.snapshot(monster,1,1,false);complete(initial);
            if(initial.get("knownNextMove")!=null || !initial.get("pendingMoveRolls").equals(1)) throw new AssertionError("initial Acid roll exposed");
            int move=opening;
            for(int completed=1;completed<=4;++completed) {
                acid.beginKnownTurn(monster,move);
                acid.knownOverride(monster,3-move);acid.setMove(monster);acid.endKnownTurn(monster);
                Map<String,Object> state=acid.snapshot(monster,completed+1,1,false);complete(state);
                Map<?,?> proof=(Map<?,?>)state.get("knownNextMove");
                if(!proof.get("kind").equals("acid_slime_s_alternation") || !proof.get("move").equals(3-move)
                        || !state.get("pendingMoveRolls").equals(0) || !state.get("generation").equals(2L*completed+1))
                    throw new AssertionError("Acid known transition lost");
                acid.observeAttack(monster,3-move==1); // deterministic query stores no hidden predicate
                if(!acid.snapshot(monster,completed+1,1,false).get("pendingAttackPredicates").equals(Collections.emptyList()))
                    throw new AssertionError("known Acid acquired hidden constraint");
                move=3-move;
            }
            Map<String,Object> dead=acid.snapshot(monster,6,1,true);complete(dead);
            if(dead.get("knownNextMove")!=null) throw new AssertionError("dead Acid kept next intent");
        }
        for(int mutation=0;mutation<6;++mutation) {
            RunicDomeTracker acid=new RunicDomeTracker(monster,"AcidSlime_S",13,1,1);
            acid.beginRoll(monster,10,10);acid.endRoll(monster);acid.beginKnownTurn(monster,1);
            if(mutation==0) { acid.endKnownTurn(monster); } // missing override
            if(mutation==1) { acid.setMove(monster);acid.endKnownTurn(monster); } // unaudited callsite
            if(mutation==2) { acid.knownOverride(monster,1);acid.setMove(monster);acid.endKnownTurn(monster); }
            if(mutation>=3) {
                acid.knownOverride(monster,2);acid.setMove(monster);acid.endKnownTurn(monster);
                if(mutation==3)acid.setMove(monster); // override outside executing turn
                if(mutation==4)acid.beginRoll(monster,10,10); // unexpected RNG lifecycle
                if(mutation==5)acid.observeAttack(monster,true); // contradicted known Lick
            }
            rejected(acid.snapshot(monster,2));
        }
        // All ordinary roll lifecycles execute public moves and defer exactly
        // one successor; counters survive beyond the two-move window.
        String[] ordinary={"Centurion","Healer","Chosen","SnakePlant","Snecko","SphericGuardian",
                "Exploder","Repulsor","Maw","Nemesis","Orb Walker","GiantHead","Donu","Deca","Spiker",
                "Serpent","SlaverBoss","GremlinFat","BookOfStabbing","TimeEater"};
        int[][] sequences={{1,2,1},{3,1,2},{5,4,3},{1,1,2},{1,2,3},{2,4,1,3,1},
                {1,1},{2,1,2},{2,5,4},{2,4,3},{1,2,1},{1,3,1,3,2,2},{2,0,2},{0,2,0},
                {2,2,1,2},{2,1,3},{2,2,2},{2,2,2},{1,2,1,1,2},{2,3,5,4}};
        for(int i=0;i<ordinary.length;++i) {
            RunicDomeTracker tracker=new RunicDomeTracker(monster,ordinary[i],33,3,2);
            tracker.beginRoll(monster,40,40,40,40,true,2,true);tracker.endRoll(monster);
            complete(tracker.snapshot(monster,1));
            int completed=0;
            for(int move:sequences[i]) {
                tracker.execute(monster,move);++completed;
                tracker.beginRoll(monster,30,40,25,40,true,2,true);tracker.endRoll(monster);
                Map<String,Object> state=tracker.snapshot(monster,completed+1);complete(state);
                if(!state.get("playerConstricted").equals(true) || !state.get("pendingMoveRolls").equals(1))
                    throw new AssertionError("ordinary public roll input lost: "+ordinary[i]);
            }
            Map<String,Object> state=tracker.snapshot(monster,completed+1);
            int misc=ordinary[i].equals("Spiker")?3:ordinary[i].equals("BookOfStabbing")?4:ordinary[i].equals("TimeEater")?1:0;
            if(!state.get("publicMisc").equals(misc)) throw new AssertionError("public counter lost "+ordinary[i]);
            tracker.setMove(monster);rejected(tracker.snapshot(monster,completed+1));
        }
        String[] knownIds={"GremlinThief","GremlinWarrior","GremlinWizard","GremlinTsundere","BanditBear","BanditLeader","BanditChild","Transient"};
        int[][] knownMoves={{1,1,1,1},{1,1,1,1},{2,2,2,1,2},{1,1,2,2},{2,3,1,3},{2,3,1,3},{1,1,1,1},{1,1,1,1}};
        int[][] knownNext={{1,1,1,1},{1,1,1,1},{2,2,1,2,2},{1,2,2,2},{3,1,3,1},{3,1,3,1},{1,1,1,1},{1,1,1,1}};
        for(int i=0;i<knownIds.length;++i) {
            RunicDomeTracker known=new RunicDomeTracker(monster,knownIds[i],34,2,3);
            known.beginRoll(monster,40,40);known.endRoll(monster);
            for(int j=0;j<knownMoves[i].length;++j) {
                known.beginKnownTurn(monster,knownMoves[i][j],j==0?3:1);
                // Setter callback may arrive in a queued SetMoveAction; capture
                // is incomplete until it has executed with the derived byte.
                Map<String,Object> unsettled=known.snapshot(monster,j+2);
                if(Boolean.TRUE.equals(unsettled.get("complete"))) throw new AssertionError("unsettled known setter accepted");
                known.knownOverride(monster,knownNext[i][j]);known.setMove(monster);known.endKnownTurn(monster);
                Map<String,Object> state=known.snapshot(monster,j+2);complete(state);
                Map<?,?> proof=(Map<?,?>)state.get("knownNextMove");
                if(!proof.get("move").equals(knownNext[i][j]) || !proof.get("kind").equals("public_deterministic_transition_v1")
                        || !state.get("pendingMoveRolls").equals(0)) throw new AssertionError("known successor lost "+knownIds[i]);
            }
        }
        RunicDomeTracker reactive=new RunicDomeTracker(monster,"WrithingMass",35,3,1);
        for(int hp:new int[]{40,38,35}) {
            reactive.beginRoll(monster,hp,40);reactive.setMove(monster);reactive.endRoll(monster);
            reactive.observeAttack(monster,hp!=38);
        }
        Map<String,Object> reactiveState=reactive.snapshot(monster,1);complete(reactiveState);
        if(!reactiveState.get("schemaVersion").equals(2) || !reactiveState.get("pendingMoveRolls").equals(3)
                || !reactiveState.get("pendingAttackPredicates").equals(Arrays.asList(Arrays.asList(1,true),Arrays.asList(2,false),Arrays.asList(3,true))))
            throw new AssertionError("indexed reactive information lost");
        reactive.execute(monster,1);reactive.beginRoll(monster,35,40);reactive.endRoll(monster);
        reactiveState=reactive.snapshot(monster,2);complete(reactiveState);
        if(!reactiveState.get("pendingMoveRolls").equals(1) || !reactiveState.get("pendingAttackPredicates").equals(Collections.emptyList())
                || !reactiveState.get("totalRolls").equals(4)) throw new AssertionError("reactive chain did not reset at public execution");
        RunicDomeTracker champ=new RunicDomeTracker(monster,"Champ",36,2,1);
        champ.beginRoll(monster,400,400);champ.endRoll(monster);
        champ.execute(monster,2);champ.beginRoll(monster,180,400);champ.endRoll(monster);
        champ.execute(monster,7);champ.beginRoll(monster,180,400);champ.endRoll(monster);
        Map<String,Object> champState=champ.snapshot(monster,3);complete(champState);
        if(!champState.get("publicMisc").equals(5)) throw new AssertionError("Champ public forge/anger count lost");
        RunicDomeTracker hardJaw=new RunicDomeTracker(monster,"JawWorm",37,3,3);
        hardJaw.beginRoll(monster,40,40);hardJaw.endRoll(monster);hardJaw.execute(monster,2);
        hardJaw.beginRoll(monster,40,40);hardJaw.endRoll(monster);complete(hardJaw.snapshot(monster,2));
        RunicDomeTracker red=new RunicDomeTracker(monster,"SlaverRed",9,1,2);
        int turn=1;
        red.beginRoll(monster,40,40);red.endRoll(monster);
        for(int move:new int[]{1,2,3,1,3}) {
            red.execute(monster,move);red.beginRoll(monster,30,40);red.endRoll(monster);++turn;
        }
        Map<String,Object> redState=red.snapshot(monster,turn);complete(redState);
        if(!redState.get("publicMisc").equals(1) || !redState.get("executedMoves").equals(Arrays.asList(1,3)))
            throw new AssertionError("public Entangle lost after history rolled over");
        red.execute(monster,2);rejected(red.snapshot(monster,turn+1));
        if(RunicDomeTracker.monsterPowerAllowed("Ritual","JawWorm")
                || RunicDomeTracker.monsterPowerAllowed("Compulsive","JawWorm"))
            throw new AssertionError("unaudited monster power accepted");
        for(boolean attacking:new boolean[]{false,true}) {
            RunicDomeTracker predicate=new RunicDomeTracker(monster,"JawWorm",1,1,1);
            predicate.beginRoll(monster,40,40);predicate.endRoll(monster);
            predicate.observeAttack(monster,attacking);predicate.observeAttack(monster,attacking);
            Map<String,Object> state=predicate.snapshot(monster,1);complete(state);
            if(!state.get("pendingAttackPredicates").equals(Arrays.asList(Arrays.asList(1,attacking))))
                throw new AssertionError("public Spot result missing");
            predicate.execute(monster,1);predicate.beginRoll(monster,30,40);predicate.endRoll(monster);
            if(!predicate.snapshot(monster,2).get("pendingAttackPredicates").equals(Collections.emptyList())) throw new AssertionError("stale predicate reused");
            predicate.observeAttack(monster,attacking);predicate.observeAttack(monster,!attacking);
            rejected(predicate.snapshot(monster,2));
        }
        for(String id:Arrays.asList("Byrd","Shelled Parasite")) {
            RunicDomeTracker d=new RunicDomeTracker(monster,id,38,2,1);
            d.beginRoll(monster,40,40);d.endRoll(monster);d.observeAttack(monster,true);
            d.beginForcedStun(monster,4);d.setMove(monster);d.endKnownTurn(monster);
            Map<String,Object> st=d.snapshot(monster,1);complete(st);
            if(!st.get("schemaVersion").equals(3) || !st.get("pendingMoveRolls").equals(0)
                    || !((Map<?,?>)st.get("knownNextMove")).get("kind").equals("public_stun_override")
                    || !st.get("pendingAttackPredicates").equals(Collections.emptyList())) throw new AssertionError("public stun proof lost");
            d.observeAttack(monster,false);
            if(id.equals("Byrd")) d.execute(monster,4);
            else { d.beginKnownTurn(monster,4);d.knownOverride(monster,1);d.setMove(monster);d.endKnownTurn(monster); }
            d.beginRoll(monster,30,40);d.endRoll(monster);
            st=d.snapshot(monster,2);complete(st);
            if(!st.get("pendingMoveRolls").equals(1) || st.get("knownNextMove")!=null
                    || (id.equals("Shelled Parasite") && !"shelled_stun_fell".equals(st.get("knownRollPredecessor"))))
                throw new AssertionError("post-stun deferred roll lost");
            if(id.equals("Byrd")) {
                d.beginKnownTurn(monster,5);d.knownOverride(monster,2);d.setMove(monster);d.endKnownTurn(monster);
                st=d.snapshot(monster,3);complete(st);
                if(!((Map<?,?>)st.get("knownNextMove")).get("kind").equals("byrd_headbutt_fly")) throw new AssertionError("Byrd Fly proof lost");
                d.execute(monster,2);d.beginRoll(monster,30,40);d.endRoll(monster);complete(d.snapshot(monster,4));
            }
            RunicDomeTracker bad=new RunicDomeTracker(monster,id,39,2,1);
            bad.beginRoll(monster,40,40);bad.endRoll(monster);bad.setMove(monster);rejected(bad.snapshot(monster,1));
        }
        RunicDomeTracker guardian=new RunicDomeTracker(monster,"TheGuardian",40,1,1);
        guardian.beginRoll(monster,250,250);guardian.endRoll(monster);
        int guardianTurn=1;
        for(int move:new int[]{6,2,7,5}) {
            guardian.beginKnownTurn(monster,move);int next=new int[]{0,3,7,4,5,6,2,5}[move];
            guardian.knownOverride(monster,next);guardian.setMove(monster);guardian.endKnownTurn(monster);
            complete(guardian.snapshot(monster,++guardianTurn));
        }
        for(int cycle=0;cycle<2;++cycle) {
            guardian.beginForcedStun(monster,1);guardian.setMove(monster);guardian.endKnownTurn(monster);
            complete(guardian.snapshot(monster,guardianTurn));
            for(int move:new int[]{1,3,4}) {
                guardian.beginKnownTurn(monster,move);int next=new int[]{0,3,7,4,5,6,2,5}[move];
                guardian.knownOverride(monster,next);guardian.setMove(monster);guardian.endKnownTurn(monster);
                complete(guardian.snapshot(monster,++guardianTurn));
            }
            if(!guardian.snapshot(monster,guardianTurn).get("publicMisc").equals(40+10*cycle)) throw new AssertionError("Guardian public threshold lost");
        }
        RunicDomeTracker hex=new RunicDomeTracker(monster,"Hexaghost",41,1,1);
        hex.beginRoll(monster,250,250);hex.endRoll(monster);
        for(int completed=1;completed<=17;++completed) {
            int move=completed==1?5:completed==2?1:new int[]{4,2,4,3,2,4,6}[(completed-3)%7];
            hex.beginHexTurn(monster,move,47);
            if(move==5) {hex.knownOverride(monster,1);hex.setMove(monster);hex.endKnownTurn(monster);}
            else {
                if((completed-2)%7==6) {hex.beginHexInferno(monster,6);hex.setMove(monster);hex.endKnownTurn(monster);}
                hex.beginRoll(monster,240,250);hex.endRoll(monster);
            }
            Map<String,Object> state=hex.snapshot(monster,completed+1);complete(state);
            if(!state.get("publicMisc").equals(4) || !state.get("pendingMoveRolls").equals(completed==1?0:1))
                throw new AssertionError("Hex public phase/Divider base lost");
            if(completed>=2 && (completed-2)%7==6 && !"hexaghost_inferno_predecessor".equals(state.get("knownRollPredecessor")))
                throw new AssertionError("Hex extra Inferno setter lost");
        }
        for(int wake=-1;wake<=2;++wake) {
            RunicDomeTracker laga=new RunicDomeTracker(monster,"Lagavulin",42,1,1);
            laga.beginRoll(monster,110,110);laga.endRoll(monster);
            int slept=0;
            for(;slept<(wake<0?3:wake);++slept) {
                laga.beginLagaTurn(monster,5);int next=slept==2?3:5;
                laga.knownOverride(monster,next);laga.setMove(monster);laga.endKnownTurn(monster);
                if(slept<2) {laga.beginRoll(monster,110,110);laga.endRoll(monster);}
                complete(laga.snapshot(monster,slept+2));
            }
            if(wake>=0) {
                laga.beginForcedStun(monster,4);laga.setMove(monster);laga.endKnownTurn(monster);
                complete(laga.snapshot(monster,slept+1));laga.beginLagaTurn(monster,4);
                laga.beginRoll(monster,100,110);laga.endRoll(monster);++slept;
            }
            for(int move:new int[]{3,3,1,3}) {
                laga.beginLagaTurn(monster,move);laga.beginRoll(monster,100,110);laga.endRoll(monster);
                complete(laga.snapshot(monster,++slept+1));
            }
        }
        RunicDomeTracker eventLaga=new RunicDomeTracker(monster,"Lagavulin",43,1,1);
        eventLaga.beginRoll(monster,110,110);eventLaga.endRoll(monster);
        eventLaga.lagaAwakePrebattle(monster,1);eventLaga.setMove(monster);eventLaga.endKnownTurn(monster);
        complete(eventLaga.snapshot(monster,1));
        for(String id:Arrays.asList("Looter","Mugger")) for(boolean attacking:new boolean[]{false,true}) {
            RunicDomeTracker thief=new RunicDomeTracker(monster,id,44,1,1);
            thief.beginRoll(monster,40,40);thief.endRoll(monster);
            thief.beginThiefTurn(monster,1);thief.recordTheft(monster,22,15);
            thief.knownOverride(monster,1);thief.setMove(monster);thief.endKnownTurn(monster);
            complete(thief.snapshot(monster,2));
            thief.beginThiefTurn(monster,1);
            if(!thief.beginHiddenSetter(monster)) throw new AssertionError("thief hidden setter scope missing");
            thief.setMove(monster);thief.endHiddenSetter(monster);
            if(Boolean.TRUE.equals(thief.snapshot(monster,3).get("complete"))) throw new AssertionError("missing theft callback accepted");
            thief.recordTheft(monster,7,15);thief.observeAttack(monster,attacking);
            Map<String,Object> state=thief.snapshot(monster,3);complete(state);
            if(!state.get("publicMisc").equals(22) || !state.get("pendingDirectMoveChoice").equals(1)
                    || !state.get("pendingAttackPredicates").equals(Arrays.asList(Arrays.asList(1,attacking))))
                throw new AssertionError("thief direct predicate/gold ledger lost");
            int thiefTurn=3;
            if(attacking) {
                thief.beginThiefTurn(monster,4);thief.recordTheft(monster,0,15);thief.knownOverride(monster,2);thief.setMove(monster);thief.endKnownTurn(monster);
                complete(thief.snapshot(monster,++thiefTurn));
            }
            thief.beginThiefTurn(monster,2);thief.knownOverride(monster,3);thief.setMove(monster);thief.endKnownTurn(monster);complete(thief.snapshot(monster,++thiefTurn));
            thief.beginThiefTurn(monster,3);thief.knownOverride(monster,3);thief.setMove(monster);thief.endKnownTurn(monster);complete(thief.snapshot(monster,++thiefTurn,0,true));
        }
        for(int deathTurn:new int[]{0,2}) {
            RunicDomeTracker awake=new RunicDomeTracker(monster,"AwakenedOne",45,3,3);
            awake.beginRoll(monster,300,300);awake.endRoll(monster);
            for(int i=0;i<deathTurn;++i) {awake.execute(monster,i==0?1:2);awake.beginRoll(monster,200,300);awake.endRoll(monster);}
            awake.beginRebirth(monster,3);awake.setMove(monster);awake.endKnownTurn(monster);
            if(Boolean.TRUE.equals(awake.snapshot(monster,deathTurn+1,2,false).get("complete"))) throw new AssertionError("missing duplicate rebirth callback accepted");
            awake.knownOverride(monster,3);awake.setMove(monster);awake.endKnownTurn(monster);
            complete(awake.snapshot(monster,deathTurn+1,2,false));
            awake.execute(monster,3);awake.beginRoll(monster,300,300);awake.endRoll(monster);
            Map<String,Object> reborn=awake.snapshot(monster,deathTurn+2,2,false);complete(reborn);
            if(!reborn.get("publicMisc").equals(1) || !reborn.get("knownTransitions").equals(2)) throw new AssertionError("public rebirth phase lost");
            awake.execute(monster,5);awake.beginRoll(monster,200,300);awake.endRoll(monster);complete(awake.snapshot(monster,deathTurn+3,2,false));
        }
        // Problem 91: the roll right after Rebirth runs before the queued heal (HP 0 of 320).
        RunicDomeTracker healAwake=new RunicDomeTracker(monster,"AwakenedOne",47,3,3);
        healAwake.beginRoll(monster,300,300);healAwake.endRoll(monster);healAwake.execute(monster,1);
        healAwake.beginRebirth(monster,3);healAwake.setMove(monster);healAwake.endKnownTurn(monster);
        healAwake.knownOverride(monster,3);healAwake.setMove(monster);healAwake.endKnownTurn(monster);
        healAwake.execute(monster,3);healAwake.beginRoll(monster,0,320);healAwake.endRoll(monster);
        complete(healAwake.snapshot(monster,3,2,false));
        RunicDomeTracker deadRoll=new RunicDomeTracker(monster,"AwakenedOne",48,3,3);
        deadRoll.beginRoll(monster,300,300);deadRoll.endRoll(monster);deadRoll.execute(monster,1);deadRoll.beginRoll(monster,0,300);
        if(Boolean.TRUE.equals(deadRoll.snapshot(monster,2,2,false).get("complete"))) throw new AssertionError("first-form HP-0 roll accepted");
        RunicDomeTracker thornsAwake=new RunicDomeTracker(monster,"AwakenedOne",46,3,3);
        thornsAwake.beginRoll(monster,300,300);thornsAwake.endRoll(monster);thornsAwake.execute(monster,1);
        thornsAwake.beginRebirth(monster,3);thornsAwake.setMove(monster);thornsAwake.endKnownTurn(monster);
        thornsAwake.beginRoll(monster,0,300);thornsAwake.setMove(monster);thornsAwake.endRoll(monster);
        if(Boolean.TRUE.equals(thornsAwake.snapshot(monster,2,2,false).get("complete"))) throw new AssertionError("half-dead overwritten roll leaked");
        thornsAwake.knownOverride(monster,3);thornsAwake.setMove(monster);thornsAwake.endKnownTurn(monster);
        Map<String,Object> thornsState=thornsAwake.snapshot(monster,2,2,false);complete(thornsState);
        if(!thornsState.get("totalRolls").equals(2) || !thornsState.get("pendingMoveRolls").equals(0)) throw new AssertionError("in-flight death roll not cancelled");
        javassist.ClassPool pool=new javassist.ClassPool(true);
        pool.appendClassPath(new javassist.LoaderClassPath(RunicDomeTrackerTest.class.getClassLoader()));
        // Use the installed ModTheSpire patcher, including its receiver binding.
        // LVT-name checks and direct raw hooks alone missed the startup failure.
        rejectLegacySpawnBinding(pool);
        javassist.CtClass action=pool.get("com.megacrit.cardcrawl.actions.unique.SpotWeaknessAction");
        RunicDomeTrackerPatch.SpotResult.raw(action.getDeclaredMethod("update"));
        if(action.toBytecode().length==0) throw new AssertionError("Spot instrumentation missing");
        action.detach();
        javassist.CtClass acidClass=pool.get("com.megacrit.cardcrawl.monsters.exordium.AcidSlime_S");
        RunicDomeTrackerPatch.AcidSlime_STurn.raw(acidClass.getDeclaredMethod("takeTurn"));
        if(acidClass.toBytecode().length==0) throw new AssertionError("Acid override instrumentation missing");
        acidClass.detach();
        for(String cls:Arrays.asList("com.megacrit.cardcrawl.actions.common.SetMoveAction",
                "com.megacrit.cardcrawl.monsters.exordium.GremlinWizard","com.megacrit.cardcrawl.monsters.exordium.GremlinTsundere",
                "com.megacrit.cardcrawl.monsters.beyond.Transient")) {
            javassist.CtClass type=pool.get(cls);
            if(cls.endsWith("SetMoveAction")) RunicDomeTrackerPatch.PublicSetMoveAction.raw(type.getDeclaredMethod("update"));
            else if(cls.endsWith("GremlinWizard")) RunicDomeTrackerPatch.GremlinWizardTurn.raw(type.getDeclaredMethod("takeTurn"));
            else if(cls.endsWith("GremlinTsundere")) RunicDomeTrackerPatch.GremlinTsundereTurn.raw(type.getDeclaredMethod("takeTurn"));
            else RunicDomeTrackerPatch.TransientTurn.raw(type.getDeclaredMethod("takeTurn"));
            if(type.toBytecode().length==0) throw new AssertionError("known setter instrumentation missing "+cls);
            type.detach();
        }

        for(String cls:Arrays.asList("Byrd","ShelledParasite")) {
            javassist.CtClass type=pool.get("com.megacrit.cardcrawl.monsters.city."+cls);
            if(cls.equals("Byrd")) {
                RunicDomeTrackerPatch.ByrdGrounded.raw(type.getDeclaredMethod("changeState"));
                RunicDomeTrackerPatch.ByrdTurn.raw(type.getDeclaredMethod("takeTurn"));
            } else {
                RunicDomeTrackerPatch.ShelledParasiteStun.raw(type.getDeclaredMethod("changeState"));
                RunicDomeTrackerPatch.ShelledParasiteTurn.raw(type.getDeclaredMethod("takeTurn"));
            }
            if(type.toBytecode().length==0) throw new AssertionError("stun instrumentation missing "+cls);
            type.detach();
        }

        javassist.CtClass guardianClass=pool.get("com.megacrit.cardcrawl.monsters.exordium.TheGuardian");
        RunicDomeTrackerPatch.GuardianDefense.raw(guardianClass.getDeclaredMethod("changeState"));
        RunicDomeTrackerPatch.Guardian_useCloseUp.raw(guardianClass.getDeclaredMethod("useCloseUp"));
        RunicDomeTrackerPatch.Guardian_useFierceBash.raw(guardianClass.getDeclaredMethod("useFierceBash"));
        RunicDomeTrackerPatch.Guardian_useVentSteam.raw(guardianClass.getDeclaredMethod("useVentSteam"));
        RunicDomeTrackerPatch.Guardian_useRollAttack.raw(guardianClass.getDeclaredMethod("useRollAttack"));
        RunicDomeTrackerPatch.Guardian_useTwinSmash.raw(guardianClass.getDeclaredMethod("useTwinSmash"));
        RunicDomeTrackerPatch.Guardian_useWhirlwind.raw(guardianClass.getDeclaredMethod("useWhirlwind"));
        RunicDomeTrackerPatch.Guardian_useChargeUp.raw(guardianClass.getDeclaredMethod("useChargeUp"));
        if(guardianClass.toBytecode().length==0) throw new AssertionError("Guardian actual helper instrumentation missing");
        guardianClass.detach();
        javassist.CtClass hexClass=pool.get("com.megacrit.cardcrawl.monsters.exordium.Hexaghost");
        RunicDomeTrackerPatch.HexaghostTurn.raw(hexClass.getDeclaredMethod("takeTurn"));
        RunicDomeTrackerPatch.HexaghostInferno.raw(hexClass.getDeclaredMethod("changeState"));
        if(hexClass.toBytecode().length==0) throw new AssertionError("Hex actual setter instrumentation missing");
        hexClass.detach();
        javassist.CtClass lagaClass=pool.get("com.megacrit.cardcrawl.monsters.exordium.Lagavulin");
        RunicDomeTrackerPatch.LagavulinTurn.raw(lagaClass.getDeclaredMethod("takeTurn"));
        RunicDomeTrackerPatch.LagavulinWake.raw(lagaClass.getDeclaredMethod("damage"));
        RunicDomeTrackerPatch.LagavulinPrebattle.raw(lagaClass.getDeclaredMethod("usePreBattleAction"));
        if(lagaClass.toBytecode().length==0) throw new AssertionError("Laga raw instrumentation missing");lagaClass.detach();
        javassist.CtClass looterClass=pool.get("com.megacrit.cardcrawl.monsters.exordium.Looter");
        RunicDomeTrackerPatch.LooterTurn.raw(looterClass.getDeclaredMethod("takeTurn"));
        looterClass.toBytecode();looterClass.detach();
        javassist.CtClass looter1=pool.get("com.megacrit.cardcrawl.monsters.exordium.Looter$1");
        RunicDomeTrackerPatch.LooterTheft1.raw(looter1.getDeclaredMethod("update"));
        looter1.toBytecode();looter1.detach();
        javassist.CtClass looter2=pool.get("com.megacrit.cardcrawl.monsters.exordium.Looter$2");
        RunicDomeTrackerPatch.LooterTheft2.raw(looter2.getDeclaredMethod("update"));
        looter2.toBytecode();looter2.detach();
        javassist.CtClass muggerClass=pool.get("com.megacrit.cardcrawl.monsters.city.Mugger");
        RunicDomeTrackerPatch.MuggerTurn.raw(muggerClass.getDeclaredMethod("takeTurn"));
        muggerClass.toBytecode();muggerClass.detach();
        javassist.CtClass mugger1=pool.get("com.megacrit.cardcrawl.monsters.city.Mugger$1");
        RunicDomeTrackerPatch.MuggerTheft1.raw(mugger1.getDeclaredMethod("update"));
        mugger1.toBytecode();mugger1.detach();
        javassist.CtClass mugger2=pool.get("com.megacrit.cardcrawl.monsters.city.Mugger$2");
        RunicDomeTrackerPatch.MuggerTheft2.raw(mugger2.getDeclaredMethod("update"));
        mugger2.toBytecode();mugger2.detach();
        javassist.CtClass awakenedClass=pool.get("com.megacrit.cardcrawl.monsters.beyond.AwakenedOne");
        RunicDomeTrackerPatch.AwakenedOneRebirth.raw(awakenedClass.getDeclaredMethod("damage"));
        if(awakenedClass.toBytecode().length==0) throw new AssertionError("Awakened raw instrumentation missing");awakenedClass.detach();
        // Hook signatures are verified against the installed JAR without
        // initializing game graphics. Pure lifecycle tests cannot prove hook
        // delivery; installed-mod smoke remains separate evidence.
        ClassLoader loader=RunicDomeTrackerTest.class.getClassLoader();
        Class<?> base=Class.forName("com.megacrit.cardcrawl.monsters.AbstractMonster",false,loader);
        base.getDeclaredMethod("rollMove");
        Class<?> intent=Class.forName("com.megacrit.cardcrawl.monsters.AbstractMonster$Intent",false,loader);
        base.getDeclaredMethod("setMove",String.class,byte.class,intent,int.class,int.class,boolean.class);
        for(String cls:Arrays.asList("JawWorm","Cultist","FungiBeast","SlaverBlue","SlaverRed","AcidSlime_S","AcidSlime_M","SpikeSlime_M","SpikeSlime_S","Sentry","GremlinNob"))
            Class.forName("com.megacrit.cardcrawl.monsters.exordium."+cls,false,loader).getDeclaredMethod("takeTurn");
        for(String pkg:Arrays.asList("city","beyond")) for(String cls:Arrays.asList("Centurion","Healer","Chosen","SnakePlant","Snecko",
                "SphericGuardian","Exploder","Repulsor","Maw","Nemesis","OrbWalker","GiantHead","Donu","Deca","Spiker","SpireGrowth",
                "Taskmaster","BookOfStabbing","TimeEater","BanditBear","BanditLeader","BanditPointy","Transient","WrithingMass","Champ")) {
            try { Class.forName("com.megacrit.cardcrawl.monsters."+pkg+"."+cls,false,loader).getDeclaredMethod("takeTurn"); }
            catch(ClassNotFoundException expectedOtherPackage) { }
        }
        // Every monster-specific Dome power is checked against the jar's POWER_ID (live problem 73: Darkling's
        // RegrowPower is "Life Link"); all mismatches are reported at once.
        List<String> powerIdErrors=new ArrayList<>();
        for(String[] power:new String[][]{{"WeakPower","FuzzyLouseNormal"},{"GenericStrengthUpPower","Orb Walker"},{"AngryPower","GremlinWarrior"},
                {"MalleablePower","SnakePlant"},{"ReactivePower","WrithingMass"},{"SlowPower","GiantHead"},{"RegrowPower","Darkling"},
                {"SplitPower","AcidSlime_L"},{"CurlUpPower","FuzzyLouseNormal"},{"MinionPower","Dagger"},{"StasisPower","BronzeOrb"},
                {"RitualPower","Cultist"},{"SporeCloudPower","FungiBeast"},{"AngerPower","GremlinNob"},{"BarricadePower","SphericGuardian"},
                {"ExplosivePower","Exploder"},{"IntangiblePower","Nemesis"},{"ThornsPower","Spiker"},{"PainfulStabsPower","BookOfStabbing"},
                {"TimeWarpPower","TimeEater"},{"ShiftingPower","Transient"},{"FadingPower","Transient"},{"FlightPower","Byrd"},
                {"CuriosityPower","AwakenedOne"},{"UnawakenedPower","AwakenedOne"},{"ThieveryPower","Looter"},{"ModeShiftPower","TheGuardian"},
                {"SharpHidePower","TheGuardian"},{"InvinciblePower","CorruptHeart"},{"BeatOfDeathPower","CorruptHeart"},
                {"PainfulStabsPower","CorruptHeart"},{"BackAttackPower","SpireShield"},
                // generic powers any monster may carry (player debuffs and monster buffs)
                {"StrengthPower","JawWorm"},{"ArtifactPower","JawWorm"},{"VulnerablePower","JawWorm"},{"watcher.BlockReturnPower","JawWorm"},
                {"ChokePower","JawWorm"},{"CorpseExplosionPower","JawWorm"},{"LockOnPower","JawWorm"},{"watcher.MarkPower","JawWorm"},
                {"MetallicizePower","JawWorm"},{"PlatedArmorPower","JawWorm"},{"PoisonPower","JawWorm"},{"RegenerateMonsterPower","JawWorm"},
                {"GainStrengthPower","JawWorm"}}) {
            try {
                String publicId=(String)pool.get("com.megacrit.cardcrawl.powers."+power[0]).getDeclaredField("POWER_ID").getConstantValue();
                if(!RunicDomeTracker.monsterPowerAllowed(publicId,power[1])) powerIdErrors.add(power[0]+" id "+publicId+" rejected for "+power[1]);
            } catch(Exception missing) { powerIdErrors.add(power[0]+": "+missing); }
        }
        if(!powerIdErrors.isEmpty()) throw new AssertionError("vanilla power IDs rejected: "+powerIdErrors);
        Class.forName("com.megacrit.cardcrawl.monsters.MonsterGroup",false,loader).getDeclaredMethod("init");
        // New occupants carry local execution history and the public global birth clock.
        for(String id:Arrays.asList("AcidSlime_L","SpikeSlime_L","SlimeBoss","BronzeAutomaton","BronzeOrb","GremlinLeader","Reptomancer","Dagger","TheCollector","TorchHead","FuzzyLouseNormal","FuzzyLouseDefensive","Darkling")) {
            Object identity=new Object();RunicDomeTracker remainingTracker=new RunicDomeTracker(identity,id,17,1,5,0);
            remainingTracker.bind(1,0,"initial",-1,0);if(id.equals("TorchHead"))remainingTracker.constructorTackle(identity);remainingTracker.globalTurn(0);remainingTracker.beginRoll(identity,40,40);remainingTracker.setMove(identity);remainingTracker.endRoll(identity);
            Map<String,Object> row=remainingTracker.snapshot(identity,1,0,false);
            if(!Boolean.TRUE.equals(row.get("complete")) || !Integer.valueOf(4).equals(row.get("schemaVersion")))throw new AssertionError("remaining initial "+id+row);
        }
        // Act 4 (Runic Dome): every turn rolls, but only one roll per cycle is random (CorruptHeart/SpireShield/SpireSpear getMove).
        act4Run("CorruptHeart",new int[]{3,1,2,4,2,1,4,1},new int[]{3,0,2,4,0,1,4,0},800);
        act4Run("SpireShield",new int[]{2,1,3,1,2,3,1},new int[]{0,1,3,0,2,3,0},110);
        act4Run("SpireSpear",new int[]{1,3,1,2,3,2,1,3},new int[]{1,3,0,2,3,0,1,3},160);
        {
            Object hm=new Object();RunicDomeTracker wrong=new RunicDomeTracker(hm,"CorruptHeart",23,4,1,20);
            wrong.bind(1,0,"initial",-1,0);wrong.globalTurn(0);wrong.beginRoll(hm,800,800,800,800,true,1);wrong.setMove(hm);wrong.endRoll(hm);
            wrong.globalTurn(1);wrong.execute(hm,1);
            wrong.beginRoll(hm,800,800,800,800,true,1);wrong.setMove(hm);wrong.endRoll(hm);
            Map<String,Object> bad=wrong.snapshot(hm,2,0,false);rejected(bad); // the first Heart move is always Debilitate
            if(!"execution_lifecycle".equals(bad.get("reason")))throw new AssertionError("Heart opener "+bad);
            rejected(new RunicDomeTracker(hm,"CorruptHeart",23,3,1,20).snapshot(hm,1,0,false));
            rejected(new RunicDomeTracker(hm,"SpireSpear",23,2,2,20).snapshot(hm,1,0,false));
        }
        // Live seed 111200463 s391 (problem 67): GremlinLeader bytes are RALLY 2, ENCOURAGE 3, STAB 4; its first STAB
        // after the minions died was refused as execution_lifecycle.
        for(int move:new int[]{2,3,4}) {
            Object leader=new Object();RunicDomeTracker leaderTracker=new RunicDomeTracker(leader,"GremlinLeader",17,2,4,20);
            leaderTracker.bind(1,0,"initial",-1,0);leaderTracker.globalTurn(0);leaderTracker.beginRoll(leader,140,140);leaderTracker.setMove(leader);leaderTracker.endRoll(leader);
            leaderTracker.globalTurn(1);leaderTracker.execute(leader,move);
            leaderTracker.beginRoll(leader,140,140,140,140,true,1);leaderTracker.setMove(leader);leaderTracker.endRoll(leader);
            Map<String,Object> leaderRow=leaderTracker.snapshot(leader,2,3,false);
            if(!Boolean.TRUE.equals(leaderRow.get("complete")))throw new AssertionError("GremlinLeader executed move "+move+" "+leaderRow);
        }
        Object badLeader=new Object();RunicDomeTracker badLeaderTracker=new RunicDomeTracker(badLeader,"GremlinLeader",17,2,4,20);
        badLeaderTracker.bind(1,0,"initial",-1,0);badLeaderTracker.globalTurn(0);badLeaderTracker.beginRoll(badLeader,140,140);badLeaderTracker.setMove(badLeader);badLeaderTracker.endRoll(badLeader);
        badLeaderTracker.globalTurn(1);badLeaderTracker.execute(badLeader,1);
        if(Boolean.TRUE.equals(badLeaderTracker.snapshot(badLeader,2,3,false).get("complete")))throw new AssertionError("GremlinLeader has no move byte 1");
        Object torchIdentity=new Object();RunicDomeTracker torchTracker=new RunicDomeTracker(torchIdentity,"TorchHead",17,2,3,0);
        torchTracker.bind(1,1,"summon",2,1);torchTracker.constructorTackle(torchIdentity);torchTracker.globalTurn(1);
        torchTracker.beginRoll(torchIdentity,40,40);torchTracker.setMove(torchIdentity);torchTracker.endRoll(torchIdentity);
        Map<String,Object> torchBorn=torchTracker.snapshot(torchIdentity,2,1,false);
        if(!Boolean.TRUE.equals(torchBorn.get("complete")) || !"torch_constructor_tackle".equals(torchBorn.get("knownRollPredecessor")) || !Long.valueOf(2).equals(torchBorn.get("generation")))throw new AssertionError("Torch constructor/initial roll "+torchBorn);
        torchTracker.globalTurn(2);torchTracker.beginKnownTurn(torchIdentity,1);torchTracker.knownOverride(torchIdentity,1);torchTracker.setMove(torchIdentity);torchTracker.endKnownTurn(torchIdentity);
        Map<String,Object> torchNext=torchTracker.snapshot(torchIdentity,3,1,false);
        if(!Boolean.TRUE.equals(torchNext.get("complete")) || !Integer.valueOf(0).equals(torchNext.get("pendingMoveRolls")) || !Integer.valueOf(1).equals(torchNext.get("totalRolls")))throw new AssertionError("Torch queued successor "+torchNext);
        for(int level:new int[]{0,19}) {
            Object automatonIdentity=new Object();RunicDomeTracker autoTracker=new RunicDomeTracker(automatonIdentity,"BronzeAutomaton",17,2,3,level);
            autoTracker.bind(1,0,"initial",-1,0);autoTracker.globalTurn(0);autoTracker.beginRoll(automatonIdentity,300,300);autoTracker.setMove(automatonIdentity);autoTracker.endRoll(automatonIdentity);
            for(int n=0;n<20;++n) {
                int move=n==0?4:new int[]{1,5,1,5,2,level>=19?5:3}[(n-1)%6];
                autoTracker.globalTurn(n+1);autoTracker.execute(automatonIdentity,move);autoTracker.beginRoll(automatonIdentity,300,300);autoTracker.setMove(automatonIdentity);autoTracker.endRoll(automatonIdentity);
                Map<String,Object> autoRow=autoTracker.snapshot(automatonIdentity,n+2,1,false);
                if(!Boolean.TRUE.equals(autoRow.get("complete")) || !Integer.valueOf(n%6==5?0:n%6).equals(autoRow.get("publicMisc")))throw new AssertionError("Automaton counter level="+level+autoRow);
            }
        }
        Object bornIdentity=new Object();RunicDomeTracker bornTracker=new RunicDomeTracker(bornIdentity,"Dagger",17,3,5,0);
        bornTracker.bind(3,7,"summon",2,1);bornTracker.globalTurn(7);bornTracker.beginRoll(bornIdentity,25,25);bornTracker.setMove(bornIdentity);bornTracker.endRoll(bornIdentity);
        if(!Boolean.TRUE.equals(bornTracker.snapshot(bornIdentity,8,4,false).get("complete")))throw new AssertionError("born local history rejected");
        bornTracker.globalTurn(8);bornTracker.execute(bornIdentity,1);bornTracker.beginRoll(bornIdentity,25,25);bornTracker.setMove(bornIdentity);bornTracker.endRoll(bornIdentity);
        Map<String,Object> bornRow=bornTracker.snapshot(bornIdentity,9,4,false);
        if(!Boolean.TRUE.equals(bornRow.get("complete")) || !Integer.valueOf(1).equals(bornRow.get("completedTurns")) || !Integer.valueOf(8).equals(bornRow.get("rollGlobalTurn")))throw new AssertionError("born clock "+bornRow);
        bornTracker.globalTurn(9);bornTracker.execute(bornIdentity,2);bornTracker.beginTerminalRoll(bornIdentity);bornTracker.setMove(bornIdentity);bornTracker.endRoll(bornIdentity);
        Map<String,Object> terminalDagger=bornTracker.snapshot(bornIdentity,10,4,true);
        if(!Boolean.TRUE.equals(terminalDagger.get("complete")) || !Integer.valueOf(0).equals(terminalDagger.get("pendingMoveRolls")) || !Integer.valueOf(3).equals(terminalDagger.get("totalRolls")))throw new AssertionError("dead Dagger trailing roll "+terminalDagger);
        Object terminalJawIdentity=new Object();RunicDomeTracker terminalJaw=new RunicDomeTracker(terminalJawIdentity,"JawWorm",18,1,1,0);
        terminalJaw.bind(1,0,"initial",-1,0);terminalJaw.globalTurn(0);terminalJaw.beginRoll(terminalJawIdentity,40,40);terminalJaw.setMove(terminalJawIdentity);terminalJaw.endRoll(terminalJawIdentity);
        terminalJaw.globalTurn(1);terminalJaw.execute(terminalJawIdentity,1);terminalJaw.beginTerminalRoll(terminalJawIdentity);terminalJaw.setMove(terminalJawIdentity);terminalJaw.endRoll(terminalJawIdentity);
        Map<String,Object> terminalJawRow=terminalJaw.snapshot(terminalJawIdentity,2,0,true);
        if(!Boolean.TRUE.equals(terminalJawRow.get("complete")) || !Long.valueOf(3).equals(terminalJawRow.get("generation")) || !Integer.valueOf(0).equals(terminalJawRow.get("pendingMoveRolls")))throw new AssertionError("retaliation terminal roll "+terminalJawRow);
        if(!RunicDomeTracker.monsterPowerAllowed("Life Link","Darkling") || RunicDomeTracker.monsterPowerAllowed("Regrow","Darkling"))
            throw new AssertionError("Darkling RegrowPower.POWER_ID is Life Link (live problem 73)");
        Object darkIdentity=new Object();RunicDomeTracker darkTracker=new RunicDomeTracker(darkIdentity,"Darkling",17,3,3,0);
        darkTracker.bind(1,0,"initial",-1,0);darkTracker.globalTurn(0);darkTracker.beginRoll(darkIdentity,50,50);darkTracker.setMove(darkIdentity);darkTracker.endRoll(darkIdentity);
        darkTracker.publicOverride(darkIdentity,4,true);darkTracker.setMove(darkIdentity);darkTracker.endKnownTurn(darkIdentity);
        if(Boolean.TRUE.equals(darkTracker.snapshot(darkIdentity,1,0,false).get("complete")))throw new AssertionError("missing duplicate Regrow accepted");
        darkTracker.knownOverride(darkIdentity,4);darkTracker.setMove(darkIdentity);darkTracker.endKnownTurn(darkIdentity);
        if(!Boolean.TRUE.equals(darkTracker.snapshot(darkIdentity,1,0,false).get("complete")))throw new AssertionError("public Regrow rejected");
        darkTracker.globalTurn(1);darkTracker.execute(darkIdentity,4);darkTracker.beginRoll(darkIdentity,0,50);darkTracker.setMove(darkIdentity);darkTracker.endRoll(darkIdentity);
        Map<String,Object> darkRow=darkTracker.snapshot(darkIdentity,2,0,false);
        if(!Boolean.TRUE.equals(darkRow.get("complete")) || !Integer.valueOf(0).equals(darkRow.get("rollHp")))throw new AssertionError("half-dead roll rejected "+darkRow);
        Object thornDarkIdentity=new Object();RunicDomeTracker thornDark=new RunicDomeTracker(thornDarkIdentity,"Darkling",18,3,3,0);
        thornDark.bind(1,0,"initial",-1,0);thornDark.globalTurn(0);thornDark.beginRoll(thornDarkIdentity,50,50);thornDark.setMove(thornDarkIdentity);thornDark.endRoll(thornDarkIdentity);
        thornDark.globalTurn(1);thornDark.execute(thornDarkIdentity,3);thornDark.publicOverride(thornDarkIdentity,4,true);thornDark.setMove(thornDarkIdentity);thornDark.endKnownTurn(thornDarkIdentity);
        thornDark.beginRoll(thornDarkIdentity,0,50);thornDark.setMove(thornDarkIdentity);thornDark.endRoll(thornDarkIdentity);
        thornDark.knownOverride(thornDarkIdentity,4);thornDark.setMove(thornDarkIdentity);thornDark.endKnownTurn(thornDarkIdentity);
        Map<String,Object> thornDarkRow=thornDark.snapshot(thornDarkIdentity,2,0,false);
        if(!Boolean.TRUE.equals(thornDarkRow.get("complete")) || !"darkling_reincarnate_before_regrow".equals(thornDarkRow.get("knownRollPredecessor")))throw new AssertionError("in-flight Darkling predecessor "+thornDarkRow);
        for(String name:Arrays.asList("AcidSlime_L","SpikeSlime_L","SlimeBoss")) {
            javassist.CtClass type=pool.get("com.megacrit.cardcrawl.monsters.exordium."+name);
            RunicDomeTrackerPatch.instrumentRemainingOverride(type.getDeclaredMethod("damage"),1);
            if(name.equals("SlimeBoss"))RunicDomeTrackerPatch.SlimeBossRemainingTurn.raw(type.getDeclaredMethod("takeTurn"));
            else RunicDomeTrackerPatch.instrumentRemainingOverride(type.getDeclaredMethod("takeTurn"),1);
            type.toBytecode();type.detach();
        }
        javassist.CtClass darkType=pool.get("com.megacrit.cardcrawl.monsters.beyond.Darkling");
        RunicDomeTrackerPatch.instrumentRemainingOverride(darkType.getDeclaredMethod("damage"),1);darkType.toBytecode();darkType.detach();
        for(String name:Arrays.asList("com.megacrit.cardcrawl.actions.common.SpawnMonsterAction","com.megacrit.cardcrawl.actions.unique.SummonGremlinAction")) {
            javassist.CtClass type=pool.get(name);RunicDomeTrackerPatch.instrumentSpawnInit(type.getDeclaredMethod("update"));
            if(name.endsWith("SpawnMonsterAction")) {
                javassist.CtConstructor ctor=type.getDeclaredConstructor(new javassist.CtClass[]{pool.get("com.megacrit.cardcrawl.monsters.AbstractMonster"),javassist.CtClass.booleanType,javassist.CtClass.intType});
                applyConstructorPatch(ctor,RunicDomeTrackerPatch.SpawnConstructed.class);
                final int[] calls={0};ctor.instrument(new javassist.expr.ExprEditor(){
                    @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                        if(call.getClassName().equals(RunicDomeTrackerPatch.SpawnConstructed.class.getName()) && call.getMethodName().equals("postfix")) {
                            if(!call.getSignature().equals("(Lcom/megacrit/cardcrawl/actions/common/SpawnMonsterAction;Lcom/megacrit/cardcrawl/monsters/AbstractMonster;)V"))
                                throw new javassist.CannotCompileException("Spawn constructor receiver/monster binding drift");
                            ++calls[0];
                        }
                    }
                });if(calls[0]!=1)throw new AssertionError("Spawn constructor postfix missing");
            }
            if(name.endsWith("SummonGremlinAction")) {
                if(!type.getDeclaredField("m").getType().getName().equals("com.megacrit.cardcrawl.monsters.AbstractMonster"))throw new AssertionError("Gremlin birth field binding drift");
                applyConstructorPatch(type.getDeclaredConstructors()[0],RunicDomeTrackerPatch.GremlinConstructed.class);
            }
            type.toBytecode();type.detach();
        }
        javassist.CtClass playerDamageType=pool.get("com.megacrit.cardcrawl.characters.AbstractPlayer");
        javassist.CtMethod playerDamage=playerDamageType.getDeclaredMethod("damage",new javassist.CtClass[]{pool.get("com.megacrit.cardcrawl.cards.DamageInfo")});
        javassist.bytecode.LocalVariableAttribute damageVars=(javassist.bytecode.LocalVariableAttribute)playerDamage.getMethodInfo().getCodeAttribute().getAttribute(javassist.bytecode.LocalVariableAttribute.tag);
        boolean namedInfo=false;for(int j=0;j<damageVars.tableLength();++j)if(damageVars.index(j)==1 && damageVars.variableName(j).equals("info"))namedInfo=true;
        if(!namedInfo)throw new AssertionError("Player.damage patch argument binding drift");
        playerDamageType.detach();
        javassist.CtClass torchType=pool.get("com.megacrit.cardcrawl.monsters.city.TorchHead");
        applyConstructorPatch(torchType.getDeclaredConstructors()[0],RunicDomeTrackerPatch.TorchConstructor.class);torchType.toBytecode();torchType.detach();
        System.out.println("RunicDomeTrackerTest PASS");
    }
}
