import struct, sys, os

# usage: python3 build_patched_280.py <extracted-280-elf.bin> <output-path>
#
# v3 differs from v2 in exactly one structural way: v2 placed the restored
# fan code at a NEW task-local address (0x2001000) that sits past what this
# session confirmed is a hard, universal 32MB per-task Address Space
# ceiling for this firmware's INTEGRITY RTOS -- see
# research/2026-11-06-kernel-re-methodology-and-pitfalls.md. v3 instead
# reclaims space from the TAIL of Health's own final VirtRange entry -- a
# large (0xe0000-byte), anonymous, reference-free region confirmed
# unchanged between 2.77 and 2.80 and never directly addressed by any
# literal in Health's own compiled code (research/2026-11-06-v3-fan-
# restore-strategy.md) -- so the whole table still ends exactly at the
# confirmed ceiling, never past it.
#
# v3 also uses a completely re-derived dependency closure (15 functions,
# not v1/v2's 8 -- the old one was missing 7 whole functions, see
# research/2026-11-06-v3-closure-rederivation.md) built by
# relocate_fan_v4.py, which must be run first to produce fan_block_v4.bin.
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FAN_BLOCK_PATH = os.path.join(SCRIPT_DIR, 'fan_block_v4.bin')

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (unchanged from v1/v2 -- well before every insertion point used here)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table
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
print(f".boottable idx={boottable_idx} addr=0x{boottable['sh_addr']:x} off=0x{boottable['sh_offset']:x} size=0x{boottable['sh_size']:x}")
print(f".secinfo   idx={secinfo_idx} addr=0x{secinfo['sh_addr']:x} off=0x{secinfo['sh_offset']:x} size=0x{secinfo['sh_size']:x}")

# ---------------------------------------------------------------------------
# 1. read-only lookups against EXISTING content (unchanged from v2)
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x}")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

LAST_SECINFO_NEXTPTR_FOFF = 0x16ece54
last_next_ptr = struct.unpack_from('<I', data, LAST_SECINFO_NEXTPTR_FOFF)[0]
assert last_next_ptr == 0, hex(last_next_ptr)

# ---------------------------------------------------------------------------
# 1a. NEW_SECINFO_INDEX and SIZE_INITIAL -- identical derivation to v2,
#     re-verified live against the binary every build (see v2's readme for
#     why this matters: these used to be bare trusted constants).
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
    assert index < 10000, "`.secinfo` linked-list walk did not terminate -- unexpected list structure"
    assert secinfo_lo <= walk_off <= secinfo_hi - SECINFO_ENTRY_SIZE, \
        ("`.secinfo` walk stepped outside the section's own bounds", hex(walk_off), hex(secinfo_lo), hex(secinfo_hi))
    next_ptr, name_ptr, text_base_addr, text_size, dw1, dw2 = struct.unpack_from('<IIIIII', data, walk_off)
    if text_base_addr == hdata_shdr['sh_addr']:
        assert hdata_secinfo_index is None, \
            ("multiple `.secinfo` entries share .health.elf.data's sh_addr -- ambiguous match", hdata_secinfo_index, index)
        hdata_secinfo_index = index
    max_existing_secinfo_end = max(max_existing_secinfo_end, text_base_addr + text_size)
    if next_ptr == 0:
        break
    walk_off = secinfo_lo + (next_ptr - secinfo['sh_addr'])
    index += 1
total_existing_secinfo_entries = index + 1
print(f".secinfo linked-list walk: {total_existing_secinfo_entries} entries, tail next_ptr field @0x{walk_off:x}, "
      f".health.elf.data found at index {hdata_secinfo_index}, highest existing "
      f"(text_base_addr+text_size)=0x{max_existing_secinfo_end:x}")

NEW_SECINFO_INDEX = 577
assert total_existing_secinfo_entries == NEW_SECINFO_INDEX, \
    ("`.secinfo` entry count disagrees with NEW_SECINFO_INDEX", total_existing_secinfo_entries, NEW_SECINFO_INDEX)
assert walk_off == LAST_SECINFO_NEXTPTR_FOFF, \
    ("walked to a different tail entry than LAST_SECINFO_NEXTPTR_FOFF points at", hex(walk_off), hex(LAST_SECINFO_NEXTPTR_FOFF))
