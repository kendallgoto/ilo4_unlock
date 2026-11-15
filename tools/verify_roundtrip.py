"""Full compression round-trip verification for a repacked iLO4 .toflash.

Python 2 (runs inside the python:2.7 toolbox container, since it imports
ilo4lib). Decompresses the ELF and kernel back out of the final .toflash via
ilo4lib.decompress_all() -- never decompress() directly, see
research/2026-11-06-kernel-re-methodology-and-pitfalls.md -- and compares
byte-for-byte against the patched inputs that went into the repack. The
bootloader is stored raw, so it's a direct slice comparison at
firmware.map['BOOTLOADER'] - firmware.map['BOOTLOADER_HDR'].

Expects, in <workdir>: firmware.map, firmware.bin.backdoored.toflash,
elf.bin, kernel_main.bin, bootloader.bin (the same four inputs passed to
ilo4_repack.py, plus its output).

usage (inside the python:2.7 container, toolbox mounted at /toolbox):
    python verify_roundtrip.py <workdir>
exits 0 if all three checks pass, 1 otherwise.
"""
import json
import sys
import struct

sys.path.insert(0, '/toolbox/scripts/iLO4')
import ilo4lib

workdir = sys.argv[1] if len(sys.argv) > 1 else '/work'

fmap = json.load(open('%s/firmware.map' % workdir))
bh = fmap['BOOTLOADER_HDR']

toflash = open('%s/firmware.bin.backdoored.toflash' % workdir, 'rb').read()
elf_patched = open('%s/elf.bin' % workdir, 'rb').read()
kernel_patched = open('%s/kernel_main.bin' % workdir, 'rb').read()
bootloader_patched = open('%s/bootloader.bin' % workdir, 'rb').read()

elf_off = fmap['ELF'] - bh
kernel_off = fmap['KERNEL_MAIN'] - bh

elf_comp_size = struct.unpack('<L', toflash[elf_off:elf_off + 4])[0]
kernel_comp_size = struct.unpack('<L', toflash[kernel_off:kernel_off + 4])[0]
print("elf_comp_size(from file)=0x%x  kernel_comp_size(from file)=0x%x" % (elf_comp_size, kernel_comp_size))

elf_comp_slice = toflash[elf_off + 4:elf_off + 4 + elf_comp_size]
kernel_comp_slice = toflash[kernel_off + 4:kernel_off + 4 + kernel_comp_size]

ilo4lib.decompress_all(elf_comp_slice, '%s/_elf_decomp.bin' % workdir)
elf_decompressed = open('%s/_elf_decomp.bin' % workdir, 'rb').read()
ilo4lib.decompress_all(kernel_comp_slice, '%s/_kernel_decomp.bin' % workdir)
kernel_decompressed = open('%s/_kernel_decomp.bin' % workdir, 'rb').read()

ok_elf = (elf_decompressed == elf_patched)
ok_kernel = (kernel_decompressed == kernel_patched)
bootloader_foff = fmap['BOOTLOADER'] - bh
bootloader_region = toflash[bootloader_foff:bootloader_foff + len(bootloader_patched)]
ok_bootloader = (bootloader_region == bootloader_patched)

print("ELF roundtrip match:", ok_elf, "(decompressed len=%d vs patched len=%d)" % (len(elf_decompressed), len(elf_patched)))
print("Kernel roundtrip match:", ok_kernel, "(decompressed len=%d vs patched len=%d)" % (len(kernel_decompressed), len(kernel_patched)))
print("Bootloader raw match:", ok_bootloader)

if not (ok_elf and ok_kernel and ok_bootloader):
    sys.exit(1)
