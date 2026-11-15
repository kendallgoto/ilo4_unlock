import struct, sys

# DIAGNOSTIC BUILD #6 -- not a real patch. Follow-up to
# patches/280-diag4-relocate-virtrange-only and
# patches/280-diag5-relocate-tight-address, which BOTH bricked with the
# identical 270 error. diag4 relocated TaskInfo.virt_space to the
# arbitrary address 0x4000000; diag5 repeated the exact same test but
# anchored the new section tight against the real image boundary
# (0x3e22b18) instead. Both bricked identically, which falsifies the
# "image_end fit-check / address choice" hypothesis from
# research/2026-11-06-kernel-re-methodology-and-pitfalls.md -- the
# relocation itself is the problem, not the specific address chosen.
#
# Taking stock of every diagnostic result so far:
#   - diag2 (append a NEW .secinfo entry, virt_space UNTOUCHED): booted fine
#   - diag3 (shrink the last VirtRange entry's rsize IN PLACE,
#     virt_space UNTOUCHED): booted fine
#   - diag1  (full relocation, count 63->64, new entry, address 0x4000000): BRICKED
#   - diag4  (relocate virt_space only, SAME 63 entries, address 0x4000000): BRICKED
#   - diag5  (relocate virt_space only, SAME 63 entries, tight address): BRICKED
#
# The clean common denominator, replicated across three independent
# builds (diag1, diag4, diag5) with different addresses and different
# amounts of accompanying change: changing TaskInfo.virt_space (the
# POINTER VALUE itself) to anything other than its stock address bricks,
# no matter where the new value points. The array must stay exactly
# where stock 2.80 put it, inside .boottable, at its original address.
#
# This build tests whether an EXISTING VirtRange entry can instead be
# RE-ATTRIBUTED, in place, to reference a brand-new module -- with NO
# relocation of the array at all:
#   - TaskInfo.virt_space is left COMPLETELY UNTOUCHED (still the
#     original address inside .boottable)
#   - TaskInfo.virt_space_size stays 63 (untouched)
#   - the VirtRange array itself DOES NOT MOVE -- it stays at its
#     original file location inside .boottable
#   - the ONLY change to the array: entry 62 (the last, previously
#     anonymous, ceiling-ending entry) has its `dw1` (present), `dw2`
#     (rights), and `mod_id` fields patched IN PLACE, at their original
#     file offsets, from (0, ?, 0xffffffff) [anonymous/free] to
#     (1, 5, <new module's mod_id>) [owned by the new module] -- exactly
#     the convention v1-v4/diag1 used for a brand-new entry, but applied
#     to the EXISTING entry instead of adding a 64th one.
#   - `rbase`/`rsize` for entry 62 are left UNCHANGED (full original
#     range, not shrunk) -- this isolates "can an entry's ownership be
#     reattributed" from "does abandoning part of its range matter"
#     (diag3 already answered the latter: yes, abandoning is safe).
#   - one new `.secinfo` entry is appended (diag2 already proved
#     `.secinfo` growth alone is safe) describing an INERT (zeroed,
#     like diag1), same-size-as-v4 content block, positioned at the top
#     of entry 62's existing range (same NEW_TASK_LOCAL_BASE = CEILING -
#     NEW_TASK_LOCAL_SIZE convention used throughout this project).
#   - the callsite `bl` is left UNTOUCHED, same as diag1/diag2/diag4 --
#     nothing can ever branch into the new region, so this remains a
#     pure structural-registration test, content-blind.
#
# If THIS bricks with 270: re-attributing an EXISTING entry's
# ownership (dw1/dw2/mod_id) is itself unsafe, independent of any
# relocation -- pointing at something that validates entry 62
# specifically, or validates non-anonymous entries differently at boot.
# If THIS boots fine: the VirtRange array can safely describe a new
# module via an existing, unmoved entry -- opening a real path to
# restoring fan without ever touching TaskInfo.virt_space or growing
# the array past 63 entries.
#
# usage: python3 build_diag6.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1-5, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1-5)
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
secinfo_idx = next(i for i in range(e_shnum) if name_of(i) == '.secinfo')
boottable = shdrs[boottable_idx]
secinfo = shdrs[secinfo_idx]

