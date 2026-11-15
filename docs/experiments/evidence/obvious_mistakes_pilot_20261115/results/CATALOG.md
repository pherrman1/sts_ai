# Katalog: offensichtliche Fehler, Pilot #1056 (20 G16-Spiele aus §782)

Jeder Eintrag ist eine Hypothese, keine Wahrheit. Kategorien: Bug (Engine oder Such-Implementierung macht etwas anderes als das Spiel), Fehlvorstellung (Netz oder Suche bewertet falsch, die Regeln stimmen), vertretbar (bei genauem Hinsehen kein Fehler oder nicht entscheidbar), offen (nicht ohne gepaarte Probe entscheidbar).

58 Einträge: vertretbar 25, Fehlvorstellung 20, offen 11, Bug 2.

Gruppen: D = Kampf, der den Lauf beendet hat; R = Kampfwurzel, an der der 16k-Baum selbst die 64k-Wahl höher bewertet; F = gewonnener Kampf mit hohem HP-Verlust gegen die §782-Norm; O = Entscheidung außerhalb des Kampfes, nach der der Critic fällt (bereinigt um den mittleren Sprung desselben Bildschirmwechsels).

Werte: p und Logit sind die PPO-Policy (net-0420, Temperatur 0, also wird immer die höchste p gewählt); der Critic schätzt P(Herz-Kill). Kampfwerte stammen aus dem 16k-Baum der gespielten Suche (Besuche, max-backed Q und mittleres q in Silver-Punkten, Prior); "64k" ist die Wahl einer frischen 64k-Suche derselben Wurzel, deren Q-Werte nicht aufgezeichnet sind.

## D-111378476-F56-THE_HEART · Fehlvorstellung · Tod F56

- A4 F56: BOSS THE_HEART: HP 98 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: 0.653 / 0.000
- Entscheidender Zug T2 (51 HP verloren); 13 von 63 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 66/111 blk 0 E 5 str 3 dex 1 FRAIL1 VULNERABLE1 WEAK1 | pots [] | hand: LIMIT_BREAK(1), SECOND_WIND+(1), DEFEND_RED(1), BURN, SHRUG_IT_OFF(1), STRIKE_RED(1) | draw 25 disc 5 | CORRUPT_HEART 776/800 [CORRUPT_HEART_ECHO]`
- Gespielte Linie im Zug: play SHRUG_IT_OFF; play DEFEND_RED [64k: play STRIKE_RED -> m0]; play DEFEND_RED; play SECOND_WIND+ [64k: play STRIKE_RED -> m0]; play STRIKE_RED -> m0; end turn; select RAGE [64k: select IMPERVIOUS]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SHRUG_IT_OFF | gespielt 64k | 13334 | 7.6 | 4.5 | 0.253 |
| play DEFEND_RED |  | 13334 | 7.2 | 4.5 | 0.231 |
| play STRIKE_RED -> m0 |  | 6666 | 7.4 | 4.0 | 0.147 |
| play LIMIT_BREAK |  | 2222 | 7.3 | 3.8 | 0.129 |
| play SECOND_WIND+ |  | 2222 | 3.0 | 1.8 | 0.230 |
| end turn |  | 2222 | -5.4 | -5.8 | 0.010 |

**Einschätzung:** Runic Dome (Absichten verborgen). Im Echo-Zug T2 stehen bei 66 HP, Frail und Vulnerable alle Linien des 16k-Baums bei qBacked um 7, die Stellung ist also schon schlecht; der Zug selbst (Shrug, 2 Defend, Second Wind+) ist der defensivste. Hypothese: der Fehler liegt außerhalb des Kampfes in der Wahl von Runic Dome (Dome auf F17 bei 29/75 HP mit p 1,00, dazu Runic Pyramid auf F34). Beide Herz-Tode der Stichprobe haben Runic Dome, die 4 Herz-Kämpfe ohne Dome wurden alle gewonnen (n = 8, nur ein Hinweis). Gepaarte Probe: dieselben Herz-Zustände mit und ohne Dome.

## D-111378633-F56-THE_HEART · offen · Tod F56

- A4 F56: BOSS THE_HEART: HP 96 -> 0
- Tränke: ['SNECKO_OIL'] -> []
- Critic vor/nach dem Kampf: -0.022 / 0.000
- Entscheidender Zug T2 (61 HP verloren); 14 von 36 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 88/96 blk 0 E 4 str 10 dex 1 FRAIL1 VULNERABLE1 WEAK1 THORNS3 | pots [] | hand: DEFEND_RED(0), DEFEND_RED(0), REAPER(1), ANGER+(0), ANGER(2), POWER_THROUGH(2), ASCENDERS_BANE | draw 12 disc 0 | CORRUPT_HEART 712/800 [CORRUPT_HEART_ECHO]`
- Gespielte Linie im Zug: play POWER_THROUGH [64k: play ANGER+ -> m0]; play ANGER+ -> m0 [64k: play ANGER -> m0]; play ANGER -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play POWER_THROUGH | gespielt | 13334 | 21.2 | 17.5 | 0.246 |
| play ANGER+ -> m0 | 64k | 13334 | 21.1 | 17.4 | 0.174 |
| play ANGER -> m0 |  | 6666 | 20.1 | 17.2 | 0.165 |
| play REAPER |  | 2222 | 17.4 | 15.4 | 0.214 |
| play DEFEND_RED |  | 2222 | 18.7 | 15.8 | 0.184 |
| end turn |  | 2222 | 12.5 | 10.5 | 0.017 |

**Einschätzung:** Runic Dome und Snecko Eye. Critic schon vor dem Kampf bei -0,02. Im Echo-Zug T2 (88 HP) spielt die Suche Power Through und zwei Anger und lässt zwei Defend zu Kosten 0 liegen; wegen Beat of Death (2 Schaden je Karte) und Frail bringt ein Defend netto nur etwa 2 HP, also kein klarer Fehler. 61 HP verloren gegen verborgenes Echo. Wie D-111378476: Dome-Hypothese, keine Einzelzug-Erklärung.

## D-111378699-F16-SLIME_BOSS · Fehlvorstellung · Tod F16

- A1 F16: BOSS SLIME_BOSS: HP 59 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: -0.019 / 0.000
- Entscheidender Zug T2 (33 HP verloren); 4 von 24 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 59/80 blk 0 E 3 str 0 dex 0  | pots [] | hand: DEFEND_RED(1), DARK_EMBRACE(2), BASH(2), STRIKE_RED(1), POMMEL_STRIKE+(1) | draw 1 disc 15 | SLIME_BOSS 127/150 [SLIME_BOSS_SLAM]`
- Gespielte Linie im Zug: play STRIKE_RED -> m0; play DEFEND_RED; play POMMEL_STRIKE+ -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play STRIKE_RED -> m0 | gespielt 64k | 5829 | 20.2 | 19.0 | 0.111 |
| play DEFEND_RED |  | 5819 | 20.1 | 18.4 | 0.109 |
| play POMMEL_STRIKE+ -> m0 |  | 3170 | 19.9 | 18.3 | 0.345 |
| play DARK_EMBRACE |  | 1165 | 19.4 | 18.5 | 0.050 |
| play BASH -> m0 |  | 1018 | 18.1 | 16.1 | 0.379 |
| end turn |  | 939 | 14.1 | 12.8 | 0.007 |

**Einschätzung:** Hypothese außerhalb des Kampfes: auf F15 bei 59/80 HP Smith (Armaments) statt Rest. Im Kampf sind alle Kandidaten fast gleich (qBacked 19,4 bis 20,2), Slam kostet 33 HP, das Deck mit 18 Karten hat kaum Block. Teil des Musters Smith vor dem Akt-1-Boss bei mittleren HP (siehe RESULT).

## D-111378773-F13-GREMLIN_NOB · Fehlvorstellung · Tod F13

- A1 F13: ELITE GREMLIN_NOB: HP 52 -> 0
- Tränke: ['SPEED_POTION'] -> []
- Critic vor/nach dem Kampf: 0.100 / 0.000
- Entscheidender Zug T2 (27 HP verloren); 2 von 16 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 42/75 blk 0 E 3 str 0 dex 0 VULNERABLE2 | pots [SPEED_POTION] | hand: STRIKE_RED(1), BASH(2), DEFEND_RED(1), STRIKE_RED(1), FEEL_NO_PAIN(1) | draw 3 disc 11 | GREMLIN_NOB 50/88 [GREMLIN_NOB_RUSH] strength2`
- Gespielte Linie im Zug: drink SPEED_POTION [64k: play STRIKE_RED -> m0]; play BASH -> m0; play STRIKE_RED -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BASH -> m0 |  | 5560 | 44.7 | 39.5 | 0.553 |
| drink SPEED_POTION | gespielt | 5435 | 44.9 | 38.3 | 0.049 |
| play STRIKE_RED -> m0 | 64k | 2689 | 40.9 | 36.4 | 0.180 |
| play DEFEND_RED |  | 909 | 31.1 | 28.4 | 0.137 |
| play FEEL_NO_PAIN |  | 905 | 30.7 | 28.1 | 0.076 |
| end turn |  | 892 | 17.6 | 17.0 | 0.006 |

**Einschätzung:** T2 gegen Rush (27 Schaden auf Vulnerable): die Suche trinkt Speed Potion (+5 Dex in diesem Zug) und spielt danach Bash und Strike, aber kein Defend; der Trank verpufft. Im 16k-Baum liegt Trinken (44,9) praktisch gleich mit Bash (44,7), die 64k-Suche wählt Strike. Nob stirbt nicht, der Lauf endet einen Zug später mit Nob bei etwa 6 HP. Fehlvorstellung der Suche über den Trankwert (Trank ohne Wirkung getrunken), vor einer gepaarten Probe nur Hypothese.

## D-111378882-F50-TIME_EATER · Fehlvorstellung · Tod F50

- A3 F50: BOSS TIME_EATER: HP 80 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: 0.401 / 0.000
- Entscheidender Zug T3 (28 HP verloren); 11 von 29 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 46/80 blk 0 E 7 str 3 dex 0 FRAIL1 VULNERABLE1 WEAK1 | pots [] | hand: DISARM+(1), DEFEND_RED(1), BLOOD_FOR_BLOOD(2), ASCENDERS_BANE | draw 3 disc 27 | TIME_EATER 368/480 [TIME_EATER_REVERBERATE] block20 strength2`
- Gespielte Linie im Zug: play BLOOD_FOR_BLOOD -> m0 [64k: play DEFEND_RED]; play DISARM+ -> m0 [64k: play ASCENDERS_BANE]; play DEFEND_RED; play ASCENDERS_BANE [64k: play HAVOC]; play HAVOC; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play DISARM+ -> m0 |  | 5517 | 10.1 | 6.3 | 0.319 |
| play BLOOD_FOR_BLOOD -> m0 | gespielt | 5515 | 10.2 | 6.3 | 0.187 |
| play DEFEND_RED | 64k | 2847 | 8.1 | 4.8 | 0.264 |
| play ASCENDERS_BANE |  | 1069 | 4.4 | -0.2 | 0.198 |
| end turn |  | 1067 | -7.8 | -9.8 | 0.032 |

**Einschätzung:** 80/80 in vier Zügen tot, Time Eater nur von 480 auf 367. Kein einzelner Zug: im 16k-Baum liegen die Linien nah beieinander (10,1 / 10,2 / 8,1). Hypothese: das Deck (36 Karten, Corruption+ und zwei Reaper spät genommen, Critic fiel bei Corruption+ um 0,175, siehe O-111378882-104) hat zu wenig Schaden pro Zug für Time Eater. Fehlvorstellung im Deckbau des Actors.

## D-111378911-F45-REPTOMANCER · offen · Tod F45

- A3 F45: ELITE REPTOMANCER: HP 93 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: 0.386 / 0.000
- Entscheidender Zug T1 (92 HP verloren); 3 von 12 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 93/96 blk 0 E 3 str 1 dex 0  | pots [] | hand: DEFEND_RED+(3), SPOT_WEAKNESS(0), HAVOC(2), BASH+(1), STRIKE_RED+(3), ASCENDERS_BANE, POMMEL_STRIKE+(3) | draw 18 disc 4 | DAGGER 25/25 [DAGGER_STAB]; DAGGER 22/22 [DAGGER_EXPLODE]; REPTOMANCER 182/195 [REPTOMANCER_SNAKE_STRIKE]; DAGGER 22/22 [DAGGER_STAB]; DAGGER 20/20 [DAGGER_EXPLODE]`
- Gespielte Linie im Zug: play DEFEND_RED+ [64k: play SPOT_WEAKNESS -> m1]; play SPOT_WEAKNESS -> m2 [64k: play SPOT_WEAKNESS -> m1]; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SPOT_WEAKNESS -> m2 |  | 3750 | 1.5 | -2.3 | 0.028 |
| play DEFEND_RED+ | gespielt | 3750 | 1.8 | -1.0 | 0.015 |
| play SPOT_WEAKNESS -> m0 |  | 1750 | -0.3 | -4.9 | 0.025 |
| play HAVOC |  | 1750 | -1.9 | -4.2 | 0.032 |
| play BASH+ -> m2 |  | 750 | -4.4 | -5.5 | 0.032 |
| play BASH+ -> m1 |  | 750 | -4.5 | -6.1 | 0.068 |
| play SPOT_WEAKNESS -> m1 | 64k | 0 | - | - | 0.035 |

**Einschätzung:** 93/96 HP, nach zwei Zügen tot. T1 kommen etwa 100 Schaden (zwei explodierende Dolche, Snake Strike, zwei Stiche); Snecko Eye macht Defend+ teuer (3), maximal 8 Block. Alle Linien des 16k-Baums bei qBacked unter 2: die Stellung war vor T1 verloren. In T0 hätte man die beiden alten Dolche (22 und 20 HP) nicht töten können. Hebel liegt im Deck (Snecko Eye, zweites Corruption auf F44 mit p 1,00) oder im Elite-Pfad, nicht in einem Zug.

