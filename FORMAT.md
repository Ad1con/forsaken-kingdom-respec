# Forsaken Kingdom save format — findings (2026-09-21, game build 3.0.0.24268)

Everything below was verified against the user's own files. Offsets are from
`Act One - Tirisfal Glades.w3z` (saved 2026-09-21 21:12) unless noted.

## Where the files live

`%USERPROFILE%\Documents\Warcraft III\BattleNet\<account id>\Campaigns\ForsakenKingdom\`

| File | What it is |
|---|---|
| `<name>.w3z` | Manual save. Full game state, ~200 MB decompressed. |
| `Blizzard\<name>\UndeadRE01_NN.w3z` | Zone snapshots the game keeps per manual save (Act One is an open hub with zone transitions). |
| `Campaigns.w3v` | Campaign game cache. Persists heroes between maps and between zones. |
| `ForsakenKingdom.w3p` | INI-style progress/difficulty file with a "Magic" checksum. Not needed. |

## Container (`.w3z` and `.w3v` are identical)

Same container as `.w3g` replays.

```
0x00  "Warcraft III recorded game\x1a\0"   28 bytes
0x1c  u32 header size (0x44)
0x20  u32 total file size
0x24  u32 header version (1)
0x28  u32 decompressed size
0x2c  u32 block count
0x30  "PX3W" + u32 version 0x27d8 + u32 build 0x1b58 + u32 flags + u32 length + u32 crc
0x44  blocks: { u32 compressedSize, u32 decompressedSize (0x100000), u32 checksum, zlib stream }
```

Solved 2026-09-21 (`tools/w3z.py`), verified byte-identical on 8 files:
- block checksum = `fold(crc32(12-byte header, checksum zeroed)) | fold(crc32(data)) << 16`,
  `fold(c) = (c ^ c >> 16) & 0xffff`
- header crc (0x40) = crc32 of the 0x44-byte header with that field zeroed
- data = zlib level 1, `Z_SYNC_FLUSH` (no stream end, no adler32)
- block size comes from block 0's dsize: 1 MB for `.w3z`, 2 KB for `.w3v`;
  last block is zero-padded, header 0x28 holds the true payload length
- Python's `flush()` can emit the empty sync block twice when output lands
  on its buffer boundary; `w3z.py` collapses it

## Game cache record (`Campaigns.w3v`, also embedded in every `.w3z` at ~0x6a00000)

Keys seen: `TransitionGarek`, `TransitionAnya`, plus per-map `HumanRE01/02/03`
records for `Garek`, `Landen`, `Ilastar`, plus quest/transition variables.

Hero record layout (Anya, w3v offset 0x1c50):

```
"TransitionAnya\0"
4cc  unit type      'ynaU' -> Uany            (all 4ccs are stored reversed)
u32  45 (constant across all heroes; purpose unknown)
then a run of 12-byte entries {4cc, u32, u32}:
     'aube' 0 0x9300         "ebua" — per-hero marker ability, level 0
     'namp' 1 0x2740         normal abilities/items: {id, level, 0x2740}
     'scse' 0 0x75           inventory items: {id, 0, 0x75}
     ...                      (~80 slots, empties are all-zero)