# ---------------------------------------------------------------------------
# 1. read-only lookups
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x} "
      f"(BOTH LEFT COMPLETELY UNTOUCHED -- the array does not move)")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

# .secinfo walk (identical derivation to v4/diag1/diag2) -- needed to
# reconfirm the 577-entry invariant and to derive the mod_id numbering
# convention (SIZE_INITIAL) used by every prior version.
hdata_shdr = shdrs[next(i for i in range(e_shnum) if name_of(i) == '.health.elf.data')]

SECINFO_ENTRY_SIZE = 24
secinfo_lo = secinfo['sh_offset']
secinfo_hi = secinfo['sh_offset'] + secinfo['sh_size']
walk_off = secinfo_lo
hdata_secinfo_index = None
max_existing_secinfo_end = 0
index = 0
while True:
    assert index < 10000
    assert secinfo_lo <= walk_off <= secinfo_hi - SECINFO_ENTRY_SIZE
    next_ptr, name_ptr, text_base_addr, text_size, dw1, dw2 = struct.unpack_from('<IIIIII', data, walk_off)
    if text_base_addr == hdata_shdr['sh_addr']:
        assert hdata_secinfo_index is None
        hdata_secinfo_index = index
    max_existing_secinfo_end = max(max_existing_secinfo_end, text_base_addr + text_size)
    if next_ptr == 0:
        break
    walk_off = secinfo_lo + (next_ptr - secinfo['sh_addr'])
    index += 1
total_existing_secinfo_entries = index + 1

NEW_SECINFO_INDEX = 577
assert total_existing_secinfo_entries == NEW_SECINFO_INDEX
LAST_SECINFO_NEXTPTR_FOFF = walk_off
last_next_ptr_check = struct.unpack_from('<I', data, LAST_SECINFO_NEXTPTR_FOFF)[0]
assert last_next_ptr_check == 0
print(f".secinfo walk: {total_existing_secinfo_entries} existing entries, tail next_ptr field @0x{walk_off:x}")

VR_ENTRY_SIZE = 0x20
HDATA_KNOWN_RSIZE = 0x91000
hdata_vr_mod_id = None
for vr_i in range(63):
    vr_dw1, vr_dw2, vr_rbase, vr_rsize, vr_mod_id, vr_dw6, vr_dw7, vr_dw8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    if vr_rsize == HDATA_KNOWN_RSIZE:
        assert hdata_vr_mod_id is None
        hdata_vr_mod_id = vr_mod_id
assert hdata_vr_mod_id is not None

HDATA_KNOWN_MOD_ID = 0x82
assert hdata_vr_mod_id == HDATA_KNOWN_MOD_ID
SIZE_INITIAL = hdata_vr_mod_id - hdata_secinfo_index
assert SIZE_INITIAL == 49
new_health_mod_id = SIZE_INITIAL + NEW_SECINFO_INDEX
print(f"mod_id convention confirmed: SIZE_INITIAL={SIZE_INITIAL}, new module's mod_id will be {new_health_mod_id}")

# ---------------------------------------------------------------------------
# 2. find the last (anonymous, ceiling-ending) entry -- identical
#    derivation to diag3/diag4/diag5.
# ---------------------------------------------------------------------------
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
print(f"last (anonymous, ceiling-ending) VirtRange entry: idx={last_entry_idx} "
      f"rbase=0x{last_rbase:x} rsize=0x{last_rsize:x} dw1={last_dw1} dw2={last_dw2} mod_id=0x{last_mod_id:x}")

# ---------------------------------------------------------------------------
# 3. THE ONLY VirtRange change in this build: patch entry 62's dw1/dw2/
#    mod_id IN PLACE, at their original file offsets, from
#    (present=0, mod_id=0xffffffff) [anonymous] to
#    (present=1, rights=5, mod_id=new_health_mod_id) [owned by new
#    module]. rbase/rsize are left COMPLETELY UNCHANGED (full original
#    range) -- this isolates re-attribution from range-shrinking.
# ---------------------------------------------------------------------------
NEW_TASK_LOCAL_SIZE = 0xc320  # same size used by v3/v4/diag1 for comparability
stub_block = b'\x00' * NEW_TASK_LOCAL_SIZE  # inert content, same as diag1/diag2 -- callsite untouched, never reached
NEW_TASK_LOCAL_BASE = last_rbase + last_rsize - NEW_TASK_LOCAL_SIZE  # top of entry 62's UNCHANGED range
assert NEW_TASK_LOCAL_BASE >= last_rbase
assert NEW_TASK_LOCAL_BASE + NEW_TASK_LOCAL_SIZE == CEILING
print(f"new module's content will sit at the top of entry 62's existing (unchanged) range: "
      f"0x{NEW_TASK_LOCAL_BASE:x}..0x{CEILING:x}")