## D-111378951-F55-SHIELD_AND_SPEAR · offen · Tod F55

- A4 F55: ELITE SHIELD_AND_SPEAR: HP 75 -> 0
- Tränke: ['ENERGY_POTION', 'ENTROPIC_BREW'] -> []
- Critic vor/nach dem Kampf: 0.637 / 0.000
- Entscheidender Zug T1 (38 HP verloren); 12 von 22 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 68/80 blk 6 E 5 str 5 dex 0 DEMON_FORM2 THORNS3 VIGOR8 | pots [STRENGTH_POTION] | hand: BURN, BURN, STRIKE_RED(1), DEMON_FORM(3), CORRUPTION(3) | draw 24 disc 8 | SPIRE_SHIELD 122/125 [SPIRE_SHIELD_FORTIFY]; SPIRE_SPEAR 154/180 [SPIRE_SPEAR_SKEWER]`
- Gespielte Linie im Zug: play STRIKE_RED -> m1 [64k: play CORRUPTION]; play CORRUPTION; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play CORRUPTION | 64k | 5335 | 52.9 | 40.5 | 0.615 |
| play STRIKE_RED -> m1 | gespielt | 5335 | 53.8 | 41.6 | 0.081 |
| drink STRENGTH_POTION |  | 2666 | 47.4 | 36.4 | 0.077 |
| play DEMON_FORM |  | 888 | 10.5 | 6.9 | 0.173 |
| play STRIKE_RED -> m0 |  | 888 | 17.1 | 8.7 | 0.048 |
| end turn |  | 888 | -1.8 | -4.2 | 0.006 |

**Einschätzung:** 75/80, zwei Züge. T0 alle vier Tränke (Entropic Brew, Power Potion für Demon Form, Energy, Fire) in einem Zug; T1 Hand Burn, Burn, Strike, Demon Form, Corruption: kein Block möglich, 38 HP verloren. Zieh-Pech plus Alles-auf-T0. 64k hätte in T0 Demon Form statt Shrug gespielt (R-111378951-F55-T0-d9, kleine Lücke 1,9). Nicht ohne Probe entscheidbar.

## D-111379064-F40-GIANT_HEAD · offen · Tod F40

- A3 F40: ELITE GIANT_HEAD: HP 89 -> 0
- Tränke: ['SKILL_POTION'] -> []
- Critic vor/nach dem Kampf: 0.446 / 0.000
- Entscheidender Zug T5 (41 HP verloren); 21 von 52 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 60/89 blk 6 E 4 str 6 dex 0 BRUTALITY1 FIRE_BREATHING6 NEXT_TURN_BLOCK3 PLATED_ARMOR2 | pots [] | hand: HEADBUTT(1), BLOOD_FOR_BLOOD(0), ANGER(0), REAPER(2), PERFECTED_STRIKE(2), CORRUPTION(3) | draw 13 disc 0 | GIANT_HEAD 267/520 [GIANT_HEAD_IT_IS_TIME] strength-2`
- Gespielte Linie im Zug: play BLOOD_FOR_BLOOD -> m0 [64k: play ANGER -> m0]; play PERFECTED_STRIKE -> m0 [64k: play ANGER -> m0]; play HEADBUTT -> m0; select BLOOD_FOR_BLOOD; play ANGER -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play REAPER |  | 5208 | 34.0 | 30.5 | 0.233 |
| play BLOOD_FOR_BLOOD -> m0 | gespielt | 5068 | 34.8 | 30.5 | 0.183 |
| play ANGER -> m0 | 64k | 2346 | 33.1 | 30.0 | 0.172 |
| play HEADBUTT -> m0 |  | 2151 | 32.2 | 29.7 | 0.153 |
| play PERFECTED_STRIKE -> m0 |  | 1018 | 33.6 | 30.9 | 0.173 |
| play CORRUPTION |  | 902 | 31.3 | 29.1 | 0.079 |

**Einschätzung:** 89/89, sieben Züge, Giant Head bei 82/520. Schadensrennen gegen It Is Time verloren. Lizard Tail war schon auf F25 (Slavers) verbraucht, also kein Engine-Fehler. Viele 64k-Abweichungen (21 von 52 Wurzeln), aber die 16k-Bäume bevorzugen fast immer die gespielte Linie. Offen; Kandidat für eine gepaarte Probe mit mehr Suche.

## D-111379098-F24-SLAVERS · offen · Tod F24

- A2 F24: ELITE SLAVERS: HP 62 -> 0
- Tränke: ['DEXTERITY_POTION', 'LIQUID_BRONZE'] -> []
- Critic vor/nach dem Kampf: 0.195 / 0.000
- Entscheidender Zug T0 (24 HP verloren); 10 von 25 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 62/68 blk 0 E 3 str 0 dex 0  | pots [DEXTERITY_POTION,LIQUID_BRONZE] | hand: STRIKE_RED(1), SHRUG_IT_OFF(1), EXHUME(1), DEFEND_RED(1), SEEING_RED(1) | draw 19 disc 0 | BLUE_SLAVER 63/63 [BLUE_SLAVER_STAB]; TASKMASTER 79/79 [TASKMASTER_SCOURING_WHIP]; RED_SLAVER 60/60 [RED_SLAVER_STAB]`
- Gespielte Linie im Zug: drink DEXTERITY_POTION [64k: drink LIQUID_BRONZE]; play SHRUG_IT_OFF; drink LIQUID_BRONZE; play BATTLE_TRANCE; play STRIKE_RED -> m1 [64k: play FEEL_NO_PAIN]; play SEEING_RED; play STRIKE_RED -> m2 [64k: play FEEL_NO_PAIN]; play FEEL_NO_PAIN; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SEEING_RED |  | 4533 | 20.9 | 11.1 | 0.076 |
| drink DEXTERITY_POTION | gespielt | 4533 | 21.4 | 11.6 | 0.196 |
| play EXHUME |  | 2533 | 14.1 | 8.2 | 0.067 |
| play STRIKE_RED -> m1 |  | 1200 | 12.7 | 7.1 | 0.052 |
| play STRIKE_RED -> m0 |  | 1200 | 12.8 | 8.0 | 0.129 |
| play SHRUG_IT_OFF |  | 400 | 8.4 | 5.8 | 0.122 |
| drink LIQUID_BRONZE | 64k | 400 | 13.2 | 8.1 | 0.196 |

**Einschätzung:** 62/68, vier Züge. T0 beide Tränke (Dex, Liquid Bronze), trotzdem 24 HP verloren; danach Wunden vom Taskmaster und kaum Block. Der 16k-Baum bevorzugt Dex zuerst (21,4) vor Liquid Bronze (13,2). Kein klarer Einzelfehler.

## D-111379099-F16-HEXAGHOST · Fehlvorstellung · Tod F16

- A1 F16: BOSS HEXAGHOST: HP 44 -> 0
- Tränke: ['GAMBLERS_BREW'] -> []
- Critic vor/nach dem Kampf: 0.088 / 0.000
- Entscheidender Zug T1 (18 HP verloren); 10 von 37 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 44/75 blk 0 E 3 str 0 dex 0  | pots [] | hand: RECKLESS_CHARGE(0), CLEAVE+(1), CARNAGE+(2), DAZED, STRIKE_RED(1) | draw 9 disc 6 | HEXAGHOST 234/264 [HEXAGHOST_DIVIDER] weak1`
- Gespielte Linie im Zug: play CARNAGE+ -> m0 [64k: play RECKLESS_CHARGE -> m0]; play RECKLESS_CHARGE -> m0; play CLEAVE+; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play CARNAGE+ -> m0 | gespielt | 5512 | 48.1 | 38.5 | 0.475 |
| play CLEAVE+ |  | 5512 | 47.8 | 38.7 | 0.268 |
| play RECKLESS_CHARGE -> m0 | 64k | 2844 | 42.2 | 37.1 | 0.088 |
| play STRIKE_RED -> m0 |  | 1066 | 37.6 | 35.4 | 0.161 |
| end turn |  | 1066 | 24.0 | 23.0 | 0.008 |

**Einschätzung:** Hypothese außerhalb des Kampfes: bei 44/75 HP vor dem Boss Smith (Blood for Blood) statt Rest; dazu Orrery mit 4 von 5 Karten (Deck 20). Im Kampf verliert Inferno die letzten HP (19 auf 6 auf 0). Teil des Musters Smith vor dem Akt-1-Boss.

## D-111379130-F27-COLOSSEUM_EVENT_SLAVERS · Fehlvorstellung · Tod F27

- A2 F27: OTHER COLOSSEUM_EVENT_SLAVERS: HP 8 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: 0.029 / 0.000
- Entscheidender Zug T0 (6 HP verloren); 0 von 9 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 8/89 blk 0 E 4 str 0 dex 0 WEAK1 THORNS3 | pots [] | hand: METALLICIZE+(1), STRIKE_RED(1), DEFEND_RED(1), STRIKE_RED(1), STRIKE_RED(1) | draw 13 disc 0 | BLUE_SLAVER 51/51 [BLUE_SLAVER_STAB] vulnerable1 weak1; RED_SLAVER 49/49 [RED_SLAVER_STAB] vulnerable1 weak1`
- Gespielte Linie im Zug: play METALLICIZE+; play STRIKE_RED -> m0; play STRIKE_RED -> m0; play STRIKE_RED -> m0; play DEFEND_RED; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play METALLICIZE+ | gespielt 64k | 5512 | 11.9 | 8.1 | 0.189 |
| play STRIKE_RED -> m1 |  | 5512 | 11.2 | 7.8 | 0.300 |
| play STRIKE_RED -> m0 |  | 2844 | 10.9 | 7.8 | 0.307 |
| play DEFEND_RED |  | 1066 | 8.8 | 4.6 | 0.202 |
| end turn |  | 1066 | -13.6 | -13.6 | 0.002 |

**Einschätzung:** Mit 8/89 HP in den Colosseum-Kampf: tot im ersten Zug. Der Fehler liegt davor: Gremlin-Leader-Elite bei 18/89 (p 0,59, danach 8 HP) und dann der ?-Raum. Fehlvorstellung des Actors über Risiko bei niedrigen HP (Muster Elite bei <= 50 % HP, siehe RESULT).

## D-111379193-F51-AWAKENED_ONE · offen · Tod F51

- A3 F51: BOSS AWAKENED_ONE: HP 61 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: 0.259 / 0.000
- Entscheidender Zug T4 (18 HP verloren); 10 von 44 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 32/92 blk 0 E 4 str 7 dex 0 DARK_EMBRACE1 THORNS3 | pots [] | hand: INFERNAL_BLADE(1), SHOCKWAVE(2), CARNAGE(2), DARK_EMBRACE(2), POMMEL_STRIKE+(1) | draw 25 disc 0 | AWAKENED_ONE 262/320 [AWAKENED_ONE_SLASH] strength4 vulnerable1`
- Gespielte Linie im Zug: play INFERNAL_BLADE [64k: play POMMEL_STRIKE+ -> m2]; play PUMMEL -> m2 [64k: play POMMEL_STRIKE+ -> m2]; play POMMEL_STRIKE+ -> m2; play WHIRLWIND+; end turn; select skip [64k: select WILD_STRIKE]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SHOCKWAVE |  | 5335 | 34.8 | 33.1 | 0.362 |
| play INFERNAL_BLADE | gespielt | 5335 | 34.8 | 32.3 | 0.170 |
| play POMMEL_STRIKE+ -> m2 | 64k | 2666 | 34.1 | 31.9 | 0.190 |
| play DARK_EMBRACE |  | 888 | 31.3 | 29.8 | 0.138 |
| play CARNAGE -> m2 |  | 888 | 33.0 | 31.6 | 0.136 |
| end turn |  | 888 | 19.7 | 19.1 | 0.004 |

**Einschätzung:** Knapp verloren: Awakened One stand bei 2/320, als der Spieler starb. Kein auffälliger Zug; Grenzfall der Kampfsuche. Kandidat für eine gepaarte Probe mit 64k im ganzen Kampf.

## D-111379236-F31-SNAKE_PLANT · Fehlvorstellung · Tod F31

