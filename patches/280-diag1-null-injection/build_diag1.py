import struct, sys, os

# DIAGNOSTIC BUILD -- not a real patch. Purpose: isolate whether the
# 270 "iLO FW Communication Issue" that bricked v1/v2/v3/v4 identically is
# caused by the STRUCTURAL additions shared by all four (new ELF section,
# Health VirtRange table extended 63->64 entries, new SectionInfo
# linked-list entry) -- or by something specific to the content/correctness
# of the restored fan code itself.
#
# Rationale: patches/280 (sig-bypass only, confirmed hardware-working,
# see patches/280/readme.md) does NONE of the structural additions below
# and boots fine. v1/v2/v3/v4 all do the SAME structural additions (only
# differing in the internal relocation details of the injected code) and
# all four bricked with the identical error. That pattern implicates the
# shared structural mechanism, not the code-relocation specifics v1-v4 each
# tried to fix.
#
# This build reproduces v4's exact geometry (same NEW_TASK_LOCAL_SIZE via
# a same-size stub, same VirtRange reclaim, same SectionInfo entry) but:
#   1. The injected section's content is an inert stub (all-zero), not real
#      relocated code -- so if something walks/validates it at boot, it
#      sees zero bytes rather than meaningful instructions.
#   2. The callsite `bl` that invokes the handler is LEFT UNTOUCHED (still
#      the original disabled branch from stock 2.80) -- nothing can ever
#      jump into the new region.
#
# If this still produces BIOS POST 270: the fault is in the structural
# registration itself (new section / VirtRange extension / SecInfo entry),
# evaluated at boot before anything related to `fan` ever executes.
# If this boots fine: the fault is specific to the injected code's content
# or to actually reaching it, and the literal-pointer-class investigation
# direction was likely still relevant.
#
# usage: python3 build_diag1.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
V4_FAN_BLOCK_PATH = os.path.join(SCRIPT_DIR, '..', '280-fan-restore-v4', 'fan_block_v4.bin')

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, and to the confirmed-working patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4)
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
# 1. read-only lookups (identical to v4)
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

LAST_SECINFO_NEXTPTR_FOFF = 0x16ece54
last_next_ptr = struct.unpack_from('<I', data, LAST_SECINFO_NEXTPTR_FOFF)[0]
assert last_next_ptr == 0, hex(last_next_ptr)

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
assert walk_off == LAST_SECINFO_NEXTPTR_FOFF
assert hdata_secinfo_index is not None

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

# ---------------------------------------------------------------------------
# 2. same reclaim-from-tail placement geometry as v4, but content is inert.
#    Size is taken from v4's real fan_block so the geometry (addresses,
#    SectionInfo struct, VirtRange entry) is byte-for-byte comparable to
#    what v4 actually tested -- only the bytes written there differ.
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
assert last_entry_end == CEILING

last_dw1, last_dw2, last_rbase, last_rsize, last_mod_id, last_dw6, last_dw7, last_dw8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, last_entry_idx * VR_ENTRY_SIZE)
assert last_dw1 == 0 and last_mod_id == 0xffffffff

v4_fan_block_size = os.path.getsize(V4_FAN_BLOCK_PATH)
NEW_TASK_LOCAL_SIZE = v4_fan_block_size
stub_block = b'\x00' * NEW_TASK_LOCAL_SIZE
NEW_TASK_LOCAL_BASE = CEILING - NEW_TASK_LOCAL_SIZE
assert NEW_TASK_LOCAL_BASE % 4 == 0

new_last_rsize = last_rsize - NEW_TASK_LOCAL_SIZE
assert new_last_rsize > 0x10000
print(f"reclaiming 0x{NEW_TASK_LOCAL_SIZE:x} bytes (inert stub, same size as v4's real fan_block); "
      f"NEW_TASK_LOCAL_BASE=0x{NEW_TASK_LOCAL_BASE:x}")

for vr_i in range(63):
    if vr_i == last_entry_idx:
        continue
    _d1, _d2, vr_rbase, vr_rsize, _mid, _d6, _d7, _d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    overlaps = vr_rbase < NEW_TASK_LOCAL_BASE + NEW_TASK_LOCAL_SIZE and NEW_TASK_LOCAL_BASE < vr_rbase + vr_rsize
    assert not overlaps

struct.pack_into('<I', existing_vr_bytes, last_entry_idx * VR_ENTRY_SIZE + 12, new_last_rsize)

# ---------------------------------------------------------------------------
# 3. build the new combined section: INERT stub (not real fan code) +
#    new SectionInfo entry + new 64-entry VirtRange array. Same structural
#    shape as v4's step 3.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000
assert NEW_PHYS_BASE >= max_existing_secinfo_end

secinfo_struct_vaddr = NEW_PHYS_BASE + len(stub_block)
assert secinfo_struct_vaddr % 4 == 0
name_bytes = b'.health.diag1_null\x00'
name_ptr = secinfo_struct_vaddr + 24
new_secinfo_struct = struct.pack('<IIIIII', 0, name_ptr, NEW_PHYS_BASE, len(stub_block), 1, 0) + name_bytes
pad1 = (-len(new_secinfo_struct)) % 4
new_secinfo_struct += b'\x00' * pad1

virtrange_array_vaddr = secinfo_struct_vaddr + len(new_secinfo_struct)
new_health_mod_id = SIZE_INITIAL + NEW_SECINFO_INDEX
new_vr_entry = struct.pack('<IIIIIIII', 1, 5, NEW_TASK_LOCAL_BASE, NEW_TASK_LOCAL_SIZE, new_health_mod_id, 0, 0, 0)
new_vr_array = bytes(existing_vr_bytes) + new_vr_entry
assert len(new_vr_array) == 64*0x20

entries = [struct.unpack_from('<IIIII', new_vr_array, i*0x20)[:4] for i in range(64)]
entries_sorted = sorted(entries, key=lambda e: e[2])
prev_end = None
max_end = 0
for dw1, dw2, rbase, rsize in entries_sorted:
    if prev_end is not None:
        assert rbase >= prev_end
    prev_end = rbase + rsize
    max_end = max(max_end, prev_end)
assert max_end == CEILING
print("new 64-entry VirtRange table verified: no overlaps, reaches exactly ceiling")

new_section_content = stub_block + new_secinfo_struct + new_vr_array
new_section_size = len(new_section_content)
print(f"new combined section (INERT): size=0x{new_section_size:x} ({new_section_size} bytes)")

# ---------------------------------------------------------------------------
# 4. callsite: DELIBERATELY NOT TOUCHED. The original disabled `bl` from
#    stock 2.80 stays exactly as-is -- nothing can ever branch into the
#    new region. This is the key difference from v1-v4.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()}) -- new region is never reachable")

# ---------------------------------------------------------------------------
# 5. perform the single insertion (identical mechanics to v4) -- but note
#    CALLSITE_FOFF is NOT rewritten below.
# ---------------------------------------------------------------------------
insertion_offset = e_shoff
maxend = max(s['sh_offset'] + s['sh_size'] for s in shdrs if s['sh_type'] != 8)
assert insertion_offset >= maxend

new_data = bytearray(data[:insertion_offset]) + bytearray(new_section_content) + bytearray(data[insertion_offset:])
delta = len(new_section_content)

# callsite intentionally NOT patched (see step 4)
struct.pack_into('<I', new_data, VIRT_SPACE_FOFF, virtrange_array_vaddr)
struct.pack_into('<I', new_data, VIRT_SPACE_SIZE_FOFF, 64)
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

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
