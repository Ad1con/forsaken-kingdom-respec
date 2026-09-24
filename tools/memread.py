"""Read ability tooltip text out of the running game and bake it into
fkrespec/tooltips_data.json, the fallback the tool uses when a save has no
definition for an ability (Relentless Cleave and Battering Ram, for example,
are never written into a save).

Read-only: opens Warcraft III.exe with PROCESS_VM_READ and scans committed
readable regions for strings. Nothing is written to the game.

The game keeps each tooltip twice: a raw form with `<AUsw,DataA1>` placeholders
and, once it has rendered it, a resolved form. Pairing the two yields the value
of every field, and those same fields appear in the per-level tooltips, so the
rest can then be filled in.

    memread.py [save folder] [--dry]

Passing the campaign save folder adds the resolved text already in those saves
to the pool, which fills in fields the game has not rendered this session.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fkrespec.heroes import HEROES        # noqa: E402
from fkrespec.tooltips import clean       # noqa: E402
from fkrespec import container            # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), '..', 'fkrespec', 'tooltips_data.json')
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
MEM_COMMIT, PAGE_NOACCESS, PAGE_GUARD = 0x1000, 0x01, 0x100
TH32CS_SNAPPROCESS = 0x2

k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', w.DWORD), ('PartitionId', w.WORD),
                ('RegionSize', ctypes.c_size_t), ('State', w.DWORD),
                ('Protect', w.DWORD), ('Type', w.DWORD)]


class PE32(ctypes.Structure):
    _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)), ('th32ModuleID', w.DWORD),
                ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD), ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', w.DWORD), ('szExeFile', ctypes.c_char * 260)]


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.decode(errors='ignore').lower() == name.lower():
            k32.CloseHandle(snap)
            return pe.th32ProcessID
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return None


def regions(h):
    k32.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    addr, mbi = 0, MBI()
    while addr < 0x7FFFFFFFFFFF:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)):
            yield mbi.BaseAddress or 0, mbi.RegionSize
        addr = (mbi.BaseAddress or 0) + mbi.RegionSize


def read(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return b''
    return buf.raw[:got.value]


STR = re.compile(rb'[\x20-\x7e][\x20-\x7e\x80-\xbf\xc2-\xef]{5,1500}')
KEEP = re.compile(rb'Level \d\|r|<[A-Za-z0-9]{4},[A-Za-z]|\|cffffcc00Level')
PH = re.compile(r'<([A-Za-z0-9]{4}),([A-Za-z0-9]+)(?:,[^>]*)?>')
LEVEL1 = 'Level 1|r - '


def scan_strings():
    pid = find_pid('Warcraft III.exe')
    if not pid:
        raise SystemExit('Warcraft III is not running')
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise SystemExit(f'cannot open process (error {ctypes.get_last_error()})')
    out = set()
    for base, size in regions(h):
        pos = 0
        while pos < size:
            chunk = read(h, base + pos, min(size - pos, 32 << 20))
            if not chunk:
                break
            for m in STR.finditer(chunk):
                s = m.group()
                if KEEP.search(s):
                    out.add(s.decode('utf-8', 'replace'))
            pos += len(chunk)
    k32.CloseHandle(h)
    return sorted(out)


def save_strings(folder, limit_per_map=1):
    """Resolved tooltip text from saves: the game wrote it there already, so it
    widens the pool of known field values well beyond what memory has rendered."""
    import glob
    best = {}
    for p in sorted(glob.glob(os.path.join(folder, '*.w3z')), key=os.path.getmtime, reverse=True):
        m = container.map_name(p)
        if m and len(best.setdefault(m, [])) < limit_per_map:
            best[m].append(p)
    out = set()
    for paths in best.values():
        for p in paths:
            try:
                _, payload, _ = container.unpack(p)
            except Exception:
                continue
            for m in STR.finditer(payload[:0x300000]):
                out.add(m.group().decode('utf-8', 'replace'))
    return out


def to_regex(raw, capture):
    """Regex matching raw's resolved twin; `capture` groups the substituted values."""
    parts = PH.split(raw)          # text, id, field, text, id, field, ..., text
    out = []
    for i, p in enumerate(parts):
        if i % 3 == 0:
            out.append(re.escape(p))
        elif i % 3 == 1:
            out.append(r'([^<>]{0,40}?)' if capture else r'[^<>]{0,40}?')
    return re.compile('^' + ''.join(out) + '$', re.S)