- A2 F31: NORMAL SNAKE_PLANT: HP 17 -> 0
- Tränke: [] -> []
- Critic vor/nach dem Kampf: -0.028 / 0.000
- Entscheidender Zug T1 (10 HP verloren); 5 von 19 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 13/86 blk 0 E 3 str 0 dex 0  | pots [] | hand: DEMON_FORM(3), SHRUG_IT_OFF(1), STRIKE_RED(1), SHRUG_IT_OFF(1), DEFEND_RED(1), DARK_EMBRACE(2), DARK_EMBRACE(2), BATTLE_TRANCE(0) | draw 19 disc 2 | SNAKE_PLANT 62/78 [SNAKE_PLANT_CHOMP] vulnerable1`
- Gespielte Linie im Zug: play SHRUG_IT_OFF; play BATTLE_TRANCE [64k: play SHRUG_IT_OFF]; play SEEING_RED [64k: play STRIKE_RED -> m0]; play SHRUG_IT_OFF; play ANGER -> m0; play STRIKE_RED -> m0; play STRIKE_RED -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SHRUG_IT_OFF | gespielt 64k | 4763 | 28.8 | 25.1 | 0.243 |
| play STRIKE_RED -> m0 |  | 4763 | 28.1 | 25.0 | 0.190 |
| play BATTLE_TRANCE |  | 2095 | 25.0 | 19.3 | 0.140 |
| play DEFEND_RED |  | 2095 | 26.4 | 23.9 | 0.171 |
| play DARK_EMBRACE |  | 761 | 11.4 | 9.2 | 0.052 |
| play DEMON_FORM |  | 761 | 7.3 | 6.7 | 0.202 |

**Einschätzung:** Normaler Kampf mit 17/86 HP: tot. Davor Elite-Route in Akt 2 bei 56/84, Gremlin Leader, dann Raum für Raum ohne Rast. Deck voller Powers (Demon Form x2, Dark Embrace x3). Fehlvorstellung des Actors über Risiko und Deckbau.

## D-111379246-F20-SHELLED_PARASITE_AND_FUNGI · offen · Tod F20

- A2 F20: NORMAL SHELLED_PARASITE_AND_FUNGI: HP 30 -> 0
- Tränke: ['FEAR_POTION', 'ELIXIR_POTION'] -> []
- Critic vor/nach dem Kampf: 0.022 / 0.000
- Entscheidender Zug T1 (17 HP verloren); 5 von 17 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 18/75 blk 0 E 3 str 0 dex 0 FRAIL2 | pots [ELIXIR_POTION] | hand: DEFEND_RED(1), ANGER(0), STRIKE_RED(1), BASH(2), ANGER(0), SHOCKWAVE+(2), STRIKE_RED(1), STRIKE_RED(1) | draw 8 disc 6 | SHELLED_PARASITE 48/74 [SHELLED_PARASITE_DOUBLE_STRIKE] block13 vulnerable2; FUNGI_BEAST 26/26 [FUNGI_BEAST_GROW]`
- Gespielte Linie im Zug: play BASH -> m1 [64k: play SHOCKWAVE+]; play DEFEND_RED [64k: play ANGER -> m1]; play ANGER -> m1; play ANGER -> m1; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BASH -> m1 | gespielt | 4533 | 39.9 | 28.7 | 0.083 |
| play DEFEND_RED |  | 4533 | 35.3 | 27.9 | 0.079 |
| play ANGER -> m0 |  | 2533 | 27.9 | 22.4 | 0.076 |
| play SHOCKWAVE+ | 64k | 1200 | 26.9 | 22.6 | 0.418 |
| play STRIKE_RED -> m0 |  | 1200 | 29.0 | 23.1 | 0.064 |
| play BASH -> m0 |  | 400 | 27.1 | 22.4 | 0.114 |

**Einschätzung:** 30/75 HP auf F20. T0 Power Through, Fear Potion, Perfected Strike, 12 HP verloren; T1 (18 HP) Bash statt Shockwave+ (16k-Baum: Bash 39,9 gegen Shockwave+ 26,9), 17 HP verloren; T2 Elixir. Mit 30 HP war der Kampf eng; kein eindeutiger Einzelfehler.

## R-111378476-F55-T5-d63 · Bug · Tod F56

- A4 F55: ELITE SHIELD_AND_SPEAR T5: gespielt select TRUE_GRIT+, 64k select FEED (16k-qBacked 149.0 vs 158.0, Lücke 9.0)
- Kampf gewonnen, HP-Verlust 16
- Zustand: `player 92/111 blk 0 E 5 str 13 dex 1 DARK_EMBRACE1 | pots [] | hand: STRIKE_RED(1), HEMOKINESIS(1), UPPERCUT(2), STRIKE_RED(1), STRIKE_RED(1), ANGER(0), ANGER(0), ANGER(0), ANGER(0) | draw 0 disc 2 | SPIRE_SPEAR 98/180 [SPIRE_SPEAR_SKEWER] strength2`
- Gespielte Linie im Zug: play EXHUME; select TRUE_GRIT+ [64k: select FEED]; play ANGER -> m1 [64k: play UPPERCUT -> m1]; play TRUE_GRIT+ [64k: play UPPERCUT -> m1]; select STRIKE_RED [64k: select UPPERCUT]; play UPPERCUT -> m1; play ANGER -> m1 [64k: play STRIKE_RED -> m1]; play STRIKE_RED -> m1

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| select FEED | 64k | 8234 | 158.0 | 153.6 | 0.049 |
| select TRUE_GRIT+ | gespielt | 3813 | 149.0 | 146.9 | 0.053 |
| select ASCENDERS_BANE |  | 3796 | 149.0 | 146.5 | 0.048 |
| select SHRUG_IT_OFF |  | 1808 | 149.0 | 146.7 | 0.050 |
| select OFFERING |  | 1790 | 149.0 | 144.9 | 0.065 |
| select MASTER_OF_STRATEGY |  | 809 | 149.0 | 146.4 | 0.066 |

**Einschätzung:** Exhume-Wahl mit 19 legalen Optionen bei k = 16. Feed hat aus dem wiederverwendeten Baum 8.234 Besuche und das höchste qBacked (158 gegen 149), wird aber nicht gespielt: Gumbel zieht die 16 Kandidaten nur aus Rauschen und Prior (fast gleich verteilt) und lässt hier Feed draußen, obwohl der geerbte Baum es klar vorzieht. Einziger solcher Fall mit Lücke >= 1 in 7.447 Wurzeln (19 Wurzeln mit geerbtem, nicht gespieltem Besuchsmaximum, alle anderen mit Lücke unter 0). Such-Design-Fehler: die Kandidatenwahl ignoriert geerbte Evidenz. Kosten hier: Feed-Max-HP vor dem Herz (Tod auf F56).

## R-111378633-F51-T3-d16 · vertretbar · Tod F56

- A3 F51: BOSS AWAKENED_ONE T3: gespielt play REAPER, 64k play ANGER -> m1 (16k-qBacked 117.7 vs 125.2, Lücke 7.5)
- Kampf gewonnen, HP-Verlust 46
- Zustand: `player 32/90 blk 9 E 4 str 23 dex 1 DEMON_FORM3 | pots [] | hand: HEADBUTT(1), FEED(0), REAPER(1), BATTLE_TRANCE(1), POWER_THROUGH(2), BASH(2), SECOND_WIND(1), ANGER(1), DEFEND_RED(1), STRIKE_RED(0) | draw 0 disc 1 | CULTIST 52/52 [CULTIST_DARK_STRIKE] strength14; CULTIST 40/50 [CULTIST_DARK_STRIKE] strength14; AWAKENED_ONE 320/320 [AWAKENED_ONE_SOUL_STRIKE] strength7`
- Gespielte Linie im Zug: play SHRUG_IT_OFF [64k: play ANGER -> m0]; play REAPER [64k: play ANGER -> m1]; play BATTLE_TRANCE [64k: play STRIKE_RED -> m2]; play SECOND_WIND [64k: play ANGER -> m0]; play ANGER -> m2 [64k: play STRIKE_RED -> m2]; play FEED -> m0 [64k: play STRIKE_RED -> m1]; play STRIKE_RED -> m1; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play FEED -> m0 |  | 3767 | 107.2 | 94.0 | 0.059 |
| play REAPER | gespielt | 3761 | 117.7 | 103.0 | 0.112 |
| play ANGER -> m0 |  | 1758 | 113.7 | 96.3 | 0.056 |
| play HEADBUTT -> m1 |  | 1752 | 113.2 | 98.5 | 0.051 |
| play BASH -> m2 |  | 756 | 109.5 | 91.6 | 0.063 |
| play DEFEND_RED |  | 753 | 114.5 | 96.3 | 0.023 |
| play ANGER -> m1 | 64k | 258 | 125.2 | 100.1 | 0.065 |

**Einschätzung:** 21 legale Optionen; die 64k-Wahl Anger -> m1 hat nur 258 Besuche, ihr hohes qBacked (125 gegen 118) ist ein Max-Backup-Wert einer dünnen Kante und damit optimistisch. Kein belastbarer Fehler.

## R-111378951-F55-T0-d9 · vertretbar · Tod F55

- A4 F55: ELITE SHIELD_AND_SPEAR T0: gespielt play SHRUG_IT_OFF, 64k play DEMON_FORM (16k-qBacked 44.0 vs 46.0, Lücke 1.9)
- Kampf verloren, HP-Verlust 75
- Zustand: `player 75/80 blk 13 E 3 str 0 dex 0 THORNS3 VIGOR8 | pots [STRENGTH_POTION] | hand: BLOOD_FOR_BLOOD(4), IMPERVIOUS(2), SHRUG_IT_OFF(1), DEFEND_RED(1), DEMON_FORM(0), SPOT_WEAKNESS(1) | draw 28 disc 2 | SPIRE_SHIELD 125/125 [SPIRE_SHIELD_BASH]; SPIRE_SPEAR 160/180 [SPIRE_SPEAR_BURN_STRIKE]`
- Gespielte Linie im Zug: drink ENTROPIC_BREW [64k: play IMPERVIOUS]; drink POWER_POTION; select DEMON_FORM; drink ENERGY_POTION [64k: play SHRUG_IT_OFF]; drink FIRE_POTION -> m1 [64k: play SHRUG_IT_OFF]; play SHRUG_IT_OFF; play DEFEND_RED [64k: play SHRUG_IT_OFF]; play SHOCKWAVE [64k: play SHRUG_IT_OFF]; play SHRUG_IT_OFF [64k: play DEMON_FORM]; play SPOT_WEAKNESS -> m1 [64k: play IMPERVIOUS]; play DEMON_FORM; play DEFEND_RED; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SHRUG_IT_OFF | gespielt | 4668 | 44.0 | 31.0 | 0.151 |
| drink STRENGTH_POTION |  | 4668 | 41.2 | 31.2 | 0.120 |
| play SPOT_WEAKNESS -> m1 |  | 2000 | 41.8 | 32.4 | 0.179 |
| play DEMON_FORM | 64k | 2000 | 46.0 | 33.3 | 0.129 |
| play SPOT_WEAKNESS -> m0 |  | 666 | 36.2 | 29.7 | 0.238 |
| play IMPERVIOUS |  | 666 | 38.9 | 33.7 | 0.131 |

**Einschätzung:** Sequential Halving hat Demon Form mit 2.000 Besuchen in einer frühen Runde aussortiert; sein höheres qBacked (46,0 gegen 44,0) ruht auf halb so vielen Besuchen. Normales Rauschen der Endauswahl.

## R-111378911-F42-T4-d21 · vertretbar · Tod F45

- A3 F42: ELITE GIANT_HEAD T4: gespielt play DISARM+ -> m0, 64k play BATTLE_TRANCE+ (16k-qBacked 138.0 vs 141.1, Lücke 3.1)
- Kampf gewonnen, HP-Verlust -5
- Zustand: `player 87/93 blk 28 E 3 str 6 dex 0 NO_DRAW1 FEEL_NO_PAIN4 | pots [] | hand: STRIKE_RED+(2), DISARM+(0), RECKLESS_CHARGE+(1), STRIKE_RED+(3), ASCENDERS_BANE, BATTLE_TRANCE+(0), FEED(3), DISARM+(0) | draw 5 disc 6 | GIANT_HEAD 160/520 [GIANT_HEAD_IT_IS_TIME] vulnerable1`
- Gespielte Linie im Zug: play SHRUG_IT_OFF; play DEFEND_RED+; play BATTLE_TRANCE; play DISARM+ -> m0 [64k: play BATTLE_TRANCE+]; play DISARM+ -> m0; play RECKLESS_CHARGE+ -> m0; play STRIKE_RED+ -> m0 [64k: play BATTLE_TRANCE+]; end turn [64k: play BATTLE_TRANCE+]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play DISARM+ -> m0 | gespielt | 4668 | 138.0 | 133.1 | 0.166 |
| play DISARM+ -> m0 |  | 4668 | 137.1 | 132.5 | 0.166 |
| play RECKLESS_CHARGE+ -> m0 |  | 2000 | 138.3 | 132.9 | 0.097 |
| play STRIKE_RED+ -> m0 |  | 2000 | 137.8 | 134.0 | 0.146 |
| play BATTLE_TRANCE+ | 64k | 666 | 141.1 | 131.8 | 0.164 |
| play FEED -> m0 |  | 666 | 127.6 | 124.4 | 0.112 |

**Einschätzung:** Battle Trance+ mit 666 Besuchen früh ausgeschieden, qBacked 141 gegen 138 auf dünner Basis. Kampf gewonnen mit HP-Gewinn.

## R-111378882-F40-T1-d11 · vertretbar · Tod F50

- A3 F40: ELITE NEMESIS T1: gespielt play ANGER -> m0, 64k play REAPER (16k-qBacked 119.5 vs 122.5, Lücke 3.0)
- Kampf gewonnen, HP-Verlust 0
- Zustand: `player 80/80 blk 0 E 5 str 0 dex 0 BUFFER1 DARK_EMBRACE1 METALLICIZE3 | pots [] | hand: DEFEND_RED(1), STRIKE_RED(1), BODY_SLAM+(0), ANGER(0), REAPER(2) | draw 11 disc 16 | NEMESIS 191/200 [NEMESIS_SCYTHE] strength-3 vulnerable4 weak4`
- Gespielte Linie im Zug: play ANGER -> m0 [64k: play REAPER]; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BODY_SLAM+ -> m0 |  | 5335 | 118.8 | 111.5 | 0.169 |
| play ANGER -> m0 | gespielt | 5335 | 119.5 | 111.5 | 0.169 |
| play STRIKE_RED -> m0 |  | 2666 | 120.3 | 109.9 | 0.129 |
| play REAPER | 64k | 888 | 122.5 | 110.2 | 0.183 |
| play DEFEND_RED |  | 888 | 122.8 | 109.4 | 0.299 |
| end turn |  | 888 | 118.2 | 106.5 | 0.051 |

**Einschätzung:** Reaper mit 888 Besuchen früh ausgeschieden (122,5 gegen 119,5). Kampf ohne HP-Verlust gewonnen.

## R-111379035-F39-T2-d17 · vertretbar · Herz-Sieg

