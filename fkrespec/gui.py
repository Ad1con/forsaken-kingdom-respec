"""Tkinter front end: one tab per campaign part, saves sorted into tabs by map.

Deliberately plain ttk. A themed build drew the hero panels in 0.84s against
0.15s here, charged per widget instance rather than once, so the theme cost a
visible pause every time a save loaded.
"""
import glob
import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import __version__
from .heroes import HEROES, CHOICES, CHECKED, PARTS, part_of_map, talent_id, talent_names
from .save import Save, RespecError
from .container import BadContainer, map_name

SUFFIX = ' Respec'
COLUMNS = 3          # three hero panels fit a 975px window; more wrap to a second row


def documents_folder():
    """The real Documents folder, which Windows may have redirected into OneDrive."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class GUID(ctypes.Structure):
            _fields_ = [('a', wt.DWORD), ('b', wt.WORD), ('c', wt.WORD),
                        ('d', ctypes.c_byte * 8)]

        tail = (ctypes.c_byte * 8)(*[c - 256 if c > 127 else c
                                     for c in bytes.fromhex('adb46c85480369c7')])
        documents = GUID(0xFDD39AD0, 0x238F, 0x46AF, tail)
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(documents), 0, None, ctypes.byref(out)) == 0:
            path = out.value
            ctypes.windll.ole32.CoTaskMemFree(out)
            if path:
                return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def default_folder():
    """Newest ForsakenKingdom save folder, wherever Documents actually lives."""
    home = os.path.expanduser('~')
    roots = [documents_folder(), os.path.join(home, 'Documents')]
    roots += glob.glob(os.path.join(home, 'OneDrive*', 'Documents'))
    hits = []
    for root in dict.fromkeys(roots):
        hits += glob.glob(os.path.join(root, 'Warcraft III', 'BattleNet',
                                       '*', 'Campaigns', 'ForsakenKingdom'))
    hits = sorted(dict.fromkeys(hits), key=os.path.getmtime, reverse=True)
    return hits[0] if hits else ''


def saves_by_part(folder):
    """{part: [paths newest first]}"""
    out = {part: [] for part, _prefixes, _ok in PARTS}
    for p in sorted(glob.glob(os.path.join(folder, '*.w3z')), key=os.path.getmtime, reverse=True):
        part = part_of_map(map_name(p) or '')
        if part:
            out[part].append(p)
    return out


def unique_target(folder, stem):
    name, n = stem + SUFFIX, 2
    while os.path.exists(os.path.join(folder, name + '.w3z')):
        name = f'{stem}{SUFFIX} {n}'
        n += 1
    return name


class Tooltip:
    """Hover text for a widget; `text` is a callable so it reflects current choices."""

    def __init__(self, widget, text):
        self.widget, self.text, self.win = widget, text, None
        widget.bind('<Enter>', self.show, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def show(self, _event=None):
        body = self.text()
        if not body or self.win:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.win = tk.Toplevel(self.widget)
        self.win.wm_overrideredirect(True)
        self.win.attributes('-topmost', True)
        tk.Label(self.win, text=body, justify='left', wraplength=540,
                 background='#fffbe6', foreground='#101010',
                 relief='solid', borderwidth=1, padx=10, pady=8).pack()
        self.win.update_idletasks()                  # keep it on screen
        w_, h_ = self.win.winfo_width(), self.win.winfo_height()
        x = min(x, self.win.winfo_screenwidth() - w_ - 8)
        y = min(y, self.win.winfo_screenheight() - h_ - 8)
        self.win.wm_geometry(f'+{max(0, x)}+{max(0, y)}')

    def hide(self, _event=None):
        if self.win:
            self.win.destroy()
            self.win = None


class HeroPanel(ttk.LabelFrame):
    def __init__(self, master, save, state):
        super().__init__(master, text=f'{state.name}  ·  level {state.level}', padding=8)
        self.save, self.before = save, state
        h = HEROES[state.utype]
        self.level_vars, self.pick_vars = [], {}

        ttk.Label(self, text='Skill points', font=('', 9, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 2))
        self.total = ttk.Label(self)
        self.total.grid(row=0, column=1, sticky='e')
        for slot, name in enumerate(h['abilities']):
            lbl = ttk.Label(self, text=name)
            lbl.grid(row=1 + slot, column=0, sticky='w', padx=(0, 12))
            lvl = state.levels[slot]
            var = tk.IntVar(value=lvl)
            self.level_vars.append(var)
            if lvl:
                # a hero's level gates how far an ability goes, the same as in game
                ctl = ttk.Spinbox(self, from_=1, to=max(state.spin_max(slot), lvl), width=4,
                                  textvariable=var, command=self.refresh, state='readonly')
            else:
                ctl = ttk.Label(self, text='not learned yet', foreground='gray')
            ctl.grid(row=1 + slot, column=1, sticky='e')
            for w in (lbl, ctl):
                Tooltip(w, lambda slot=slot: self.ability_tip(slot))

        if state.stat_max:      # the acts add a fifth slot the prologue does not have
            lbl = ttk.Label(self, text='Attribute Bonus')
            lbl.grid(row=5, column=0, sticky='w', padx=(0, 12))
            ctl = ttk.Label(self, text=str(state.stat), foreground='gray')
            ctl.grid(row=5, column=1, sticky='e')
            for w in (lbl, ctl):
                Tooltip(w, self.stat_tip)

        ttk.Label(self, text='Talents', font=('', 9, 'bold')).grid(row=6, column=0, sticky='w', pady=(10, 2))
        for i, (row, (label, _choices, _slot)) in enumerate(sorted(h['rows'].items())):
            names = talent_names(state.utype, row)
            lbl = ttk.Label(self, text=label)
            lbl.grid(row=7 + i, column=0, sticky='w', padx=(0, 12))
            pick = state.picks.get(row)
            if pick:
                var = tk.StringVar(value=names[CHOICES.index(pick)])
                self.pick_vars[row] = var
                ctl = ttk.Combobox(self, values=names, textvariable=var, state='readonly', width=24)
            else:
                ctl = ttk.Label(self, text='not picked yet', foreground='gray')
            ctl.grid(row=7 + i, column=1, sticky='e')
            for w in (lbl, ctl):
                Tooltip(w, lambda row=row: self.talent_tip(row))
        self.columnconfigure(1, weight=1)
        self.refresh()

    # ------------------------------------------------------------ hover text
    def ability_tip(self, slot):
        h = HEROES[self.before.utype]
        base = h['base'][slot]
        level = self.level_vars[slot].get()
        if not level:
            return (self.save.tips.ability(base, 1, base) or h['abilities'][slot]) + self.gate(slot)
        rid = self.before.current[slot]
        row = next((r for r, (_, _, s) in h['rows'].items() if s == slot), None)
        if row in self.pick_vars:       # show the variant for the choice currently selected
            c = CHOICES[talent_names(self.before.utype, row).index(self.pick_vars[row].get())]
            rid = self.save.variant_for(self.before, slot, c)
        text = self.save.tips.ability(rid, level, base) or h['abilities'][slot]
        return text + self.gate(slot)

    def gate(self, slot):
        """What the next point would cost, for the level currently shown."""
        s = self.before
        # one above whatever the spinner shows, so this moves as you drag it
        nxt = (self.level_vars[slot].get() or 0) + 1
        if nxt > s.max_levels[slot]:
            return ''
        rule = '─' * 30
        line = (f'Level {nxt} requires hero level {s.requirement(slot, nxt)}. '
                f'{s.name} is level {s.level}.')
        if not s.gated:
            line += '\nUnconfirmed for this act, so it is not enforced.'
        return f'\n\n{rule}\n{line}'

    def stat_tip(self):
        text = self.save.tips.ability('Aaml', max(1, self.before.stat)) or 'Attribute Bonus'
        rule = '─' * 30
        return f'{text}\n\n{rule}\nRead-only. Stat points cannot be changed.'

    def talent_tip(self, row):
        chosen = self.pick_vars[row].get() if row in self.pick_vars else None
        parts = []
        for c, name in zip(CHOICES, talent_names(self.before.utype, row)):
            body = self.save.tips.talent(talent_id(self.before.utype, row, c)) or name
            mark = '▶ ' if name == chosen else '   '
            parts.append(mark + body.replace('\n', '\n   ', 1))
        return '\n\n'.join(parts)

    def refresh(self):
        assigned = sum(v.get() for v in self.level_vars) + self.before.stat
        spare = self.before.budget - assigned
        text = f'{assigned} of {self.before.budget} assigned'
        if spare > 0:
            text += f'  ·  {spare} to spend in game'
        self.total.configure(text=text, foreground='#d13438' if spare < 0 else '')
        return spare >= 0

    def over_level(self):
        """Abilities set past what the hero's level allows; only possible where
        the gate is advice rather than a rule."""
        h = HEROES[self.before.utype]
        return [h['abilities'][i] for i, v in enumerate(self.level_vars)
                if v.get() > max(self.before.levels[i], self.before.rank_cap(i))]

    def after(self):
        s = self.before.copy()
        s.levels = [v.get() for v in self.level_vars]
        for row, var in self.pick_vars.items():
            s.picks[row] = CHOICES[talent_names(s.utype, row).index(var.get())]
        return s

    def changed(self):
        a = self.after()
        return a.levels != self.before.levels or a.picks != self.before.picks


class PartTab(ttk.Frame):
    """One campaign part: its saves, and the heroes of the selected save."""

    def __init__(self, master, app, part):
        super().__init__(master, padding=10)
        self.app, self.part = app, part
        self.unchecked = part not in CHECKED
        self.saves, self.save, self.panels = [], None, []
        self.pending = False          # saves listed but not read yet
        self.generation = 0           # bumped per load, so a stale read is ignored
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text='Save game').grid(row=0, column=0, sticky='w')
        self.save_box = ttk.Combobox(top, state='readonly', width=58)
        self.save_box.grid(row=0, column=1, sticky='ew', padx=6)
        self.save_box.bind('<<ComboboxSelected>>', lambda e: self.load())
        self.build_lbl = ttk.Label(top, foreground='gray')
        self.build_lbl.grid(row=1, column=1, sticky='w', padx=6, pady=(4, 0))
        self.body = ttk.Frame(self)
        self.body.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        ttk.Label(bottom, text="Writes a new save named '… Respec'. The original save is never changed.",
                  foreground='gray').grid(row=0, column=0, sticky='w')
        self.write_btn = ttk.Button(bottom, text='Write New Save', command=self.write, state='disabled')
        self.write_btn.grid(row=0, column=1, sticky='e', padx=(12, 0))
        self.status = ttk.Label(bottom, text='', wraplength=560, justify='left')
        self.status.grid(row=1, column=0, sticky='w', pady=(6, 0))
        self.progress = ttk.Progressbar(bottom, mode='determinate', length=160)
        self.progress.grid(row=1, column=1, sticky='e', pady=(6, 0))
        self.progress.grid_remove()          # only shown while writing
        bottom.columnconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def relist(self, paths):
        """Refresh the list of saves without re-reading the one on screen."""
        keep = self.save.path if self.save else None
        self.saves = paths
        self.save_box['values'] = [os.path.splitext(os.path.basename(p))[0] for p in paths]
        if keep in paths:
            self.save_box.current(paths.index(keep))
        elif paths and not self.panels:
            self.save_box.current(0)
            self.pending = True

    def set_saves(self, paths):
        """List the saves; reading one is deferred until the tab is shown."""
        self.saves = paths
        self.save_box['values'] = [os.path.splitext(os.path.basename(p))[0] for p in paths]
        self.clear()
        if paths:
            self.save_box.current(0)
            self.pending = True
        else:
            self.status.configure(text=f'No {self.part} saves in this folder.' + self.caveat())

    def show(self):
        if self.pending:
            self.pending = False
            self.load()

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.panels, self.save = [], None
        self.write_btn.configure(state='disabled')
        self.build_lbl.configure(text='')
        self.status.configure(text='')

    def load(self):
        """Read the selected save on a worker thread and show it when it lands."""
        self.clear()
        path = self.saves[self.save_box.current()]
        self.generation += 1
        mine = self.generation           # a later pick wins; this result is dropped
        job = {'done': False}

        def work():
            try:
                save = Save(path)
                job['result'] = (save, save.heroes())
            except (BadContainer, RespecError, OSError, ValueError) as ex:
                job['error'] = str(ex)
            except Exception as ex:      # never leave the poller waiting on a dead thread
                job['error'] = f'{type(ex).__name__}: {ex}'
            finally:
                job['done'] = True

        self.status.configure(text='Reading save…')
        threading.Thread(target=work, daemon=True).start()
        self.after(40, lambda: self._loading(job, mine))

    def _loading(self, job, mine):
        if mine != self.generation:      # the user moved on
            return
        if not job['done']:
            self.after(40, lambda: self._loading(job, mine))
            return
        if 'error' in job:
            self.status.configure(text=f"Could not read this save: {job['error']}")
            return
        self.save, states = job['result']
        self._show_heroes(states)

    def _show_heroes(self, states):
        ver, build = self.save.build
        if self.save.build_label:
            self.build_lbl.configure(text=f'Game build {self.save.build_label} — tested', foreground='gray')
        else:
            self.build_lbl.configure(text=f'Game build {ver:#x}/{build:#x} has not been tested with this tool',
                                     foreground='#d13438')
        if not states:
            known = ', '.join(h['name'] for h in HEROES.values()
                              if self.part in h['parts']) or 'none yet'
            self.status.configure(text=f'No heroes the editor knows are in this save '
                                       f'({self.part} heroes known: {known}).' + self.caveat())
            return
        for i, st in enumerate(states):
            row, col = divmod(i, COLUMNS)
            last_in_row = col == COLUMNS - 1 or i == len(states) - 1
            p = HeroPanel(self.body, self.save, st)
            p.grid(row=row, column=col, sticky='nsew', pady=(4, 4),
                   padx=(0, 0 if last_in_row else 10))        # no padding past the last panel,
            self.body.columnconfigure(col, weight=1)          # so the edges line up with the button
            self.panels.append(p)
        self.write_btn.configure(state='normal')
        # A rank the table says is out of reach means the table is wrong here.
        off = [st.name for st in states
               if any(lv > st.rank_cap(i) for i, lv in enumerate(st.levels))]
        note = ''
        if off:
            note = (f'  {", ".join(off)} already hold an ability level this act is not '
                    f'expected to allow, so the level requirements here are wrong.')
        self.status.configure(text=(self.caveat() + note).lstrip())

    def caveat(self):
        """Said on any part no save has confirmed: its heroes may not be these."""
        if not self.unchecked:
            return ''
        return (f'  {self.part} is untested: an act can add a hero the editor '
                f'has never seen, as Act Two does.')

    def write(self):
        if not all(p.refresh() for p in self.panels):
            messagebox.showwarning('Skill points',
                                   'A hero cannot be given more skill points than they have.')
            return
        if not any(p.changed() for p in self.panels):
            self.status.configure(text='Nothing changed.')
            return
        # Where the gate is advice, say what is past it rather than refusing.
        past = [(p.before.name, name) for p in self.panels for name in p.over_level()]
        if past:
            listed = '\n'.join(f'  {who}: {what}' for who, what in past)
            if not messagebox.askyesno(
                    'Above the hero level',
                    f'{self.part} has not been checked against a real save, so what '
                    f'each ability level needs is taken from the earlier acts.\n\n'
                    f'These go past it:\n{listed}\n\n'
                    f'The game may refuse to spend them. Write it anyway?'):
                return
        src = self.save.path
        folder, stem = os.path.dirname(src), os.path.splitext(os.path.basename(src))[0]
        target = unique_target(folder, stem)
        # Read the hero panels here, on the UI thread; the worker only touches files.
        edits = [(p.before, p.after()) for p in self.panels]
        job = {'done': False, 'error': None, 'step': 0.0}

        def work():
            try:
                fresh = Save(src)      # apply to a clean copy so repeated writes never stack
                for before, after in edits:
                    fresh.apply(before, after)
                job['step'] = 0.3
                fresh.write(os.path.join(folder, target + '.w3z'),
                            progress=lambda i, n: job.__setitem__('step', 0.3 + 0.7 * i / n))
                zones = os.path.join(folder, 'Blizzard', stem)
                if os.path.isdir(zones):
                    shutil.copytree(zones, os.path.join(folder, 'Blizzard', target))
            except RespecError as ex:
                job['error'] = str(ex)
            except Exception as ex:          # never leave the poller waiting on a dead thread
                import traceback
                job['error'] = f'{type(ex).__name__}: {ex}'
                job['trace'] = traceback.format_exc()
            finally:
                job['done'] = True

        self.write_btn.configure(state='disabled')
        self.save_box.configure(state='disabled')
        self.status.configure(text=f"Writing '{target}'…")
        self.progress.grid()
        self.progress['value'] = 0
        threading.Thread(target=work, daemon=True).start()
        self.after(60, lambda: self._writing(job, target))

    def _writing(self, job, target):
        """Poll the writer thread so the window stays responsive."""
        self.progress['value'] = job['step'] * 100
        if not job['done']:
            self.after(60, lambda: self._writing(job, target))
            return
        self.progress.grid_remove()
        self.save_box.configure(state='readonly')
        if job['error']:
            self.write_btn.configure(state='normal')
            self.status.configure(text='')
            messagebox.showerror('Could not write the save', job['error'])
            return
        self.app.relist()      # list the new save; re-reading it here would stall the window
        self.write_btn.configure(state='normal')
        self.status.configure(text=f"Written: '{target}'. Load it from the campaign's Load Game screen.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'Forsaken Kingdom Respec {__version__}')
        self.resizable(False, False)

        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text='Save folder').grid(row=0, column=0, sticky='w')
        self.folder = tk.StringVar(value=default_folder())
        ttk.Entry(top, textvariable=self.folder, width=66).grid(row=0, column=1, sticky='ew', padx=6)
        ttk.Button(top, text='Browse…', command=self.browse).grid(row=0, column=2)
        ttk.Button(top, text='Refresh', command=self.scan).grid(row=0, column=3, padx=(6, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky='nsew', padx=10, pady=10)
        self.tabs = {}
        for part, _prefixes, checked in PARTS:
            tab = PartTab(self.notebook, self, part)
            self.notebook.add(tab, text=part if checked else f'{part} (untested)')
            self.tabs[part] = tab
        self.notebook.bind('<<NotebookTabChanged>>', self.tab_changed)
        self.scan()

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get() or os.path.expanduser('~'))
        if d:
            self.folder.set(d)
            self.scan()

    def relist(self):
        by_part = saves_by_part(self.folder.get())
        for part, tab in self.tabs.items():
            tab.relist(by_part[part])

    def tab_changed(self, _event=None):
        self.nametowidget(self.notebook.select()).show()

    def scan(self):
        by_part = saves_by_part(self.folder.get())
        newest = None
        for part, tab in self.tabs.items():
            tab.set_saves(by_part[part])
            if by_part[part] and (newest is None or os.path.getmtime(by_part[part][0]) > newest[0]):
                newest = (os.path.getmtime(by_part[part][0]), part)
        if newest:
            self.notebook.select(self.tabs[newest[1]])
        self.nametowidget(self.notebook.select()).show()      # only the visible tab reads a save


def main():
    App().mainloop()