def field_values(strings, extra_plains=()):
    """{(id, field): value} learned by pairing raw tooltips with resolved ones."""
    raws = [s for s in strings if PH.search(s)]
    plains = [s for s in strings if not PH.search(s)]
    plains += [s for s in extra_plains if not PH.search(s)]
    values = {}
    for raw in raws:
        rx = to_regex(raw, capture=True)
        hits = {m.groups() for m in (rx.match(p) for p in plains) if m}
        if len(hits) != 1:          # no twin, or twins that disagree about the values
            continue
        fields = [(m.group(1), m.group(2)) for m in PH.finditer(raw)]
        for key, val in zip(fields, hits.pop()):
            values.setdefault(key, val)
    return values, raws


def resolve(raw, values):
    """Substitute every placeholder, or return None if any value is unknown."""
    missing = []

    def sub(m):
        v = values.get((m.group(1), m.group(2)))
        if v is None:
            missing.append(m.group(0))
            return m.group(0)
        return v
    out = PH.sub(sub, raw)
    return None if missing else out


def owner(raw):
    """The ability id a tooltip belongs to: the one its placeholders name most."""
    ids = [m.group(1) for m in PH.finditer(raw)]
    return max(set(ids), key=ids.count) if ids else None


def level_of(raw):
    """1-5 when every placeholder shares one trailing digit, else None."""
    digits = {m.group(2)[-1] for m in PH.finditer(raw) if m.group(2)[-1].isdigit()}
    return int(digits.pop()) if len(digits) == 1 else None


def wanted_ids():
    ids = set()
    for h in HEROES.values():
        for slot, base in enumerate(h['base']):
            ids.add(base)
            prefix = h['variant'].get(base)
            if prefix:
                ids |= {prefix + str(n) for n in (1, 2, 3)}
        for _row, (_label, choices, _slot) in h['rows'].items():
            ids |= {rid for _n, rid in choices}
    return ids


def names_by_id():
    out = {}
    for h in HEROES.values():
        for slot, base in enumerate(h['base']):
            out[base] = h['abilities'][slot]
            prefix = h['variant'].get(base)
            if prefix:
                for n in (1, 2, 3):
                    out[prefix + str(n)] = h['abilities'][slot]
        for _row, (_label, choices, _slot) in h['rows'].items():
            for cname, rid in choices:
                out[rid] = cname
    return out


def build(strings, extra_plains=()):
    values, raws = field_values(strings, extra_plains)
    ids, names = wanted_ids(), names_by_id()
    data = {}
    for raw in raws:
        rid = owner(raw)
        if rid not in ids:
            continue
        text = resolve(raw, values)
        if not text or '<' in text or '>' in text:   # a partial match leaves wreckage
            continue
        entry = data.setdefault(rid, {'name': names.get(rid, ''), 'desc': '', 'levels': [], 'learn': ''})
        if rid[1] == 'T':                             # a talent: one description, no levels
            if len(text) > len(entry['desc']):
                entry['desc'] = clean(text)
            continue
        if LEVEL1 in text:
            if len(text) > len(entry['learn']):
                entry['learn'] = clean(text)
        else:
            lvl = level_of(raw)
            if lvl:
                while len(entry['levels']) < lvl:
                    entry['levels'].append('')
                if len(text) > len(entry['levels'][lvl - 1]):
                    entry['levels'][lvl - 1] = clean(text)
            elif rid[1] == 'T' and len(text) > len(entry['desc']):
                # only talents carry a plain description; a talent's text names the
                # ability's data fields, so it would otherwise land on the ability
                entry['desc'] = clean(text)
    for entry in data.values():                       # drop ragged level lists
        if entry['levels'] and not all(entry['levels']):
            entry['levels'] = []
    return {k: v for k, v in data.items() if v['learn'] or v['levels'] or v['desc']}


def main():
    strings = scan_strings()
    folder = next((a for a in sys.argv[1:] if os.path.isdir(a)), None)
    extra = save_strings(folder) if folder else ()
    if folder:
        print(f'{len(extra)} resolved strings from saves in {folder}')
    data = build(strings, extra)
    have_levels = sum(1 for v in data.values() if v['levels'])
    have_learn = sum(1 for v in data.values() if v['learn'])
    print(f'{len(strings)} strings scanned -> {len(data)} abilities '
          f'({have_levels} with per-level text, {have_learn} with a learn tooltip)')
    if '--dry' in sys.argv:
        for rid in sorted(data):
            v = data[rid]
            print(f"  {rid}  {v['name']!r:28} levels={len(v['levels'])} learn={'y' if v['learn'] else 'n'}")
        return
    old = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding='utf-8'))
    for rid, v in data.items():                       # keep the richer of the two
        cur = old.get(rid)
        if not cur or (len(v['levels']), len(v['learn'])) > (len(cur['levels']), len(cur['learn'])):
            old[rid] = v
    json.dump(old, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False, sort_keys=True)
    print(f'{OUT}: {len(old)} abilities')


if __name__ == '__main__':
    main()
