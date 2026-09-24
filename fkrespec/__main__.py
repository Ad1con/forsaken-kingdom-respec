"""python -m fkrespec            -> window
   python -m fkrespec show SAVE  -> print heroes, talents and levels
"""
import sys


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == 'show':
        from .save import Save
        from .heroes import HEROES, talent_name
        s = Save(sys.argv[2])
        print(f'game build {s.build_label or s.build}, map {s.map} ({s.part})')
        for st in s.heroes():
            h = HEROES[st.utype]
            print(f'== {st.name}  ({st.points} skill points)')
            for slot, name in enumerate(h['abilities']):
                print(f'   {name:20} level {st.levels[slot] or "-"} of {st.max_levels[slot]}')
            for row, (label, _choices, _slot) in sorted(h['rows'].items()):
                c = st.picks.get(row)
                name = talent_name(st.utype, row, c) if c else '-'
                print(f'   {label:20} {name}')
        return
    from .gui import main as gui_main
    gui_main()


if __name__ == '__main__':
    main()
