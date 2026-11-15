import struct, sys

# DIAGNOSTIC BUILD #4 -- not a real patch. Follow-up to
# patches/280-diag2-secinfo-only-growth (BOOTED FINE -- cleared .secinfo
# list growth, 577->578, as a cause on its own) and
# patches/280-diag3-shrink-only (BOOTED FINE -- cleared shrinking the
# pre-existing last anonymous VirtRange entry's rsize in place, as a cause
# on its own).
#
# With diag2 and diag3 both clean, the fault is narrowed to what's left of
# diag1's VirtRange-side change:
#   (b1) relocating the 63-entry VirtRange array out of its original
#        location inside .boottable into a brand-new, freshly-appended ELF
#        section (required because the original array has no room to grow
#        in place once a 64th entry is added)
#   (b2) bumping Health TaskInfo.virt_space_size 63 -> 64
#   (b3) appending a new, real 64th VirtRange entry
#
# This build tests (b1) ALONE, as minimally as possible: it copies the
# existing 63 VirtRange entries BYTE-FOR-BYTE UNCHANGED (no shrink, no new
# entry) into a new section appended to the file, and repoints
# TaskInfo.virt_space (the pointer) at the new location. Nothing else
# changes:
# - Health TaskInfo.virt_space_size stays 63 (byte-identical, untouched)
# - no new VirtRange entry is added -- the copied array is exactly the
#   same 63 entries, same bytes, same order
# - no new `.secinfo` entry is added (diag2 already cleared .secinfo
#   growth as a cause, so this build doesn't re-exercise it)
# - the callsite `bl` is untouched
# - the ONLY field touched in TaskInfo is the virt_space pointer itself
#
# If THIS bricks with 270: merely moving the VirtRange array's storage
# location -- independent of entry count or content -- is sufficient on
# its own. That would point at something that only works when
# TaskInfo.virt_space resolves through the original static .boottable
# mapping (e.g. a boot-time path that computes the table's file/physical
# location structurally from .boottable rather than through the same
# resolution used for other relocatable regions), rather than at the new,
# dynamically-appended section.
# If THIS boots fine: relocation itself is safe, and the fault is
# isolated to (b2) and/or (b3) -- bumping virt_space_size to 64 and/or
# the new 64th entry's presence/content. The next diagnostic would test
# bumping the count to 64 with a new entry that's a harmless duplicate of
# an existing one, vs. a genuinely new entry claiming new address space.
#
# usage: python3 build_diag4.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1/2/3, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1/diag2/diag3)
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
# 1. read-only lookups (identical derivation to v4/diag1/diag2/diag3)
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
# 2. the ONLY change in this build: copy the 63 existing VirtRange entries,
#    BYTE-FOR-BYTE UNCHANGED, into a brand-new section appended to the
#    file, and repoint TaskInfo.virt_space at the new location. No new
#    entry, no count change, no .secinfo entry, no callsite change.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000

new_section_content = existing_vr_bytes  # byte-for-byte identical copy, nothing added
new_section_size = len(new_section_content)
assert new_section_size == 63*0x20
new_virtrange_vaddr = NEW_PHYS_BASE  # array sits at the very start of the new section

print(f"new section (relocated VirtRange array ONLY, byte-identical copy): "
      f"size=0x{new_section_size:x} ({new_section_size} bytes) @ vaddr 0x{new_virtrange_vaddr:x}")

# ---------------------------------------------------------------------------
# 3. callsite: NOT TOUCHED (same as diag1/diag2) -- irrelevant to this test,
#    kept untouched for consistency with every prior diagnostic.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 4. perform the single insertion (identical mechanics to v4/diag1/diag2) --
#    the ONLY global registration field touched is VIRT_SPACE_FOFF itself.
#    VIRT_SPACE_SIZE_FOFF, .secinfo, and the callsite are all left exactly
#    as they are in stock 2.80.
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
print(f"virt_space pointer: 0x{virt_space:x} (in .boottable) -> 0x{new_virtrange_vaddr:x} (new section)")
print("Health TaskInfo.virt_space_size: unchanged (still 63); .secinfo: unchanged; callsite: unchanged")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