- A3 F39: MONSTER TRANSIENT T2: gespielt play RECKLESS_CHARGE -> m0, 64k play INFLAME+ (16k-qBacked 157.9 vs 160.4, Lücke 2.5)
- Kampf gewonnen, HP-Verlust 6
- Zustand: `player 69/75 blk 17 E 5 str 3 dex 0 FEEL_NO_PAIN9 THORNS3 | pots [ENERGY_POTION,POWER_POTION,BLOCK_POTION,FLEX_POTION] | hand: SWORD_BOOMERANG+(1), RECKLESS_CHARGE(0), INFLAME+(1), DEFEND_RED+(0), ASCENDERS_BANE | draw 7 disc 8 | TRANSIENT 923/999 [TRANSIENT_ATTACK] vulnerable3 weak1`
- Gespielte Linie im Zug: play SHRUG_IT_OFF; play RECKLESS_CHARGE -> m0 [64k: play INFLAME+]; play SWORD_BOOMERANG+; play DEFEND_RED+ [64k: play INFLAME+]; play INFLAME+; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play DEFEND_RED+ |  | 4689 | 156.5 | 150.3 | 0.213 |
| play RECKLESS_CHARGE -> m0 | gespielt | 4598 | 157.9 | 150.1 | 0.117 |
| play SWORD_BOOMERANG+ |  | 2774 | 157.6 | 150.9 | 0.245 |
| play INFLAME+ | 64k | 1430 | 160.4 | 152.7 | 0.301 |
| drink POWER_POTION |  | 1260 | 155.6 | 152.2 | 0.024 |
| drink FLEX_POTION |  | 458 | 155.2 | 146.4 | 0.024 |

**Einschätzung:** Transient, Reckless Charge vs. Inflame+ zuerst (beide gespielt). Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111378335-F12-T0-d2 · vertretbar · Herz-Sieg

- A1 F12: ELITE LAGAVULIN T0: gespielt end turn, 64k drink ENERGY_POTION (16k-qBacked 50.7 vs 53.2, Lücke 2.4)
- Kampf gewonnen, HP-Verlust 13
- Zustand: `player 30/89 blk 0 E 1 str 0 dex 0  | pots [ENERGY_POTION] | hand: STRIKE_RED(1), DEFEND_RED(1), STRIKE_RED(1), CLOTHESLINE+(2) | draw 11 disc 1 | LAGAVULIN 112/112 [LAGAVULIN_SLEEP] strength2 vulnerable2`
- Gespielte Linie im Zug: play BASH -> m0 [64k: drink ENERGY_POTION]; end turn [64k: drink ENERGY_POTION]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| end turn | gespielt | 8942 | 50.7 | 41.8 | 0.091 |
| play DEFEND_RED |  | 7555 | 50.5 | 43.4 | 0.117 |
| drink ENERGY_POTION | 64k | 2449 | 53.2 | 47.7 | 0.470 |
| play STRIKE_RED -> m0 |  | 2388 | 52.9 | 46.5 | 0.322 |

**Einschätzung:** Lagavulin schläft, 1 Energie übrig: Zug beenden oder Energy Potion trinken. Der Trank hat 2.449 Besuche gegen 8.942; beide Wege sind vertretbar.

## R-111379035-F39-T4-d27 · vertretbar · Herz-Sieg

- A3 F39: MONSTER TRANSIENT T4: gespielt play HEADBUTT -> m0, 64k play SPOT_WEAKNESS -> m0 (16k-qBacked 160.6 vs 162.9, Lücke 2.3)
- Kampf gewonnen, HP-Verlust 6
- Zustand: `player 69/75 blk 0 E 5 str 6 dex 0 FEEL_NO_PAIN9 THORNS3 | pots [ENERGY_POTION,POWER_POTION,BLOCK_POTION,FLEX_POTION] | hand: HEADBUTT(1), DAZED, BLOOD_FOR_BLOOD(3), INFLAME(1), SPOT_WEAKNESS(0) | draw 7 disc 0 | TRANSIENT 818/999 [TRANSIENT_ATTACK] vulnerable1`
- Gespielte Linie im Zug: play HEADBUTT -> m0 [64k: play SPOT_WEAKNESS -> m0]; play INFLAME; play SPOT_WEAKNESS -> m0; play BLOOD_FOR_BLOOD -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BLOOD_FOR_BLOOD -> m0 |  | 4592 | 159.2 | 153.7 | 0.341 |
| play HEADBUTT -> m0 | gespielt | 4588 | 160.6 | 154.5 | 0.166 |
| play INFLAME |  | 2587 | 160.6 | 154.7 | 0.155 |
| play SPOT_WEAKNESS -> m0 | 64k | 1253 | 162.9 | 155.7 | 0.214 |
| drink BLOCK_POTION |  | 1247 | 158.6 | 149.5 | 0.029 |
| drink ENERGY_POTION |  | 447 | 157.5 | 143.4 | 0.029 |

**Einschätzung:** Transient, Headbutt vs. Spot Weakness zuerst (beide gespielt). Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111379067-F45-T1-d9 · vertretbar · Herz-Sieg

- A3 F45: ELITE REPTOMANCER T1: gespielt play SHOCKWAVE, 64k play DISARM -> m2 (16k-qBacked 136.1 vs 138.4, Lücke 2.3)
- Kampf gewonnen, HP-Verlust 22
- Zustand: `player 58/75 blk 14 E 5 str 0 dex 0 BRUTALITY1 PANACHE10 | pots [] | hand: DISARM(1), POWER_THROUGH(1), BLOOD_FOR_BLOOD+(2), STRIKE_RED(1), OFFERING(0), SHOCKWAVE(2) | draw 20 disc 4 | DAGGER 13/23 [DAGGER_EXPLODE] vulnerable2 weak2; REPTOMANCER 182/192 [REPTOMANCER_SUMMON] vulnerable2 weak2; DAGGER 25/25 [DAGGER_STAB]; DAGGER 23/23 [DAGGER_STAB]`
- Gespielte Linie im Zug: play SHOCKWAVE [64k: play DISARM -> m2]; play STRIKE_RED -> m2 [64k: play OFFERING]; play OFFERING; play DISARM -> m2 [64k: play POWER_THROUGH]; play BLOOD_FOR_BLOOD+ -> m1; play DARK_EMBRACE; play WHIRLWIND+; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SHOCKWAVE | gespielt | 3750 | 136.1 | 130.7 | 0.139 |
| play STRIKE_RED -> m3 |  | 3750 | 134.3 | 130.0 | 0.024 |
| play BLOOD_FOR_BLOOD+ -> m4 |  | 1750 | 137.0 | 129.8 | 0.030 |
| play STRIKE_RED -> m1 |  | 1750 | 136.4 | 129.3 | 0.064 |
| play DISARM -> m3 |  | 750 | 136.0 | 128.5 | 0.054 |
| play DISARM -> m2 | 64k | 750 | 138.4 | 131.7 | 0.063 |

**Einschätzung:** Reptomancer, Shockwave vs. Disarm zuerst (beide gespielt), 750 Besuche. Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111378486-F44-T1-d7 · vertretbar · Herz-Sieg

- A3 F44: ELITE NEMESIS T1: gespielt play SECRET_WEAPON+, 64k play ENTRENCH+ (16k-qBacked 160.1 vs 162.3, Lücke 2.2)
- Kampf gewonnen, HP-Verlust 2
- Zustand: `player 104/104 blk 14 E 5 str 1 dex 0  | pots [ELIXIR_POTION] | hand: BASH+(2), SENTINEL+(1), ENTRENCH+(1), FLEX+(0), CLEAVE+(1), DISARM+(1), SECRET_WEAPON+(0), DARK_EMBRACE+(1) | draw 23 disc 7 | NEMESIS 150/200 [NEMESIS_ATTACK] strength-3`
- Gespielte Linie im Zug: play APOTHEOSIS+ [64k: play SEEING_RED+]; play SEEING_RED+; play SECRET_WEAPON+ [64k: play ENTRENCH+]; select REAPER+ [64k: select IMMOLATE+]; play FLEX+; play ENTRENCH+ [64k: play DISARM+ -> m0]; play CLEAVE+ [64k: play DARK_EMBRACE+]; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play SENTINEL+ |  | 5139 | 157.4 | 147.8 | 0.051 |
| play SECRET_WEAPON+ | gespielt | 5056 | 160.1 | 148.2 | 0.157 |
| drink ELIXIR_POTION |  | 2538 | 158.9 | 147.8 | 0.018 |
| play DARK_EMBRACE+ |  | 1947 | 162.2 | 150.7 | 0.190 |
| play ENTRENCH+ | 64k | 1903 | 162.3 | 148.5 | 0.056 |
| play CLEAVE+ |  | 1181 | 162.6 | 149.8 | 0.058 |

**Einschätzung:** Nemesis, Secret Weapon+ vs. Entrench+ zuerst (beide gespielt). Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111378911-F27-T1-d5 · vertretbar · Tod F45

- A2 F27: MONSTER THREE_CULTIST T1: gespielt play RECKLESS_CHARGE+ -> m2, 64k play BLUDGEON+ -> m0 (16k-qBacked 63.2 vs 65.3, Lücke 2.1)
- Kampf gewonnen, HP-Verlust 12
- Zustand: `player 34/75 blk 0 E 3 str 1 dex 0  | pots [ANCIENT_POTION] | hand: RECKLESS_CHARGE+(0), SHRUG_IT_OFF(1), DEFEND_RED+(1), POMMEL_STRIKE+(1), POWER_THROUGH(1), BLUDGEON+(3) | draw 12 disc 2 | CULTIST 43/56 [CULTIST_DARK_STRIKE]; CULTIST 47/55 [CULTIST_DARK_STRIKE]; CULTIST 40/55 [CULTIST_DARK_STRIKE]`
- Gespielte Linie im Zug: play RECKLESS_CHARGE+ -> m2 [64k: play BLUDGEON+ -> m0]; play BLUDGEON+ -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play RECKLESS_CHARGE+ -> m2 | gespielt | 3861 | 63.2 | 57.2 | 0.011 |
| play RECKLESS_CHARGE+ -> m0 |  | 3861 | 62.4 | 55.7 | 0.011 |
| play BLUDGEON+ -> m2 |  | 1857 | 65.2 | 63.0 | 0.263 |
| play BLUDGEON+ -> m0 | 64k | 1857 | 65.3 | 63.5 | 0.276 |
| play BLUDGEON+ -> m1 |  | 856 | 57.7 | 54.1 | 0.292 |
| play RECKLESS_CHARGE+ -> m1 |  | 856 | 62.7 | 54.0 | 0.010 |

**Einschätzung:** Reihenfolge Reckless Charge vs. Bludgeon in einem Zug, in dem beide gespielt werden; Lücke 2 auf 1.857 Besuchen.

## R-111378335-F44-T3-d13 · vertretbar · Herz-Sieg

- A3 F44: ELITE GIANT_HEAD T3: gespielt play METALLICIZE, 64k play CLOTHESLINE+ -> m0 (16k-qBacked 78.8 vs 80.2, Lücke 1.4)
- Kampf gewonnen, HP-Verlust 49
- Zustand: `player 101/101 blk 0 E 3 str 3 dex 2 WEAK1 DARK_EMBRACE1 DEMON_FORM3 | pots [FAIRY_POTION] | hand: STRIKE_RED(3), REAPER(2), SPOT_WEAKNESS(0), FEED(3), SECOND_WIND(3), CLOTHESLINE+(3), DEFEND_RED(1), FEEL_NO_PAIN(2), METALLICIZE(1), DEFEND_RED(0) | draw 9 disc 5 | GIANT_HEAD 471/520 [GIANT_HEAD_IT_IS_TIME] vulnerable3 weak6`
- Gespielte Linie im Zug: play METALLICIZE [64k: play CLOTHESLINE+ -> m0]; play FEEL_NO_PAIN [64k: play DEFEND_RED]; play SPOT_WEAKNESS -> m0; end turn [64k: play DEFEND_RED]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play METALLICIZE | gespielt | 4365 | 78.8 | 69.3 | 0.145 |
| play REAPER |  | 4365 | 75.9 | 66.1 | 0.038 |
| play DEFEND_RED |  | 2364 | 81.0 | 69.4 | 0.072 |
| play SPOT_WEAKNESS -> m0 |  | 1030 | 80.8 | 67.9 | 0.116 |
| play FEED -> m0 |  | 1030 | 76.8 | 65.8 | 0.046 |
| play CLOTHESLINE+ -> m0 | 64k | 1030 | 80.2 | 70.3 | 0.096 |

**Einschätzung:** Metallicize vs. Clothesline+ gegen It Is Time bei 101/101; Clothesline+ mit 1.030 Besuchen früh ausgeschieden, Lücke 1,4.

## R-111379035-F45-T0-d2 · vertretbar · Herz-Sieg

- A3 F45: MONSTER WRITHING_MASS T0: gespielt play DEFEND_RED+, 64k play FEEL_NO_PAIN (16k-qBacked 151.3 vs 153.4, Lücke 2.0)
- Kampf gewonnen, HP-Verlust 0
- Zustand: `player 60/75 blk 0 E 6 str 0 dex 0 BUFFER1 THORNS3 VIGOR8 | pots [ENERGY_POTION,ENTROPIC_BREW,FLEX_POTION] | hand: DEFEND_RED+(1), STRIKE_RED+(1), OFFERING(0), FEEL_NO_PAIN(1), BASH(2) | draw 28 disc 0 | WRITHING_MASS 175/175 [INVALID]`
- Gespielte Linie im Zug: select multi ; play DEFEND_RED+ [64k: play FEEL_NO_PAIN]; drink ENERGY_POTION; drink FLEX_POTION; drink ENTROPIC_BREW; play FEEL_NO_PAIN; play OFFERING; play TRUE_GRIT+; select WHIRLWIND; play FIEND_FIRE -> m0; play INFERNAL_BLADE; play HEADBUTT -> m0; select TRUE_GRIT+; play TWIN_STRIKE -> m0 [64k: play FLEX]; end turn [64k: play TWIN_STRIKE -> m0]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play DEFEND_RED+ | gespielt | 4506 | 151.3 | 143.8 | 0.028 |
| drink ENERGY_POTION |  | 4372 | 150.7 | 144.4 | 0.149 |
| play FEEL_NO_PAIN | 64k | 3837 | 153.4 | 143.0 | 0.120 |
| play STRIKE_RED+ -> m0 |  | 2375 | 150.4 | 142.8 | 0.011 |
| play BASH -> m0 |  | 1042 | 153.3 | 142.3 | 0.035 |
| discard FLEX_POTION |  | 1036 | 151.3 | 142.4 | 0.149 |