u32  0x647  (1607)  probably hero XP
u32  4              unknown (level? talent points?)
u32,u32,u32,f32,u32,u32,f32,f32,u32,f32,u32   the 3.0 stat block (ability amp, crit, resolve...)
4 hero-ability slots x 12 bytes {baseId, currentVariantId, level}:
     AUwf -> AUw1 lvl1      Q  Withering Fire, talent variant 1
     AUla -> AUl2 lvl2      W  Lantern, talent variant 2
     AUdb -> AUdb lvl1      E  Deathseeker, untalented
     (empty)                R  Wail, not learned
{Aaml, Aaml, 1}                attribute-bonus style 5th ability
u32  0x244e1 ... small ints (03, 01, 06) — talent-point counters, exact split TBD
talent list, 8 bytes each {4cc, u32 0}:  AT1a, AT2b
```

Talent ID scheme: `<HeroInitial>T<row><choice>` — A=Anya, U=Undead Garek,
G=Human Garek, L=Landen, I=Ilastar; rows 1–6, choices a/b/c matching the
in-game top-to-bottom order. Example: AT5c = Anya row 5 choice c
= Poison-tipped Arrows (confirmed from the ability definition table at 0x13f005).

Garek (undead): AUsw -> AUs3, AUbd -> AUb3, AUbr, AUvg, Aaml; talents UT1c, UT2c.

## Live hero state inside the `.w3z` (verified 2026-09-21, the editor)

The cache copy is NOT what the running game uses, and it goes stale: talents
picked since the last zone transition exist only as live objects. Live state
sits above ~0x1000000; object/definition tables sit below ~0x300000.

Every live object starts `espi`, u32 size, then fields. Ability and talent
objects (talents are abilities: `AT1a` etc.) carry:

```
+0x2c  4cc ability id            +0x30  u32 level-1
+0x4c  4cc ability id (again)    ... rest of object
```
Sizes: base and talented variant of the same ability serialize identically
(AUwf = AUw1 = 0x108, AUbd = AUb3 = 0xf4); every talent object is 0x90.

Hero block, anchored on the base-ability list (count 5 + 4 base ids + Aaml):

```
anchor-0x74  u32 5, then 5 x 4cc   current ability ids (talented variants)
anchor-0x5c  12 x u32              constant (5,5,5,5,3,2,5,1,1,1,6,4): max levels etc.
anchor-0x2c  2 x (u32,u32)         handles
anchor-0x1c  u32 "n"               unknown; 4/3 in the first Act One save, 10/9 later
anchor-0x18  u32 5, then 5 x 4cc   current ability ids again (must match)
anchor       u32 5, then 5 x 4cc   base ability ids
```
XP lives in the `AHre` object just before (Anya 1607, matches the cache).

Talent picks are the set of `AT/UT` objects the hero owns. Picking a talent on
a Q/W/E/R row also swaps that slot's ability for a variant: choice a/b/c ->
variant 1/2/3 with the base's letter (`AUwf`->`AUw1..3`, `AUla`->`AUl1..3`,
`AUdb`->`AUd1..2`, `AUwc`->`AUi1/3`, `AUsw`->`AUs1..3`, `AUbd`->`AUb1..3`,
`AUbr`->`AUr1..3`, `AUvg`->`AUv1..3`). `AUd3` and `AUi2` are not defined, so
those two talents keep the base ability. Rows 5–6 are passive: talent object
only. Skill points = the level field in each ability object.

An edit therefore touches: both current lists, the variant object's two ids,
the talent object's two ids (or level field), and the cache hero record.

## Talent ids

Anya (`AT`): 1 Withering Fire (Rain of Arrows / Deathmark / Deadeye),
2 Soul Lantern (Spirit Leech / Wraithguard / Guiding Light), 3 Deathseeker
Arrows (Death Sentence / Flow State / Umbral Rupture), 4 Banshee's Wail
(Soul Harvest / Curse of the Darkfallen / Howling Tempest), 5 Attacks
(Marksmanship / Arcane Archer / Poison-tipped Arrows), 6 Stats (Ranger's
Dexterity / Heightened Reflexes / Blackened Soul).

Garek (`UT`): 1 Relentless Cleave (Forsaken Might / Bloodthirst / Bladestorm),
2 Undying Defiance (Counter Attack / Parry / The Best Defense), 3 Battering
Ram (Endurance / Thirst For Battle / Furious Charge), 4 Grim Conviction (Inner
Fire / Soulthirst / Unending Fury), 5 Stats (Improved Armor / Swordsmanship /
All Brawn), 6 Stats (Mighty Swing / Quick Recovery / Warrior's Focus).

Cache counters: `Act1TalentPointsGained` = 3 as of the last transition. The
hero record's ext[28]/ext[30] u16s (Anya 3/1, Garek 1/1) and the live "n" are
still unexplained; unspent-point counters have not been located.

## Map script facts

Script symbols present: `GiveTalentTome`, `TalentGivenQ`, `Hint_Talent_Q`,
`udg_Int_ConsumedTalentTomes`, cache key `Act1TalentPointsGained`. No talent
selection/reset natives referenced. Talent picking is engine-side in 3.0.

## Tome of Retraining (`tret`, ability `Aret`)

Standard WC3 item. Sold by a shop in the prologue, absent from Act One.
Neither the Act One save nor `Homecoming (10).w3z` contains a "Tome of
Retraining" name string; both contain `tret` only inside the standard Goblin
Merchant (`ngme`) stock list. The in-save object table only carries the
campaign's renamed objects (e.g. "|cff40da00Tome of Strength|r"), so standard
item ids are not proof of absence — `tret` should be instantiable in any map.
Open question: does it reset talents or only skill points? Prologue test needed.

## Game data store (CASC) — checked 2026-09-21

`tools/casc.py` reads the local store (build config -> text root of
`path|content md5` lines -> encoding -> .idx -> data.NNN, BLTE zlib frames).
Verified: classic maps (`Campaign/Classic/ROC/Human01.w3m`) extract as plain
MPQ. All 20 Forsaken Kingdom maps are `.w3xd` and come out as uniformly random
bytes (zlib ratio 1.0): encrypted, only the game can open them. Static
extraction of FK object data is therefore not available; hero/talent/tooltip
data must come from saves (or from the running game's memory).

## Which ability definitions a save carries

A save's definition table holds full records only for a subset of abilities
(all talents; Anya's four abilities and her picked variants; Garek's Undying
Defiance and Grim Conviction; Battering Ram only in the `Reborn` saves;
Relentless Cleave never). Everything else is loaded from the map at runtime.
Tooltip lookups fall back to the base ability, then to the name alone.

## Prologue heroes (from Homecoming / Treachery / Siege / Vengeance saves)

Four talent rows each, all ability rows, abilities cap at 3 levels. Rows do
not always line up with slots: Ilastar's row 1 is Light's Mercy (slot W),
row 3 Sacred Aura (slot Q). Variant prefixes are arbitrary per slot
(`AHhs`->`AHv`, `AHsf`->`AHm`, `AHmc`->`AHz`) and some choices have no variant
at all (`AHm2`, `AHc2`, `AHz2`, `AHv3`, `AHe1`, `AHe2`; in Act One `AUd3`,
`AUi2`): the talent object carries the effect and the ability stays base.
Hero cache records are per mission (`Garek`, `Landen`, `Ilastar`), so lookups
must match the whole name (`TransitionGarek` contains `Garek`).

| type | hero | Q W E R |
|---|---|---|
| Hctr | Garek | AHsw Sweeping Strike, AHbd Unyielding Guard, AHch Valiant Charge, AHwc Warcry |
| Hctl | Landen | AHhs Heroic Slash, AHen Apprehend, AHic Inspire Courage, AHct Raise the Banner |
| Hjsm | Ilastar | AHas Sacred Aura, AHsf Light's Mercy, AHmc Mind Control, AHsl Holy Bolts |

The map name at payload offset ~0x19 (`HumanRE02`, `UndeadRE01`...) sorts a
save into its campaign part.

## Tooltip text in the running game (tools/memread.py, 2026-09-22)

A save's definition table only holds abilities the map rewrote at runtime, so
Relentless Cleave (`AUsw`) and Battering Ram (`AUbr`) appear in no save at all.
The running game holds the object data as a key/value store ("Name", "Tip",
"Ubertip", ...) and keeps each tooltip twice:

- raw, with `<AUsw,DataA1>` placeholders naming the ability and the data field
- resolved, once the game has rendered that tooltip

Pairing a raw string with its unique resolved twin yields the value of every
field it names. Those same fields appear in the per-level tooltips
(`DataA1..DataA5`), so once the learn tooltip is paired the per-level text can
be filled in without the game having rendered it. Resolved text from saves
widens the pool further, which is why `memread.py` takes the save folder.

Yield on this machine: 74 abilities, 36 with per-level text, 31 with a learn
tooltip -> `fkrespec/tooltips_data.json`, bundled into the exe and used as a
fallback when a save has no definition.

## Learning an ability (from the 12:26 / 12:28 Tirisfal pair, 2026-09-22)

An ability the hero has not learned has **no live object at all**; the game
creates one when the point is spent. Comparing two saves of the same zone
either side of Garek learning Grim Conviction, the hero block is byte-identical
(only per-save handles differ) and the ability list already names `AUvg` in
both. The entire difference is one new object in the stream.

So learning = inserting a well-formed ability object, and unlearning = removing
one. Neither is supported yet, which is why the editor refuses to move a point
onto an unlearned ability or off a learned one.

Object layout (AUvg, 0xf4 bytes, objects are packed contiguously):

```
+0x00  "espi"  u32 size  u32 flags(0x10)  u32 handle  u32 handle2
+0x28  02 00 11 00
+0x2c  4cc id          +0x30  u32 level-1      +0x34  ff x 8
+0x4c  4cc id again    +0x50  floats (0.5, 0.75)
+0xc0  u32 type/handle
+0xd4  owner handle pair
```

Open question before this can be built: whether anything in the save stores
absolute offsets (which insertion would break). The Tirisfal pair answers it —
synthesize Garek's object into the 12:26 save and compare with the 12:28 one.

## Performance notes

Measured on a 43 MB save (231 MB payload):

| stage | cost | note |
|---|---|---|
| inflate | 0.85 s | zlib, releases the interpreter lock |
| block checksums | 0.02 s | always on; the only check that catches a corrupt block that still inflates |
| index ability objects | 0.32 s | one `espi`-anchored pass, filtered by the ids in play |
| find a hero anchor | 0.05 s | `rfind`, not a walk over every match |
| repack | 2.2 s | zlib level 1, on a worker thread |
| Tk drawing the hero panels | 0.15 s | plain ttk; a themed build cost 0.84 s |

What used to be slow and why:

- every ability lookup copied the whole live region first, ~40 times per save
  (6.8 s -> 0.3 s once one pass indexes them all)
- the payload was grown block by block and then copied twice more
  (one pre-sized allocation, and `unpack` hands back the bytearray it built)
- `_anchor` walked every match to keep the last one; `rfind` gets it directly
- every tab read its save at startup, not just the one on screen
- reading and writing both ran on the UI thread, so Windows greyed the window
  out during a write; both are on a worker thread now

The window used the Sun Valley theme until 0.2.0. It drew the hero panels in
0.84 s against 0.15 s on plain ttk, and the price is charged per widget
instance rather than once per widget type, so warming it with a throwaway panel
made things worse rather than better. The theme was dropped: the window now
appears in 0.16 s instead of 0.42 s and the pause when a save lands roughly
halves.

## Hero unit object (Act One Garek, from the 12:26 / 12:28 pair)

The ability lists sit at the end of the hero's unit object. Aligning the two
saves on them, anchor-relative:

```
-0xc4  u32 experience          (1989 -> 2013 between the two saves)
-0xb0  u32 42                  unchanged
-0xa8  floats                  hit points, mana, position
-0x90  u32 22                  then three floats (2.7, 1.8, 1.5)
-0x5c  12 x u32                5,5,5,5,3,2,5,1,1,1,6,4 - identical for both
                               heroes and across saves, so not levels
