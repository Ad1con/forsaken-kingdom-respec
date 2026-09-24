"""In-game tooltip text, read from the ability records inside a save.

A record starts with its id, eight zero bytes and the id again, then art
paths, then count-prefixed lists of NUL-terminated strings:
  talents:    [1] name  [1] icon  [1] tip  [1] description
  abilities:  [1] name  [1] icon ... [1] "Learn X - [Level %d]"
              [n] level tips  [n] per-level descriptions ...
"""
import json
import os
import re
import struct
import sys

DEF_LIMIT = 0x300000
_BASE = getattr(sys, '_MEIPASS', None)      # set when running from the packed exe
DATA_FILE = (os.path.join(_BASE, 'fkrespec', 'tooltips_data.json') if _BASE
             else os.path.join(os.path.dirname(__file__), 'tooltips_data.json'))
BACKSLASH = bytes([92])
COLOR = re.compile(r'\|c[0-9a-fA-F]{8}|\|r')


def rev(s):
    return s.encode('latin1')[::-1]


def clean(s):
    return COLOR.sub('', s).replace('|n', '\n').strip()


def is_path(s):
    return BACKSLASH in s or s.endswith((b'.blp', b'.mdl', b'.dds'))


def string_lists(chunk):
    """Yield the count-prefixed string lists in a record chunk, in order."""
    p = 0
    while p + 4 <= len(chunk):
        n = struct.unpack_from('<I', chunk, p)[0]
        if 1 <= n <= 10:
            q, items = p + 4, []
            for _ in range(n):
                end = chunk.find(b'\0', q)
                s = chunk[q:end] if end != -1 else b''
                if not s or not all(0x20 <= c < 0x7f or c >= 0x80 for c in s):
                    items = None
                    break
                items.append(s)
                q = end + 1
            if items:
                yield items
                p = q
                continue
        p += 1


def parse_record(chunk):
    lists = []
    for L in string_lists(chunk):
        if L[0].startswith(b'giro'):     # 'giro' + next id: the record boundary
            break
        lists.append(L)
    name = None
    rest = []
    for L in lists:
        if name is None:
            if len(L) == 1 and not is_path(L[0]):
                name = L[0]
            continue
        if all(not is_path(s) for s in L):
            rest.append(L)
    if name is None:
        return None
    text = lambda b: clean(b.decode('utf-8', 'replace'))
    info = {'name': text(name), 'desc': '', 'levels': [], 'learn': ''}
    learn = next((i for i, L in enumerate(rest) if len(L) == 1 and L[0].startswith(b'Learn ')), None)
    if learn is not None:
        for i, L in enumerate(rest[learn + 1:], learn + 1):
            if len(L) >= 2 and not any(b'Level' in s and b' - [' in s for s in L):
                info['levels'] = [text(s) for s in L]
                # the learn tooltip (general text + per-level breakdown) follows
                after = next((M[0] for M in rest[i + 1:] if len(M) == 1 and len(M[0]) > 30), None)
                if after:
                    info['learn'] = text(after)
                break
    else:
        # [name, icon, tip, description]: the tip is usually the name again but
        # can be the base ability's name, so take the last text, not the first
        tail = [L[0] for L in rest if len(L) == 1 and (b' ' in L[0] or len(L[0]) >= 8)]
        if tail:
            info['desc'] = text(tail[-1])
    return info


def _baked():
    """Text extracted from the game for abilities no save defines (tools/memread.py)."""
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


BAKED = _baked()


class Tooltips:
    def __init__(self, payload):
        self.d = payload
        self.cache = {}

    def get(self, rid):
        """{'name', 'desc', 'levels': [...]} or None."""
        if rid in self.cache:
            return self.cache[rid]
        pat = rev(rid) + bytes(8) + rev(rid)
        info, i = None, self.d.find(pat, 0, DEF_LIMIT)
        while i != -1:
            chunk = self.d[i + 12:i + 12 + 0x1000]
            if BACKSLASH in chunk[:64]:           # full records open with an art path;
                found = parse_record(chunk)      # the id index does not
                if found and (found['desc'] or found['levels']):
                    info = found
                    break
                info = info or found
            i = self.d.find(pat, i + 1, DEF_LIMIT)
        baked = BAKED.get(rid)
        if baked and (not info or (len(baked.get('levels', [])), len(baked.get('learn', '')))
                      > (len(info['levels']), len(info.get('learn', '')))):
            info = dict(baked)
        self.cache[rid] = info
        return info

    @staticmethod
    def _richness(info):
        return (len(info['levels']), len(info.get('learn', '')), len(info.get('desc', '')))

    def ability(self, rid, level, base=None):
        info = self.get(rid)
        if base and base != rid:            # a variant with no text of its own
            alt = self.get(base)            # reads better as the base ability
            if alt and (not info or self._richness(alt) > self._richness(info)):
                info = alt
        if not info:
            return ''
        learn = info.get('learn', '')
        if info['levels'] and 1 <= level <= len(info['levels']):
            out = f"{info['name']} — Level {level}\n\n{info['levels'][level - 1]}"
            if learn:                               # the game's learn tooltip: per-level breakdown
                out += '\n\n' + '─' * 30 + '\n' + learn
            return out
        if learn:                                   # no per-level text, but the breakdown covers it
            return f"{info['name']} — Level {level}\n\n{learn}"
        return info['name'] + ('\n\n' + info['desc'] if info['desc'] else '')

    def talent(self, rid):
        info = self.get(rid)
        return f"{info['name']}\n{info['desc']}" if info else ''
