import struct, sys

# DIAGNOSTIC BUILD #5 -- not a real patch. Follow-up to
# patches/280-diag4-relocate-virtrange-only (BRICKED with 270 -- proved
# that relocating the VirtRange array out of .boottable into a
# newly-appended section is sufficient on its own to brick, independent
# of entry count or content).
#
# After diag4 bricked, research/2026-11-06-kernel-re-methodology-and-
# pitfalls.md was consulted: it documents a REAL, Ghidra-decompiled
# boot-time/flash-validation routine (FUN_2000b16c) that does, for every
# task:
#
#   virtspace_ptr = relocate(TaskInfo + 8)
#   if (image_end < virtspace_ptr + virt_space_size * 0x20) goto fail;
#
# This is a STRUCTURAL fit-inside-the-loaded-image check on the pointer
# VALUE itself, independent of what's actually stored at that address --
# exactly the kind of check that would reject ANY relocation to an
# address beyond the image's real extent, regardless of entry count or
# content, and would explain diag4's result on its own.
#
# Measuring the REAL, unmodified 2.80 elf.bin directly:
#   - the highest (sh_addr + sh_size) across every real section is
#     0x3e22b18 (~62.14 MB) -- the ".secinfo" section itself, the
#     highest-addressed thing in the genuine firmware.
#   - v1 through v4, diag1, and diag4 all anchored their newly-appended
#     section at NEW_PHYS_BASE = 0x4000000 (exactly 64 MB) -- a round
#     number chosen only because it was "past everything currently
#     used" (checked against max_existing_secinfo_end as a LOWER bound),
#     never checked against any UPPER bound. 0x4000000 sits ~1.86 MB
#     *beyond* the real image's highest address.
#   - every build that relocated TaskInfo.virt_space into that
#     0x4000000-anchored section bricked (v1-v4, diag1, diag4). Every
#     build that left virt_space untouched (diag2, diag3) booted fine.
#     This is exactly the pattern FUN_2000b16c's fit-check predicts.
#
# This build is diag4's EXACT test (relocate the unchanged 63-entry
# VirtRange array, byte-for-byte identical, into a new section; count,
# content, .secinfo, and callsite all untouched) with ONE change: the
# new section is anchored immediately after the REAL end of the existing
# image (0x3e22b18, 4-byte aligned) instead of the arbitrary 0x4000000.
#
# If THIS boots fine: the image_end/address-choice hypothesis is
# confirmed. The actual root cause of every 270 brick in this entire
# investigation (v1, v2, v3, v4, diag1, diag4) was simply inserting new
# data at an address beyond the image's real extent -- not any
# relocation-math error, not an Address-Space ceiling, not entry count.
# The real fan-restore patch would need to anchor its new section
# tightly against the real image end (not a round placeholder number).
# If THIS still bricks: relocation out of .boottable is broken for a
# different/additional reason, and FUN_2000b16c's fit-check is not the
# (or not the only) culprit.
#
# usage: python3 build_diag5.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1/2/3/4, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1/diag2/diag3/diag4)
# ---------------------------------------------------------------------------
e_shoff = struct.unpack_from('<I', data, 0x20)[0]
e_shentsize = struct.unpack_from('<H', data, 0x2e)[0]
e_shnum = struct.unpack_from('<H', data, 0x30)[0]
shstrtab_idx = struct.unpack_from('<H', data, 0x32)[0]
assert e_shentsize == 40

SHDR_FIELDS = ['sh_name','sh_type','sh_flags','sh_addr','sh_offset','sh_size','sh_link','sh_info','sh_addralign','sh_entsize']

def read_shdr(i):
    off = e_shoff + i*e_shentsize
    return dict(zip(SHDR_FIELDS, struct.unpack_from('<IIIIIIIIII', data, off)))

shdrs = [read_shdr(i) for i in range(e_shnum)]
shstrtab_off = shdrs[shstrtab_idx]['sh_offset']

def name_of(i):
    n = shdrs[i]['sh_name']
    end = data.index(b'\x00', shstrtab_off+n)
    return data[shstrtab_off+n:end].decode('latin1')

boottable_idx = next(i for i in range(e_shnum) if name_of(i) == '.boottable')
boottable = shdrs[boottable_idx]

