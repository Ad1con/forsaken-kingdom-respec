"""StoreUnit hero records in the game cache (Campaigns.w3v, and the copy the
game embeds in every .w3z).

record = name\\0, 4cc unitType, u32 nSlots, nSlots x {4cc, u32, u32},
         then a 226-byte tail:
           +52   4 x {4cc base, 4cc variant, u32 level}   Q/W/E/R
           +154  6 x {4cc talent, u32, u32}                picks, in pick order
4ccs are stored byte-reversed.
"""
import struct

TAIL = 226
SLOTS_AT = 52
TALENTS_AT = 154


def rev(s):
    return s.encode('latin1')[::-1]


def fcc(b):
    return b[::-1].decode('latin1') if any(b) else None


class HeroRecord:
    def __init__(self, d, off):
        name_end = d.index(b'\x00', off)
        self.name = d[off:name_end].decode('latin1')
        p = name_end + 1
        self.unit_type = fcc(d[p:p + 4])
        n = struct.unpack_from('<I', d, p + 4)[0]
        self.tail = p + 8 + 12 * n
        if self.tail + TAIL > len(d):
            raise ValueError('truncated hero record')

    def slot_off(self, slot):
        return self.tail + SLOTS_AT + 12 * slot

    def talent_offs(self, d):
        """{talent id: offset of its entry}"""
        out = {}
        for i in range(6):
            p = self.tail + TALENTS_AT + 12 * i
            t = fcc(d[p:p + 4])
            if t:
                out[t] = p
        return out


def find_record(d, key):
    """Last record stored under `key` (e.g. b'TransitionAnya'), or None."""
    i = d.rfind(b'\x00' + key + b'\x00')      # whole name only: 'Garek' must not match 'TransitionGarek'
    return HeroRecord(d, i + 1) if i != -1 else None