assert hdata_secinfo_index is not None, "never found .health.elf.data's SectionInfo entry while walking .secinfo"

VR_ENTRY_SIZE = 0x20
HDATA_KNOWN_RSIZE = 0x91000
hdata_vr_mod_id = None
for vr_i in range(63):
    vr_dw1, vr_dw2, vr_rbase, vr_rsize, vr_mod_id, vr_dw6, vr_dw7, vr_dw8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    if vr_rsize == HDATA_KNOWN_RSIZE:
        assert hdata_vr_mod_id is None, \
            ("multiple existing Health VirtRange entries share rsize=0x91000", hdata_vr_mod_id, vr_mod_id)
        hdata_vr_mod_id = vr_mod_id
assert hdata_vr_mod_id is not None, \
    "no existing Health VirtRange entry has .health.elf.data's documented rsize=0x91000"

HDATA_KNOWN_MOD_ID = 0x82
assert hdata_vr_mod_id == HDATA_KNOWN_MOD_ID, \
    ("VirtRange-derived mod_id disagrees with v1's recorded value", hex(hdata_vr_mod_id), hex(HDATA_KNOWN_MOD_ID))

SIZE_INITIAL = hdata_vr_mod_id - hdata_secinfo_index
assert SIZE_INITIAL == 49, \
    ("derived SIZE_INITIAL disagrees with the previously-documented value", SIZE_INITIAL, hdata_vr_mod_id, hdata_secinfo_index)

# ---------------------------------------------------------------------------
# 2. v3's placement: shrink the TAIL of the LAST (anonymous, reference-free)
#    VirtRange entry instead of appending a 64th entry past the ceiling.
#    Find it generically (don't hardcode its index) and verify, every
#    build, that it really is the last entry, really is anonymous
#    (present=0, mod_id=0xffffffff), and really ends exactly at the
#    confirmed 0x2000000 per-task ceiling -- if any of that stops being
#    true for a future extraction, fail loudly rather than silently
#    reusing a different, unverified region.
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
     "0x2000000 per-task ceiling -- re-check research/2026-11-06-kernel-re-methodology-and-pitfalls.md "
     "before trusting this placement on a different extraction", hex(last_entry_end))

last_dw1, last_dw2, last_rbase, last_rsize, last_mod_id, last_dw6, last_dw7, last_dw8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, last_entry_idx * VR_ENTRY_SIZE)
assert last_dw1 == 0 and last_mod_id == 0xffffffff, \
    ("the entry at the ceiling is NOT anonymous (present=0, mod_id=0xffffffff) as expected -- "
     "this placement strategy specifically depends on reclaiming anonymous, not file-backed, space",
     last_dw1, hex(last_mod_id))
print(f"last (anonymous, ceiling-ending) VirtRange entry: idx={last_entry_idx} rbase=0x{last_rbase:x} rsize=0x{last_rsize:x}")

fan_block = open(FAN_BLOCK_PATH, 'rb').read()
NEW_TASK_LOCAL_SIZE = len(fan_block)
NEW_TASK_LOCAL_BASE = CEILING - NEW_TASK_LOCAL_SIZE
assert NEW_TASK_LOCAL_BASE % 4 == 0

new_last_rsize = last_rsize - NEW_TASK_LOCAL_SIZE
assert new_last_rsize > 0x10000, \
    ("reclaiming fan_block's size would leave less than 64KB of the anonymous region -- "
     "re-examine whether fan_block has grown unexpectedly", hex(new_last_rsize))
print(f"reclaiming 0x{NEW_TASK_LOCAL_SIZE:x} bytes from the tail of the anonymous region "
      f"(0x{last_rsize:x} -> 0x{new_last_rsize:x}); NEW_TASK_LOCAL_BASE=0x{NEW_TASK_LOCAL_BASE:x}")