-0x30  u32 4, then handle pairs
-0x18  u32 5 + current ability ids
 0x00  u32 5 + base ability ids
```

No field in the object changed from 1 to 0 when the point was spent, so the
engine's skill-point counter is either outside this object or derived. Untested
either way; `tools/` has the diff scripts if this is picked up again.

Lowering an ability's level is therefore the cheap way to hand a point back:
the object stays, only its level field changes. Whether the game then offers
the point for spending is the open question the editor now warns about.

## Skill points are tracked separately from ability levels (tested 2026-09-22)

Lowering Deathseeker Arrows from 2 to 1 in a save and loading it: the ability
dropped a level and the hero did **not** gain a point to spend. So the engine
keeps its own count and the ability object's level field is only half the
story; editing one without the other loses a point.

The counter is not in the hero's unit object. Comparing the 12:26 and 12:28
Tirisfal saves (Garek spent one point between them, experience 1989 -> 2013, no
level-up), every field of that object is identical apart from experience, hit
points, position and handles. A context-matched search for a u32 going 1 -> 0
around the hero found only a false positive (an entry shifting inside a list of
16-byte records).

To find it: two saves seconds apart, one with a point unspent and one right
after spending it. Everything else stays still, so the field falls out of the
diff. Until then the editor requires skill-point totals to match.

## Unspent skill points: hero object, anchor-0xb0 (verified in game 2026-09-22)

Right after experience:

```
anchor-0xb4  u32 experience
anchor-0xb0  u32 unspent skill points
```

Found by comparing Anya (one point to spend) with Garek (none) at the same
anchor-relative offsets in one save: exactly one u32 was 1 for her and 0 for
him, and it reads 0 for her in every earlier save. Spending a point decrements
it, so a level change has to be paid for out of it - which is why simply
lowering an ability's level loses the point.

Verified: refunding a point (Deathseeker 2 -> 1) gave the hero that point back
in game, and it could then be spent on an ability she had never learned, which
is how to reach an unlearned ability without synthesizing its object.

The game cache hero record holds a second count at tail+4 (2, 4, 5 ... across
saves): the number of points spent as of the last zone transition, not the live
figure. The game rewrites it on the next transition, so the editor leaves it
alone.

## Talent rows are not the ids that share a row digit (found 2026-09-22)

Act One Garek's two passive rows are shuffled across the id numbering. The
game's own per-row tables, read out of memory, group them as:

```
UT5a UT5b UT6a    Improved Armor, Swordsmanship, Mighty Swing
UT5c UT6b UT6c    All Brawn, Quick Recovery, Warrior's Focus
```

Every other hero's rows are the a/b/c of one digit. The same tables also give
the order the Talents screen lists rows in - for Anya, AT1 AT2 AT5 then
AT3 AT4 AT6 - so a passive row is shown third, not last. `heroes.py` therefore
stores each choice's talent id explicitly and keys rows in screen order.

Finding them again: scan the game's memory for runs of `[AGILU]T[1-6][abc]`
ids within 32 bytes of each other (`tools/` has the script). Runs of exactly
three are the rows; a hero's current picks show up as a run too.

Blizzard bug worth knowing: Swordsmanship's description in the map data is
`Gain <UT5b,DataA1,%>% Spell Amp.`, the same line Anya's Blackened Soul uses.
The game shows that text too, so the tool is not wrong when it looks odd.

## Prologue verified against the running game (2026-09-22)

With the prologue loaded (HumanRE04), read out of the game's own tables:

- talent rows group by the digit in the id for all three prologue heroes
  (GT1a/b/c and so on). Only Act One Garek breaks that pattern.
- each prologue hero has four rows, listed in digit order.
- the regular abilities carry data fields and per-level tooltips for levels
  1-3, so they cap at 3.
- **the three ultimates cap at 1.** Warcry, Raise the Banner and Holy Bolts
  have no per-level tooltips in the game's memory or in any save, where every
  other ability has three, and across 44 prologue saves none of them is ever
  above level 1. `max_levels` for the prologue heroes is therefore [3, 3, 3, 1]
  - the editor previously offered levels 2 and 3 on them, which the game has no
  way to represent.

## Unspent talent points are not stored next to the hero (searched 2026-09-22)

A save with Anya holding one unspent talent point and Garek holding none (he
had just taken his fourth) gives the same differential the skill-point counter
fell out of. Nothing survives it: of 13 offsets that read 1 for her and 0 for
him, none reads 0 for both in the two preceding saves. The window searched was
anchor-0x600 to anchor+0x200, which covers the whole hero object.

The talent system is map script rather than engine, so the count is script
side. `Act1TalentPointsGained` in the game cache reads 3 even in the save where
Garek has taken a fourth talent, so that copy is written at zone transitions
and is not the live figure.

**Resolved by a zone transition (2026-09-22).** A transition makes the script
write its live values into the cache. Before: `Act1TalentPointsGained` 3, with
Anya on 3 talents and Garek on 4. After: **4**, with the same picks. So points
are granted globally, both heroes get the same number, and what a hero has
spare is that number minus the talents they hold - there is no stored per-hero
count, which is why the differential above found nothing.

The practical consequence: un-picking a talent should hand the point back on
its own, with no counter to patch. What it still needs is the talent object
removed from the object stream, which is the one edit that changes the
payload's length.

Zone saves need not hold the heroes at all. `Act One - Race` (UndeadRE01_04)
has no hero units, no ability objects and no talent objects - only the cache
copies written at the transition. The editor correctly reports no supported
heroes; the heroes reappear in the zones where you control them.

## Removing a talent object crashes the game (tried 2026-09-22)

Cutting a talent object out of the stream produces a save the game refuses to
load: `ACCESS_VIOLATION (Failed to write address 0x0000000000000020)`, a null
dereference a few frames into the load.

The stream itself takes it fine - it is one contiguous chain of ~302,000
objects with no count or byte-length header near it, and the payload length is
recomputed on write. The problem is what still points at the object. Each one
carries a handle pair in its header (+0x0c and +0x10), and that pair also
appears in:

- a handle registry, entries tagged `hdlr`, listing every object's handle
- at least one other object, which holds the pair at its own +0x14

so the lookup finds a stale entry and writes through nothing. Removing an
object means finding and fixing every referrer, and each one missed is another
crash.

Un-picking a talent therefore stays unsupported. Swapping a picked talent for
another in the same row rewrites ids in place, leaves every handle alone and
does not change the payload's length, which is why it is safe.

### What removal would actually involve (surveyed 2026-09-23)

An attempt to make unlearning an ability possible, so the last skill point in it
could come back. It is not close to ready, and this is how far it got.

The framing is `espi`, a u32 size, then that many bytes, so the next object
starts at `off + 8 + size`. The objects do not form one chain: a prologue save
walks into 2544 separate runs totalling ~98,000 objects, and a run ends wherever
the next four bytes are not `espi`.

Handles are stored as the same u32 twice in a row, which makes a referrer search
cheap and fairly specific. Garek's Unyielding Guard object carries handle 0x5142
at +0x0c, and that pair appears in 15 places across 5 distinct structures:

- the ability object itself, at +0x0c
- a ~4.5 KB object sitting just before the hero, which holds it 8 times over
- three ~0xa8-byte nodes, each holding its own handle at +0x14, two more handles
  after it, and the owning unit's handle at +0x34
- one more large object, once

The small nodes are the readable part. Laid side by side they chain: each names
the node before it, and they all name the same owner, so unlinking one is an
ordinary list removal rather than something exotic:

    self    prev-ish  prev     owner
    0x5142  0x513a    0x513b   0x512d
    0x514b  0x513b    0x5142   0x512d
    0x514d  0x5142    0x514b   0x512d
    0x5153  0x514b    0x514d   0x512d

Two findings argue against pressing on with it as it stands. Garek's other two
ability objects sit together at 0x2d374c0 and 0x2d375f4, but Sweeping Strike's
is 0x68000 away at 0x2d9f911 and has no duplicated handle pair at +0x0c at all,
so the object header is not uniform. And locating any of this from the hero
outward does not generalise: the same walk that finds 27 references to the unit
handle in one Act One save finds none in two others.

So the blocker is no longer "the handles are a mystery." It is that the
structures cannot yet be located reliably in an arbitrary save, and writing a
removal without that means shipping guesses whose only feedback is whether the
game crashes on load. The payoff is one skill point per abandoned ability, which
does not justify that, so unlearning stays unsupported and the floor stays at
level 1.

Parked 2026-09-23, with more saves being kept from here on, which is exactly
what this needs: the way to make the structures locatable is to walk outward
from the hero in several saves at once and keep only what is invariant, and one
save per state is too thin a base for that.

## Act Two is the same heroes (checked 2026-09-23)

An Act Two save (map `UndeadRE02`) holds the same two heroes as Act One: the
same unit types, the same four abilities each with the same ids, the same 36
talent ids across six rows, the same ability variants and the same level caps.
Nothing new to define - the heroes simply had to stop being tied to one part.
`heroes.py` therefore gives Anya and Garek `parts = ACTS`.

Act Three is assumed to match and costs nothing if it does not: a hero whose
base ability list is not in the save is simply not found, which is already how
the editor handles a zone that does not hold the heroes.

## Three tooltip bugs Act Two exposed (fixed 2026-09-23)

A talent record is `[name, icon, tip, description]`. The tip is usually the
name again, so taking the first text after the name looked right - until
Furious Charge, whose tip is `Shoulder Bash`, the name of the prologue talent
it borrows its icon from. The description is the **last** text before the
`giro` boundary, not the first.

A talent's description names the ability variant's data fields
(`Battering Ram ... stuns targets for <AUr3,Dur1,.>`), so `memread.owner()`
attributed it to `AUr3` and Battering Ram's own tooltip showed the talent's
text. Only talent ids carry a plain description; an ability's text is its
per-level entries and its learn tooltip.

A variant with no text of its own (`AUs1`, Relentless Cleave under Forsaken
Might) showed just a name, because the fallback to the base ability only fired
when the variant had no entry at all rather than no *usable* entry. The tooltip
now takes whichever of the two actually carries text.

Also dropped baked text holding unresolved placeholder wreckage - a partial
regex match had left Warcry reading `DataA1,%>% Ability Vamp.`. Better a bare
name than nonsense.

## Act Two adds a third hero: Leonid (found 2026-09-23)

Read out of the running game with Act Two loaded, so this is what the map
itself says, not a guess:

```
unit type   Hleo, "Leonid", race campaign, category heroes
abilities   AHhr Headsplitter, AHhc Provoke, AHgr Grit, AHgh Guiding Hand
variants    AHh* , AHu* , AHg* , AHq*  (one per choice, as elsewhere)
talents     BT1a..BT6c, and the game groups them by the row digit, so no
            shuffle like Act One Garek
