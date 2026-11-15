import struct, sys, os

# DIAGNOSTIC BUILD #2 -- not a real patch. Follow-up to
# patches/280-diag1-null-injection, which proved the 270 brick is caused by
# the STRUCTURAL registration additions shared by v1-v4, not by any
# fan-code content or the callsite branch (diag1 had zeroed content and an
# untouched callsite, and still bricked identically).
#
# diag1 bundled two distinct structural changes together:
#   (a) Health TaskInfo.virt_space_size 63 -> 64, VirtRange table extended
#       with a new 64th entry (reclaiming the tail of the last anonymous
#       entry)
#   (b) the firmware-wide `.secinfo` linked list extended from 577 to 578
#       entries (a new tail entry appended)
#
# This build isolates (b) ALONE: it appends a new `.secinfo` entry (so the
# list grows to 578) but leaves Health's TaskInfo and VirtRange table
# COMPLETELY untouched -- virt_space_size stays 63, VIRT_SPACE_FOFF still
# points at the original, byte-for-byte unmodified 63-entry array. The new
# .secinfo entry claims a physical range that nothing virtually maps to.
#
# If THIS bricks with 270: merely growing the `.secinfo` list count (from
# 577 to 578) is sufficient on its own -- independent of VirtRange --
# which would mean something elsewhere in the firmware treats 577 as a
# fixed/expected total (an integrity check, a hardcoded loop bound, a
# separately-stored count that must agree with the walked list length).
# This project's own build scripts already flag 577 as a suspiciously
# fixed, independently-asserted constant (NEW_SECINFO_INDEX) -- this test
# directly checks whether that's exactly the trip wire.
#
# If THIS boots fine: the fault is specifically in the VirtRange
# 63->64 extension (TaskInfo.virt_space_size change and/or the new 64th
# entry), e.g. a fixed-size 63-slot buffer elsewhere in the kernel that
# gets overflowed regardless of the new entry's content.
#
# usage: python3 build_diag2.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4 and to confirmed-working patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1)
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

secinfo_idx = next(i for i in range(e_shnum) if name_of(i) == '.secinfo')
secinfo = shdrs[secinfo_idx]

# ---------------------------------------------------------------------------
# 1. read-only .secinfo walk (identical derivation to v4/diag1) -- NOTE:
#    Health TaskInfo / VirtRange are intentionally NEVER READ OR TOUCHED
#    in this build, to guarantee those bytes are 100% identical to stock
#    2.80.
# ---------------------------------------------------------------------------
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
print(f".secinfo walk: {total_existing_secinfo_entries} existing entries, tail next_ptr field @0x{walk_off:x}, "
      f"highest existing (text_base_addr+text_size)=0x{max_existing_secinfo_end:x}")

# ---------------------------------------------------------------------------
# 2. new content: an inert stub, same size as diag1's, claiming a fresh
#    physical range -- but NOT referenced by any VirtRange entry anywhere.
#    Health's own TaskInfo/VirtRange bytes are never touched by this script.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000
assert NEW_PHYS_BASE >= max_existing_secinfo_end

STUB_SIZE = 0xc320  # same size as diag1/v4's content, for apples-to-apples comparison
stub_block = b'\x00' * STUB_SIZE

secinfo_struct_vaddr = NEW_PHYS_BASE + STUB_SIZE
assert secinfo_struct_vaddr % 4 == 0
name_bytes = b'.health.diag2_secinfo_only\x00'
name_ptr = secinfo_struct_vaddr + 24
new_secinfo_struct = struct.pack('<IIIIII', 0, name_ptr, NEW_PHYS_BASE, STUB_SIZE, 1, 0) + name_bytes
pad1 = (-len(new_secinfo_struct)) % 4
new_secinfo_struct += b'\x00' * pad1

new_section_content = stub_block + new_secinfo_struct
new_section_size = len(new_section_content)
print(f"new combined section (INERT, secinfo-only): size=0x{new_section_size:x} ({new_section_size} bytes)")
print("Health TaskInfo / VirtRange: NOT TOUCHED (remain byte-identical to stock 2.80)")

# ---------------------------------------------------------------------------
# 3. callsite: NOT TOUCHED (same as diag1) -- nothing can ever reach the
#    new region, and nothing in Health's own per-task view even knows it
#    exists, since VirtRange is untouched.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 4. perform the single insertion (identical mechanics to v4/diag1) --
#    the ONLY global registration field touched is LAST_SECINFO_NEXTPTR_FOFF.
# ---------------------------------------------------------------------------
insertion_offset = e_shoff
maxend = max(s['sh_offset'] + s['sh_size'] for s in shdrs if s['sh_type'] != 8)
assert insertion_offset >= maxend

new_data = bytearray(data[:insertion_offset]) + bytearray(new_section_content) + bytearray(data[insertion_offset:])
delta = len(new_section_content)

struct.pack_into('<I', new_data, LAST_SECINFO_NEXTPTR_FOFF, secinfo_struct_vaddr)
# NOTE: VIRT_SPACE_FOFF and VIRT_SPACE_SIZE_FOFF (Health TaskInfo, at
# 0x166059c+4 and +8) are intentionally NEVER WRITTEN in this script.

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
print("Health TaskInfo.virt_space_size: unchanged (still 63)")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
