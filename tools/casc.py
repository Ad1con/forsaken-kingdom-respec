"""Minimal reader for the local CASC store of Warcraft III: Reforged.

    casc.py list  [substring]          list file paths in the store
    casc.py get   <path> <out>          extract one file

Local store layout: Data/config/<build config> names the root and encoding
files; Data/data/*.idx map 9-byte encoding keys to (archive, offset, size);
Data/data/data.NNN hold BLTE-encoded blobs behind a 30-byte header; the root
is a text listing of 'path|content key' lines; encoding maps content keys
to encoding keys.
"""
import glob
import os
import struct
import sys
import zlib

GAME = r'C:\Program Files (x86)\Warcraft III'


def be(b):
    return int.from_bytes(b, 'big')


class Store:
    def __init__(self, game=GAME):
        self.data_dir = os.path.join(game, 'Data', 'data')
        self._archives = {}
        self.build = self._build_config(game)
        self.index = self._load_indexes()
        self.encoding = self._load_encoding()
        self.files = {}
        root_ekey = self.encoding[bytes.fromhex(self.build['root'].split()[0])]
        self._load_root(self.blte(self.read_ekey(root_ekey)))

    # ---------------------------------------------------------------- config
    def _build_config(self, game):
        info = open(os.path.join(game, '.build.info'), encoding='utf-8').read().splitlines()
        cols = [c.split('!')[0] for c in info[0].split('|')]
        row = dict(zip(cols, info[1].split('|')))
        key = row['Build Key']
        text = open(os.path.join(game, 'Data', 'config', key[:2], key[2:4], key), encoding='utf-8').read()
        cfg = {}
        for line in text.splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
        return cfg

    # ---------------------------------------------------------------- indexes
    def _load_indexes(self):
        newest = {}
        for p in glob.glob(os.path.join(self.data_dir, '*.idx')):
            name = os.path.basename(p)
            bucket, ver = int(name[:2], 16), int(name[2:10], 16)
            if bucket not in newest or ver > newest[bucket][0]:
                newest[bucket] = (ver, p)
        index = {}
        for bucket, (_, p) in newest.items():
            d = open(p, 'rb').read()
            hdr_size = struct.unpack_from('<I', d, 0)[0]
            ver, bidx, extra, span_size, span_off, ekey_len, off_bits = struct.unpack_from('<HBBBBBB', d, 8)
            assert ver == 7 and ekey_len == 9 and span_off == 5 and span_size == 4, (p, ver, ekey_len)
            pos = (8 + hdr_size + 15) & ~15
            entries_size = struct.unpack_from('<I', d, pos)[0]
            pos += 8
            end = pos + entries_size
            esize = ekey_len + span_off + span_size
            while pos + esize <= end:
                ekey = d[pos:pos + 9]
                packed = be(d[pos + 9:pos + 14])
                size = struct.unpack_from('<I', d, pos + 14)[0]
                if any(ekey):
                    index[ekey] = (packed >> off_bits, packed & ((1 << off_bits) - 1), size)
                pos += esize
        return index

    def read_ekey(self, ekey):
        """Raw BLTE blob for a 9- or 16-byte encoding key."""
        arch, off, size = self.index[bytes(ekey[:9])]
        f = self._archives.get(arch)
        if f is None:
            f = self._archives[arch] = open(os.path.join(self.data_dir, f'data.{arch:03d}'), 'rb')
        f.seek(off + 30)             # 16-byte reversed key, u32 size, u16 flags, 2 x u32 checksum
        return f.read(size - 30)

    # ---------------------------------------------------------------- BLTE
    @staticmethod
    def blte(d):
        assert d[:4] == b'BLTE', 'not BLTE'
        hsize = be(d[4:8])
        out = bytearray()
        if hsize == 0:
            frames = [(None, None, d[8:])]
        else:
            n = be(d[9:12])
            frames, pos, data_pos = [], 12, hsize
            for _ in range(n):
                csize, dsize = be(d[pos:pos + 4]), be(d[pos + 4:pos + 8])
                frames.append((csize, dsize, d[data_pos:data_pos + csize]))
                pos += 24
                data_pos += csize
        for csize, dsize, frame in frames:
            kind, body = frame[:1], frame[1:]
            if kind == b'N':
                out += body
            elif kind == b'Z':
                out += zlib.decompress(body)
            elif kind == b'F':
                out += Store.blte(body)
            else:
                raise ValueError(f'unsupported BLTE frame {kind!r}')
        return bytes(out)

    @staticmethod
    def blte_peek(d, n=16):
        """First n decoded bytes of a BLTE blob without decoding it all."""
        if d[:4] != b'BLTE':
            return b''
        hsize = be(d[4:8])
        frame = d[8:8 + 4096] if hsize == 0 else d[hsize:hsize + min(4096, be(d[12:16]))]
        kind, body = frame[:1], frame[1:]
        if kind == b'N':
            return body[:n]
        if kind == b'Z':
            try:
                return zlib.decompressobj().decompress(body, n)
            except zlib.error:
                return b''
        return b''

    # ---------------------------------------------------------------- encoding
    def _load_encoding(self):
        ekey = bytes.fromhex(self.build['encoding'].split()[1])
        d = self.blte(self.read_ekey(ekey))
        assert d[:2] == b'EN'
        ck_size, ek_size = d[3], d[4]
        ck_page_kb = be(d[5:7])
        ck_pages = be(d[9:13])
        espec_size = be(d[18:22])
        pos = 22 + espec_size + ck_pages * (ck_size + 16)
        table = {}
        page_len = ck_page_kb * 1024
        for _ in range(ck_pages):
            page = d[pos:pos + page_len]
            q = 0
            while q + 6 <= len(page):
                nkeys = page[q]
                if nkeys == 0:
                    break
                ckey = page[q + 6:q + 6 + ck_size]
                table[ckey] = page[q + 6 + ck_size:q + 6 + ck_size + ek_size]
                q += 6 + ck_size + nkeys * ek_size
            pos += page_len
        return table

    # ---------------------------------------------------------------- root
    def _load_root(self, d):
        """Text root: one 'path|content md5|flags|' line per file."""
        for line in d.decode('utf-8', 'replace').splitlines():
            parts = line.split('|')
            if len(parts) < 2 or len(parts[1]) != 32:
                continue
            ckey = bytes.fromhex(parts[1])
            ekey = self.encoding.get(ckey)
            self.files[parts[0]] = (ekey, ekey is not None and ekey[:9] in self.index)

    def get(self, path):
        ekey, local = self.files[path]
        if not local:
            raise KeyError(f'{path} is not in the local store')
        return self.blte(self.read_ekey(ekey))


if __name__ == '__main__':
    s = Store()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if cmd == 'list':
        needle = sys.argv[2].lower() if len(sys.argv) > 2 else ''
        for p in sorted(s.files):
            if needle in p.lower():
                print(p, '' if s.files[p][1] else '(not local)')
    elif cmd == 'get':
        open(sys.argv[3], 'wb').write(s.get(sys.argv[2]))
        print('wrote', sys.argv[3])
