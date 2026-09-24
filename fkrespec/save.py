"""Read hero talents and skill levels from a Forsaken Kingdom .w3z save and
write a respec'd copy.

Three layers are kept in agreement (see FORMAT.md in the repo):
  1. the live hero block: two copies of the current ability-id list
  2. the live ability / talent objects: id at +0x2c and +0x4c, level-1 at +0x30
  3. the hero record in the embedded game cache
"""
import re
import struct

from . import container, cache
from .heroes import HEROES, CHOICES, CHECKED, talent_id, part_of_map
from .tooltips import Tooltips

LIVE_START = 0x1000000   # definition tables sit below this, live objects above
ID_AT, LEVEL_AT, ID2_AT = 0x2c, 0x30, 0x4c
XP_AT, POINTS_AT = -0xb4, -0xb0          # hero object, relative to the ability-list anchor
# Two count-prefixed runs of five: each slot's maximum rank, then the hero level
# its first point needs. FORMAT.md has the readings for both campaigns.
LEARN_AT = -0x5c
# Warcraft III's stock table; the save carries no hero level
XP_TABLE = (200, 500, 900, 1400, 2000, 2700, 3500, 4400, 5400, 6500, 7700, 9000,
            10400, 11900, 13500, 15200, 17000, 18900, 20900, 23000)
OBJECT = re.compile(b'espi.{40}(....).{4}' + bytes([255]) * 8, re.S)   # live ability objects
OBJECT_MAX = 0x40        # longest an OBJECT match can be, so chunks overlap by this much
SCAN_CHUNK = 8 << 20


def rev(s):
    return s.encode('latin1')[::-1]


def fcc(b):
    return b[::-1].decode('latin1')


def slot_of(h, row):
    """Which ability slot a talent row modifies, or None for a passive row."""
    return h['rows'][row][2]


class RespecError(Exception):
    pass


class HeroState:
    """What the editor lets you change for one hero."""

    def __init__(self, utype):
        self.utype = utype
        self.name = HEROES[utype]['name']
        self.anchor = None
        self.current = []                 # current ability ids, Q W E R
        self.levels = [0, 0, 0, 0]        # 0 = not learned
        self.max_levels = list(HEROES[utype]['max_levels'])
        self.picks = {}                   # row -> choice ('a'/'b'/'c')
        self.available = 0                # unspent skill points
        self.xp = 0
        self.level_required = [0, 0, 0, 0]   # hero level each ability's first point needs
        self.level_skip = list(HEROES[utype]['level_skip'])
        # Attribute Bonus: a fifth slot the acts add, shared by every hero under
        # one id, so its rank is derived rather than read (FORMAT.md).
        self.stat = 0
        self.stat_max = 0
        self.stat_required = 0
        # A rule only where the requirement table has been read from the game;
        # advice elsewhere, since the save does not carry the level skip.
        self.gated = True

    @property
    def level(self):
        """Hero level, from experience: the save has no field for it."""
        return 1 + sum(1 for need in XP_TABLE if self.xp >= need)

    def requirement(self, slot, rank):
        """Hero level needed to put `rank` points into an ability."""
        return self.level_required[slot] + (rank - 1) * self.level_skip[slot]

    def spin_max(self, slot):
        """Highest rank the editor will offer: the level's, or the ability's own
        where the level gate is only advice."""
        return self.max_levels[slot] if not self.gated else self.rank_cap(slot)

    def rank_cap(self, slot):
        """Highest rank this hero's level allows, capped by the ability's own maximum."""
        cap = 0
        while cap < self.max_levels[slot] and self.requirement(slot, cap + 1) <= self.level:
            cap += 1
        return cap

    @property
    def points(self):
        return sum(self.levels) + self.stat

    @property
    def budget(self):
        """Points this hero can have assigned: what is spent plus what is unspent."""
        return self.points + self.available

    def copy(self):
        c = HeroState(self.utype)
        c.anchor, c.current = self.anchor, list(self.current)
        c.levels, c.max_levels, c.picks = list(self.levels), list(self.max_levels), dict(self.picks)
        c.available, c.xp = self.available, self.xp
        c.level_required = list(self.level_required)
        c.level_skip = list(self.level_skip)
        c.stat, c.stat_max, c.stat_required = self.stat, self.stat_max, self.stat_required
        c.gated = self.gated
        return c