entry_62_file_off = existing_vr_off + last_entry_idx * VR_ENTRY_SIZE
# sanity: re-read the three fields we're about to patch, confirm they match what we just derived
cur_dw1, cur_dw2 = struct.unpack_from('<II', data, entry_62_file_off)
assert cur_dw1 == last_dw1 and cur_dw2 == last_dw2
cur_mod_id = struct.unpack_from('<I', data, entry_62_file_off + 16)[0]
assert cur_mod_id == last_mod_id

NEW_DW1 = 1   # present
NEW_DW2 = 5   # rights: executable (matches v1-v4/diag1's convention for code)
struct.pack_into('<I', data, entry_62_file_off + 0, NEW_DW1)
struct.pack_into('<I', data, entry_62_file_off + 4, NEW_DW2)
struct.pack_into('<I', data, entry_62_file_off + 16, new_health_mod_id)
print(f"patched entry 62 IN PLACE @0x{entry_62_file_off:x}: "
      f"dw1 {last_dw1}->{NEW_DW1}, dw2 {last_dw2}->{NEW_DW2}, mod_id 0x{last_mod_id:x}->0x{new_health_mod_id:x}")
print("rbase/rsize for entry 62: UNCHANGED (still full original range)")
print("TaskInfo.virt_space / virt_space_size: UNTOUCHED -- array does not move, count stays 63")

# ---------------------------------------------------------------------------
# 4. new combined section: INERT stub (zeroed, like diag1) + new
#    .secinfo entry (like diag2) describing it. No VirtRange array is
#    built or inserted here at all -- entry 62, already in place inside
#    .boottable, is what references this module via mod_id.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000  # address choice is irrelevant to this test (diag4/diag5
                           # already showed address value doesn't matter for virt_space
                           # relocation -- this new section is only reached via .secinfo,
                           # never via a relocated virt_space pointer, so reuse the
                           # established convention for consistency)
assert NEW_PHYS_BASE >= max_existing_secinfo_end

secinfo_struct_vaddr = NEW_PHYS_BASE + len(stub_block)
assert secinfo_struct_vaddr % 4 == 0
name_bytes = b'.health.diag6_reattributed\x00'
name_ptr = secinfo_struct_vaddr + 24
new_secinfo_struct = struct.pack('<IIIIII', 0, name_ptr, NEW_PHYS_BASE, len(stub_block), 1, 0) + name_bytes
pad1 = (-len(new_secinfo_struct)) % 4
new_secinfo_struct += b'\x00' * pad1

new_section_content = stub_block + new_secinfo_struct
new_section_size = len(new_section_content)
print(f"new combined section (INERT stub + new secinfo entry): size=0x{new_section_size:x} ({new_section_size} bytes)")

# ---------------------------------------------------------------------------
# 5. callsite: NOT TOUCHED (same as diag1/diag2/diag4/diag5) -- content-
#    blind structural test, nothing can ever branch into the new region.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 6. perform the single insertion -- the ONLY global registration fields
#    touched are entry 62's dw1/dw2/mod_id (step 3, already applied
#    directly to `data`) and the .secinfo tail pointer below.
#    VIRT_SPACE_FOFF / VIRT_SPACE_SIZE_FOFF are never written.
# ---------------------------------------------------------------------------
insertion_offset = e_shoff
maxend = max(s['sh_offset'] + s['sh_size'] for s in shdrs if s['sh_type'] != 8)
assert insertion_offset >= maxend

new_data = bytearray(data[:insertion_offset]) + bytearray(new_section_content) + bytearray(data[insertion_offset:])
delta = len(new_section_content)

struct.pack_into('<I', new_data, LAST_SECINFO_NEXTPTR_FOFF, secinfo_struct_vaddr)

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
print(f".secinfo entries: {total_existing_secinfo_entries} -> {total_existing_secinfo_entries + 1}")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