**Einschätzung:** Writhing Mass, Defend+ vs. Feel No Pain zuerst (beide gespielt). Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111378476-F51-T3-d25 · vertretbar · Tod F56

- A3 F51: BOSS TIME_EATER T3: gespielt play DARK_SHACKLES -> m0, 64k play INFLAME+ (16k-qBacked 49.0 vs 51.0, Lücke 2.0)
- Kampf gewonnen, HP-Verlust 38
- Zustand: `player 57/108 blk 0 E 4 str 0 dex 1 FRAIL1 VULNERABLE1 WEAK1 | pots [] | hand: SHRUG_IT_OFF(1), FLAME_BARRIER(2), DARK_SHACKLES(0), INFLAME+(1), MASTER_OF_STRATEGY(0), HEMOKINESIS(1) | draw 10 disc 13 | TIME_EATER 446/480 [TIME_EATER_RIPPLE] block20 strength2 weak1`
- Gespielte Linie im Zug: play DARK_SHACKLES -> m0 [64k: play INFLAME+]; play HEMOKINESIS -> m0 [64k: play MASTER_OF_STRATEGY]; play INFLAME+; play SHRUG_IT_OFF; play MASTER_OF_STRATEGY; play DEFEND_RED; play STRIKE_RED -> m0; select JUGGERNAUT

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play DARK_SHACKLES -> m0 | gespielt | 4763 | 49.0 | 39.7 | 0.083 |
| play SHRUG_IT_OFF |  | 4763 | 48.2 | 34.6 | 0.149 |
| play INFLAME+ | 64k | 2095 | 51.0 | 35.6 | 0.233 |
| play HEMOKINESIS -> m0 |  | 2095 | 45.5 | 37.6 | 0.081 |
| play MASTER_OF_STRATEGY |  | 761 | 31.9 | 27.3 | 0.160 |
| play FLAME_BARRIER |  | 761 | 44.2 | 33.8 | 0.173 |

**Einschätzung:** Dark Shackles vs. Inflame+ zuerst; beide werden im Zug gespielt, Lücke 2 auf 2.095 Besuchen.

## R-111379035-F39-T3-d22 · vertretbar · Herz-Sieg

- A3 F39: MONSTER TRANSIENT T3: gespielt play HAVOC+, 64k play DEFEND_RED+ (16k-qBacked 161.3 vs 162.9, Lücke 1.6)
- Kampf gewonnen, HP-Verlust 6
- Zustand: `player 69/75 blk 0 E 5 str 6 dex 0 FEEL_NO_PAIN9 THORNS3 | pots [ENERGY_POTION,POWER_POTION,BLOCK_POTION,FLEX_POTION] | hand: PUMMEL(1), SEEING_RED+(0), HAVOC+(0), DEFEND_RED+(0), SECOND_WIND(0) | draw 3 disc 10 | TRANSIENT 869/999 [TRANSIENT_ATTACK] vulnerable2`
- Gespielte Linie im Zug: play HAVOC+ [64k: play DEFEND_RED+]; play SEEING_RED+; play SECOND_WIND [64k: play PUMMEL -> m0]; play PUMMEL -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play PUMMEL -> m0 |  | 4637 | 161.2 | 152.4 | 0.264 |
| play HAVOC+ | gespielt | 4551 | 161.3 | 152.3 | 0.170 |
| play SEEING_RED+ |  | 2626 | 161.8 | 151.4 | 0.129 |
| play DEFEND_RED+ | 64k | 1285 | 162.9 | 153.4 | 0.138 |
| play SECOND_WIND |  | 1269 | 158.9 | 148.2 | 0.185 |
| drink POWER_POTION |  | 409 | 150.3 | 149.6 | 0.026 |

**Einschätzung:** Transient, Havoc+ vs. Defend+ zuerst. Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111379170-F42-T1-d24 · vertretbar · Herz-Sieg

- A3 F42: ELITE REPTOMANCER T1: gespielt play MADNESS, 64k play DARK_EMBRACE (16k-qBacked 153.9 vs 155.4, Lücke 1.5)
- Kampf gewonnen, HP-Verlust 0
- Zustand: `player 94/94 blk 38 E 0 str 2 dex 0 NO_DRAW1 DARK_EMBRACE2 FLAME_BARRIER4 | pots [DEXTERITY_POTION] | hand: ANGER(2), CORRUPTION(0), POMMEL_STRIKE+(2), INTIMIDATE(0), MADNESS(0), DISARM(0), DARK_EMBRACE(0), PERFECTED_STRIKE(1), FEED+(3), INTIMIDATE(0) | draw 8 disc 9 | DAGGER 22/22 [DAGGER_STAB]; REPTOMANCER 156/195 [REPTOMANCER_BIG_BITE] vulnerable2; DAGGER 5/25 [DAGGER_STAB]`
- Gespielte Linie im Zug: play STRIKE_RED+ -> m4 [64k: play CORRUPTION]; play DARK_EMBRACE [64k: play FLAME_BARRIER]; play CORRUPTION; play MADNESS; play FLAME_BARRIER [64k: play INTIMIDATE]; play SHRUG_IT_OFF+ [64k: play MADNESS]; play DEFEND_RED; play RECKLESS_CHARGE -> m2 [64k: play CORRUPTION]; play DEFEND_RED; play DEFEND_RED [64k: play DARK_EMBRACE]; play LIMIT_BREAK [64k: play BATTLE_TRANCE]; play BATTLE_TRANCE; play MADNESS [64k: play DARK_EMBRACE]; play DARK_EMBRACE [64k: play DISARM -> m2]; play CORRUPTION [64k: play FEED+ -> m4]; play INTIMIDATE [64k: play FEED+ -> m4]; play FEED+ -> m1; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play CORRUPTION |  | 4548 | 152.6 | 143.4 | 0.101 |
| play MADNESS | gespielt | 4541 | 153.9 | 140.8 | 0.121 |
| play INTIMIDATE |  | 2544 | 153.8 | 142.6 | 0.133 |
| play INTIMIDATE |  | 1217 | 155.7 | 142.4 | 0.133 |
| play DISARM -> m1 |  | 1214 | 154.2 | 142.8 | 0.107 |
| play DISARM -> m2 |  | 416 | 155.2 | 143.9 | 0.132 |
| play DARK_EMBRACE | 64k | 412 | 155.4 | 146.6 | 0.125 |

**Einschätzung:** Reptomancer, Madness vs. Dark Embrace zuerst (beide gespielt), 412 Besuche. Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111379035-F33-T1-d4 · vertretbar · Herz-Sieg

- A2 F33: BOSS COLLECTOR T1: gespielt play RECKLESS_CHARGE -> m1, 64k drink SWIFT_POTION (16k-qBacked 90.6 vs 92.1, Lücke 1.5)
- Kampf gewonnen, HP-Verlust 14
- Zustand: `player 75/75 blk 0 E 4 str 0 dex 0 BUFFER1 FEEL_NO_PAIN3 THORNS3 VIGOR8 | pots [ENERGY_POTION,SWIFT_POTION] | hand: INFLAME(1), SHRUG_IT_OFF(0), FEEL_NO_PAIN(1), ASCENDERS_BANE, RECKLESS_CHARGE(0) | draw 19 disc 3 | TORCH_HEAD 45/45 [TORCH_HEAD_TACKLE]; TORCH_HEAD 41/41 [TORCH_HEAD_TACKLE]; THE_COLLECTOR 300/300 [THE_COLLECTOR_BUFF]`
- Gespielte Linie im Zug: play RECKLESS_CHARGE -> m1 [64k: drink SWIFT_POTION]; drink SWIFT_POTION; play DEFEND_RED+ [64k: play SHRUG_IT_OFF]; play SHRUG_IT_OFF; play INFLAME; play FLAME_BARRIER+; play STRIKE_RED+ -> m2 [64k: play FEEL_NO_PAIN]; play STRIKE_RED+ -> m1 [64k: play FEEL_NO_PAIN]; play FEEL_NO_PAIN; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play RECKLESS_CHARGE -> m1 | gespielt | 4579 | 90.6 | 78.8 | 0.052 |
| play RECKLESS_CHARGE -> m0 |  | 4579 | 90.4 | 78.4 | 0.046 |
| play INFLAME |  | 2578 | 96.4 | 79.0 | 0.165 |
| play FEEL_NO_PAIN |  | 1244 | 97.5 | 80.0 | 0.331 |
| play RECKLESS_CHARGE -> m2 |  | 1244 | 106.3 | 85.7 | 0.031 |
| play SHRUG_IT_OFF |  | 444 | 100.9 | 81.5 | 0.158 |
| drink SWIFT_POTION | 64k | 444 | 92.1 | 87.6 | 0.104 |

**Einschätzung:** Collector, Reckless Charge vs. Swift Potion zuerst (beide gespielt), 444 Besuche. Sequential Halving hat die 64k-Wahl früh mit weniger Besuchen aussortiert; ihr höheres qBacked ruht auf dünnerer Basis. Normales Rauschen der Endauswahl.

## R-111378476-F35-T2-d16 · vertretbar · Tod F56

- A3 F35: MONSTER THREE_DARKLINGS T2: gespielt play STRIKE_RED -> m2, 64k play ANGER -> m0 (16k-qBacked 111.2 vs 112.5, Lücke 1.3)
- Kampf gewonnen, HP-Verlust 4
- Zustand: `player 72/82 blk 31 E 5 str 3 dex 1  | pots [] | hand: STRIKE_RED(1), STRIKE_RED(1), ANGER(0), CARNAGE(2), DARK_SHACKLES(0) | draw 10 disc 5 | DARKLING 29/52 [DARKLING_NIP] strength2 weak1; DARKLING 53/53 [DARKLING_NIP] strength2 weak1; DARKLING 56/56 [DARKLING_CHOMP] weak1`
- Gespielte Linie im Zug: play IMPERVIOUS; play STRIKE_RED -> m2 [64k: play ANGER -> m0]; play CARNAGE -> m0 [64k: play STRIKE_RED -> m1]; play STRIKE_RED -> m1; end turn; select IRON_WAVE

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play CARNAGE -> m1 |  | 4502 | 110.9 | 104.2 | 0.106 |
| play STRIKE_RED -> m2 | gespielt | 4189 | 111.2 | 103.6 | 0.055 |
| play DARK_SHACKLES -> m2 |  | 2384 | 110.3 | 103.3 | 0.082 |
| play STRIKE_RED -> m0 |  | 2265 | 111.9 | 104.9 | 0.068 |
| play ANGER -> m0 | 64k | 1214 | 112.5 | 104.4 | 0.066 |
| play DARK_SHACKLES -> m1 |  | 1108 | 112.2 | 103.8 | 0.082 |

**Einschätzung:** Reihenfolge von Angriffen gegen Darklings, Lücke 1,3.

## R-111378911-F42-T3-d10 · vertretbar · Tod F45

- A3 F42: ELITE GIANT_HEAD T3: gespielt play POWER_THROUGH+, 64k play INFERNAL_BLADE (16k-qBacked 135.1 vs 136.2, Lücke 1.1)
- Kampf gewonnen, HP-Verlust -5
- Zustand: `player 87/93 blk 0 E 3 str 6 dex 0  | pots [] | hand: WRITHE, SECOND_WIND(0), HAVOC(0), BLUDGEON+(0), INFERNAL_BLADE(0), IRON_WAVE+(3), FEEL_NO_PAIN+(0), WOUND, DEFEND_RED+(0), POWER_THROUGH+(0) | draw 16 disc 3 | GIANT_HEAD 493/520 [GIANT_HEAD_IT_IS_TIME] vulnerable2`
- Gespielte Linie im Zug: play POWER_THROUGH+ [64k: play INFERNAL_BLADE]; play INFERNAL_BLADE; play IRON_WAVE+ -> m0 [64k: play FEEL_NO_PAIN+]; play FEEL_NO_PAIN+; play DEFEND_RED+ [64k: play BLUDGEON+ -> m0]; play BLUDGEON+ -> m0; play FIEND_FIRE -> m0 [64k: play HAVOC]; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play POWER_THROUGH+ | gespielt | 4579 | 135.1 | 120.8 | 0.120 |
| play DEFEND_RED+ |  | 4579 | 135.0 | 126.6 | 0.065 |
| play INFERNAL_BLADE | 64k | 2578 | 136.2 | 123.9 | 0.091 |
| play FEEL_NO_PAIN+ |  | 1244 | 130.5 | 123.4 | 0.292 |
| play IRON_WAVE+ -> m0 |  | 1244 | 130.5 | 122.4 | 0.122 |
| play SECOND_WIND |  | 444 | 83.7 | 78.9 | 0.064 |

**Einschätzung:** Power Through+ vs. Infernal Blade zuerst, beide werden gespielt; Lücke 1,1.

## F-111378773-F7-EXORDIUM_WILDLIFE · offen · Tod F13