class Save:
    def __init__(self, path):
        self.path = path
        self.header, self.d, self.block = container.unpack(path)
        self.build, self.build_label = container.game_build(self.header)
        m = re.search(rb'[A-Za-z]+RE\d\d\w*', self.d[:64])
        self.map = m.group().decode() if m else ''
        self.part = part_of_map(self.map)
        self.tips = Tooltips(self.d)
        self._index = None

    # ------------------------------------------------------------ reading
    def defined(self, rid):
        """Is this ability id in the save's definition table?"""
        return self.d.find(rev(rid) + bytes(8) + rev(rid), 0, LIVE_START) != -1

    def _anchor(self, h):
        """The hero's ability-list anchor: the last copy of the base-ability list."""
        pat = b'\x05\x00\x00\x00' + b''.join(rev(x) for x in h['base'])
        i = self.d.rfind(pat, LIVE_START)
        return i if i != -1 else None

    def _ids_in_play(self):
        """Every ability and talent id the heroes of this campaign part can hold."""
        ids = set()
        for utype, h in HEROES.items():
            if self.part not in h['parts']:
                continue
            for base in h['base']:
                ids.add(base)
                prefix = h['variant'].get(base)
                if prefix:
                    ids.update(prefix + str(n) for n in (1, 2, 3))
            for _row, (_label, choices, _slot) in h['rows'].items():
                ids.update(rid for _name, rid in choices)
        return ids

    def _build_index(self, ids):
        """{id: [espi offsets]} for the given ids, in one pass over the buffer.

        Scanning once per id used to copy the whole live region each time, which
        cost seconds per save. Anchoring on the `espi` marker keeps it to a
        single pass the regex engine can drive with a literal prefix, and the
        id set is checked first so most objects cost one set lookup.
        """
        want = {rev(i) for i in ids}
        index = {i: [] for i in ids}
        # Chunked: one sweep over 200 MB holds the interpreter lock long enough
        # to stall the window from a worker thread.
        lo = LIVE_START
        while lo < len(self.d):
            hi = min(lo + SCAN_CHUNK, len(self.d))
            for m in OBJECT.finditer(self.d, lo, min(hi + OBJECT_MAX, len(self.d))):
                if m.start() >= hi:            # belongs to the next chunk
                    break
                tag = m.group(1)
                if tag in want and self.d[m.start() + ID2_AT:m.start() + ID2_AT + 4] == tag:
                    index[fcc(tag)].append(m.start())
            lo = hi
        return index

    def _objects(self, rid):
        """espi offsets of every live object tagged with rid."""
        if self._index is None:
            self._index = self._build_index(self._ids_in_play())
        if rid not in self._index:                      # an id from another part
            self._index.update(self._build_index({rid}))
        return self._index[rid]

    def _level(self, e):
        return struct.unpack_from('<I', self.d, e + LEVEL_AT)[0] + 1

    def hero(self, utype):
        """HeroState for a hero, or None if the hero is not in this save."""
        h = HEROES[utype]
        a = self._anchor(h)
        if a is None:
            return None
        s = HeroState(utype)
        s.gated = self.part in CHECKED
        s.anchor = a
        cur1 = [fcc(self.d[a - 0x70 + 4 * k:a - 0x6c + 4 * k]) for k in range(4)]
        cur2 = [fcc(self.d[a - 0x14 + 4 * k:a - 0x10 + 4 * k]) for k in range(4)]
        if cur1 != cur2 or self.d[a - 0x74:a - 0x70] != b'\x05\x00\x00\x00':
            raise RespecError(f'{s.name}: hero block does not look as expected')
        s.current = cur1
        s.xp, s.available = struct.unpack_from('<II', self.d, a + XP_AT)
        block = struct.unpack_from('<12I', self.d, a + LEARN_AT)
        if block[0] == 5 and block[6] == 5:      # the save's own caps beat the table
            s.max_levels = list(block[1:5])
            s.level_required = list(block[7:11])
            s.stat_max, s.stat_required = block[5], block[11]
        for slot, rid in enumerate(cur1):
            objs = self._objects(rid)
            s.levels[slot] = self._level(objs[0]) if objs else 0
            # heroes.py holds the caps; a save only ever raises one, never lowers it
            s.max_levels[slot] = max(s.max_levels[slot], s.levels[slot])
        # Whatever the other four slots and the unspent counter leave over is in
        # Attribute Bonus, which needs no object of its own.
        if s.stat_max:
            s.stat = max(0, min(s.stat_max, s.level - s.available - sum(s.levels)))
        for row in h['rows']:
            for c in CHOICES:
                if self._objects(talent_id(utype, row, c)):
                    s.picks[row] = c
        return s

    def heroes(self):
        found = [s for s in (self.hero(u) for u, h in HEROES.items() if self.part in h['parts'])
                 if s is not None]
        return sorted(found, key=lambda s: HEROES[s.utype]['order'])

    # ------------------------------------------------------------ writing
    def _retag(self, e, old, new):
        for at in (ID_AT, ID2_AT):
            if self.d[e + at:e + at + 4] != rev(old):
                raise RespecError(f'object at {e:#x} is not {old}')
            self.d[e + at:e + at + 4] = rev(new)
        self._index = None        # ids moved; the index no longer describes the buffer

    def variant_for(self, state, slot, choice):
        """Ability id the slot should carry for this talent choice."""
        h = HEROES[state.utype]
        base = h['base'][slot]
        prefix = h['variant'].get(base)
        if state.current[slot] != base:            # learn the prefix from what the game did
            prefix = state.current[slot][:3]
        if not prefix:
            return base
        vid = prefix + str(CHOICES.index(choice) + 1)
        return vid if self.defined(vid) else base

    def _only(self, rid):
        objs = self._objects(rid)
        if len(objs) != 1:
            raise RespecError(f'expected one live {rid} object, found {len(objs)}')
        return objs[0]

    def apply(self, before, after):
        """Change hero `before` (as read) into `after` (as edited)."""
        h = HEROES[before.utype]
        a = before.anchor
        rec = cache.find_record(self.d, h['cache_key'].encode())
        # The engine keeps its own count of unspent points next to experience, so a
        # level change has to be paid for out of it (or refunded into it).
        spend = after.points - before.points
        if spend > before.available:
            raise RespecError(f'{before.name} has {before.available} skill '
                              f'point{"" if before.available == 1 else "s"} to spend')
        for slot in range(4):
            if before.levels[slot] == 0 and after.levels[slot] != 0:
                raise RespecError(f"{h['abilities'][slot]} is not learned yet; learn it in game")
            if after.levels[slot] == 0 and before.levels[slot] != 0:
                raise RespecError(f"{h['abilities'][slot]} cannot go below level 1 "
                                  f"(unlearning would mean deleting it from the save)")
            if not 0 <= after.levels[slot] <= before.max_levels[slot]:
                raise RespecError(f"{h['abilities'][slot]} goes up to level {before.max_levels[slot]}")
            if before.gated and after.levels[slot] > max(before.levels[slot], before.rank_cap(slot)):
                raise RespecError(
                    f"{h['abilities'][slot]} reaches level {after.levels[slot]} at hero level "
                    f"{before.requirement(slot, after.levels[slot])}; "
                    f"{before.name} is level {before.level}")
        # Swaps only: removing a talent object leaves handles pointing at nothing
        # and the game crashes on load (FORMAT.md).
        if set(after.picks) != set(before.picks):
            raise RespecError('talent rows can only be changed, not added or removed')

        if spend:
            struct.pack_into('<I', self.d, a + POINTS_AT, before.available - spend)

        for slot in range(4):
            if after.levels[slot] != before.levels[slot]:
                e = self._only(before.current[slot])
                struct.pack_into('<I', self.d, e + LEVEL_AT, after.levels[slot] - 1)
                if rec:
                    struct.pack_into('<I', self.d, rec.slot_off(slot) + 8, after.levels[slot])

        for row, new_c in after.picks.items():
            old_c = before.picks[row]
            if new_c == old_c:
                continue
            old_t, new_t = talent_id(before.utype, row, old_c), talent_id(before.utype, row, new_c)
            self._retag(self._only(old_t), old_t, new_t)
            if rec:
                offs = rec.talent_offs(self.d)
                if old_t in offs:       # absent when picked since the last zone transition
                    self.d[offs[old_t]:offs[old_t] + 4] = rev(new_t)
            # A passive row modifies no ability, so there is no variant to look up
            slot = slot_of(h, row)
            new_v = self.variant_for(before, slot, new_c) if slot is not None else None
            self._set_slot_ability(before, rec, row, new_v)

    def _set_slot_ability(self, before, rec, row, new_v):
        """Point a hero's ability slot at `new_v`, in both live lists and the cache."""
        slot = slot_of(HEROES[before.utype], row)
        if slot is None or new_v is None:
            return
        old_v = before.current[slot]
        if old_v == new_v:
            return
        self._retag(self._only(old_v), old_v, new_v)
        for base_off in (before.anchor - 0x70, before.anchor - 0x14):
            self.d[base_off + 4 * slot:base_off + 4 * slot + 4] = rev(new_v)
        if rec:
            p = rec.slot_off(slot)
            self.d[p + 4:p + 8] = rev(new_v)
        before.current[slot] = new_v

    def write(self, out_path, progress=None):
        data = container.pack(self.header, self.d, self.block, progress)   # no full copy
        open(out_path, 'wb').write(data)
