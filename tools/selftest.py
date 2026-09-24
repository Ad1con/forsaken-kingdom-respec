"""Check the editor against your own saves.

    selftest.py [save folder]

Reads every save it finds and checks the things that must hold:

  * repacking an untouched save reproduces the original file byte for byte
  * a save with a corrupted block is rejected rather than silently read
  * every hero reads back with sane levels, talents and skill points
  * an edit reads back as the edit, and the totals still add up
  * the edits the tool refuses are still refused

Nothing is written to the save folder; edits are made on copies in a temporary
directory.
"""
import glob
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fkrespec import container                      # noqa: E402
from fkrespec.gui import default_folder             # noqa: E402
from fkrespec.heroes import HEROES, CHOICES         # noqa: E402
from fkrespec.save import Save, RespecError         # noqa: E402

passed = failed = 0


def check(label, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  ok    {label}')
    else:
        failed += 1
        print(f'  FAIL  {label}  {detail}')


def check_raises(label, fn):
    try:
        fn()
    except RespecError:
        check(label, True)
        return
    check(label, False, 'was accepted')


def main(argv):
    folder = argv[0] if argv else default_folder()
    saves = sorted(glob.glob(os.path.join(folder, '*.w3z')), key=os.path.getmtime, reverse=True)
    if not saves:
        print(f'no saves in {folder}')
        return 1
    print(f'{len(saves)} saves in {folder}\n')
    tmp = tempfile.mkdtemp()
    try:
        for path in saves:
            name = os.path.basename(path)[:38]
            t = time.perf_counter()
            save = Save(path)
            states = save.heroes()
            out = os.path.join(tmp, 'rt.w3z')
            save.write(out)
            same = open(out, 'rb').read() == open(path, 'rb').read()
            check(f'{name:40} round-trip', same)
            for st in states:
                h = HEROES[st.utype]
                check(f'{name:40} {st.name} levels',
                      all(0 <= lv <= mx for lv, mx in zip(st.levels, st.max_levels)),
                      f'{st.levels} vs max {st.max_levels}')
                check(f'{name:40} {st.name} talents',
                      all(c in CHOICES and row in h['rows'] for row, c in st.picks.items()),
                      str(st.picks))
                # a hero holding a rank the table says they cannot reach means the
                # requirement table is wrong for that campaign
                if st.gated:
                    check(f'{name:40} {st.name} levels are reachable',
                          all(lv <= st.rank_cap(i) for i, lv in enumerate(st.levels)),
                          f'{st.levels} vs reachable '
                          f'{[st.rank_cap(i) for i in range(4)]} at level {st.level}')
                # every level grants exactly one point, so counting all five slots
                # plus the unspent ones has to come back to the hero's level
                check(f'{name:40} {st.name} points match the level',
                      st.budget == st.level,
                      f'{st.levels} + stat {st.stat} + {st.available} spare '
                      f'!= level {st.level}')
            if states:
                print(f'        ({time.perf_counter() - t:.2f}s, {len(save.d) / 1e6:.0f} MB payload)')

        # editing: use the newest save that has a hero with a learned ability to move
        save = Save(saves[0])
        state = next((s for s in save.heroes() if sum(1 for lv in s.levels if lv) >= 2), None)
        if state:
            move_from = max((i for i, lv in enumerate(state.levels) if lv > 1), default=None)
            # the destination has to be one the hero's level allows, not just one
            # under the ability's own cap
            move_to = next((i for i, lv in enumerate(state.levels)
                            if lv and i != move_from and lv < state.rank_cap(i)), None)
            if move_from is not None and move_to is not None:
                after = state.copy()
                after.levels[move_from] -= 1
                after.levels[move_to] += 1
                save.apply(state, after)
                edited = os.path.join(tmp, 'edit.w3z')
                save.write(edited)
                back = next(s for s in Save(edited).heroes() if s.utype == state.utype)
                check('edit reads back', back.levels == after.levels,
                      f'{back.levels} != {after.levels}')
                check('skill points still add up',
                      back.points + back.available == state.points + state.available)

            # a passive talent row modifies no ability, which once meant the write
            # looked up a variant for a slot that does not exist
            for path in saves[:6]:
                trial = Save(path)
                hero = next((x for x in trial.heroes()
                             if any(HEROES[x.utype]['rows'][r][2] is None for r in x.picks)), None)
                if not hero:
                    continue
                row = next(r for r in hero.picks if HEROES[hero.utype]['rows'][r][2] is None)
                other = next(c for c in CHOICES if c != hero.picks[row])
                want = hero.copy()
                want.picks[row] = other
                trial.apply(hero, want)
                swapped = os.path.join(tmp, 'passive.w3z')
                trial.write(swapped)
                got = next(x for x in Save(swapped).heroes() if x.utype == hero.utype)
                check('passive talent row swaps', got.picks[row] == other,
                      f'{got.picks[row]} != {other}')
                check('passive swap leaves the abilities alone',
                      got.current == hero.current, f'{got.current} != {hero.current}')
                break

            fresh = Save(saves[0])
            st = next(s for s in fresh.heroes() if s.utype == state.utype)
            over = st.copy()
            over.levels = [lv + 1 if lv else lv for lv in over.levels]
            check_raises('overspending refused', lambda: fresh.apply(st, over))

            # the hero's level gates how far an ability goes, so a rank the game
            # would not offer must be refused even when the points are there
            beyond = next((i for i, lv in enumerate(st.levels)
                           if lv and st.rank_cap(i) < st.max_levels[i]), None)
            if beyond is not None:
                far = st.copy()
                far.levels[beyond] = st.rank_cap(beyond) + 1
                far.available = st.available + st.levels[beyond] - far.levels[beyond]
                check_raises('rank above the hero level refused',
                             lambda: fresh.apply(st, far))
                check(f'{st.name} rank cap matches the requirement table',
                      all(st.requirement(i, st.rank_cap(i)) <= st.level
                          for i in range(4) if st.rank_cap(i)))

            unlearned = next((i for i, lv in enumerate(st.levels) if lv == 0), None)
            if unlearned is not None:
                learn = st.copy()
                learn.levels[unlearned] = 1
                check_raises('learning an unlearned ability refused',
                             lambda: fresh.apply(st, learn))

        # a corrupt block must not read as if it were fine
        broken = os.path.join(tmp, 'broken.w3z')
        d = bytearray(open(saves[-1], 'rb').read())
        d[0x100:0x140] = b'\0' * 0x40
        open(broken, 'wb').write(d)
        try:
            Save(broken)
            check('corrupt save rejected', False, 'it was read without complaint')
        except container.BadContainer:
            check('corrupt save rejected', True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f'\n{passed} passed, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