# Re-check collision-freedom against all 63 EXISTING entries individually,
# same discipline as v2.
for vr_i in range(63):
    if vr_i == last_entry_idx:
        continue  # this is the one we're intentionally shrinking
    _d1, _d2, vr_rbase, vr_rsize, _mid, _d6, _d7, _d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    overlaps = vr_rbase < NEW_TASK_LOCAL_BASE + NEW_TASK_LOCAL_SIZE and NEW_TASK_LOCAL_BASE < vr_rbase + vr_rsize
    assert not overlaps, \
        ("NEW_TASK_LOCAL_BASE's reservation overlaps an EXISTING Health VirtRange entry",
         vr_i, hex(vr_rbase), hex(vr_rsize))

# Apply the shrink in place, then append the new entry.
struct.pack_into('<I', existing_vr_bytes, last_entry_idx * VR_ENTRY_SIZE + 12, new_last_rsize)

# ---------------------------------------------------------------------------
# 3. build the new combined section: fan_block_v4.bin (code+data, already
#    fully relocated and self-verified by relocate_fan_v4.py -- this script
#    does NOT re-derive any branch targets, it only places the block) +
#    new SectionInfo entry + new 64-entry VirtRange array.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000
assert NEW_PHYS_BASE >= max_existing_secinfo_end, \
    ("NEW_PHYS_BASE collides with or precedes the highest physical address already claimed by an "
     "existing `.secinfo` entry", hex(NEW_PHYS_BASE), hex(max_existing_secinfo_end))

secinfo_struct_vaddr = NEW_PHYS_BASE + len(fan_block)
assert secinfo_struct_vaddr % 4 == 0
name_bytes = b'.health.fan_restore_v4\x00'
name_ptr = secinfo_struct_vaddr + 24
new_secinfo_struct = struct.pack('<IIIIII', 0, name_ptr, NEW_PHYS_BASE, len(fan_block), 1, 0) + name_bytes
pad1 = (-len(new_secinfo_struct)) % 4
new_secinfo_struct += b'\x00' * pad1

virtrange_array_vaddr = secinfo_struct_vaddr + len(new_secinfo_struct)
new_health_mod_id = SIZE_INITIAL + NEW_SECINFO_INDEX
new_vr_entry = struct.pack('<IIIIIIII', 1, 5, NEW_TASK_LOCAL_BASE, NEW_TASK_LOCAL_SIZE, new_health_mod_id, 0, 0, 0)
new_vr_array = bytes(existing_vr_bytes) + new_vr_entry
assert len(new_vr_array) == 64*0x20

# Sanity-check the new 64-entry table has NO OVERLAPS and still reaches
# exactly the ceiling at the top. (Earlier analysis this session assumed
# the *entire* original 63-entry table was gap-free; building this for
# real against the genuine 2.80 binary found that's not quite true -- there
# is one pre-existing 0x1000-byte gap elsewhere in the table, between
# .health.elf.data's entry and the next one. That's a pre-existing property
# of the untouched table, not something this script introduces, so it's
# not fatal -- but it means "perfectly contiguous" was an overstatement;
# what actually matters, and what's checked here, is that the ceiling is
# respected and nothing overlaps.)
entries = [struct.unpack_from('<IIIII', new_vr_array, i*0x20)[:4] for i in range(64)]
entries_sorted = sorted(entries, key=lambda e: e[2])
prev_end = None
max_end = 0
for dw1, dw2, rbase, rsize in entries_sorted:
    if prev_end is not None:
        assert rbase >= prev_end, \
            ("new 64-entry VirtRange table has an OVERLAP -- this is fatal, unlike a gap",
             hex(prev_end), hex(rbase))
        if rbase > prev_end:
            print(f"  (pre-existing gap: 0x{prev_end:x} - 0x{rbase:x}, {rbase-prev_end} bytes -- not introduced by this script)")
    prev_end = rbase + rsize
    max_end = max(max_end, prev_end)
assert max_end == CEILING, ("new 64-entry table's highest entry does not end exactly at the ceiling", hex(max_end))
print(f"new 64-entry VirtRange table verified: no overlaps, reaches exactly 0x{CEILING:x}")

new_section_content = fan_block + new_secinfo_struct + new_vr_array
new_section_size = len(new_section_content)
print(f"new combined section: size=0x{new_section_size:x} ({new_section_size} bytes)")
print(f"  fan code+data:   0x{NEW_PHYS_BASE:x} - 0x{NEW_PHYS_BASE+len(fan_block):x}")
print(f"  secinfo struct:  0x{secinfo_struct_vaddr:x} (name @ 0x{name_ptr:x})")
print(f"  virtrange array: 0x{virtrange_array_vaddr:x} (64 entries, new entry mod_id=0x{new_health_mod_id:x})")

