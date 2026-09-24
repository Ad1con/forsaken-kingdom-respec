"""Dump the live hero block of a save, for working out a new hero's layout.

    livehero.py <save.w3z> [hero name]

Prints, for every hero the editor knows about that appears in the save, the
bytes around the ability-list anchor: experience and unspent skill points, the
current ability ids and the base ability ids. Adding a hero from a later act
starts here - see "Adding a hero" in the README.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fkrespec.save import Save            # noqa: E402
from fkrespec.heroes import HEROES        # noqa: E402


def dump(save, state):
    d, a = save.d, state.anchor
    print(f"{state.name} ({state.utype})  anchor {a:#x}  xp {state.xp}  "
          f"{state.available} unspent  levels {state.levels}")
    print(f'   current {state.current}')
    print(f"   base    {HEROES[state.utype]['base']}")
    for row in range(-0xc0, 0x20, 16):
        chunk = bytes(d[a + row:a + row + 16])
        text = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
        print(f'   {row:+#07x}  {chunk.hex(" ")}  {text}')
    print()


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    save = Save(argv[0])
    print(f'{os.path.basename(argv[0])}: map {save.map} ({save.part})\n')
    wanted = argv[1].lower() if len(argv) > 1 else None
    for state in save.heroes():
        if wanted is None or state.name.lower() == wanted:
            dump(save, state)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
