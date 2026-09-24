"""Unpack / repack the .w3z and .w3v container from the command line.

    w3z.py unpack <in.w3z> <out.bin>
    w3z.py pack   <template.w3z> <in.bin> <out.w3z>

`pack` takes the header and block size from the template, so repacking an
unmodified payload reproduces the original file byte for byte. The format
itself is documented in fkrespec/container.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fkrespec import container            # noqa: E402


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    if argv[0] == 'unpack':
        _header, payload, block = container.unpack(argv[1])
        with open(argv[2], 'wb') as f:
            f.write(payload)
        print(f'{len(payload)} payload bytes ({block}-byte blocks) -> {argv[2]}')
    elif argv[0] == 'pack' and len(argv) >= 4:
        header, _payload, block = container.unpack(argv[1])
        with open(argv[2], 'rb') as f:
            payload = f.read()
        out = container.pack(header, payload, block)
        with open(argv[3], 'wb') as f:
            f.write(out)
        print(f'{len(out)} bytes -> {argv[3]}')
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
