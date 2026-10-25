#!/usr/bin/env python3
"""Seed-free focused hook contract tests with an instrumented semantic API stub.
Real simulator integration is qualified separately by exact flag-off prefix parity.
"""
import json
from pathlib import Path
import subprocess
import tempfile
from build_runtime import HERE, SOURCE

STUB = r'''
#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace sts {
enum class ScreenState { REWARDS, MAP_SCREEN };
struct GameContext { std::uint64_t seed=111101032; int act=1, floorNum=0; ScreenState screenState=ScreenState::REWARDS; };
namespace search {
enum class OocSemanticEffect { SKIP_CARD_REWARD, TAKE_CARD };
enum class OocSemanticSource { REWARDS, EVENT };
struct OocSemanticAction { OocSemanticEffect effect=OocSemanticEffect::SKIP_CARD_REWARD; OocSemanticSource source=OocSemanticSource::REWARDS; std::string key; };
struct OocEnumerationResult { bool supported=true,complete=true; std::string error; std::vector<OocSemanticAction> actions; };
struct OocExecutionResult { bool ok=true; std::string error; };
inline int enumerations=0,executions=0;
inline bool executionOk=true;
inline OocEnumerationResult next;
inline OocEnumerationResult enumerateOocSemanticActions(const GameContext &) {++enumerations;return next;}
inline OocExecutionResult executeOocSemanticAction(GameContext &,const OocSemanticAction &) {++executions;return {executionOk,"test failure"};}
inline std::string canonicalOocSemanticActionKey(const OocSemanticAction &a) {return a.key;}
}}
'''
TEST = r'''
#include "infinity_frozen_skips.h"
#include <cassert>
#include <iostream>
using namespace sts;
using namespace sts::search;
using one_combat::InfinityFrozenSkips;
int main(int argc,char **argv) {
 std::ifstream f(argv[1]); nlohmann::json manifest; f>>manifest;
 auto entries=manifest.at("interventions");
 unsetenv("STS_INFINITY_SKIP_MANIFEST");
 InfinityFrozenSkips off(111101032); GameContext gc;
 assert(!off.enabled() && !off.tryApply(gc) && enumerations==0 && executions==0);
 std::cout<<"PASS disabled: zero semantic enumeration/execution\n";
 setenv("STS_INFINITY_SKIP_MANIFEST",argv[1],1);
 bool thrown=false; try {InfinityFrozenSkips wrong(1);} catch(...) {thrown=true;} assert(thrown);
 InfinityFrozenSkips hook(111101032);
 gc.screenState=ScreenState::MAP_SCREEN;
 assert(!hook.tryApply(gc) && enumerations==0);
 gc.screenState=ScreenState::REWARDS; gc.floorNum=999;
 assert(!hook.tryApply(gc) && enumerations==0);
 gc.floorNum=entries.at(0).at("floor");
 assert(!hook.tryApply(gc) && enumerations==1);
 assert(hook.summary(true).at("not_seen")==5);
 std::cout<<"PASS wrong seed rejected; irrelevant screen/floor do not enumerate; absent groups stay NOT_SEEN\n";
 // Every frozen key fires once; re-presenting it cannot execute twice.
 for(const auto &j:entries) {
   gc.act=j.at("act"); gc.floorNum=j.at("floor");
   next.actions={{OocSemanticEffect::SKIP_CARD_REWARD,OocSemanticSource::REWARDS,j.at("forced_skip_key")}};
   const int before=executions;
   assert(hook.tryApply(gc)); assert(!hook.tryApply(gc)); assert(executions==before+1);
 }
 assert(hook.summary(true).at("matched")==5 && hook.summary(true).at("not_seen")==0);
 std::cout<<"PASS all 5 exact semantic keys; at-most-once accounting; decision indices unused\n";
 gc.act=1;gc.floorNum=entries.at(0).at("floor");
 const auto key=entries.at(0).at("forced_skip_key").get<std::string>();
 for(int test=0;test<5;++test) {
   InfinityFrozenSkips bad(111101032); next={};executionOk=true;
   next.actions={{OocSemanticEffect::SKIP_CARD_REWARD,OocSemanticSource::REWARDS,key}};
   if(test==0) next.supported=false;
   if(test==1) next.complete=false;
   if(test==2) next.actions.push_back(next.actions[0]);
   if(test==3) next.actions[0].effect=OocSemanticEffect::TAKE_CARD;
   if(test==4) executionOk=false;
   thrown=false;try {bad.tryApply(gc);} catch(const std::runtime_error &) {thrown=true;}
   assert(thrown && bad.summary(false).at("failed")==1);
   thrown=false;try {bad.summary(true);} catch(...) {thrown=true;}assert(thrown);
 }
 std::cout<<"PASS unsupported/incomplete/ambiguous/wrong-type/failed execution abort and mark MATCH_FAILED_FATAL\n";

 // R1 disables only the frozen floor0 entry, even if unsupported candidates
 // are supplied. No enumeration is permitted for this disabled-only location.
 setenv("STS_INFINITY_SKIP_MANIFEST",argv[2],1);
 enumerations=executions=0;next={};next.supported=false;next.complete=false;
 InfinityFrozenSkips r1(111101032);gc.act=1;gc.floorNum=entries.at(0).at("floor");
 assert(!r1.tryApply(gc) && enumerations==0 && executions==0);
 assert(r1.summary(true).at("disabled_by_design")==1 && r1.summary(true).at("not_seen")==4);
 std::cout<<"PASS disabled entry never enumerates/matches/executes and reports DISABLED_BY_DESIGN\n";
 next={};executionOk=true;
 for(std::size_t i=1;i<entries.size();++i) {
   const auto &j=entries.at(i);gc.act=j.at("act");gc.floorNum=j.at("floor");
   next.actions={{OocSemanticEffect::SKIP_CARD_REWARD,OocSemanticSource::REWARDS,j.at("forced_skip_key")}};
   assert(r1.tryApply(gc));assert(!r1.tryApply(gc));
 }
 assert(r1.summary(true).at("matched")==4 && r1.summary(true).at("not_seen")==0 && r1.summary(true).at("disabled_by_design")==1 && executions==4);
 std::cout<<"PASS 4 unchanged enabled targets fire once; matched+unseen+disabled=5\n";
 // Explicit true has the same matching/execution semantics as omitted enabled.
 setenv("STS_INFINITY_SKIP_MANIFEST",argv[3],1);
 InfinityFrozenSkips allTrue(111101032);
 for(const auto &j:entries) {
   gc.act=j.at("act");gc.floorNum=j.at("floor");
   next.actions={{OocSemanticEffect::SKIP_CARD_REWARD,OocSemanticSource::REWARDS,j.at("forced_skip_key")}};
   assert(allTrue.tryApply(gc));
 }
 assert(allTrue.summary(true).at("matched")==5 && allTrue.summary(true).at("disabled_by_design")==0);
 setenv("STS_INFINITY_SKIP_MANIFEST",argv[4],1);
 thrown=false;try {InfinityFrozenSkips invalid(111101032);} catch(...) {thrown=true;}assert(thrown);
 std::cout<<"PASS omitted/true preserve all5 targets; nonboolean enabled fails closed\n";

 for(int mask=0;mask<32;++mask) {
   std::string bits;
   for(int b=4;b>=0;--b)bits+=((mask>>b)&1)?'1':'0';
   const auto path=std::string(argv[5])+"/"+bits+".json";
   setenv("STS_INFINITY_SKIP_MANIFEST",path.c_str(),1);
   InfinityFrozenSkips candidate(111101032);next={};executionOk=true;int count=0;
   for(int bit=0;bit<5;++bit) {
     const auto &j=entries.at(bit);gc.act=j.at("act");gc.floorNum=j.at("floor");
     next.actions={{OocSemanticEffect::SKIP_CARD_REWARD,OocSemanticSource::REWARDS,j.at("forced_skip_key")}};
     const int before=enumerations;const bool expected=mask&(1<<bit);
     assert(candidate.tryApply(gc)==expected);assert(!candidate.tryApply(gc));
     if(!expected)assert(enumerations==before);
     count+=expected;
   }
   assert(candidate.summary(true).at("matched")==count && candidate.summary(true).at("disabled_by_design")==5-count);
 }
 std::cout<<"PASS complete32-mask enablement/at-most-once/accounting contract\n";
 std::cout<<"9 focused contract groups passed (stub; no gameplay run)\n";


}
'''

def main():
    with tempfile.TemporaryDirectory() as directory:
        temp=Path(directory); (temp/'sim/search').mkdir(parents=True)
        (temp/'sim/search/OocSemanticAction.h').write_text(STUB)
        (temp/'test.cpp').write_text(TEST)
        command=['g++','-std=c++20','-O0','-I'+str(temp),'-I'+str(SOURCE/'apps/one_combat'),'-I'+str(SOURCE/'json/include'),str(temp/'test.cpp'),'-o',str(temp/'check')]
        subprocess.run(command,check=True)
        original=HERE/'FROZEN_INTERVENTIONS.json'
        explicit=json.loads(original.read_text())
        for e in explicit['interventions']:e['enabled']=True
        (temp/'true.json').write_text(json.dumps(explicit))
        explicit['interventions'][0]['enabled']='false'
        (temp/'invalid.json').write_text(json.dumps(explicit))
        subprocess.run([str(temp/'check'),str(original),str(HERE/'manifests/11110.json'),str(temp/'true.json'),str(temp/'invalid.json'),str(HERE/'manifests')],check=True)

if __name__=='__main__':main()
