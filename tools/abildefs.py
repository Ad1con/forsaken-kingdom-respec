"""List ability definitions (id, base, name) from the object table at the
front of a .w3z payload. Records look like: id, u64 0, baseId, art paths...,
name. Only ids matching the talent / hero-ability patterns are printed."""
import sys, re

BACKSLASH = bytes([92])

d = open(sys.argv[1], 'rb').read()[:0x300000]
want = re.compile(rb'[AGILU]T[1-6][abc]|A[UH][a-z0-9][a-z0-9]')
out = {}
for m in re.finditer(rb'(....)\x00\x00\x00\x00\x00\x00\x00\x00(....)', d):
    rid = m.group(1)[::-1]; base = m.group(2)[::-1]
    if not want.fullmatch(rid):
        continue
    tail = d[m.end():m.end() + 0x400]
    strs = re.findall(rb'[\x20-\x7e]{3,}', tail)
    name = next((s.decode() for s in strs
                 if BACKSLASH not in s
                 and not s.endswith((b'.blp', b'.mdl'))
                 and not s.startswith(b'|')), '?')
    out.setdefault(rid.decode(), (base.decode(), name, m.start()))
for rid, (base, name, off) in sorted(out.items()):
    print(f'{rid}  base={base}  {name!r:40}  @{off:#x}')
