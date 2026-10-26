# Exhaustive ordinary-root matrix

All identities and ingredient locations (including physical IDs) are in RESULT.json and FREEZE.json. Draw bags are unordered. Turn uses the captured zero-based counter.

|Decision|Turn|Player HP|Enemy HP|Vuln|Active|Hand|Draw bag|Dropkick / Bash / Pommel locations|Supported|Nodes|Depth|Candidate / certified|Reach|Caps / unsupported|Witness|
|---:|---:|---:|---|---|---:|---|---|---|---:|---|---|---|---|---|---|
|1|0|64|[75]|[0]|14|ENTRENCH#9, BARRICADE#8, FIRE_BREATHING#11, BASH#1, DROPKICK#7|ARMAMENTS#4, ASCENDERS_BANE#0, BERSERK#5, DROPKICK#10, FIRE_BREATHING#2, INFLAME#6, POMMEL_STRIKE#3, RAGE#13, WILD_STRIKE#12|drawPile:1,hand:1 / hand:1 / drawPile:1|4|[18, 20, 18, 20]|[3, 4, 3, 4]|0.0 / 0.0|None|0 / 0|none|
|2|0|64|[75]|[0]|14|ENTRENCH#9, BARRICADE#8, FIRE_BREATHING#11, BASH#1, DROPKICK#7|ARMAMENTS#4, ASCENDERS_BANE#0, BERSERK#5, DROPKICK#10, FIRE_BREATHING#2, INFLAME#6, POMMEL_STRIKE#3, RAGE#13, WILD_STRIKE#12|drawPile:1,hand:1 / hand:1 / drawPile:1|4|[20, 18, 18, 18]|[4, 3, 3, 3]|0.0 / 0.0|None|0 / 0|none|
|3|0|64|[75]|[0]|13|ENTRENCH#9, BARRICADE#8, BASH#1, DROPKICK#7|ARMAMENTS#4, ASCENDERS_BANE#0, BERSERK#5, DROPKICK#10, FIRE_BREATHING#2, INFLAME#6, POMMEL_STRIKE#3, RAGE#13, WILD_STRIKE#12|drawPile:1,hand:1 / hand:1 / drawPile:1|4|[4, 4, 4, 4]|[1, 1, 1, 1]|0.0 / 0.0|None|0 / 0|none|
|4|0|64|[75]|[0]|13|BARRICADE#8, BASH#1, DROPKICK#7|ARMAMENTS#4, ASCENDERS_BANE#0, BERSERK#5, DROPKICK#10, FIRE_BREATHING#2, INFLAME#6, POMMEL_STRIKE#3, RAGE#13, WILD_STRIKE#12|drawPile:1,hand:1 / hand:1 / drawPile:1|4|[1, 1, 1, 1]|[0, 0, 0, 0]|0.0 / 0.0|None|0 / 0|none|
|5|1|64|[75]|[0]|13|WILD_STRIKE#12, ASCENDERS_BANE#0, INFLAME#6, POMMEL_STRIKE#3, BERSERK#5|ARMAMENTS#4, DROPKICK#10, FIRE_BREATHING#2, RAGE#13|discardPile:1,drawPile:1 / discardPile:1 / hand:1|4|[99, 99, 99, 84]|[4, 4, 4, 4]|0.0 / 0.0|None|0 / 0|none|
|6|1|64|[75]|[0]|12|WILD_STRIKE#12, ASCENDERS_BANE#0, POMMEL_STRIKE#3, BERSERK#5|ARMAMENTS#4, DROPKICK#10, FIRE_BREATHING#2, RAGE#13|discardPile:1,drawPile:1 / discardPile:1 / hand:1|4|[35, 20, 20, 20]|[4, 3, 3, 3]|0.0 / 0.0|None|0 / 0|none|
|7|1|64|[69]|[0]|12|WILD_STRIKE#12, ASCENDERS_BANE#0, BERSERK#5, FIRE_BREATHING#2|ARMAMENTS#4, DROPKICK#10, RAGE#13|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[8, 8, 8, 8]|[2, 2, 2, 2]|0.0 / 0.0|None|0 / 0|none|
|8|1|64|[69]|[0]|11|WILD_STRIKE#12, ASCENDERS_BANE#0, BERSERK#5|ARMAMENTS#4, DROPKICK#10, RAGE#13|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[2, 2, 2, 2]|[1, 1, 1, 1]|0.0 / 0.0|None|0 / 0|none|
|9|1|64|[69]|[0]|10|WILD_STRIKE#12, ASCENDERS_BANE#0|ARMAMENTS#4, DROPKICK#10, RAGE#13|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[1, 1, 1, 1]|[0, 0, 0, 0]|0.0 / 0.0|None|0 / 0|none|
|10|2|44|[69]|[0]|9|ARMAMENTS#4, RAGE#13, DROPKICK#10, BARRICADE#8, DROPKICK#7|BASH#1, ENTRENCH#9, POMMEL_STRIKE#3, WILD_STRIKE#12|hand:2 / drawPile:1 / drawPile:1|4|[54, 54, 54, 54]|[4, 4, 4, 4]|0.0 / 0.0|None|0 / 0|none|
|12|2|44|[69]|[0]|9|DROPKICK#10, BARRICADE#8, DROPKICK#7, RAGE#13+|BASH#1, ENTRENCH#9, POMMEL_STRIKE#3, WILD_STRIKE#12|hand:2 / drawPile:1 / drawPile:1|4|[19, 19, 19, 19]|[3, 3, 3, 3]|0.0 / 0.0|None|0 / 0|none|
|13|2|44|[69]|[0]|9|DROPKICK#10, BARRICADE#8, DROPKICK#7|BASH#1, ENTRENCH#9, POMMEL_STRIKE#3, WILD_STRIKE#12|hand:2 / drawPile:1 / drawPile:1|4|[6, 6, 6, 6]|[2, 2, 2, 2]|0.0 / 0.0|None|0 / 0|none|
|14|2|44|[69]|[0]|9|BARRICADE#8, DROPKICK#7|BASH#1, ENTRENCH#9, POMMEL_STRIKE#3, WILD_STRIKE#12|discardPile:1,hand:1 / drawPile:1 / drawPile:1|4|[2, 2, 2, 2]|[1, 1, 1, 1]|0.0 / 0.0|None|0 / 0|none|
|15|2|44|[68]|[0]|9|BARRICADE#8|BASH#1, ENTRENCH#9, POMMEL_STRIKE#3, WILD_STRIKE#12|discardPile:2 / drawPile:1 / drawPile:1|4|[1, 1, 1, 1]|[0, 0, 0, 0]|0.0 / 0.0|None|0 / 0|none|
|16|3|37|[68]|[0]|9|ENTRENCH#9, WILD_STRIKE#12, BASH#1, POMMEL_STRIKE#3, DROPKICK#10|ARMAMENTS#4, BARRICADE#8, DROPKICK#7, RAGE#13+|drawPile:1,hand:1 / hand:1 / hand:1|4|[202, 173, 106, 183]|[6, 5, 5, 5]|0.0 / 0.0|None|0 / 0|none|
|17|3|37|[68]|[2]|9|ENTRENCH#9, WILD_STRIKE#12, POMMEL_STRIKE#3, DROPKICK#10|ARMAMENTS#4, BARRICADE#8, DROPKICK#7, RAGE#13+|drawPile:1,hand:1 / discardPile:1 / hand:1|4|[47, 24, 41, 48]|[4, 4, 4, 5]|0.0 / 0.0|None|0 / 0|none|
|18|3|37|[49]|[2]|9|ENTRENCH#9, WILD_STRIKE#12, DROPKICK#10, BARRICADE#8|ARMAMENTS#4, DROPKICK#7, RAGE#13+|drawPile:1,hand:1 / discardPile:1 / discardPile:1|4|[5, 5, 9, 5]|[2, 2, 4, 2]|0.0 / 0.0|None|0 / 0|none|
|19|3|37|[39]|[2]|9|ENTRENCH#9, WILD_STRIKE#12, BARRICADE#8, RAGE#13+|ARMAMENTS#4, DROPKICK#7|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[5, 5, 5, 5]|[2, 2, 2, 2]|0.0 / 0.0|None|0 / 0|none|
|20|3|37|[39]|[2]|9|ENTRENCH#9, WILD_STRIKE#12, BARRICADE#8|ARMAMENTS#4, DROPKICK#7|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[2, 2, 2, 2]|[1, 1, 1, 1]|0.0 / 0.0|None|0 / 0|none|
|21|3|37|[14]|[2]|10|ENTRENCH#9, BARRICADE#8|ARMAMENTS#4, DROPKICK#7, WOUND#14|discardPile:1,drawPile:1 / discardPile:1 / discardPile:1|4|[1, 1, 1, 1]|[0, 0, 0, 0]|0.0 / 0.0|None|0 / 0|none|
|22|4|30|[18]|[1]|10|DROPKICK#7, WOUND#14, ARMAMENTS#4, POMMEL_STRIKE#3, BASH#1|BARRICADE#8, DROPKICK#10, ENTRENCH#9, RAGE#13+, WILD_STRIKE#12|drawPile:1,hand:1 / hand:1 / hand:1|4|[14, 15, 15, 12]|[3, 3, 3, 2]|0.0 / 0.0|None|0 / 0|none|

**TARGET_COMBAT_EXHAUSTED_NO_SIGNAL**

```json
{
  "annotated_roots": 21,
  "bash_in_hand_roots": 6,
  "candidate_roots": 0,
  "candidate_worlds": 0,
  "cap_roots": 0,
  "cap_worlds": 0,
  "certified_roots": 0,
  "certified_worlds": 0,
  "dropkick_in_hand_roots": 12,
  "maximum_depth": 6,
  "minimum_active_pool": 9,
  "ordinary_roots": 21,
  "pommel_strike_in_hand_roots": 5,
  "supported_worlds": 84,
  "total_nodes": 1954,
  "unsupported_roots": 0,
  "unsupported_worlds": 0,
  "vulnerable_roots": 6
}
```

NONE is a bounded observation, never a training negative. Unsupported/capped worlds are not negatives.
