package stsmodelinspector;

import com.megacrit.cardcrawl.rooms.AbstractRoom.RoomPhase;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon.CurrentScreen;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

/** Pure boundary and selection projection checks, without game/render initialization. */
public final class CombatBoundaryTest {
    private static void verifyRetiredSlimeBoss() {
        Object boss=new Object();java.util.Set<Object> retired=new java.util.HashSet<>();
        if(!STSModelInspector.replacedSlimeBossParent("SLIME_BOSS","SlimeBoss",boss,true,true,retired))
            throw new AssertionError("initial boss split parent was retained");
        // Once both large children split (or die), they no longer prove the
        // original parent's retirement in the current monster list.
        if(!STSModelInspector.replacedSlimeBossParent("SLIME_BOSS","SlimeBoss",boss,true,false,retired))
            throw new AssertionError("boss parent resurrected after both large children split");
        if(STSModelInspector.replacedSlimeBossParent("SLIME_BOSS","SlimeBoss",boss,false,false,retired)
                || STSModelInspector.replacedSlimeBossParent("LARGE_SLIME","SlimeBoss",boss,true,true,retired)
                || STSModelInspector.replacedSlimeBossParent("SLIME_BOSS","SlimeBoss",new Object(),true,false,retired)
                || STSModelInspector.replacedSlimeBossParent("SLIME_BOSS","AcidSlime_L",boss,true,true,retired))
            throw new AssertionError("unqualified parent was hidden");
    }
    private static void verifyChosenAndByrds() {
        // Overnight seed 111194461 floor 31: Byrd + Chosen had no encounter id.
        java.util.Map<String,Integer> counts=new java.util.HashMap<>();
        counts.put("Byrd",1);counts.put("Chosen",1);
        if(!"CHOSEN_AND_BYRDS".equals(STSModelInspector.multiEncounterName(counts,false)))
            throw new AssertionError("one Byrd + Chosen is CHOSEN_AND_BYRDS");
        counts.put("Byrd",2);
        if(!STSModelInspector.multiEncounterName(counts,false).isEmpty())
            throw new AssertionError("two Byrds + Chosen is not a native encounter");
    }
    public static void main(String[] args) {
        verifyRetiredSlimeBoss();
        verifyChosenAndByrds();
        // Vanilla Searing Blow writes its repeat-upgrade count, while Rampage
        // grows baseDamage through ModifyDamageAction without changing misc.
        if (STSModelInspector.combatCardMisc("Searing Blow", 0, 3, 27) != 3
                || STSModelInspector.combatCardMisc("Searing Blow", 99, 0, 12) != 0
                || STSModelInspector.combatCardMisc("Rampage", 0, 0, 13) != 5
                || STSModelInspector.combatCardMisc("Rampage", 99, 1, 24) != 16
                || STSModelInspector.combatCardMisc("RitualDagger", 27, 1, 27) != 27
                || STSModelInspector.combatCardMisc("Strike_R", 7, 0, 99) != 7)
            throw new AssertionError("combat card growth projection lost its native meaning");
        // Armaments under a large accelerated frame can expire before the
        // confirmed selection is retrieved. Normal play must not accept its
        // incomplete piles; an active popup and already retrieved UI residue
        // are separate, valid states.
        if (!STSModelInspector.orphanedHandSelection(true, false, 1)
                || STSModelInspector.orphanedHandSelection(false, false, 1)
                || STSModelInspector.orphanedHandSelection(true, true, 1)
                || STSModelInspector.orphanedHandSelection(true, false, 0))
            throw new AssertionError("orphaned hand selection became ordinary play");
        if(STSModelInspector.publicMonsterMiscInfo(false,()->null)!=null
                || STSModelInspector.publicMonsterMiscInfo(false,()->7)!=7
                || STSModelInspector.publicMonsterMiscInfo(true,()->{throw new AssertionError("Dome read private monster state");})!=0)
            throw new AssertionError("nullable monster state projection changed");
        try {
            javassist.ClassPool pool=new javassist.ClassPool(true);
            for(String name:new String[]{"GremlinWarrior","GremlinTsundere"}) {
                Object id=pool.get("com.megacrit.cardcrawl.monsters.exordium."+name).getDeclaredField("ID").getConstantValue();
                if(!name.equals(id) || !Integer.valueOf(0).equals(STSModelInspector.statelessMonsterMiscInfo((String)id)))
                    throw new AssertionError("vanilla gremlin zero-state ID was omitted: "+id);
            }
        } catch(javassist.NotFoundException error){throw new AssertionError(error);}
        if(STSModelInspector.statelessMonsterMiscInfo("UnknownMonster")!=null)
            throw new AssertionError("unknown monster state was guessed");
        // Later-turn Warcry has a stale monsterAttacksQueued=true even with
        // no enemy/pre-turn work. Only the actual player end-turn lifecycle
        // flags can prohibit an otherwise qualified player selection.
        for (int flags=0; flags<8; ++flags)
            if (STSModelInspector.playerSelectionTurn((flags&1)!=0,(flags&2)!=0,(flags&4)!=0) != (flags==0))
                throw new AssertionError("player selection end-turn lifecycle guard");
        if (STSModelInspector.awakenedNativePhase(null, false) != null
                || STSModelInspector.awakenedNativePhase(true, false) != 0
                || STSModelInspector.awakenedNativePhase(false, true) != 0
                || STSModelInspector.awakenedNativePhase(false, false) != 1)
            throw new AssertionError("Awakened One rebirth phase projection");
        String[][] selections = {
            {"common.PutOnDeckAction", "WARCRY"}, {"unique.ForethoughtAction", "FORETHOUGHT"},
            {"unique.SkillFromDeckToHandAction", "SECRET_TECHNIQUE"},
            {"unique.AttackFromDeckToHandAction", "SECRET_WEAPON"},
            {"common.ExhaustAction", "EXHAUST_ONE"}, {"unique.DiscardPileToTopOfDeckAction", "HEADBUTT"},
            {"unique.ArmamentsAction", "ARMAMENTS"}, {"unique.ExhumeAction", "EXHUME"},
            {"unique.DualWieldAction", "DUAL_WIELD"}};
        for (int i = 0; i < selections.length; ++i) {
            String name = "com.megacrit.cardcrawl.actions." + selections[i][0];
            boolean hand = i < 2 || i == 4 || i == 6 || i == 8;
            if (!selections[i][1].equals(STSModelInspector.actionSelectionTask(name, hand, false, 1))
                    || !"".equals(STSModelInspector.actionSelectionTask(name, !hand, false, 1))
                    || !"".equals(STSModelInspector.actionSelectionTask(name, hand, true, 1))
                    || !"".equals(STSModelInspector.actionSelectionTask(name, hand, false, 2)))
                throw new AssertionError("action-owned selection mismatch: " + name);
            try { Class.forName(name, false, CombatBoundaryTest.class.getClassLoader()); }
            catch (ClassNotFoundException error) { throw new AssertionError(error); }
        }
        String[][] sourceOwners={{"WARCRY","red.Warcry"},{"WARCRY","colorless.ThinkingAhead"},
            {"EXHAUST_ONE","red.TrueGrit"},{"EXHAUST_ONE","red.BurningPact"},{"ARMAMENTS","red.Armaments"},
            {"DUAL_WIELD","red.DualWield"},{"EXHUME","red.Exhume"},{"HEADBUTT","red.Headbutt"},
            {"FORETHOUGHT","colorless.Forethought"},{"EXHAUST_MANY","colorless.Purity"},
            {"SECRET_TECHNIQUE","colorless.SecretTechnique"},{"SECRET_WEAPON","colorless.SecretWeapon"},{"DISCOVERY","colorless.Discovery"}};
        if(!STSModelInspector.sourceCleanupExhaust(false,true,"com.megacrit.cardcrawl.powers.CorruptionPower")
                || !STSModelInspector.sourceCleanupExhaust(true,false,null)
                || STSModelInspector.sourceCleanupExhaust(false,false,"com.megacrit.cardcrawl.powers.CorruptionPower")
                || STSModelInspector.sourceCleanupExhaust(false,true,"modded.CorruptionPower"))
            throw new AssertionError("Corruption source cleanup exhaust projection changed");
        if(!STSModelInspector.zeroCopyPower("Double Tap","com.megacrit.cardcrawl.powers.DoubleTapPower",0)
                || !STSModelInspector.zeroCopyPower("DuplicationPower","com.megacrit.cardcrawl.powers.DuplicationPower",0)
                || STSModelInspector.zeroCopyPower("Double Tap","com.megacrit.cardcrawl.powers.DoubleTapPower",1)
                || STSModelInspector.zeroCopyPower("Double Tap","modded.DoubleTapPower",0)
                || STSModelInspector.zeroCopyPower("Strength","com.megacrit.cardcrawl.powers.StrengthPower",0))
            throw new AssertionError("copy power zero-charge normalization escaped exact vanilla proof");
        for(String[] owner:sourceOwners) {
            String className="com.megacrit.cardcrawl.cards."+owner[1];
            if(!STSModelInspector.sourceSelectionOwner(owner[0],className)
                    || STSModelInspector.sourceSelectionOwner("GAMBLE",className)
                    || STSModelInspector.sourceSelectionOwner(owner[0],"modded."+owner[1]))
                throw new AssertionError("source-owned cleanup qualification changed");
            try {Class.forName(className,false,CombatBoundaryTest.class.getClassLoader());}
            catch(ClassNotFoundException error){throw new AssertionError(error);}
        }
        try {
            // Problem 32: the played-types state lives in the relic's static flags.
            Class<?> pellets=Class.forName("com.megacrit.cardcrawl.relics.OrangePellets",false,CombatBoundaryTest.class.getClassLoader());
            for(String flag:new String[]{"ATTACK","SKILL","POWER"}) {
                java.lang.reflect.Field field=pellets.getDeclaredField(flag);
                if(field.getType()!=boolean.class || !java.lang.reflect.Modifier.isStatic(field.getModifiers()))
                    throw new AssertionError("OrangePellets "+flag+" flag contract changed");
            }
        } catch(ReflectiveOperationException error){throw new AssertionError(error);}
        if(STSModelInspector.orangePelletsNativeBits(true,false,false)!=1
                || STSModelInspector.orangePelletsNativeBits(false,true,false)!=2
                || STSModelInspector.orangePelletsNativeBits(true,false,true)!=5
                || STSModelInspector.orangePelletsNativeBits(false,false,false)!=0
                || STSModelInspector.orangePelletsNativeBits(true,null,false)!=null)
            throw new AssertionError("Orange Pellets native bits changed");
        try {
            Class<?> cleanup=Class.forName("com.megacrit.cardcrawl.actions.utility.UseCardAction",false,CombatBoundaryTest.class.getClassLoader());
            Class<?> cleanse=Class.forName("com.megacrit.cardcrawl.actions.unique.RemoveDebuffsAction",false,CombatBoundaryTest.class.getClassLoader());
            if(cleanse.getDeclaredField("c").getType()!=com.megacrit.cardcrawl.core.AbstractCreature.class)
                throw new AssertionError("Pellets action recipient contract changed");
            if(cleanup.getDeclaredField("targetCard").getType()!=com.megacrit.cardcrawl.cards.AbstractCard.class
                    || cleanup.getDeclaredField("exhaustCard").getType()!=boolean.class
                    || cleanup.getDeclaredField("returnToHand").getType()!=boolean.class
                    || cleanup.getDeclaredField("reboundCard").getType()!=boolean.class
                    || cleanup.getSuperclass().getDeclaredField("duration").getType()!=float.class)
                throw new AssertionError("UseCardAction JAR lifecycle contract changed");
        } catch(ReflectiveOperationException error){throw new AssertionError(error);}
        if (STSModelInspector.actionSelectionTask("unknown.Action", true, false, 1) != null)
            throw new AssertionError("unknown action was guessed");
        for(int act:new int[]{2,3})for(int defect=-1;defect<8;++defect) {
            int floor=17*(act-1)+1;
            java.util.List<String> resolved=new java.util.ArrayList<>(java.util.Collections.nCopies(floor-1,"M"));
            resolved.set(floor-3,"B");resolved.set(floor-2,null);
            java.util.List<Integer> combats=java.util.Arrays.asList(floor-2);
            if(defect==0)resolved.set(floor-3,"M");
            if(defect==1)resolved.set(floor-2,"M");
            if(defect==2)combats=java.util.Collections.emptyList();
            if(defect==3)resolved.remove(resolved.size()-1);
            if(defect==4){resolved.add("M");resolved.add("M");}
            String previous=STSModelInspector.previousRoomAtActEntry(act,defect==5?floor+1:floor,
                    defect==6?1:0,defect==7?null:resolved,combats);
            if("BOSS_TREASURE".equals(previous)!=(defect==-1))
                throw new AssertionError("act-entry previous room qualification "+act+"/"+defect);
        }
        for (int initial : new int[]{30, 35, 40}) {
            for (int cycle = 0; cycle < 3; ++cycle) {
                int threshold = initial + 10 * cycle;
                if (STSModelInspector.guardianNativeThreshold(threshold, 10, true) != threshold
                        || STSModelInspector.guardianNativeThreshold(threshold + 10, 10, false) != threshold)
                    throw new AssertionError("Guardian threshold/cycle projection");
            }
        }
        if (STSModelInspector.guardianNativeThreshold(null, 10, true) != null
                || STSModelInspector.guardianNativeThreshold(30, null, true) != null
                || STSModelInspector.guardianNativeThreshold(30, 10, null) != null
                || STSModelInspector.guardianNativeThreshold(30, 11, true) != null
                || STSModelInspector.guardianNativeThreshold(10, 10, false) != null)
            throw new AssertionError("Guardian missing or invalid fields accepted");
        try {
            Class<?> guardian = Class.forName("com.megacrit.cardcrawl.monsters.exordium.TheGuardian", false,
                    CombatBoundaryTest.class.getClassLoader());
            if (guardian.getDeclaredField("dmgThreshold").getType() != int.class
                    || guardian.getDeclaredField("dmgThresholdIncrease").getType() != int.class
                    || guardian.getDeclaredField("isOpen").getType() != boolean.class)
                throw new AssertionError("Guardian JAR field types changed");
        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
        // Native uses vanilla numTurns, including zero after Hyper Beam at A19.
        for (int turns : new int[]{0, 1, 2, 3, 4}) {
            Integer captured = STSModelInspector.bronzeAutomatonNativeTurns(turns);
            if (captured == null || captured != turns)
                throw new AssertionError("Automaton counter " + turns);
        }
        if (STSModelInspector.bronzeAutomatonNativeTurns(null) != null
                || STSModelInspector.bronzeAutomatonNativeTurns(-1) != null
                || STSModelInspector.bronzeAutomatonNativeTurns(5) != null)
            throw new AssertionError("Automaton missing or invalid numTurns accepted");
        try {
            Class<?> automatonClass = Class.forName("com.megacrit.cardcrawl.monsters.city.BronzeAutomaton", false,
                    CombatBoundaryTest.class.getClassLoader());
            if (automatonClass.getDeclaredField("numTurns").getType() != int.class)
                throw new AssertionError("BronzeAutomaton numTurns field type changed");
        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.HAND_SELECT, false, true, false)
                || !STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.GRID, false, true, false)
                || !STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.CARD_REWARD, false, true, false))
            throw new AssertionError("unknown selection must retain combat classification");
        // Event fights use this same phase-based gate; no room subclass is required.
        if (!STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, true, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.EVENT, CurrentScreen.NONE, true, false, false))
            throw new AssertionError("event combat phase gate");
        if (STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, false, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMPLETE, CurrentScreen.CARD_REWARD, false, true, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.GRID, false, false, false)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMPLETE, CurrentScreen.HAND_SELECT, false, true, false))
            throw new AssertionError("transitional or OOC modal misclassified");
        // Smoke Bomb: the escape animation and the post-endBattle window are
        // idle COMBAT frames, but native combat already ended.
        if (STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.NONE, true, false, true)
                || STSModelInspector.isCombatBoundary(RoomPhase.COMBAT, CurrentScreen.HAND_SELECT, false, true, true)
                || !STSModelInspector.isCombatEnding(false, false, true)
                || !STSModelInspector.isCombatEnding(true, false, false)
                || !STSModelInspector.isCombatEnding(false, true, false)
                || STSModelInspector.isCombatEnding(false, false, false))
            throw new AssertionError("escaping or ended combat published as a decision");
        java.util.List<String> uuids = java.util.Arrays.asList("physical-c", "physical-a", "physical-b");
        for (String task : new String[]{"GAMBLE","EXHAUST_MANY"}) {
            int count="GAMBLE".equals(task)?99:3;
            String owner="GAMBLE".equals(task)?"com.megacrit.cardcrawl.actions.unique.GamblingChipAction":"com.megacrit.cardcrawl.actions.common.ExhaustAction";
            JsonObject multi=new Gson().fromJson(STSModelInspector.singleSelectionJson(task,"HAND_SELECT",true,true,count,0,uuids,3),JsonObject.class);
            if(!task.equals(multi.get("task").getAsString()) || !owner.equals(multi.get("actionClass").getAsString())
                    || !task.equals(STSModelInspector.actionSelectionTask(owner,true,true,count)))
                throw new AssertionError("source-owned multi selector rejected");
        }
        for(String kind:new String[]{"DRAW","GAIN_BLOCK","GAIN_ENERGY","DAMAGE_ALL","DAMAGE_RANDOM","GAMBLE","UPGRADE_RANDOM","REMOVE_PEN_NIB","REMOVE_PLAYER_DEBUFFS"})
            if(STSModelInspector.publicPendingActionJson(kind,3,null)==null)throw new AssertionError("public typed action missing: "+kind);
        if(STSModelInspector.publicPendingActionJson("BUFF_PLAYER",2,"Strength")==null
                || STSModelInspector.publicPendingActionJson("DEBUFF_PLAYER",2,"Flex")==null
                || STSModelInspector.publicPendingActionJson("DEBUFF_PLAYER",1,"Weakened")==null
                || STSModelInspector.publicPendingActionJson("DEBUFF_ALL_ENEMY",1,"Vulnerable")==null
                || STSModelInspector.publicPendingActionJson("SHUFFLE_WOUNDS",2,null)==null
                || STSModelInspector.publicPendingActionJson("BUFF_PLAYER",1,"Pen Nib")==null
                || STSModelInspector.publicPendingActionJson("BUFF_PLAYER",2,"Pen Nib")!=null
                || STSModelInspector.publicPendingActionJson("SHUFFLE_WOUNDS",3,null)!=null
                || STSModelInspector.publicPendingActionJson("SHUFFLE_DAZED",1,null)==null
                || STSModelInspector.publicPendingActionJson("SHUFFLE_DAZED",2,null)!=null
                || STSModelInspector.publicPendingActionJson("LOSE_ENERGY",1,null)==null
                || STSModelInspector.publicPendingActionJson("LOSE_ENERGY",2,null)!=null
                || STSModelInspector.publicPendingActionJson("DRAW",11,null)!=null
                || STSModelInspector.publicPendingActionJson("BUFF_PLAYER",1,"Echo Form")!=null
                || STSModelInspector.publicPendingActionJson("DEBUFF_PLAYER",1,"Weak")!=null
                || STSModelInspector.publicPendingActionJson("HEAL_PLAYER",5,null)==null
                || STSModelInspector.publicPendingActionJson("HEAL_PLAYER",4,null)!=null
                || STSModelInspector.publicPendingActionJson("PRIVATE_RANDOM_CARD",1,null)!=null)
            throw new AssertionError("public pending action qualification");
        if(!"{\"kind\":\"MONSTER_GAIN_BLOCK\",\"amount\":6,\"slot\":0}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_GAIN_BLOCK",6,0))
                || !"{\"kind\":\"REACTIVE_ROLL_MOVE\",\"slot\":0}".equals(STSModelInspector.monsterReactionItemJson("REACTIVE_ROLL_MOVE",null,0))
                || !"{\"kind\":\"MONSTER_REDUCE_PLATED_ARMOR\",\"amount\":1,\"slot\":1}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_REDUCE_PLATED_ARMOR",1,1))
                || !"{\"kind\":\"MONSTER_THORNS\",\"amount\":4,\"slot\":0}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_THORNS",4,0))
                || STSModelInspector.monsterReactionItemJson("MONSTER_THORNS",4,1)!=null
                || !"{\"kind\":\"MONSTER_REDUCE_FLIGHT\",\"amount\":1,\"slot\":2}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_REDUCE_FLIGHT",1,2))
                || STSModelInspector.monsterReactionItemJson("MONSTER_REDUCE_FLIGHT",2,0)!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_THORNS",0,0)!=null
                || STSModelInspector.monsterReactionItemJson("REACTIVE_ROLL_MOVE",null,1)!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_REDUCE_PLATED_ARMOR",2,0)!=null
                || !"{\"kind\":\"MONSTER_LAGAVULIN_OPEN\",\"amount\":8,\"slot\":0}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_LAGAVULIN_OPEN",8,0))
                || STSModelInspector.monsterReactionItemJson("MONSTER_LAGAVULIN_OPEN",8,1)!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_LAGAVULIN_OPEN",0,0)!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_GAIN_BLOCK",null,0)!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_GAIN_BLOCK",3,5)!=null
                || !"{\"kind\":\"GUARDIAN_DEFENSIVE_SHIFT\",\"slot\":0}".equals(STSModelInspector.monsterReactionItemJson("GUARDIAN_DEFENSIVE_SHIFT",null,0))
                || STSModelInspector.monsterReactionItemJson("GUARDIAN_DEFENSIVE_SHIFT",null,1)!=null
                || !"{\"kind\":\"MONSTER_CURL_UP\",\"amount\":10,\"slot\":1}".equals(STSModelInspector.monsterReactionItemJson("MONSTER_CURL_UP",10,1))
                || STSModelInspector.monsterReactionItemJson("MONSTER_CURL_UP",0,0)!=null
                || !"{\"kind\":\"MONSTER_SET_MOVE\",\"move\":4,\"slot\":2}".equals(STSModelInspector.monsterSetMoveItemJson(4,2))
                || STSModelInspector.monsterSetMoveItemJson(3,0)!=null
                || STSModelInspector.monsterSetMoveItemJson(4,5)!=null
                || !"{\"kind\":\"MONSTER_SPLIT_SET_MOVE\",\"slot\":1}".equals(STSModelInspector.monsterSplitItemJson(1))
                || STSModelInspector.monsterSplitItemJson(5)!=null
                || !"{\"kind\":\"MINION_LEADER_ESCAPE\",\"slots\":[1,2]}".equals(STSModelInspector.leaderEscapeItemJson(java.util.Arrays.asList(1,2)))
                || STSModelInspector.leaderEscapeItemJson(java.util.Arrays.asList(1,1))!=null
                || STSModelInspector.leaderEscapeItemJson(java.util.Arrays.asList(0,5))!=null
                || STSModelInspector.leaderEscapeItemJson(new java.util.ArrayList<Integer>())!=null
                || STSModelInspector.monsterReactionItemJson("MONSTER_ROLL_PRIVATE",0,0)!=null)
            throw new AssertionError("monster reaction pending action qualification");
        for(int count:new int[]{1,2}) {
            String owner="com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction";
            JsonObject liquid=new Gson().fromJson(STSModelInspector.singleSelectionJson("LIQUID_MEMORIES_POTION","GRID",false,false,count,0,uuids,3),JsonObject.class);
            if(!"LIQUID_MEMORIES_POTION".equals(liquid.get("task").getAsString())
                    || !"LIQUID_MEMORIES_POTION".equals(STSModelInspector.actionSelectionTask(owner,false,false,count)))
                throw new AssertionError("Liquid Memories source-owned amount rejected");
        }
        try {
            Class<?> dual=Class.forName("com.megacrit.cardcrawl.actions.unique.DualWieldAction",false,CombatBoundaryTest.class.getClassLoader());
            Class<?> liquid=Class.forName("com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction",false,CombatBoundaryTest.class.getClassLoader());
            if(dual.getDeclaredField("dupeAmount").getType()!=int.class || dual.getDeclaredField("cannotDuplicate").getType()!=java.util.ArrayList.class
                    || liquid.getDeclaredField("numberOfCards").getType()!=int.class || liquid.getDeclaredField("newCost").getType()!=int.class
                    || liquid.getDeclaredField("optional").getType()!=boolean.class || liquid.getDeclaredField("setCost").getType()!=boolean.class)
                throw new AssertionError("selector JAR private field contract changed");
        } catch(ReflectiveOperationException error) {throw new AssertionError(error);}
        JsonObject single = new Gson().fromJson(STSModelInspector.singleSelectionJson(
                "SECRET_WEAPON", "GRID", false, false, 1, 0, uuids, 3), JsonObject.class);
        if (!single.getAsJsonArray("liveChoices").get(0).getAsJsonObject().get("uuid").getAsString().equals("physical-c")
                || single.getAsJsonArray("liveChoices").get(2).getAsJsonObject().get("choiceIndex").getAsInt() != 3)
            throw new AssertionError("physical selector occurrence order changed");
        JsonObject forethought = new Gson().fromJson(STSModelInspector.singleSelectionJson(
                "FORETHOUGHT", "HAND_SELECT", true, true, 99, 0, uuids, 3), JsonObject.class);
        if (!forethought.get("canPickAnyNumber").getAsBoolean() || !forethought.get("canPickZero").getAsBoolean()
                || !forethought.get("actionClass").getAsString().endsWith(".ForethoughtAction")
                || !"FORETHOUGHT".equals(STSModelInspector.actionSelectionTask(
                    "com.megacrit.cardcrawl.actions.unique.ForethoughtAction", true, true, 99)))
            throw new AssertionError("upgraded Forethought initial transaction missing");
        String[] badSingles = {
            STSModelInspector.singleSelectionJson("WARCRY", "HAND_SELECT", false, false, 1, 0, uuids, 2),
            STSModelInspector.singleSelectionJson("WARCRY", "HAND_SELECT", false, false, 1, 1, uuids, 3),
            STSModelInspector.singleSelectionJson("FORETHOUGHT", "HAND_SELECT", false, true, 2, 0, uuids, 3),
            STSModelInspector.singleSelectionJson("SECRET_WEAPON", "HAND_SELECT", false, false, 1, 0, uuids, 3),
            STSModelInspector.singleSelectionJson("WARCRY", "HAND_SELECT", true, false, 1, 0, uuids, 3),
            STSModelInspector.singleSelectionJson("WARCRY", "HAND_SELECT", false, false, 1, 0,
                    java.util.Arrays.asList("physical-a", "physical-a", "physical-b"), 3),
            STSModelInspector.singleSelectionJson("WARCRY", "HAND_SELECT", false, false, 1, 0,
                    java.util.Arrays.asList("physical-a", null, "physical-b"), 3)};
        for (String serialized : badSingles)
            if (!new Gson().fromJson(serialized, JsonObject.class).has("unsupportedReason"))
                throw new AssertionError("ambiguous or partial selector accepted");
        String discovery = "com.megacrit.cardcrawl.actions.unique.DiscoveryAction";
        java.util.List<String> offers = java.util.Arrays.asList("Anger", "Shrug It Off", "Flash of Steel");
        for (int copies : new int[]{1, 2}) {
            JsonObject offer = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                    discovery, copies, false, "none", offers, true), JsonObject.class);
            if (!"DISCOVERY".equals(offer.get("task").getAsString())
                    || !"CARD_REWARD".equals(offer.get("origin").getAsString())
                    || offer.get("data0").getAsInt() != copies
                    || offer.get("canPickZero").getAsBoolean()
                    || !offer.get("setCostToZero").getAsBoolean()
                    || offer.getAsJsonArray("cards").size() != 3)
                throw new AssertionError("Discovery copies/offer semantics lost");
        }
        JsonObject typedPotion = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                discovery, 2, true, "none", offers, true), JsonObject.class);
        JsonObject toolbox = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                "com.megacrit.cardcrawl.actions.utility.ChooseOneColorless", 1, false, "none", offers, true), JsonObject.class);
        if (!typedPotion.get("canPickZero").getAsBoolean() || toolbox.get("setCostToZero").getAsBoolean())
            throw new AssertionError("typed potion skip or Toolbox normal cost lost");
        JsonObject potionTail = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                discovery, 1, true, "public_actions", offers, true), JsonObject.class);
        JsonObject toolboxPublic = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                "com.megacrit.cardcrawl.actions.utility.ChooseOneColorless", 1, false, "public_actions", offers, true), JsonObject.class);
        if (potionTail.has("unsupportedReason") || !"public_actions".equals(potionTail.get("continuation").getAsString())
                || !"silver_card_reward_pending_actions".equals(toolboxPublic.get("unsupportedReason").getAsString()))
            throw new AssertionError("potion offer public tail not limited to DiscoveryAction");
        java.util.List<String> openingDraw = java.util.Arrays.asList(
                "com.megacrit.cardcrawl.actions.common.DrawCardAction",
                "com.megacrit.cardcrawl.actions.common.EnableEndTurnButtonAction");
        if (STSModelInspector.toolboxDrawAfter(openingDraw, 5, true) != 5
                || STSModelInspector.toolboxDrawAfter(openingDraw, 5, false) != -1
                || STSModelInspector.toolboxDrawAfter(openingDraw, null, true) != -1
                || STSModelInspector.toolboxDrawAfter(openingDraw.subList(0, 1), 5, true) != -1)
            throw new AssertionError("Toolbox remaining action queue was guessed");
        java.util.List<String> bagDraws = java.util.Arrays.asList(openingDraw.get(0), openingDraw.get(1),
                "com.megacrit.cardcrawl.actions.common.RelicAboveCreatureAction", openingDraw.get(0));
        if (!java.util.Arrays.asList(5, 2).equals(STSModelInspector.toolboxDrawsAfter(bagDraws, java.util.Arrays.asList(5, 2), true))
                || STSModelInspector.toolboxDrawsAfter(bagDraws, java.util.Arrays.asList(7), true) != null
                || STSModelInspector.toolboxDrawsAfter(bagDraws, java.util.Arrays.asList(5, 2), false) != null
                || STSModelInspector.toolboxDrawsAfter(java.util.Arrays.asList(openingDraw.get(0),
                    "unknown.Action", openingDraw.get(1)), java.util.Arrays.asList(5), true) != null)
            throw new AssertionError("Toolbox ordered Bag of Preparation draws were guessed or combined");
        java.util.List<String> endTurnQueue = java.util.Arrays.asList(
                "com.megacrit.cardcrawl.actions.defect.TriggerEndOfTurnOrbsAction");
        JsonObject codex = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                "com.megacrit.cardcrawl.actions.unique.CodexAction", 0, true, "codex_end_turn", offers, true), JsonObject.class);
        if (!"CODEX".equals(codex.get("task").getAsString()) || !codex.get("canPickZero").getAsBoolean()
                || !STSModelInspector.codexEndTurnContinuation(endTurnQueue, true, true, true)
                || STSModelInspector.codexEndTurnContinuation(endTurnQueue, false, true, true)
                || STSModelInspector.codexEndTurnContinuation(endTurnQueue, true, false, true)
                || STSModelInspector.codexEndTurnContinuation(endTurnQueue, true, true, false)
                || STSModelInspector.codexEndTurnContinuation(java.util.Collections.<String>emptyList(), true, true, true))
            throw new AssertionError("Codex exact end-turn continuation lost or guessed");
        String owner = "com.megacrit.cardcrawl.actions.common.PutOnDeckAction";
        String confirmation = STSModelInspector.completedSingleSelectionJson("WARCRY", owner, 1,
                java.util.Arrays.asList("selected-card"), 0, true, false);
        if (confirmation == null || !new Gson().fromJson(confirmation, JsonObject.class)
                .get("mechanicalTransition").getAsString().equals("single_select_confirm")
                || STSModelInspector.completedSingleSelectionJson("WARCRY", owner, 1,
                    java.util.Arrays.asList("selected-card"), 1, true, false) != null
                || STSModelInspector.completedSingleSelectionJson("WARCRY", owner, 1,
                    java.util.Arrays.asList("selected-card"), 0, true, true) != null
                || STSModelInspector.completedSingleSelectionJson("WARCRY", owner, 1,
                    java.util.Arrays.asList("selected-card"), 0, false, false) != null)
            throw new AssertionError("single HAND confirmation was guessed");
        JsonObject cardOffer = new Gson().fromJson(STSModelInspector.cardRewardSelectionJson(
                discovery, 1, false, "discovery_card", offers, true), JsonObject.class);
        if (!"discovery_card".equals(cardOffer.get("continuation").getAsString()))
            throw new AssertionError("Discovery cleanup continuation lost");
        String[] rejected = {
            STSModelInspector.cardRewardSelectionJson(discovery, 1, null, "none", offers, true),
            STSModelInspector.cardRewardSelectionJson(discovery, 0, false, "none", offers, true),
            STSModelInspector.cardRewardSelectionJson(discovery, 3, false, "none", offers, true),
            STSModelInspector.cardRewardSelectionJson(discovery, 1, false, "unsupported", offers, true),
            STSModelInspector.cardRewardSelectionJson(discovery, 1, false, "none", offers, false),
            STSModelInspector.cardRewardSelectionJson(discovery, 1, false, "none", offers.subList(0, 2), true),
            STSModelInspector.cardRewardSelectionJson(discovery, 1, false, "none",
                    java.util.Arrays.asList("Anger", "Anger", "Shrug It Off"), true),
            STSModelInspector.cardRewardSelectionJson(discovery, 1, false, "none",
                    java.util.Arrays.asList("Anger", "Shrug It Off", "Flash of Steel", "Discovery"), true),
            STSModelInspector.cardRewardSelectionJson("unknown.Action", 1, false, "none", offers, true),
            STSModelInspector.cardRewardSelectionJson("com.megacrit.cardcrawl.actions.unique.CodexAction",
                    1, true, "unsupported", offers, true),
            STSModelInspector.cardRewardSelectionJson("com.megacrit.cardcrawl.actions.utility.ChooseOneColorless",
                    2, false, "none", offers, true)};
        for (String serialized : rejected) {
            JsonObject offer = new Gson().fromJson(serialized, JsonObject.class);
            if (!offer.has("unsupportedReason") || !offer.get("task").getAsString().isEmpty())
                throw new AssertionError("unsupported combat offer was guessed or truncated");
        }
        for (boolean canPickZero : new boolean[]{false, true}) {
            JsonObject selection = new Gson().fromJson(
                    STSModelInspector.selectionJson("", canPickZero, true, 99, null), JsonObject.class);
            if (!selection.get("task").getAsString().isEmpty()
                    || selection.get("canPickZero").getAsBoolean() != canPickZero
                    || !selection.get("canPickAnyNumber").getAsBoolean()
                    || selection.get("pickCount").getAsInt() != 99)
                throw new AssertionError("unknown selector or canPickZero lost");
        }
        for (int counter : new int[]{0, 1, 2, 3, -1, -2}) {
            if (STSModelInspector.combatEntryRelicData("NeowsBlessing", counter, false) != counter)
                throw new AssertionError("active/invalid Neow counter changed");
        }
        if (STSModelInspector.combatEntryRelicData("NeowsBlessing", -2, true) != 0
                || STSModelInspector.combatEntryRelicData("NeowsBlessing", -1, true) != -1
                || STSModelInspector.combatEntryRelicData("Omamori", -2, true) != 0
                || STSModelInspector.combatEntryRelicData("Omamori", 2, false) != 2
                || STSModelInspector.combatEntryRelicData("Omamori", -2, false) != -2
                || STSModelInspector.combatEntryRelicData("Pen Nib", -2, true) != -2)
            throw new AssertionError("spent charge mapping is not exact and relic-specific");
        if (STSModelInspector.combatEntryRelicData("Ancient Tea Set", -2, false) != 1
                || STSModelInspector.combatEntryRelicData("Ancient Tea Set", -1, false) != 0)
            throw new AssertionError("Ancient Tea Set charge is not mapped to native 1/0");
        System.out.println("CombatBoundaryTest: 8 boundary, 2 selection and 14 entry-relic checks passed");
    }
}
