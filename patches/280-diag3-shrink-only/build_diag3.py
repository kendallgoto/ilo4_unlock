import struct, sys

# DIAGNOSTIC BUILD #3 -- not a real patch. Follow-up to
# patches/280-diag1-null-injection (bricked -- confirmed the fault is in
# the structural registration mechanism, not fan-code content/relocation)
# and patches/280-diag2-secinfo-only-growth (BOOTED FINE -- cleared .secinfo
# list growth, 577->578, as a cause on its own).
#
# With diag2 clearing .secinfo growth, the fault is isolated to the
# VirtRange side of diag1's change, which itself bundled TWO things:
#   (a) shrinking the pre-existing LAST anonymous VirtRange entry's rsize
#       field in place (reclaiming its tail)
#   (b) bumping Health TaskInfo.virt_space_size 63 -> 64 and appending a
#       brand-new 64th VirtRange entry (which requires relocating the
#       whole array to a new location, since the existing 63-entry array
#       has no room to grow in place)
#
# This build tests (a) ALONE, in the most minimal way possible: it patches
# ONLY the 4-byte rsize field of the existing last anonymous VirtRange
# entry, in place, at its ORIGINAL file location. Nothing else changes:
# - Health TaskInfo.virt_space_size stays 63 (byte-identical, untouched)
# - VIRT_SPACE_FOFF (the pointer to the VirtRange array) stays untouched,
#   still pointing at the ORIGINAL array location (not relocated)
# - No new ELF section is inserted at all
# - No new `.secinfo` entry is added
# - The callsite `bl` is untouched
# The reclaimed tail space is left completely unregistered -- not claimed
# by anything, not backed by any content. The file does not even grow.
#
# If THIS bricks with 270: merely shrinking that one pre-existing entry's
# size value is sufficient on its own -- independent of the count bump or
# the new entry -- which would point at something validating that specific
# entry's size (a checksum, a cross-reference elsewhere expecting the
# original 0xe0000-ish rsize value).
# If THIS boots fine: the fault is isolated to (b) -- bumping
# virt_space_size to 64 and/or appending the new 64th entry and/or
# relocating the array to a new location.
#
# usage: python3 build_diag3.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1, diag2, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1/diag2)
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
# 1. read-only lookups (identical derivation to v4/diag1/diag2)
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x} (will NOT be touched)")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

VR_ENTRY_SIZE = 0x20
CEILING = 0x2000000
last_entry_idx = None
last_entry_end = 0
for vr_i in range(63):
    _d1, _d2, vr_rbase, vr_rsize, _mid, _d6, _d7, _d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    end = vr_rbase + vr_rsize
    if end > last_entry_end:
        last_entry_end = end
        last_entry_idx = vr_i
assert last_entry_end == CEILING, \
    ("the highest-ending existing VirtRange entry does not end exactly at the confirmed "
     "0x2000000 per-task ceiling", hex(last_entry_end))

last_dw1, last_dw2, last_rbase, last_rsize, last_mod_id, last_dw6, last_dw7, last_dw8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, last_entry_idx * VR_ENTRY_SIZE)
assert last_dw1 == 0 and last_mod_id == 0xffffffff, \
    ("the entry at the ceiling is NOT anonymous as expected", last_dw1, hex(last_mod_id))
print(f"last (anonymous, ceiling-ending) VirtRange entry: idx={last_entry_idx} rbase=0x{last_rbase:x} rsize=0x{last_rsize:x}")

# ---------------------------------------------------------------------------
# 2. the ONLY change in this build: shrink this one entry's rsize field,
#    IN PLACE at its original file offset. Same shrink amount used by
#    v3/v4/diag1 (0xc320 bytes), for apples-to-apples comparison, but the
#    reclaimed space is left completely unregistered -- nothing points at
#    it, nothing is inserted into the file, the file does not grow.
# ---------------------------------------------------------------------------
SHRINK_AMOUNT = 0xc320
new_last_rsize = last_rsize - SHRINK_AMOUNT
assert new_last_rsize > 0x10000

last_entry_file_off = existing_vr_off + last_entry_idx * VR_ENTRY_SIZE + 12  # rsize is dword index 3 (offset 12)
cur = struct.unpack_from('<I', data, last_entry_file_off)[0]
assert cur == last_rsize, (hex(cur), hex(last_rsize))
struct.pack_into('<I', data, last_entry_file_off, new_last_rsize)
print(f"patched last entry's rsize IN PLACE @0x{last_entry_file_off:x}: 0x{last_rsize:x} -> 0x{new_last_rsize:x}")
print("Everything else (TaskInfo, VIRT_SPACE_FOFF, VIRT_SPACE_SIZE_FOFF, .secinfo, callsite, "
      "file size) is UNTOUCHED.")

open(OUT_PATH, 'wb').write(data)
print(f"\nWrote {OUT_PATH} ({len(data)} bytes, same size as input -- no insertion)")
