import struct, sys

# DIAGNOSTIC BUILD #9 -- not a real patch. Follow-up to the now-closed
# VirtRange-reattribution series (diag1-8, 6/6 hardware bricks, see
# research/2026-11-12-virtrange-reattribution-closed.md) and the entry-2
# dead-space investigation (research/2026-11-12-entry2-literal-table-
# re-examined.md, confirmed live in all 6 shipped firmware versions).
#
# Every prior diagnostic changed a VirtRange entry's `present` field
# (dw1) from 0 to 1 -- converting an anonymous, unclaimed-looking entry
# into a real module link. All six that did this bricked. The leading
# explanation (INTEGRITY RTOS Address Spaces are fixed at build time; an
# anonymous entry's descriptor has no real MMU page-table backing, so
# flipping `present` makes the kernel try to use a mapping that was
# never built) is about *presence*, not *permission*. This build tests
# the other half of that theory directly: does an ALREADY-present entry's
# `rights` field (dw2: 5=executable, 7=data) also have fixed, build-time
# MMU backing that can't be changed -- or is only *presence* fixed, with
# permission bits free to change on an already-mapped region?
#
# This build picks an existing, already-present (dw1=1), data (dw2=7)
# VirtRange entry and flips ONLY its rights field to 5 (executable),
# in place. `present`, `rbase`, `rsize`, `mod_id`, and the entry's actual
# content are all left completely untouched -- the only bit that changes
# anywhere in the file is dw2's low byte (7 -> 5). No new VirtRange
# entry, no .secinfo change, no array relocation, no content byte
# touched. This is the single most narrowly-isolated variable this
# project has tested yet.
#
# Entry selection: the first present=1, rights=7 (data), rsize=0x1000
# VirtRange entry found by index order (there are 4 such entries;
# picking the first, lowest-index one arbitrarily -- the specific entry
# shouldn't matter for what this tests, since nothing about its content
# is touched).
#
# How to read the result:
# - If this bricks with 270: permission bits are ALSO fixed at build
#   time for an already-present entry, not just presence itself. This
#   would mean the INTEGRITY Address Space model enforces the *entire*
#   MEM_RANGE descriptor (presence AND permission) as immutable once
#   built, closing off "reuse an existing module's slot with different
#   permissions" as a mechanism too -- on top of the already-closed
#   "create a new present link" and "existing module space is free"
#   findings.
# - If this boots fine: presence is the only build-time-fixed property;
#   permission bits on an already-mapped region can be changed freely.
#   This wouldn't by itself reopen a placement option (no present=1
#   module has been shown to have free space large enough for the fan
#   closure -- see the entry-2 investigation), but it would meaningfully
#   narrow what "Address Space fixed at build time" actually means at
#   the kernel level, which matters for interpreting any future finding.
#
# usage: python3 build_diag9.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1-8, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1-8)
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
# 1. read-only lookups
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x} "
      f"(UNTOUCHED -- array does not move, count stays 63)")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

VR_ENTRY_SIZE = 0x20

# ---------------------------------------------------------------------------
# 2. find the target entry fresh -- first (lowest-index) present=1,
#    rights=7 (data), rsize=0x1000 entry. Not hardcoded; re-derived and
#    asserted every build, same discipline as every prior diagnostic.
# ---------------------------------------------------------------------------
target_idx = None
for vr_i in range(63):
    dw1, dw2, rbase, rsize, mod_id, d6, d7, d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    if dw1 == 1 and dw2 == 7 and rsize == 0x1000:
        target_idx = vr_i
        break
assert target_idx is not None, "no present=1, rights=7, rsize=0x1000 VirtRange entry found"

t_dw1, t_dw2, t_rbase, t_rsize, t_mod_id, t_dw6, t_dw7, t_dw8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, target_idx * VR_ENTRY_SIZE)
assert t_dw1 == 1 and t_dw2 == 7, ("target entry is not present=1/rights=7 as expected", t_dw1, t_dw2)
print(f"target entry {target_idx}: present={t_dw1} rights={t_dw2} rbase=0x{t_rbase:x} "
      f"rsize=0x{t_rsize:x} mod_id=0x{t_mod_id:x}")

# ---------------------------------------------------------------------------
# 3. THE ONLY change in this entire build: flip entry {target_idx}'s
#    rights field (dw2) from 7 (data) to 5 (executable), in place.
#    present, rbase, rsize, mod_id: all UNCHANGED. No content byte
#    touched anywhere. No new .secinfo entry, no array relocation, no
#    count change.
# ---------------------------------------------------------------------------
entry_file_off = existing_vr_off + target_idx * VR_ENTRY_SIZE
cur_dw2 = struct.unpack_from('<I', data, entry_file_off + 4)[0]
assert cur_dw2 == 7
struct.pack_into('<I', data, entry_file_off + 4, 5)
print(f"patched entry {target_idx} rights field @0x{entry_file_off+4:x}: 7 (data) -> 5 (executable)")
print("present/rbase/rsize/mod_id: UNCHANGED")
print("entry's actual content bytes: UNTOUCHED")
print(".secinfo: UNTOUCHED -- no new entry")
print("TaskInfo.virt_space / virt_space_size: UNTOUCHED -- array does not move, count stays 63")

# ---------------------------------------------------------------------------
# 4. callsite: NOT TOUCHED (same as every prior diagnostic) -- content-
#    blind structural test, nothing can ever branch into this entry
#    differently than stock firmware already could (or couldn't).
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 5. no insertion at all -- the file is otherwise byte-for-byte identical
#    to stock 2.80 (plus the sig-bypass from step 0). No e_shoff/e_shnum
#    changes, no new section.
# ---------------------------------------------------------------------------
open(OUT_PATH, 'wb').write(data)
print(f"\nWrote {OUT_PATH} ({len(data)} bytes, same size as input -- no insertion, no growth)")