- A1 F7: NORMAL EXORDIUM_WILDLIFE: HP 73 -> 43
- Tränke: ['ESSENCE_OF_STEEL'] -> ['ESSENCE_OF_STEEL']
- z 3.58 gegen Norm 1.7 ± 7.9
- Critic vor/nach dem Kampf: 0.197 / 0.136
- Entscheidender Zug T0 (19 HP verloren); 7 von 23 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 73/75 blk 0 E 3 str 0 dex 0  | pots [ESSENCE_OF_STEEL] | hand: STRIKE_RED(1), STRIKE_RED(1), STRIKE_RED(1), DEFEND_RED(1), DEFEND_RED(1) | draw 11 disc 0 | JAW_WORM 43/43 [JAW_WORM_CHOMP]; ACID_SLIME_M 29/29 [ACID_SLIME_M_TACKLE]`
- Gespielte Linie im Zug: play STRIKE_RED -> m1; play STRIKE_RED -> m1; play DEFEND_RED; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play STRIKE_RED -> m1 | gespielt 64k | 5512 | 106.7 | 98.7 | 0.339 |
| play DEFEND_RED |  | 5512 | 106.6 | 99.1 | 0.263 |
| drink ESSENCE_OF_STEEL |  | 2844 | 102.5 | 96.3 | 0.176 |
| play STRIKE_RED -> m0 |  | 1066 | 99.2 | 95.8 | 0.215 |
| end turn |  | 1066 | 87.1 | 82.6 | 0.007 |

**Einschätzung:** 73 -> 43 HP gegen Jaw Worm und Acid Slime (Norm 1,7 +- 7,9) mit ungenutzter Essence of Steel; der 16k-Baum bewertet Trinken niedriger (102,5 gegen 106,7). Hypothese: die Suche hortet Tränke; 30 HP fehlen sechs Etagen später beim tödlichen Nob.

## F-111378699-F7-LAGAVULIN · vertretbar · Tod F16

- A1 F7: ELITE LAGAVULIN: HP 75 -> 19
- Tränke: ['FAIRY_POTION'] -> ['FAIRY_POTION']
- z 3.26 gegen Norm 13.7 ± 13.0
- Critic vor/nach dem Kampf: 0.192 / 0.068
- Entscheidender Zug T6 (20 HP verloren); 6 von 27 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 50/80 blk 0 E 3 str -2 dex -2  | pots [FAIRY_POTION] | hand: STRIKE_RED(1), STRIKE_RED(1), STRIKE_RED(1), POMMEL_STRIKE+(1), STRIKE_RED(1) | draw 7 disc 0 | LAGAVULIN 51/115 [LAGAVULIN_ATTACK] vulnerable1`
- Gespielte Linie im Zug: play POMMEL_STRIKE+ -> m0; play STRIKE_RED -> m0; play STRIKE_RED -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play POMMEL_STRIKE+ -> m0 | gespielt 64k | 6667 | 101.4 | 94.4 | 0.671 |
| play STRIKE_RED -> m0 |  | 6667 | 98.7 | 93.2 | 0.325 |
| end turn |  | 2666 | 55.1 | 49.7 | 0.004 |

**Einschätzung:** Lagavulin auf F7 mit Startdeck (13 Karten) kostet viel; Fairy Potion kann man nicht trinken. Die Wahl der Elite bei 75/80 ist vertretbar, der Kampf selbst ohne auffälligen Zug.

## F-111379035-F24-SLAVERS · offen · Herz-Sieg

- A2 F24: ELITE SLAVERS: HP 67 -> 8
- Tränke: [] -> []
- z 2.97 gegen Norm 12.2 ± 15.8
- Critic vor/nach dem Kampf: 0.276 / 0.210
- Entscheidender Zug T1 (21 HP verloren); 8 von 32 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 53/75 blk 0 E 4 str 0 dex 0 FEEL_NO_PAIN3 | pots [] | hand: BLOOD_FOR_BLOOD(3), INFLAME(1), STRIKE_RED(1), STRIKE_RED(1), HEADBUTT(1) | draw 16 disc 5 | BLUE_SLAVER 34/51 [BLUE_SLAVER_STAB] block6; TASKMASTER 57/60 [TASKMASTER_SCOURING_WHIP] block6 strength1; RED_SLAVER 50/50 [RED_SLAVER_ENTANGLE] block6`
- Gespielte Linie im Zug: play INFLAME; play HEADBUTT -> m0 [64k: play STRIKE_RED -> m0]; select GHOSTLY_ARMOR; play STRIKE_RED -> m0; play STRIKE_RED -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play INFLAME | gespielt 64k | 4365 | 13.5 | 8.4 | 0.255 |
| play HEADBUTT -> m1 |  | 4365 | 10.8 | 7.4 | 0.056 |
| play STRIKE_RED -> m1 |  | 2364 | 11.7 | 5.6 | 0.039 |
| play STRIKE_RED -> m0 |  | 1030 | 13.2 | 6.0 | 0.087 |
| play HEADBUTT -> m2 |  | 1030 | 13.2 | 8.2 | 0.070 |
| play HEADBUTT -> m0 |  | 1030 | 13.6 | 7.8 | 0.124 |

**Einschätzung:** 67 -> 8 HP ohne Tränke, Lauf endet trotzdem mit Herz-Sieg. Teuerster Zug T1 (21 HP): Inflame, Headbutt, zwei Strikes gegen drei Slavers; alle Linien des 16k-Baums liegen bei qBacked 11-14, die Stellung war schon eng. Kein eindeutiger Einzelfehler.

## F-111378476-F22-SNECKO · vertretbar · Tod F56

- A2 F22: NORMAL SNECKO: HP 82 -> 57
- Tränke: ['POWER_POTION'] -> ['POWER_POTION']
- z 2.92 gegen Norm -1.0 ± 8.9
- Critic vor/nach dem Kampf: 0.149 / 0.106
- Entscheidender Zug T2 (20 HP verloren); 9 von 27 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 82/82 blk 0 E 4 str 0 dex 1 VULNERABLE2 WEAK2 | pots [POWER_POTION] | hand: INTIMIDATE(2), BASH(2), STRIKE_RED(2), UPPERCUT(3), CORRUPTION(0) | draw 4 disc 10 | SNECKO 87/123 [SNECKO_TAIL_WHIP]`
- Gespielte Linie im Zug: play STRIKE_RED -> m0 [64k: play BASH -> m0]; play BASH -> m0; play CORRUPTION; play UPPERCUT -> m0; play INTIMIDATE; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BASH -> m0 | 64k | 4763 | 126.6 | 122.0 | 0.216 |
| play STRIKE_RED -> m0 | gespielt | 4763 | 126.6 | 122.2 | 0.046 |
| play CORRUPTION |  | 2095 | 124.6 | 121.0 | 0.312 |
| play UPPERCUT -> m0 |  | 2095 | 124.0 | 120.6 | 0.211 |
| play INTIMIDATE |  | 761 | 122.3 | 118.8 | 0.181 |
| drink POWER_POTION |  | 761 | 118.7 | 116.7 | 0.028 |

**Einschätzung:** Snecko (Confuse) auf F22, 25 HP verloren; Strike vs. Bash zuerst ist ein Gleichstand (126,6 / 126,6).

## F-111378486-F2-CULTIST · vertretbar · Herz-Sieg

