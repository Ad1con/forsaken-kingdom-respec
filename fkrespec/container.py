"""The container shared by .w3z saves, .w3v caches and .w3g replays.

  0x00  "Warcraft III recorded game\\x1a\\0"
  0x1c  u32 header size (0x44)    0x20  u32 file size    0x24  u32 header version
  0x28  u32 payload size          0x2c  u32 block count
  0x30  "PX3W"  u32 version  u32 build  u32 flags  u32 crc32(header, crc zeroed)
  0x44  blocks: u32 csize, u32 dsize, u32 checksum, zlib data (level 1, Z_SYNC_FLUSH)

block checksum = fold(crc32(12-byte header, checksum zeroed)) | fold(crc32(data)) << 16
fold(c) = (c ^ c >> 16) & 0xffff.  Payload is zero-padded to whole blocks.
"""
import re
import struct
import zlib

MAGIC = b'Warcraft III recorded game\x1a\x00'
SYNC = bytes([0, 0, 0, 255, 255])   # empty stored block that Z_SYNC_FLUSH emits

# (version, build) pairs the editor has been tested against
KNOWN_BUILDS = {(0x27d8, 0x1b58): '3.0.0.24268'}


class BadContainer(Exception):
    pass


def fold(c):
    return (c ^ (c >> 16)) & 0xFFFF


def unpack(path):
    """Return (header, payload as a bytearray, block size).

    Block checksums are always verified: it costs about 2% of the read and is
    the only thing that catches a corrupt block whose bytes still inflate.
    """
    with open(path, 'rb') as f:
        d = f.read()
    if d[:28] != MAGIC:
        raise BadContainer('not a Warcraft III save')
    hdr_size, _total, _ver, payload_len, nblocks = struct.unpack_from('<IIIII', d, 28)
    header = d[:hdr_size]
    block = struct.unpack_from('<I', d, hdr_size + 4)[0]
    out = bytearray(nblocks * block)          # one allocation instead of growing
    pos, at = hdr_size, 0
    for i in range(nblocks):
        csize, dsize, chk = struct.unpack_from('<III', d, pos)
        blob = d[pos + 12:pos + 12 + csize]
        want = fold(zlib.crc32(struct.pack('<III', csize, dsize, 0))) | (fold(zlib.crc32(blob)) << 16)
        if want != chk:
            raise BadContainer(f'block {i} checksum mismatch')
        try:
            dec = zlib.decompressobj().decompress(blob)
        except zlib.error as ex:
            raise BadContainer(f'block {i} will not decompress ({ex})')
        out[at:at + len(dec)] = dec
        at += len(dec)
        pos += 12 + csize
    del out[payload_len:]
    return header, out, block


def pack(header, payload, block, progress=None):
    """`progress(done, total)` is called per block, for a caller showing a bar."""
    nblocks = (len(payload) + block - 1) // block
    body = bytearray()
    for i in range(nblocks):
        if progress is not None:
            progress(i, nblocks)
        chunk = payload[i * block:(i + 1) * block]
        chunk = chunk + b'\0' * (block - len(chunk))
        co = zlib.compressobj(1)
        blob = co.compress(chunk) + co.flush(zlib.Z_SYNC_FLUSH)
        if blob.endswith(SYNC + SYNC):     # Python's flush() can double the sync block
            blob = blob[:-len(SYNC)]       # when output lands on its buffer boundary
        hdr0 = struct.pack('<III', len(blob), block, 0)
        chk = fold(zlib.crc32(hdr0)) | (fold(zlib.crc32(blob)) << 16)
        body += struct.pack('<III', len(blob), block, chk) + blob
    h = bytearray(header)
    struct.pack_into('<III', h, 0x20, len(h) + len(body), 1, len(payload))
    struct.pack_into('<I', h, 0x2c, nblocks)
    struct.pack_into('<I', h, 0x40, 0)
    struct.pack_into('<I', h, 0x40, zlib.crc32(bytes(h)) & 0xFFFFFFFF)
    return bytes(h) + bytes(body)


def map_name(path):
    """The map a save belongs to (e.g. 'UndeadRE01'), read from the first block only."""
    with open(path, 'rb') as f:
        d = f.read(0x44 + 12 + 8192)
    if d[:28] != MAGIC:
        return None
    hdr_size = struct.unpack_from('<I', d, 28)[0]
    try:
        head = zlib.decompressobj().decompress(d[hdr_size + 12:], 256)
    except zlib.error:
        return None
    m = re.search(rb'[A-Za-z]+RE\d\d\w*', head)
    return m.group().decode() if m else None


def game_build(header):
    """(version, build) from the sub-header, and the tested-version label or None."""
    ver, build = struct.unpack_from('<II', header, 0x34)
    return (ver, build), KNOWN_BUILDS.get((ver, build))
