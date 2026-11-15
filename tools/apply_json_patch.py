#!/usr/bin/env python3
"""Apply a util/patch.py-style JSON byte-patch file to a binary.

Supports only plain hex prev_data/patch entries (no "file"/keystone-assembled
patches) -- that covers every sig-bypass patch this project uses
(patches/280/patch_bootloader.json, patches/280/patch_kernel.json). If a
patch needs keystone assembly, use util/patch.py instead.

usage: apply_json_patch.py <input.bin> <patch.json> <output.bin>
"""
import sys
import json


def main():
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} <input.bin> <patch.json> <output.bin>")
        sys.exit(1)
    in_path, patch_path, out_path = sys.argv[1:4]

    data = bytearray(open(in_path, 'rb').read())
    patches = json.load(open(patch_path))

    for patch in patches:
        if 'file' in patch:
            raise NotImplementedError(
                f"patch {patch.get('remark')!r} uses a keystone-assembled 'file' patch; "
                "this lightweight applier only supports plain hex patches. Use util/patch.py instead."
            )
        offset = int(patch['offset'], 0)
        size = patch['size']
        prev = bytes.fromhex(patch['prev_data'])
        new = bytes.fromhex(patch['patch'])
        assert len(prev) == size and len(new) == size, \
            (patch.get('remark'), len(prev), len(new), size)

        current = bytes(data[offset:offset + size])
        if current != prev:
            raise AssertionError(
                f"patch {patch.get('remark')!r} @0x{offset:x}: "
                f"expected {prev.hex()}, found {current.hex()}"
            )
        data[offset:offset + size] = new
        print(f"applied: {patch.get('remark')!r} @0x{offset:x}: {prev.hex()} -> {new.hex()}")

    open(out_path, 'wb').write(data)
    print(f"wrote {out_path} ({len(data)} bytes)")


if __name__ == '__main__':
    main()