# ---------------------------------------------------------------------------
# 4. callsite patch: re-point the fan trampoline's disabled `bl` at the
#    relocated handler's NEW task-local address, computed by
#    relocate_fan_v4.py and re-derived here independently (not trusted as
#    a bare constant) by locating the main handler's own offset inside
#    fan_block_v4.bin -- it's the very first function in the assembled
#    block, so its new task-local address is simply NEW_TASK_LOCAL_BASE.
# ---------------------------------------------------------------------------
MAIN_HANDLER_OFFSET_IN_BLOCK = 0  # relocate_fan_v4.py places chunk 0 (which contains the
                                  # main handler) at the very start of the assembled block
new_handler_task_local = NEW_TASK_LOCAL_BASE + MAIN_HANDLER_OFFSET_IN_BLOCK
# but the handler itself is NOT at chunk 0's own start -- it's offset within
# that chunk by (0xe16970 - 0xe1589c), re-derive that here rather than
# trusting relocate_fan_v4.py's own printed value blindly
MAIN_HANDLER_TRUE_VADDR = 0xe16970
CHUNK0_START_TRUE_VADDR = 0xe1589c
new_handler_task_local = NEW_TASK_LOCAL_BASE + (MAIN_HANDLER_TRUE_VADDR - CHUNK0_START_TRUE_VADDR)
print(f"main handler new task-local entry point (re-derived): 0x{new_handler_task_local:x}")

CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
assert CALLSITE_FOFF < boottable['sh_offset']

health_text_shdr = shdrs[next(i for i in range(e_shnum) if name_of(i) == '.health.elf.text')]
callsite_shdr = next(s for s in shdrs
                      if s['sh_type'] != 8
                      and s['sh_offset'] <= CALLSITE_FOFF < s['sh_offset'] + s['sh_size'])
assert callsite_shdr is health_text_shdr, \
    ("the callsite is not inside `.health.elf.text` as expected", name_of(shdrs.index(callsite_shdr)))
callsite_true_vaddr = callsite_shdr['sh_addr'] + (CALLSITE_FOFF - callsite_shdr['sh_offset'])
callsite_task_local = callsite_true_vaddr - health_text_shdr['sh_addr'] + 0x10000
print(f"callsite: file_off=0x{CALLSITE_FOFF:x} true_vaddr=0x{callsite_true_vaddr:x} task_local=0x{callsite_task_local:x}")

# Compute and verify the new `bl` immediate exactly as v2 does, but
# targeting the new handler address.
disp = new_handler_task_local - (callsite_task_local + 8)
assert disp % 4 == 0
imm24 = (disp // 4) & 0xFFFFFF
check = imm24 - 0x1000000 if imm24 & 0x800000 else imm24
decoded_target = (callsite_task_local + 8 + check * 4) & 0xFFFFFFFF
assert decoded_target == new_handler_task_local, \
    ("callsite `bl` does NOT decode to the intended handler address",
     hex(decoded_target), hex(new_handler_task_local))
NEW_BL_BYTES = struct.pack('<I', (0xEB << 24) | imm24)
print(f"new callsite bl bytes: {NEW_BL_BYTES.hex()} -> decoded target 0x{decoded_target:x}")

# ---------------------------------------------------------------------------
# 5. perform the single insertion: append the new section's content right
#    before the section header table (same lowest-impact approach as v2).
# ---------------------------------------------------------------------------
insertion_offset = e_shoff
maxend = max(s['sh_offset'] + s['sh_size'] for s in shdrs if s['sh_type'] != 8)
assert insertion_offset >= maxend, (hex(insertion_offset), hex(maxend))

new_data = bytearray(data[:insertion_offset]) + bytearray(new_section_content) + bytearray(data[insertion_offset:])
delta = len(new_section_content)

new_data[CALLSITE_FOFF:CALLSITE_FOFF+4] = NEW_BL_BYTES
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