# ---------------------------------------------------------------------------
# 1. read-only lookups (identical derivation to v4/diag1/diag2/diag3/diag4)
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} (will stay 63, untouched) "
      f"virt_space=0x{virt_space:x} (will be REPOINTED, value only)")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytes(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

VR_ENTRY_SIZE = 0x20
CEILING = 0x2000000
last_entry_end = 0
for vr_i in range(63):
    _d1, _d2, vr_rbase, vr_rsize, _mid, _d6, _d7, _d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    end = vr_rbase + vr_rsize
    last_entry_end = max(last_entry_end, end)
assert last_entry_end == CEILING, \
    ("the highest-ending existing VirtRange entry does not end exactly at the confirmed "
     "0x2000000 per-task ceiling", hex(last_entry_end))
print(f"existing 63-entry VirtRange table: verified intact, reaches exactly ceiling 0x{CEILING:x}")

# ---------------------------------------------------------------------------
# 2. THE ONE CHANGE FROM diag4: anchor the new section immediately after
#    the REAL end of the existing image (max sh_addr+sh_size across every
#    real section with a nonzero address), 4-byte aligned -- instead of
#    the arbitrary round number 0x4000000 that diag4 (and v1-v4, diag1)
#    used, which sits ~1.86MB beyond the real image extent.
# ---------------------------------------------------------------------------
real_image_end = 0
for s in shdrs:
    if s['sh_addr'] == 0:
        continue
    real_image_end = max(real_image_end, s['sh_addr'] + s['sh_size'])

NEW_PHYS_BASE = (real_image_end + 3) & ~3  # 4-byte align, round UP (never down)
assert NEW_PHYS_BASE >= real_image_end
print(f"real image end (max sh_addr+sh_size across all real sections) = 0x{real_image_end:x}")
print(f"NEW_PHYS_BASE (tight, 4-byte aligned, immediately past real image end) = 0x{NEW_PHYS_BASE:x} "
      f"(vs. the arbitrary 0x4000000 used by every prior relocating build)")

new_section_content = existing_vr_bytes  # byte-for-byte identical copy, nothing added
new_section_size = len(new_section_content)
assert new_section_size == 63*0x20
new_virtrange_vaddr = NEW_PHYS_BASE  # array sits at the very start of the new section

print(f"new section (relocated VirtRange array ONLY, byte-identical copy): "
      f"size=0x{new_section_size:x} ({new_section_size} bytes) @ vaddr 0x{new_virtrange_vaddr:x}")

# ---------------------------------------------------------------------------
# 3. callsite: NOT TOUCHED (same as diag1/diag2/diag4) -- irrelevant to
#    this test, kept untouched for consistency with every prior diagnostic.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 4. perform the single insertion (identical mechanics to v4/diag1/diag2/
#    diag4) -- the ONLY global registration field touched is
#    VIRT_SPACE_FOFF itself. VIRT_SPACE_SIZE_FOFF, .secinfo, and the
#    callsite are all left exactly as they are in stock 2.80.
# ---------------------------------------------------------------------------
insertion_offset = e_shoff
maxend = max(s['sh_offset'] + s['sh_size'] for s in shdrs if s['sh_type'] != 8)
assert insertion_offset >= maxend

new_data = bytearray(data[:insertion_offset]) + bytearray(new_section_content) + bytearray(data[insertion_offset:])
delta = len(new_section_content)

struct.pack_into('<I', new_data, VIRT_SPACE_FOFF, new_virtrange_vaddr)
# NOTE: VIRT_SPACE_SIZE_FOFF (stays 63), .secinfo, and the callsite are all
# intentionally NEVER WRITTEN in this script.

new_e_shoff = e_shoff + delta
struct.pack_into('<I', new_data, 0x20, new_e_shoff)

new_shdr = struct.pack('<IIIIIIIIII',
    0, 1, 6, NEW_PHYS_BASE, insertion_offset, new_section_size, 0, 0, 0, 0)

new_shdr_table_off = new_e_shoff + e_shnum*e_shentsize
new_data[new_shdr_table_off:new_shdr_table_off+40] = new_shdr
new_e_shnum = e_shnum + 1
struct.pack_into('<H', new_data, 0x30, new_e_shnum)

print(f"\ne_shoff: 0x{e_shoff:x} -> 0x{new_e_shoff:x}")
print(f"e_shnum: {e_shnum} -> {new_e_shnum}")
print(f"virt_space pointer: 0x{virt_space:x} (in .boottable) -> 0x{new_virtrange_vaddr:x} (new section, tight)")
print("Health TaskInfo.virt_space_size: unchanged (still 63); .secinfo: unchanged; callsite: unchanged")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
