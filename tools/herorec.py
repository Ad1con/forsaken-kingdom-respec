"""Dump the StoreUnit hero records in a game cache.

    herorec.py <Campaigns.w3v | save.w3z> [-v]

Every zone transition stores each hero into the campaign cache, and a copy of
that cache is embedded in each save. The record layout is in FORMAT.md; the
parsing lives in fkrespec/cache.py. `-v` also lists the item and ability slots.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fkrespec import cache, container     # noqa: E402

# a record is a NUL-terminated name, a 4cc unit type, then the slot count (45)
RECORD = re.compile(rb'([A-Za-z][A-Za-z0-9 ]{1,30})\x00([\x20-\x7e]{4})\x2d\x00\x00\x00')


def dump(d, rec, verbose=False):
    xp, spent = struct.unpack_from('<II', d, rec.tail)
    print(f'[{rec.name}] type={rec.unit_type}  xp={xp}  points spent at last transition={spent}')
    slots = []
    for i in range(4):
        p = rec.slot_off(i)
        base, variant, level = cache.fcc(d[p:p + 4]), cache.fcc(d[p + 4:p + 8]), \
            struct.unpack_from('<I', d, p + 8)[0]
        if base:
            slots.append(f'{base}->{variant} L{level}')
    print('   abilities:', ', '.join(slots) or '(none)')
    print('   talents  :', ', '.join(sorted(rec.talent_offs(d))) or '(none)')
    if verbose:
        print('   raw tail :', bytes(d[rec.tail:rec.tail + 64]).hex())


def main(argv):
    args = [a for a in argv if not a.startswith('-')]
    if not args:
        print(__doc__)
        return 1
    path = args[0]
    _header, d, _block = container.unpack(path)
    print(f'{os.path.basename(path)}: {len(d)} payload bytes\n')
    for m in RECORD.finditer(bytes(d)):
        try:
            rec = cache.HeroRecord(d, m.start())
        except ValueError:
            continue
        dump(d, rec, '-v' in argv)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