- A1 F2: NORMAL CULTIST: HP 58 -> 51
- Tränke: ['STRENGTH_POTION'] -> ['STRENGTH_POTION']
- z 2.90 gegen Norm -3.0 ± 3.4
- Critic vor/nach dem Kampf: 0.164 / 0.164
- Entscheidender Zug T2 (9 HP verloren); 5 von 13 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 54/75 blk 0 E 3 str 0 dex 0  | pots [STRENGTH_POTION] | hand: STRIKE_RED(1), STRIKE_RED(1), BASH(2), STRIKE_RED(1), DEFEND_RED(1) | draw 5 disc 0 | CULTIST 38/52 [CULTIST_DARK_STRIKE] strength3 vulnerable1`
- Gespielte Linie im Zug: play STRIKE_RED -> m0 [64k: play DEFEND_RED]; play STRIKE_RED -> m0; play STRIKE_RED -> m0; end turn

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play BASH -> m0 |  | 5661 | 113.8 | 111.7 | 0.457 |
| play STRIKE_RED -> m0 | gespielt | 5650 | 113.8 | 111.5 | 0.353 |
| play DEFEND_RED | 64k | 2935 | 112.3 | 105.3 | 0.162 |
| drink STRENGTH_POTION |  | 1083 | 107.8 | 104.4 | 0.019 |
| end turn |  | 1069 | 86.5 | 81.6 | 0.008 |

**Einschätzung:** Nur 7 HP verloren; z ist hoch, weil die Norm wegen Burning Blood negativ ist (-3 +- 3,4). Kein Fehler.

## F-111378335-F44-GIANT_HEAD · vertretbar · Herz-Sieg

- A3 F44: ELITE GIANT_HEAD: HP 101 -> 58
- Tränke: ['FAIRY_POTION'] -> ['FAIRY_POTION']
- z 2.84 gegen Norm 1.2 ± 14.7
- Critic vor/nach dem Kampf: 1.176 / 1.116
- Entscheidender Zug T3 (27 HP verloren); 18 von 35 Wurzeln mit anderer 64k-Wahl
- Zustand: `player 101/101 blk 0 E 3 str 3 dex 2 WEAK1 DARK_EMBRACE1 DEMON_FORM3 | pots [FAIRY_POTION] | hand: STRIKE_RED(3), REAPER(2), SPOT_WEAKNESS(0), FEED(3), SECOND_WIND(3), CLOTHESLINE+(3), DEFEND_RED(1), FEEL_NO_PAIN(2), METALLICIZE(1), DEFEND_RED(0) | draw 9 disc 5 | GIANT_HEAD 471/520 [GIANT_HEAD_IT_IS_TIME] vulnerable3 weak6`
- Gespielte Linie im Zug: play METALLICIZE [64k: play CLOTHESLINE+ -> m0]; play FEEL_NO_PAIN [64k: play DEFEND_RED]; play SPOT_WEAKNESS -> m0; end turn [64k: play DEFEND_RED]

| Aktion | | Besuche 16k | qBacked | q | Prior |
|---|---|---|---|---|---|
| play METALLICIZE | gespielt | 4365 | 78.8 | 69.3 | 0.145 |
| play REAPER |  | 4365 | 75.9 | 66.1 | 0.038 |
| play DEFEND_RED |  | 2364 | 81.0 | 69.4 | 0.072 |
| play SPOT_WEAKNESS -> m0 |  | 1030 | 80.8 | 67.9 | 0.116 |
| play FEED -> m0 |  | 1030 | 76.8 | 65.8 | 0.046 |
| play CLOTHESLINE+ -> m0 | 64k | 1030 | 80.2 | 70.3 | 0.096 |

**Einschätzung:** 101 -> 58 gegen Giant Head, gewonnen, Lauf endet mit Herz-Sieg. Fairy Potion nicht trinkbar.

## O-111378882-104 · Fehlvorstellung · Tod F50

- A2 F33: REWARDS: Critic 0.775 -> 0.600 (dv -0.175, bereinigt -0.178; Übergang REWARDS->REWARDS, Mittel +0.003 über 562)
- Änderung: +Corruption+
- Zustand: `A2 F33 REWARDS HP 67/80 gold 526 deck 27 pots [] relics 12`
- Relikte: BURNING_BLOOD, FOSSILIZED_HELIX, MUMMIFIED_HAND, INK_BOTTLE, FROZEN_EGG, MEAL_TICKET, SOZU, ENCHIRIDION, GAMBLING_CHIP, CERAMIC_FISH, BAG_OF_PREPARATION, QUESTION_CARD
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Twin Strike+, Headbutt, Metallicize, Battle Trance, Anger, Immolate+, Blood for Blood, Metallicize+, Ghostly Armor, Reaper, Reaper, Disarm+, Second Wind, Exhume, Body Slam+, Inflame+, Shockwave+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card CORRUPTION+ | gewählt | 0.793 | 4.54 |
| card REAPER |  | 0.193 | 3.13 |
| potion CULTIST_POTION |  | 0.009 | 0.11 |
| card DEMON_FORM+ |  | 0.005 | -0.62 |
| card JUGGERNAUT+ |  | 0.000 | -4.30 |
| SKIP |  | 0.000 | -7.10 |

**Einschätzung:** Actor nimmt Corruption+ (p 0,79) gegen Reaper (0,19); Critic fällt um 0,175. Muster: über 20 Spiele fällt der Critic nach jeder der 15 Corruption-Wahlen im Mittel um 0,039, bei allen anderen Karten um 0,000 (n 386). Actor und Critic sind sich über Corruption uneinig; welcher Kopf recht hat, zeigt nur eine gepaarte Probe.

## O-111378882-52 · vertretbar · Tod F50

- A1 F16: REWARDS: Critic 0.545 -> 0.393 (dv -0.152, bereinigt -0.155; Übergang REWARDS->BOSS_RELIC, Mittel +0.003 über 30)
- Änderung: +Reaper
- Zustand: `A1 F16 REWARDS HP 75/80 gold 285 deck 21 pots [REGEN_POTION,EXPLOSIVE_POTION] relics 6`
- Relikte: BURNING_BLOOD, FOSSILIZED_HELIX, MUMMIFIED_HAND, INK_BOTTLE, FROZEN_EGG, MEAL_TICKET
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Twin Strike+, Headbutt, Metallicize, Battle Trance, Anger, Immolate+, Blood for Blood, Metallicize+, Ghostly Armor, Reaper

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card REAPER | gewählt | 1.000 | 12.33 |
| card BERSERK+ |  | 0.000 | -8.38 |
| card BLUDGEON |  | 0.000 | -10.56 |
| SKIP |  | 0.000 | -6.88 |

**Einschätzung:** Reaper genommen, Critic -0,15. Reaper ist im Mittel kein Muster (+0,006 über 10 Wahlen); Einzelausreißer vor dem Boss-Relikt-Bildschirm.

## O-111378303-116 · Fehlvorstellung · Herz-Sieg

- A2 F34: BOSS_RELIC: Critic 0.630 -> 0.481 (dv -0.149, bereinigt -0.137; Übergang BOSS_RELIC->MAP (act change), Mittel -0.011 über 30)
- Änderung: Relikt +RUNIC_CUBE
- Zustand: `A2 F34 BOSS_RELIC HP 68/68 gold 96 deck 23 pots [] relics 11`
- Relikte: BURNING_BLOOD, TURNIP, ORNAMENTAL_FAN, STRIKE_DUMMY, SELF_FORMING_CLAY, CERAMIC_FISH, RUNIC_DOME, PEN_NIB, ORANGE_PELLETS, INK_BOTTLE, MUTAGENIC_STRENGTH
- Deck: Ascender's Bane, Strike, Strike, Strike, Defend, Defend, Defend, Bash, Shrug It Off, Anger, Impervious, Shockwave+, Pommel Strike+, Anger, Fiend Fire, Pommel Strike+, Shockwave+, Reaper, Battle Trance, Spot Weakness+, Dark Embrace+, Armaments+, Corruption

| Option | | p (Netz) | Logit |
|---|---|---|---|
| relic RUNIC_CUBE | gewählt | 1.000 | 9.74 |
| relic ASTROLABE |  | 0.000 | -0.07 |
| relic TINY_HOUSE |  | 0.000 | -5.58 |
| SKIP |  | 0.000 | -9.44 |

**Einschätzung:** Runic Cube (p 1,00) statt Astrolabe; Critic -0,149. Muster: Runic-Relikte (Dome, Pyramid, Cube) senken den Critic im Mittel um 0,05, andere Boss-Relikte heben ihn um etwa 0,01; der Actor nimmt Runic in 9 von 30 Boss-Relikt-Wahlen.

## O-111379170-100 · Fehlvorstellung · Herz-Sieg

- A2 F33: REWARDS: Critic 0.452 -> 0.326 (dv -0.127, bereinigt -0.130; Übergang REWARDS->BOSS_RELIC, Mittel +0.003 über 30)
- Änderung: +Corruption
- Zustand: `A2 F33 REWARDS HP 64/82 gold 176 deck 29 pots [] relics 10`
- Relikte: BURNING_BLOOD, STONE_CALENDAR, VAJRA, PEN_NIB, WHETSTONE, SNECKO_EYE, TOY_ORNITHOPTER, RED_SKULL, MUTAGENIC_STRENGTH, ORICHALCUM
- Deck: Ascender's Bane, Strike+, Strike, Strike+, Defend, Defend, Defend, Defend, Bash+, Pummel, Perfected Strike, Battle Trance, Reckless Charge, Anger, Headbutt, Corruption, Shrug It Off, Flame Barrier+, Headbutt, Reaper, Shrug It Off+, Flame Barrier+, Writhe, Dark Embrace, Pommel Strike+, Feed+, Limit Break, Intimidate, Intimidate

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card CORRUPTION | gewählt | 0.998 | 8.60 |
| card DEMON_FORM |  | 0.002 | 2.40 |
| card BARRICADE |  | 0.000 | 0.53 |
| SKIP |  | 0.000 | -8.35 |

**Einschätzung:** Corruption (p 1,00), Critic -0,127; Corruption-Muster wie O-111378882-104.

## O-111379064-123 · Fehlvorstellung · Tod F40

- A3 F37: EVENT Falling: Critic 0.641 -> 0.511 (dv -0.130, bereinigt -0.122; Übergang EVENT->MAP, Mittel -0.008 über 85)
- Änderung: -Shockwave
- Zustand: `A3 F37 EVENT HP 94/94 gold 151 deck 26 pots [SKILL_POTION] relics 15`
- Relikte: BURNING_BLOOD, LIZARD_TAIL, LANTERN, SINGING_BOWL, ODD_MUSHROOM, SELF_FORMING_CLAY, PANDORAS_BOX, ORICHALCUM, THREAD_AND_NEEDLE, PAPER_PHROG, TORII, PANTOGRAPH, MEDICAL_KIT, FROZEN_EGG, BLACK_STAR
- Deck: Ascender's Bane, Flame Barrier, Inflame+, Battle Trance, Reaper, Headbutt, Anger, Disarm, Corruption, Iron Wave, Immolate, Barricade, Blood for Blood, Flame Barrier, Berserk, Perfected Strike, Dropkick, Fire Breathing, Discovery, Corruption, Brutality, Impervious, Shockwave, Pommel Strike+, Spot Weakness, Corruption+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| FALLING_SKILL SHOCKWAVE | gewählt | 0.620 | -4.42 |
| FALLING_POWER BARRICADE |  | 0.306 | -5.12 |
| FALLING_ATTACK REAPER |  | 0.074 | -6.54 |

**Einschätzung:** Falling: Shockwave verlieren (p 0,62) statt Barricade (0,31); Critic -0,13. Actor und Critic uneinig; Lauf stirbt auf F40.

## O-111378335-110 · Fehlvorstellung · Herz-Sieg

- A3 F36: EVENT Duplicator: Critic 0.973 -> 0.854 (dv -0.119, bereinigt -0.114; Übergang EVENT->CARD_SELECT, Mittel -0.005 über 18)
- Zustand: `A3 F36 EVENT HP 92/92 gold 208 deck 26 pots [FIRE_POTION] relics 13`
- Relikte: BURNING_BLOOD, SELF_FORMING_CLAY, KUNAI, REGAL_PILLOW, RED_SKULL, HAPPY_FLOWER, RUNIC_PYRAMID, DREAM_CATCHER, HORN_CLEAT, INCENSE_BURNER, ODDLY_SMOOTH_STONE, POTION_BELT, SNECKO_EYE
- Deck: Ascender's Bane, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Clothesline+, Anger, Dark Embrace, Clothesline+, Metallicize, Demon Form+, Spot Weakness+, Reaper, Second Wind, Disarm, Shockwave, Feel No Pain, Dark Embrace, Pummel, Shockwave, Feed, Spot Weakness

| Option | | p (Netz) | Logit |
|---|---|---|---|
| DUPLICATOR_DUPLICATE | gewählt | 1.000 | 4.08 |
| DUPLICATOR_DUPLICATE+1 |  | 0.000 | -4.18 |

**Einschätzung:** Duplicator: Duplizieren (p 1,00) senkt den Critic um 0,12, bevor überhaupt eine Karte gewählt ist. Duplizieren ist fast nie schlecht; vermutlich ein Critic-Artefakt auf diesem seltenen Bildschirm (Fehlvorstellung des Critic).

## O-111378633-110 · offen · Tod F56

- A3 F39: SHOP: Critic 0.279 -> 0.190 (dv -0.088, bereinigt -0.109; Übergang SHOP->CARD_SELECT, Mittel +0.020 über 29)
- Zustand: `A3 F39 SHOP HP 92/92 gold 319 deck 23 pots [SWIFT_POTION,BLOOD_POTION] relics 13`
- Relikte: BURNING_BLOOD, PAPER_PHROG, BOTTLED_FLAME, ART_OF_WAR, RUNIC_DOME, RED_MASK, BRIMSTONE, GAMBLING_CHIP, ODDLY_SMOOTH_STONE, MEAL_TICKET, ANCHOR, POCKETWATCH, SNECKO_EYE
- Deck: Ascender's Bane, Strike, Strike, Strike, Defend, Defend, Defend, Bash, Headbutt, Battle Trance, Disarm+, Inflame+, Battle Trance, Burning Pact, Anger, Demon Form+, Shrug It Off, Reaper, Second Wind, Flex+, Havoc, Power Through, Feed

| Option | | p (Netz) | Logit |
|---|---|---|---|
| REMOVE | gewählt | 0.475 | 3.08 |
| relic RED_SKULL |  | 0.425 | 2.96 |
| SKIP |  | 0.041 | 0.62 |
| OPEN_CHEST+1 |  | 0.036 | 0.49 |
| relic LEES_WAFFLE |  | 0.015 | -0.42 |
| card BARRICADE |  | 0.008 | -1.05 |

**Einschätzung:** Shop: Entfernen (p 0,48) knapp vor Red Skull (0,42), Critic -0,11 (bereinigt). Entfernen ist meist gut; Critic oder Actor, nicht entscheidbar.

## O-111378335-50 · Fehlvorstellung · Herz-Sieg

- A1 F17: BOSS_RELIC: Critic 0.456 -> 0.339 (dv -0.117, bereinigt -0.105; Übergang BOSS_RELIC->MAP (act change), Mittel -0.011 über 30)
- Änderung: Relikt +RUNIC_PYRAMID
- Zustand: `A1 F17 BOSS_RELIC HP 46/89 gold 210 deck 19 pots [SWIFT_POTION,SKILL_POTION] relics 6`
- Relikte: BURNING_BLOOD, SELF_FORMING_CLAY, KUNAI, REGAL_PILLOW, RED_SKULL, HAPPY_FLOWER
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Clothesline+, Anger, Dark Embrace, Clothesline+, Metallicize, Demon Form, Spot Weakness, Reaper

| Option | | p (Netz) | Logit |
|---|---|---|---|
| relic RUNIC_PYRAMID | gewählt | 0.709 | 9.06 |
| relic COFFEE_DRIPPER |  | 0.291 | 8.17 |
| relic BLACK_STAR |  | 0.000 | -3.80 |
| SKIP |  | 0.000 | -10.01 |

**Einschätzung:** Runic Pyramid (p 0,71) statt Coffee Dripper bei 46/89 HP; Critic -0,117. Runic-Muster wie O-111378303-116.

## O-111378303-57 · Fehlvorstellung · Herz-Sieg

- A1 F17: BOSS_RELIC: Critic 0.457 -> 0.342 (dv -0.115, bereinigt -0.104; Übergang BOSS_RELIC->MAP (act change), Mittel -0.011 über 30)
- Änderung: Relikt +RUNIC_DOME
- Zustand: `A1 F17 BOSS_RELIC HP 57/68 gold 240 deck 20 pots [ANCIENT_POTION,FLEX_POTION] relics 6`
- Relikte: BURNING_BLOOD, TURNIP, ORNAMENTAL_FAN, STRIKE_DUMMY, SELF_FORMING_CLAY, CERAMIC_FISH
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Bash, Shrug It Off, Anger, Impervious, Shockwave+, Pommel Strike+, Anger, Fiend Fire, Pommel Strike+, Shockwave, Reaper

| Option | | p (Netz) | Logit |
|---|---|---|---|
| relic RUNIC_DOME | gewählt | 0.527 | 9.81 |
| relic RUNIC_PYRAMID |  | 0.471 | 9.70 |
| relic PHILOSOPHERS_STONE |  | 0.002 | 3.95 |
| SKIP |  | 0.000 | -9.37 |

**Einschätzung:** Runic Dome (p 0,53) gegen Runic Pyramid (0,47); Critic -0,115. Runic-Muster.

## O-111379193-74 · Fehlvorstellung · Tod F51

- A2 F22: CARD_SELECT: Critic 0.248 -> 0.153 (dv -0.095, bereinigt -0.101; Übergang CARD_SELECT->MAP, Mittel +0.005 über 69)
- Änderung: +Dark Embrace
- Zustand: `A2 F22 CARD_SELECT HP 46/89 gold 106 deck 21 pots [WEAK_POTION] relics 7`
- Relikte: BURNING_BLOOD, BAG_OF_PREPARATION, ANCIENT_TEA_SET, STRAWBERRY, BRONZE_SCALES, PANDORAS_BOX, NILRYS_CODEX
- Deck: Ascender's Bane, Bash, Power Through, Feel No Pain, Pommel Strike, Blood for Blood, Carnage, Pummel, Pommel Strike, Infernal Blade, Limit Break, Flame Barrier, Bludgeon, Clothesline, True Grit, Offering, Barricade, Shrug It Off, Intimidate, Evolve+, Whirlwind+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card DARK_EMBRACE | gewählt | 0.710 | 7.11 |
| card BATTLE_TRANCE |  | 0.273 | 6.15 |
| card SPOT_WEAKNESS |  | 0.016 | 3.33 |
| card SHRUG_IT_OFF |  | 0.000 | -2.35 |
| card HAVOC |  | 0.000 | -1.52 |
| card ENTRENCH |  | 0.000 | -12.25 |

**Einschätzung:** Dark Embrace (p 0,71) statt Battle Trance; Critic -0,10. Dark Embrace ist im Mittel -0,013 über 13 Wahlen; das Deck sammelt Powers.

## O-111378486-101 · Fehlvorstellung · Herz-Sieg

- A3 F37: CARD_SELECT: Critic 0.452 -> 0.335 (dv -0.117, bereinigt -0.097; Übergang CARD_SELECT->SHOP, Mittel -0.020 über 29)
- Änderung: -Combust
- Zustand: `A3 F37 CARD_SELECT HP 93/97 gold 404 deck 32 pots [COLORLESS_POTION,BLESSING_OF_THE_FORGE] relics 10`
- Relikte: BURNING_BLOOD, STONE_CALENDAR, BOTTLED_LIGHTNING, TOXIC_EGG, PANDORAS_BOX, PRESERVED_INSECT, OLD_COIN, HORN_CLEAT, RUNIC_PYRAMID, ANCIENT_TEA_SET
- Deck: Ascender's Bane, Bash, Disarm+, Battle Trance, Metallicize, Inflame+, Corruption, Power Through, Sentinel, True Grit+, Dark Embrace, Flex+, Offering+, Reaper, Cleave, Bludgeon, Seeing Red+, Feed, Cleave, Entrench+, Combust, Immolate, Entrench+, Intimidate+, Decay, Bloodletting+, Flex+, Sentinel+, Armaments+, Disarm+, Juggernaut, Burning Pact+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card COMBUST | gewählt | 0.394 | 7.48 |
| card CLEAVE |  | 0.196 | 6.78 |
| card CLEAVE |  | 0.196 | 6.78 |
| card BLUDGEON |  | 0.185 | 6.73 |
| card IMMOLATE |  | 0.013 | 4.09 |
| card BASH |  | 0.011 | 3.95 |

**Einschätzung:** Shop-Entfernung: Combust (p 0,39) statt Cleave; Critic -0,12. Hypothese: der Actor entfernt eine gute Karte.

## O-111378486-98 · vertretbar · Herz-Sieg

- A3 F36: MAP: Critic 0.433 -> 0.340 (dv -0.093, bereinigt -0.095; Übergang MAP->SHOP, Mittel +0.002 über 49)
- Zustand: `A3 F36 MAP HP 93/97 gold 641 deck 32 pots [COLORLESS_POTION,BLESSING_OF_THE_FORGE] relics 9`
- Relikte: BURNING_BLOOD, STONE_CALENDAR, BOTTLED_LIGHTNING, TOXIC_EGG, PANDORAS_BOX, PRESERVED_INSECT, OLD_COIN, HORN_CLEAT, RUNIC_PYRAMID
- Deck: Ascender's Bane, Bash, Disarm+, Battle Trance, Metallicize, Inflame+, Corruption, Power Through, Sentinel, True Grit+, Dark Embrace, Flex+, Offering+, Reaper, Cleave, Bludgeon, Seeing Red+, Feed, Cleave, Entrench+, Combust, Immolate, Entrench+, Intimidate+, Decay, Bloodletting+, Flex+, Sentinel+, Armaments+, Disarm+, Juggernaut, Burning Pact+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| path x5 SHOP | gewählt | 1.000 | 8.55 |
| path x4 EVENT |  | 0.000 | 0.78 |

**Einschätzung:** Pfad zum Shop mit 641 Gold (p 1,00); der Critic fällt erst, als er das zufällige Shop-Angebot sieht. Zufall, kein Fehler.

## O-111379170-106 · offen · Herz-Sieg

- A3 F36: SHOP: Critic 0.450 -> 0.377 (dv -0.073, bereinigt -0.093; Übergang SHOP->CARD_SELECT, Mittel +0.020 über 29)
- Zustand: `A3 F36 SHOP HP 81/86 gold 230 deck 32 pots [] relics 11`
- Relikte: BURNING_BLOOD, STONE_CALENDAR, VAJRA, PEN_NIB, WHETSTONE, SNECKO_EYE, TOY_ORNITHOPTER, RED_SKULL, MUTAGENIC_STRENGTH, ORICHALCUM, COFFEE_DRIPPER
- Deck: Ascender's Bane, Strike+, Strike, Strike+, Defend, Defend, Defend, Defend, Bash+, Pummel, Perfected Strike, Battle Trance, Reckless Charge, Anger, Headbutt, Corruption, Shrug It Off, Flame Barrier+, Headbutt, Reaper, Shrug It Off+, Flame Barrier+, Writhe, Dark Embrace, Pommel Strike+, Feed+, Limit Break, Intimidate, Intimidate, Corruption, Flame Barrier, Dark Embrace

| Option | | p (Netz) | Logit |
|---|---|---|---|
| REMOVE | gewählt | 0.361 | 2.79 |
| potion BLESSING_OF_THE_FORGE |  | 0.346 | 2.75 |
| potion DUPLICATION_POTION |  | 0.197 | 2.19 |
| potion GAMBLERS_BREW |  | 0.033 | 0.41 |
| relic AKABEKO |  | 0.028 | 0.24 |
| SKIP |  | 0.023 | 0.04 |

**Einschätzung:** Shop: Entfernen (p 0,36) vor Blessing of the Forge (0,35); Critic -0,09 bereinigt. Wie O-111378633-110.

## O-111378633-148 · Fehlvorstellung · Tod F56

- A4 F54: SHOP: Critic 0.062 -> -0.042 (dv -0.105, bereinigt -0.093; Übergang SHOP->SHOP, Mittel -0.012 über 75)
- Zustand: `A4 F54 SHOP HP 93/93 gold 137 deck 23 pots [DISTILLED_CHAOS] relics 17`
- Relikte: BURNING_BLOOD, PAPER_PHROG, BOTTLED_FLAME, ART_OF_WAR, RUNIC_DOME, RED_MASK, BRIMSTONE, GAMBLING_CHIP, ODDLY_SMOOTH_STONE, MEAL_TICKET, ANCHOR, POCKETWATCH, SNECKO_EYE, RED_SKULL, MAW_BANK, PRESERVED_INSECT, BRONZE_SCALES
- Deck: Ascender's Bane, Strike, Defend, Defend, Defend, Bash, Headbutt, Battle Trance, Disarm+, Inflame+, Battle Trance, Burning Pact, Anger, Demon Form+, Shrug It Off, Reaper, Second Wind, Flex+, Havoc, Power Through, Feed, Seeing Red, Entrench

| Option | | p (Netz) | Logit |
|---|---|---|---|
| potion SNECKO_OIL | gewählt | 0.326 | 1.57 |
| card UPPERCUT |  | 0.240 | 1.26 |
| card EVOLVE |  | 0.120 | 0.57 |
| card DISARM |  | 0.118 | 0.55 |
| card ENTRENCH |  | 0.102 | 0.41 |
| REMOVE |  | 0.029 | -0.85 |

**Einschätzung:** Snecko Oil auf F54 gekauft; Critic von 0,06 auf -0,04, also außerhalb von [0, 1]. Der Critic ist auf dieser Skala nicht beschränkt (auch Werte über 1,1 kommen vor); Fehlvorstellung des Critic, nicht unbedingt des Kaufs.

## O-111379064-51 · Fehlvorstellung · Tod F40

- A1 F16: REWARDS: Critic 0.476 -> 0.387 (dv -0.089, bereinigt -0.092; Übergang REWARDS->REWARDS, Mittel +0.003 über 562)
- Änderung: +Corruption
- Zustand: `A1 F16 REWARDS HP 45/77 gold 174 deck 19 pots [] relics 6`
- Relikte: BURNING_BLOOD, LIZARD_TAIL, LANTERN, SINGING_BOWL, ODD_MUSHROOM, SELF_FORMING_CLAY
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Perfected Strike, Flame Barrier, Inflame, Battle Trance, Reaper, Headbutt, Anger, Disarm

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card CORRUPTION | gewählt | 0.988 | 5.63 |
| potion WEAK_POTION |  | 0.011 | 1.17 |
| SINGING_BOWL |  | 0.000 | -2.78 |
| card JUGGERNAUT |  | 0.000 | -5.70 |
| card LIMIT_BREAK |  | 0.000 | -6.10 |
| SKIP |  | 0.000 | -7.71 |

**Einschätzung:** Corruption (p 0,99), Critic -0,09; Corruption-Muster.

## O-111378951-150 · Fehlvorstellung · Tod F55

- A3 F48: REWARDS: Critic 0.692 -> 0.605 (dv -0.087, bereinigt -0.085; Übergang REWARDS->MAP, Mittel -0.002 über 478)
- Änderung: +Sentinel
- Zustand: `A3 F48 REWARDS HP 80/80 gold 132 deck 35 pots [ENERGY_POTION] relics 17`
- Relikte: BURNING_BLOOD, BRONZE_SCALES, AKABEKO, ORICHALCUM, REGAL_PILLOW, POTION_BELT, PEN_NIB, FUSION_HAMMER, THE_ABACUS, SUNDIAL, SMILING_MASK, SELF_FORMING_CLAY, OMAMORI, COFFEE_DRIPPER, CLOCKWORK_SOUVENIR, SINGING_BOWL, BAG_OF_PREPARATION
- Deck: Ascender's Bane, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Clash, Metallicize, Reckless Charge+, Second Wind, Impervious, Uppercut+, Uppercut, Blood for Blood, Pommel Strike, Reaper, Dark Embrace, Ghostly Armor, Shrug It Off, Spot Weakness, Demon Form, Battle Trance, Spot Weakness, Shockwave, Corruption, Shrug It Off, Flex+, Seeing Red, Burning Pact, Flame Barrier, Feel No Pain+, Shrug It Off

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card SENTINEL | gewählt | 0.487 | -0.01 |
| card BLOOD_FOR_BLOOD+ |  | 0.280 | -0.57 |
| card ARMAMENTS+ |  | 0.159 | -1.13 |
| SINGING_BOWL |  | 0.074 | -1.90 |
| SKIP |  | 0.001 | -6.67 |

**Einschätzung:** Sentinel (p 0,49) statt Blood for Blood+ (0,28); Critic -0,087; Sentinel im Mittel -0,035 (n 3).

## O-111378911-105 · Bug · Tod F45

- A3 F37: EVENT Match and Keep: Critic 0.300 -> 0.217 (dv -0.084, bereinigt -0.082; Übergang EVENT->EVENT, Mittel -0.002 über 47)
- Zustand: `A3 F37 EVENT HP 57/84 gold 388 deck 27 pots [ANCIENT_POTION] relics 12`
- Relikte: BURNING_BLOOD, ANCIENT_TEA_SET, CENTENNIAL_PUZZLE, VAJRA, DREAM_CATCHER, MATRYOSHKA, RUNIC_PYRAMID, STRIKE_DUMMY, PAPER_PHROG, WHETSTONE, MAGIC_FLOWER, SNECKO_EYE
- Deck: Ascender's Bane, Strike+, Strike+, Strike+, Strike+, Defend+, Defend+, Bash+, Pummel+, Reckless Charge+, Shrug It Off, Iron Wave+, Power Through, Pommel Strike+, Infernal Blade, Disarm+, Bludgeon+, Corruption, Battle Trance+, Feel No Pain+, Havoc, Battle Trance, Feed, Writhe, Uppercut, Second Wind, Feed

| Option | | p (Netz) | Logit |
|---|---|---|---|
| OPEN_CHEST+2 5g | gewählt | 0.083 | -0.57 |
| OPEN_CHEST+2 5g |  | 0.083 | -0.57 |
| OPEN_CHEST+2 5g |  | 0.083 | -0.57 |
| OPEN_CHEST+2 5g |  | 0.083 | -0.57 |
| OPEN_CHEST+2 5g |  | 0.083 | -0.57 |
| OPEN_CHEST+2 5g |  | 0.083 | -0.57 |

**Einschätzung:** Match and Keep: alle 12 Optionen haben exakt gleiche Logits (p 0,083 je). Die Policy kann die Karten offenbar nicht unterscheiden; Kandidat für einen Beobachtungs-Fehler (Karteninhalt nicht kodiert). Die Optionsnamen in dieser Zeile stammen aus dem Pilot-Renderer und sind für dieses Event falsch. Vor einer Prüfung der Kodierung nur Hypothese.

## O-111378951-115 · Fehlvorstellung · Tod F55

- A3 F38: SHOP: Critic 0.589 -> 0.495 (dv -0.094, bereinigt -0.082; Übergang SHOP->SHOP, Mittel -0.012 über 75)
- Änderung: Relikt +CLOCKWORK_SOUVENIR
- Zustand: `A3 F38 SHOP HP 75/75 gold 223 deck 31 pots [WEAK_POTION,WEAK_POTION] relics 14`
- Relikte: BURNING_BLOOD, BRONZE_SCALES, AKABEKO, ORICHALCUM, REGAL_PILLOW, POTION_BELT, PEN_NIB, FUSION_HAMMER, THE_ABACUS, SUNDIAL, SMILING_MASK, SELF_FORMING_CLAY, OMAMORI, COFFEE_DRIPPER
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Bash, Clash, Metallicize, Reckless Charge+, Second Wind, Impervious, Uppercut+, Uppercut, Blood for Blood, Pommel Strike, Reaper, Dark Embrace, Ghostly Armor, Shrug It Off, Spot Weakness, Demon Form, Battle Trance, Spot Weakness, Shockwave, Corruption, Shrug It Off, Flex+

| Option | | p (Netz) | Logit |
|---|---|---|---|
| relic CLOCKWORK_SOUVENIR | gewählt | 0.907 | 7.25 |
| REMOVE |  | 0.050 | 4.35 |
| card SPOT_WEAKNESS |  | 0.041 | 4.15 |
| SKIP |  | 0.002 | 0.86 |
| card FLAME_BARRIER |  | 0.000 | -2.02 |
| potion FEAR_POTION |  | 0.000 | -2.47 |

**Einschätzung:** Clockwork Souvenir gekauft (p 0,91); Critic -0,08 bereinigt. Actor und Critic uneinig.

## O-111379098-49 · vertretbar · Tod F24

- A1 F16: REWARDS: Critic 0.284 -> 0.209 (dv -0.075, bereinigt -0.078; Übergang REWARDS->BOSS_RELIC, Mittel +0.003 über 30)
- Änderung: +Reaper
- Zustand: `A1 F16 REWARDS HP 34/68 gold 246 deck 21 pots [LIQUID_BRONZE] relics 6`
- Relikte: BURNING_BLOOD, THE_ABACUS, STONE_CALENDAR, ORNAMENTAL_FAN, ORICHALCUM, THE_COURIER
- Deck: Ascender's Bane, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Bash, Seeing Red, Armaments+, Shrug It Off, Twin Strike, Reckless Charge, Exhume, Havoc+, Feel No Pain, Pommel Strike, Demon Form, Second Wind

| Option | | p (Netz) | Logit |
|---|---|---|---|
| card REAPER | gewählt | 0.999 | 6.71 |
| card IMPERVIOUS |  | 0.001 | -0.43 |
| card JUGGERNAUT |  | 0.000 | -6.05 |
| SKIP |  | 0.000 | -9.59 |

**Einschätzung:** Reaper bei 34/68 vor dem Boss-Relikt; Critic -0,08. Reaper ist im Mittel kein Muster.