caps        5, 5, 5, 3 - the ultimate at 3, matching the other act heroes
```

That also explains `AHgh`, `AHgr`, `AHhc` and `AHhr`, which turned up as
unattributed abilities when the prologue tooltips were first extracted.

A save with him in the party filled in the rest. Rows 1 to 4 modify the four
ability slots in order, rows 5 and 6 are passives, and the talent names read
from the definition records as usual.

His variant prefixes are the one place the usual rule breaks. Everywhere else a
slot's variants are its base id's first three characters plus the choice digit,
but Headsplitter and Provoke would both claim `AHh` and Grit and Guiding Hand
would both claim `AHg`. The real mapping came from a save where he had taken
choice c in all four rows:

    AHhr -> AHh      AHhc -> AHu      AHgr -> AHg      AHgh -> AHq

## Granting skill points, if it is ever wanted

Parked 2026-09-23 as a cheat-mode idea rather than something the editor does.
It is also the cheap way around the level-1 floor: the last point in an ability
could be handed back while leaving the ability where it is, which gets the point
where it is wanted without touching a single handle. It is also a little odd for a respec
tool, since it grants a point rather than moving one, so it belongs behind an
explicit cheat toggle if that mode is ever built.


Unspent skill points are one u32 at `anchor-0xb0`. The refund path already
writes it - taking a point off an ability writes a larger number there - and
that was confirmed in game, so granting points needs no new mechanism at all:

```python
struct.pack_into('<I', self.d, state.anchor + POINTS_AT, state.available + n)
```

What is known: 1 -> 2 was verified in game. Nothing suggests the engine would
refuse a larger jump, since the map script itself hands out points with
`UnitModifySkillPoints`, but no large value has been tested. A hero can only
ever spend up to the sum of their level caps: 18 for Anya, 17 for Garek.

If it is added it should sit behind a toggle - a flag or a clearly separate
section, not the main window. The editor's case for existing is that it repairs
what the game will not let you undo; a points button in the middle of that
makes it a cheat tool, which changes both how it is received and how easily a
bug in the editor can be papered over.

Talent points cannot be granted the same way. They are not stored per hero:
the script grants them globally and a hero's spare ones are that count minus
the talents held. The live count is not in the save, only the copy written at
the last zone transition.

## What the editor enforces, and what it does not

Enforced:

- the point total, taken from the engine's own unspent counter, so a hero can
  never be given points they have not earned
- each ability's level cap, from `max_levels`, which is how many levels its
  learn tooltip lists
- talents may only be swapped within a row, never added or cleared

**Not enforced: the hero level each rank requires.** Warcraft III normally
gates rank N of an ability behind hero level 2N-1, and an ultimate behind level
6. Both heroes here learned their ultimate at exactly level 6, so the campaign
does keep that rule. The editor does not check it, so a distribution it accepts
may be one the game itself would not have allowed - for example five ranks in
Withering Fire at level 8.

Loading such a save is probably harmless, since an ability object only carries
a level and the requirement is checked by the learn UI when a point is spent,
but it is out of spec and untested.

Fixing it needs the hero's level, which is not stored anywhere near the hero
object - a monotonic search across 21 saves found nothing level-shaped. It can
be inferred, because the point budget has matched the level in every save so
far, but only while the campaign has granted no bonus skill points; it tracks
those separately in `BonusSkillPointsGiven`, which is still 0. Inferring a
level from a budget and then refusing edits on it would refuse legal ones the
moment that changes, so a warning is the safer shape until the level field is
found.

## The caps and level requirements are in the save after all (2026-09-23)

The twelve u32s at `anchor-0x5c`, left unexplained for most of this work, are
two count-prefixed runs of five:

```
5   5 5 5 3 2     how many levels each ability slot has  (Act One / Act Two)
5   1 1 1 6 4     the hero level each one needs
5   3 3 3 1 0     the prologue, whose ultimates have a single level
5   1 1 1 6 0
```

The fifth slot is the attribute bonus. The caps agree exactly with what the
learn tooltips gave, including the prologue ultimates at 1, which is a useful
independent confirmation - and they correct one thing the tooltips got wrong:
Garek's Undying Defiance caps at **5**, not 4. Its learn tooltip only lists
four levels.

The `6` is the ultimate's level requirement, matching the saves, where both
heroes learned their ultimate at exactly level 6.

`hero()` now reads both from the save and only falls back to the table in
`heroes.py`, so a hero the editor has never seen still gets the right caps.

Still missing: the hero's **level**, and the rule that forces points to be
spread across abilities rather than poured into one. Neither is in this block -
it gives one required level per ability, not one per rank, and nothing about
spreading. The level looks derived rather than stored: the experience at which
the point budget goes up lines up with Warcraft III's default table (500, 900,
1400, 2000, 2700, 3500), though some saves do not fit that, so it is not
settled. A spread rule would most likely be a gameplay constant in the map,
which is encrypted, or enforced by the campaign script.

## Where the hero level is not (searched 2026-09-23)

Not in the save's hero object: a monotonic search across 21 saves over
anchor-0x140..+0x20 turned up nothing level-shaped, and the caps/requirements
block next to it gives one required level per ability, not the hero's own.

Not readable from the live game by reusing the save's layout either. The
ability-list pattern does appear in memory - both prologue heroes were found
that way - but the bytes around it are not the serialized hero object:
experience reads 0 and the caps block is garbage. The save format is a
serialization, so finding the level in a running game means walking the live
unit structure, which is its own job.

### The game cache stores the level, one zone transition behind

The two u32s just after the hero record's slot entries are experience and
level minus one - the same zero-based convention the ability objects use for
their own level. Across every save, 14 distinct pairs, the second field is
always exactly what the stock table makes of the first:

    cache xp  541  1607  2185  3292  3762  3890  5400
    field       2     4     5     6     7     7     9
    level       3     5     6     7     8     8    10

This is the only stored hero level anywhere in the save, and it is not the
current one: the cache is written at zone transitions, so it lags live play (a
save with cache xp 2185 had Anya on 2737). The prologue heroes' records are all
zeros, so it covers the acts only.

Two things follow. It is an independent confirmation of the experience table,
from data the game wrote itself rather than from a reading of the UI. And
since the live hero object carries experience but no level, the engine most
likely derives the live level from experience on load.

### The live level comes from experience, not from the point budget

Four heroes were read off the game UI: Garek 4 and Landen 5 with a HumanRE02
save loaded, Garek and Anya both 10 in Act Two. All four are reproduced exactly
by looking the hero's experience up in Warcraft III's stock table:

    level  2    3    4    5     6     7     8     9     10
    xp     200  500  900  1400  2000  2700  3500  4400  5400

    Garek 902 -> 4     Landen 1403 -> 5     Anya 5616 -> 10

So experience is the level, and the tool can compute it without finding the
field.

The point budget is the level as well - every level grants exactly one skill
point, in both campaigns. That took a correction. Counting only the four
abilities made act heroes look two points short of their level, and this
document previously concluded that the acts skipped two grants. They do not:
the two points were in Attribute Bonus, the fifth slot the editor was not
reading. Counting all five, spent plus unspent equals the hero's level in all 84
hero states across the saves, with no exceptions.

Both readings hold only while the campaign has granted no bonus skill points,
which it tracks separately in `BonusSkillPointsGiven` and is still 0.

## Attribute Bonus, the fifth ability slot

The ability lists hold five ids, not four, and the caps block covers five slots.
The fifth is `Aaml`, Attribute Bonus - the `X` button in game, worth 5 points of
every stat per rank. The acts give it a cap of 2 and a first-rank requirement of
hero level 4; the prologue gives it a cap of 0, meaning prologue heroes do not
have it at all, so the number of slots is whatever the save's own caps say.

Its level cannot be read the way the other four are. Every hero's Attribute
Bonus is the same ability id, so a search for `Aaml` objects returns one per
hero who has learned it and nothing says which is whose. Leonid is the case that
exposes it: he has none at all, and taking the first `Aaml` object in the save
reports Garek's 2.

Arithmetic settles it without touching an object. Every point is either spent or
unspent, so what the other four slots and the unspent counter do not account for
is in Attribute Bonus:

    stat rank = hero level - unspent - sum of the other four

Checked against Leonid at level 12 with ranks 3/3/3/2 and one point unspent,
that gives 0, which is what the game shows.

Writing it needs the object, and that needs ownership. Three ways were tried
and measured against abilities whose owner is already known, since those have
unique ids:

- **Proximity, in six flavours.** A unit's ability objects do sit near the unit
  - Leonid's hero handle is 0xcada and his abilities run 0xcac4 to 0xcad2 - but
  near is not owned. Scored against 509 abilities with known owners: nearest
  hero object 89.8%, nearest hero handle 86.1%, nearest preceding hero 83.7%,
  handle just above the hero's 83.7%, and the two reversed forms 16.3%. The best
  of them still misassigns one ability in ten, which is not a rule.
- **The handles in the hero block.** The four u32s at `anchor-0x2c` are not
  object handles: none of them resolves to an object, for any of the three
  heroes. Whatever they index, it is not the ability list.
- **An owner field in the object.** The small nodes near the prologue heroes
  carry what looks like an owning-unit handle at +0x34, but no such node exists
  for any ability object in the act saves: 104 handles, none of them named.
- **A per-unit ability table.** Garek does have an object holding all four of
  his ability handles and exactly one `Aaml` handle, which would settle his.
  Anya and Leonid have none, so it cannot be used generally.

- **An ability container.** Leonid spent a point into Attribute Bonus between
  two saves a minute apart, which let the game itself show what it writes. It
  created a fresh 0x90-byte object, handle 0xc764, level 1, and that handle then
  appears in 14 places. One of them is an object holding three of Leonid's four
  ability handles and none of Anya's or Garek's, which looks exactly like a
  per-unit ability container. As a rule - "the object holding two or more of
  this hero's uniquely named abilities and none of another hero's" - it gets 53
  of 58 hero states right, misses one entirely, and is wrong four times.

### The ability container

The before/after pair also shows what that container is. Leonid's is 0x10e2
bytes and its body is a table of 12-byte records, each holding an ability handle
with two values beside it - the second of which repeats across a run, so the
records come in groups:

    +0x1f4   cac8  e2a6  d0144        Grit
    +0x200   cacc  e2a2  d0144        Provoke
    +0x20c   cad2  e29c  d0144        Headsplitter

The object is exactly the same length before and after, and its header does not
change, so the slots are fixed and learning an ability fills empty ones rather
than growing the table. Attribute Bonus took three of them.

Every handle in it that belongs to one of the three heroes is Leonid's, which is
what made it look like ownership. As a rule - "the object that mentions this
hero's own ability handles most often, then read whichever `Aaml` handle it
names" - it reached 55 of 58 hero states.

It is not an ownership structure. Resolving its first field across the whole
table gives 28 distinct ability ids, of which `Amov` - plain unit movement -
accounts for 1555 entries, alongside `Aatk`, `Avul`, `Ablr`, `ADhr` and other
generic abilities belonging to units all over the map. Only two entries are
Leonid's. It is a global table, and the reason it held some of his handles and
none of Anya's or Garek's is how those handles partition, not whose they are.
The 12-byte record reading does not survive either: looking for a repeating
5-word record that ends in 1 matches only 22 of 215 positions, so the table is
not a simple array of fixed records.

That retires the lead. The 95% was a coincidence with a plausible story attached
to it, which is worse than an obviously bad heuristic, and it is exactly what
scoring a rule against data cannot tell you on its own.

That is roughly 95%, and 95% is not enough to write with. The derived rank is
already exact, so the only thing a write would add is the ability to change it,
and getting the hero wrong would silently edit someone else's build. Worse, when
two heroes hold the same rank - Anya and Garek are both on 2 in every save - a
wrong pick cannot be caught by checking the value afterwards.

Nothing near the hero helps either: a sweep of 0x4000 bytes either side of each
hero object finds only the ability objects themselves, at their own +0x0c. There
is no handle list beside the hero to read.

So the editor reads Attribute Bonus and does not write it, and there is no lead
left worth the name. Everything tried - six proximity rules, the hero block's
handles, the prologue nodes' owner field, a per-unit ability table, and the
global table that impersonated one - either fails outright or works most of the
time for reasons unrelated to ownership.

What would actually settle it is a save where two heroes hold *different*
non-zero Attribute Bonus ranks. Every save so far has Anya and Garek both on 2,
which means no test can distinguish a correct assignment from a swapped one, and
no rule can be falsified where it matters most. Until such a save exists, this
is not worth reopening.

## Rank requirements

The block at `anchor-0x5c` is two count-prefixed runs of five and nothing more -
the dump either side of it is ability ids and handles, so there is no third run
hiding next to it:

    5 | 5 5 5 3 2 | 5 | 1 1 1 6 4      Act One and Act Two
    5 | 3 3 3 1 0 | 5 | 1 1 1 6 0      prologue

The first run is the maximum rank per ability, the second the hero level needed
for that ability's *first* point. Every save agrees with the second run: the
first rank in an ultimate never appears below hero level 6, in either campaign.

What the save does not carry is the level needed for the second and later ranks.
Warcraft III keeps that as a separate per-ability field, `levelSkip`, and the
requirement for rank N is `reqLevel + (N-1) * levelSkip`. The field is not in
the hero block, and the campaign's own ability data is inside the encrypted map,
so it has to be read out of the game.

The game states it plainly in the learn tooltip. With Anya at level 10 her
Banshee's Wail tooltip reads:

    Learn Banshee's Wail - [Level 2] (R)
    Requires:
     - Hero level: 12

`reqLevel` 6 and rank 2 at 12 gives the ultimate a `levelSkip` of 6, so its
three ranks want hero levels 6, 12 and 18. Level 12 is above the level 10 cap
seen so far, which is why no save has ever held a second rank in an ultimate.

Withering Fire gives the basics: its rank 4 tooltip asks for hero level 13, and
with `reqLevel` 1 that is a `levelSkip` of 4. The act table is therefore

    basics    reqLevel 1  skip 4   ->  ranks at hero level 1, 5, 9, 13, 17
    ultimate  reqLevel 6  skip 6   ->  ranks at hero level 6, 12, 18

which the save history confirms at both ends without a single exception. Rank 2
first appears at hero level 5, never earlier. Rank 3 first appears at hero level
10 and is absent from every level-8 save, matching a gate at 9. And the whole
of Anya's level-10 build, [3,2,2,1], is exactly what those numbers permit.

The requirement block only renders when the requirement is *not* met. Anya's
Deathseeker Arrows tooltip at level 10 shows no "Requires" line at all, because
its next rank wants level 9. So the game cannot be mined for the whole table
from one high-level save - each number has to be read while the hero is still
below it.

Act Three is not enforced. The skip is the one figure the save does not carry,
and it already differs between campaigns, so applying Act Two's 4 to an act
nobody has played would be a guess that silently blocks legal picks. There the
editor offers the full range, says in the tooltip that the figure is
unconfirmed, and asks before writing a save that goes past it. A hero found
holding a rank the table says they cannot reach is reported on load, in any
part, since that is how a changed skip announces itself.

The prologue is the same shape with a smaller skip. Garek's Sweeping Strike at
rank 2, read at hero level 4, asks for hero level 5 to reach rank 3, which is a
skip of 2:

    basics    reqLevel 1  skip 2   ->  ranks at hero level 1, 3, 5
    ultimate  reqLevel 6           ->  one rank, at hero level 6

The same reading confirms both halves of the display rule. Unyielding Guard at
rank 1 printed no requirement, because rank 2 wants level 3 and Garek was 4;
Warcry printed one, because it wants 6.

All five numbers the game has shown are reproduced by `HeroState.requirement`,
and `rank_cap` turns them into the highest rank a hero may hold. The editor
enforces it: a rank the game would not offer is refused on write, the spinner
will not climb past it, and hovering an ability names the level its next rank
needs.

That text is not in the save. Searching a full Act Two payload for "Requires",
"Hero level" and "Hero Level" returns zero hits, and a full scan of the running
game found it neither as ASCII nor as UTF-16, so the UI composes it per frame
from the numeric fields rather than storing a rendered string. The generic
`D_levelSkip_4_<id>` property keys that are in memory cover 14 stock abilities
(Adef, Aenr, Ahsb and the like) and none of the campaign's.

### There is no spread rule

Worth recording because it looked certain and was wrong. Every act distribution
in the saves keeps the three basic abilities within one rank of each other -
[2,1,1,0], [2,2,2,1], [3,2,2,1], [2,2,3,1] - and the game appears to refuse
another point in Q or W until E has one. The rule that fits, "an
ability cannot pass rank N until the others reach it," is contradicted by the
prologue, where both heroes reach [3,1,1,0] at level 5.

A test save settled it: Anya at [2,2,1,1] with 2 spare points at level 10 was
offered a point in all three basics, including taking Withering Fire to rank 3
while Deathseeker sat at 1. So no spread rule, in either campaign.

What that really is, is the level gate: a level requirement that works out that
way when the ultimate is taken at every point it becomes available. Spend one point on the ultimate the moment each of its
ranks opens, and the basics are left holding a budget that their own gates can
only absorb evenly. Q and W sit at the highest rank the hero's level allows, E
does not, and E is the only ability in the panel that will take a point - which
feels like a rule about spreading and is nothing but arithmetic.

That also settles the shape of the fix: gate each ability on the hero's level
alone, and the even distributions follow. No cross-ability requirement is
needed, and the editor does not implement one.
