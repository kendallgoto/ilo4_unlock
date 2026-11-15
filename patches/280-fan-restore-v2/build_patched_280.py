import struct, sys, os

# usage: python3 build_patched_280.py <extracted-280-elf.bin> <output-path>
# (produces an elf.bin with both the sig-bypass patch AND the v2 fan-restore
# patch applied; feed the result to ilo4_repack.py as the patched userland)
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]
FAN_BLOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fan_block.bin')

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (unaffected by anything below -- file offset 0x964dfc is well
#    before every insertion/edit point used here)
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
# 1. read-only lookups against EXISTING content -- no resizing of
#    .boottable/.secinfo happens anywhere in this script. These offsets are
#    specific to the 2.80 build; see elf_patch_summary.md.
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x}")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytes(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

LAST_SECINFO_NEXTPTR_FOFF = 0x16ece54
last_next_ptr = struct.unpack_from('<I', data, LAST_SECINFO_NEXTPTR_FOFF)[0]
assert last_next_ptr == 0, hex(last_next_ptr)

# ---------------------------------------------------------------------------
# 1a. NEW_SECINFO_INDEX and SIZE_INITIAL below used to be bare constants
#     trusted from an earlier one-off manual scan -- exactly the class of
#     unverified assumption that bricked v1 (see
#     research/2026-11-06-fan-restore-v2-postmortem.md). Both are now
#     independently re-derived from the live binary and cross-checked two
#     different ways, instead of only being documented in a comment. If this
#     script is ever re-run against a different 2.80 extraction, a mismatch
#     here raises loudly instead of silently computing a wrong mod_id.
# ---------------------------------------------------------------------------
hdata_shdr = shdrs[next(i for i in range(e_shnum) if name_of(i) == '.health.elf.data')]

# Walk the live `.secinfo` linked list from its head, bounds-checking every
# step against the section's own declared extent. A naive walk that only
# trusts struct.unpack_from to raise on a bad offset is NOT sufficient:
# struct.unpack_from silently treats a *negative* offset as "count from the
# end of the buffer" rather than raising (verified interactively against
# Python's actual behavior, not assumed) -- so if next_ptr/sh_addr were ever
# misread, the walk could silently wander into unrelated file content
# instead of failing loudly, which defeats the entire point of this check.
SECINFO_ENTRY_SIZE = 24
secinfo_lo = secinfo['sh_offset']
secinfo_hi = secinfo['sh_offset'] + secinfo['sh_size']
walk_off = secinfo_lo
hdata_secinfo_index = None
max_existing_secinfo_end = 0  # highest (text_base_addr + text_size) seen -- re-derives, from the
                               # live binary, the "nothing else uses physical addresses up here"
                               # claim NEW_PHYS_BASE's placement depends on, instead of trusting the
                               # postmortem's one-off "0x3e22b18" scan result.
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

NEW_SECINFO_INDEX = 577  # the new entry's own eventual index == count of existing entries
assert total_existing_secinfo_entries == NEW_SECINFO_INDEX, \
    ("`.secinfo` entry count disagrees with NEW_SECINFO_INDEX", total_existing_secinfo_entries, NEW_SECINFO_INDEX)
assert walk_off == LAST_SECINFO_NEXTPTR_FOFF, \
    ("walked to a different tail entry than LAST_SECINFO_NEXTPTR_FOFF points at", hex(walk_off), hex(LAST_SECINFO_NEXTPTR_FOFF))
assert hdata_secinfo_index is not None, "never found .health.elf.data's SectionInfo entry while walking .secinfo"

# Cross-check SIZE_INITIAL two independent ways rather than trusting either
# alone:
#   (a) scan the 63 EXISTING Health VirtRange entries (already loaded as
#       existing_vr_bytes) for the one whose reservation size matches
#       .health.elf.data's hardware-confirmed rsize=0x91000 -- the exact
#       value whose misinterpretation bricked v1 (see this patch's readme,
#       "Why v1 failed") -- and read ITS mod_id field directly from the
#       binary, instead of trusting any human-recorded value for it.
#   (b) patches/280-fan-restore/build_patched_280.py's fixup comment
#       separately states this same entry's mod_id is 0x82 -- that was never
#       actually read by that script's own code, so on its own it is just a
#       claim, but it must still agree with (a).
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

HDATA_KNOWN_MOD_ID = 0x82  # from patches/280-fan-restore/build_patched_280.py's fixup comment (unverified by that script itself)
assert hdata_vr_mod_id == HDATA_KNOWN_MOD_ID, \
    ("VirtRange-derived mod_id disagrees with v1's recorded value", hex(hdata_vr_mod_id), hex(HDATA_KNOWN_MOD_ID))

SIZE_INITIAL = hdata_vr_mod_id - hdata_secinfo_index
assert SIZE_INITIAL == 49, \
    ("derived SIZE_INITIAL disagrees with the previously-documented value", SIZE_INITIAL, hdata_vr_mod_id, hdata_secinfo_index)

# ---------------------------------------------------------------------------
# 2. build the new combined section content: fan code + new SectionInfo
#    entry (struct+name) + new 64-entry Health VirtRange array.
#    All of this lives at a BRAND NEW physical address (0x4000000) that
#    collides with nothing in the firmware's existing address space
#    (confirmed: highest existing true-vaddr use tops out at 0x3e22b18),
#    unlike v1 of this patch, which reused unallocated space inside an
#    EXISTING module's declared VirtRange and turned out to collide with
#    that module's live BSS. See research/ for the post-mortem.
# ---------------------------------------------------------------------------
NEW_PHYS_BASE = 0x4000000
assert NEW_PHYS_BASE >= max_existing_secinfo_end, \
    ("NEW_PHYS_BASE collides with or precedes the highest physical address already claimed by an "
     "existing `.secinfo` entry -- re-derived above by walking the LIVE `.secinfo` list, not trusted "
     "from the postmortem's one-off scan result", hex(NEW_PHYS_BASE), hex(max_existing_secinfo_end))

NEW_TASK_LOCAL_BASE = 0x2001000  # Health task-local; existing entries top out at 0x2000000
NEW_TASK_LOCAL_SIZE = 0x4000

# 0x2000000 is NOT just "the highest address anything currently uses" -- see
# research/2026-11-06-kernel-re-methodology-and-pitfalls.md. This firmware
# runs Green Hills INTEGRITY RTOS, confirmed by strings in this exact image
# (`AddressSpace`, `INTEGRITY`) and independently corroborated by public
# research on this exact firmware (Perigaud/Gazet/Czarny, REcon 2018):
# INTEGRITY gives every userland task a fixed-size virtual Address Space,
# sized at system-build time, not grown dynamically. Every one of the 31
# userland tasks in this exact 2.80 image (and all 32 in 2.77) independently
# ends its own VirtRange table at exactly 0x2000000 despite wildly differing
# module counts (54-72 entries) -- strong evidence this is a hard, universal
# per-task ceiling, not headroom. `NEW_TASK_LOCAL_BASE` placed this v2
# attempt ONE ENTRY PAST that ceiling, which is the leading (still not
# 100%-confirmed-by-kernel-code) explanation for why v2 bricked hardware the
# same way v1 did. This assertion makes that specific mistake impossible to
# repeat silently.
assert NEW_TASK_LOCAL_BASE + NEW_TASK_LOCAL_SIZE <= 0x2000000, \
    ("NEW_TASK_LOCAL_BASE+NEW_TASK_LOCAL_SIZE exceeds the per-task Address "
     "Space ceiling that EVERY task in this firmware (both 2.77 and 2.80) "
     "independently respects -- this is believed to be a hard INTEGRITY RTOS "
     "limit, not free space. See research/2026-11-06-kernel-re-methodology-"
     "and-pitfalls.md before overriding this.",
     hex(NEW_TASK_LOCAL_BASE), hex(NEW_TASK_LOCAL_SIZE))

# Re-check task-local collision-freedom against all 63 EXISTING Health
# VirtRange entries individually, not just the "existing entries top out at
# 0x2000000" summary claim above -- a summary of the max doesn't rule out a
# smaller, oddly-placed existing entry overlapping this new one if the
# existing entries aren't actually laid out in strictly increasing order.
for vr_i in range(63):
    _d1, _d2, vr_rbase, vr_rsize, _mid, _d6, _d7, _d8 = \
        struct.unpack_from('<IIIIIIII', existing_vr_bytes, vr_i * VR_ENTRY_SIZE)
    overlaps = vr_rbase < NEW_TASK_LOCAL_BASE + NEW_TASK_LOCAL_SIZE and NEW_TASK_LOCAL_BASE < vr_rbase + vr_rsize
    assert not overlaps, \
        ("NEW_TASK_LOCAL_BASE's reservation overlaps an EXISTING Health VirtRange entry",
         vr_i, hex(vr_rbase), hex(vr_rsize), hex(NEW_TASK_LOCAL_BASE), hex(NEW_TASK_LOCAL_SIZE))

fan_block = open(FAN_BLOCK_PATH, 'rb').read()
assert len(fan_block) == 15548

secinfo_struct_vaddr = NEW_PHYS_BASE + len(fan_block)
assert secinfo_struct_vaddr % 4 == 0
name_bytes = b'.health.fan_restore\x00'
name_ptr = secinfo_struct_vaddr + 24
new_secinfo_struct = struct.pack('<IIIIII', 0, name_ptr, NEW_PHYS_BASE, len(fan_block), 1, 0) + name_bytes
pad1 = (-len(new_secinfo_struct)) % 4
new_secinfo_struct += b'\x00' * pad1

virtrange_array_vaddr = secinfo_struct_vaddr + len(new_secinfo_struct)
new_health_mod_id = SIZE_INITIAL + NEW_SECINFO_INDEX
new_vr_entry = struct.pack('<IIIIIIII', 1, 5, NEW_TASK_LOCAL_BASE, NEW_TASK_LOCAL_SIZE, new_health_mod_id, 0, 0, 0)
new_vr_array = existing_vr_bytes + new_vr_entry
assert len(new_vr_array) == 64*0x20

new_section_content = fan_block + new_secinfo_struct + new_vr_array
new_section_size = len(new_section_content)
print(f"new combined section: size=0x{new_section_size:x} ({new_section_size} bytes)")
print(f"  fan code:        0x{NEW_PHYS_BASE:x} - 0x{NEW_PHYS_BASE+len(fan_block):x}")
print(f"  secinfo struct:  0x{secinfo_struct_vaddr:x} (name @ 0x{name_ptr:x})")
print(f"  virtrange array: 0x{virtrange_array_vaddr:x} (64 entries, new entry mod_id=0x{new_health_mod_id:x})")

# ---------------------------------------------------------------------------
# 3. callsite patch: re-point the fan trampoline's disabled `bl` at the
#    relocated handler's new task-local address (0x2001000). Precomputed for
#    this exact placement -- if NEW_TASK_LOCAL_BASE above ever changes, this
#    byte sequence must be regenerated (see elf_patch_summary.md).
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
NEW_BL_BYTES = bytes.fromhex('eb6b7feb')
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
assert CALLSITE_FOFF < boottable['sh_offset']  # unaffected by the append-at-end insertion

# ---------------------------------------------------------------------------
# 3a. Round-trip-verify the single most safety-critical patched instruction:
#     the callsite `bl` that actually invokes the restored handler. Per this
#     patch's readme, `encode_branch` silently wraps the 24-bit immediate on
#     overflow instead of raising, so a wrong encoding would NOT have been
#     caught by a "zero unresolved targets" check that only verifies
#     resolve_target() doesn't throw -- the only way to actually catch that
#     failure class is to decode the real bytes and independently compute
#     where they branch to, not trust what the script intends.
#
#     An earlier version of this check resolved the callsite's task-local
#     address via the mod_id/`.secinfo` VirtRange chain used for the NEW
#     entry elsewhere in this script. Run against the real firmware, that
#     chain failed (no existing VirtRange entry had the predicted mod_id).
#     Investigation found two compounding bugs in the check itself, not in
#     the patch: (1) the callsite-section lookup didn't exclude SHT_NOBITS
#     sections, so it matched `.embmedia.heap` (a zero-content BSS
#     placeholder sharing `.health.elf.text`'s sh_offset) instead of the real
#     code section -- the same NOBITS exclusion the pre-existing `maxend`
#     check elsewhere in this script already applies, just not replicated
#     here; (2) the mod_id/VirtRange mechanism is for ADDITIONAL,
#     dynamically-mapped modules (like `.health.elf.data`'s BSS extension),
#     not for a task's own primary, directly-loaded code section -- which
#     instead uses the much simpler convention already documented in
#     `research/2022-02-17-docs.md` for `.ConAppCLI.elf.text`:
#     `task_local = true_vaddr - section_sh_addr + 0x10000`. Applying that
#     correct convention here, using the real section header, reproduces the
#     readme's "~0x2604c" value EXACTLY (zero discrepancy) against the real
#     extracted 2.80 firmware.
# ---------------------------------------------------------------------------
health_text_shdr = shdrs[next(i for i in range(e_shnum) if name_of(i) == '.health.elf.text')]
callsite_shdr = next(s for s in shdrs
                      if s['sh_type'] != 8  # exclude SHT_NOBITS placeholders (see maxend, above)
                      and s['sh_offset'] <= CALLSITE_FOFF < s['sh_offset'] + s['sh_size'])
assert callsite_shdr is health_text_shdr, \
    ("the callsite is not inside `.health.elf.text` as expected -- the task-local conversion below "
     "assumes it is", name_of(shdrs.index(callsite_shdr)))
callsite_true_vaddr = callsite_shdr['sh_addr'] + (CALLSITE_FOFF - callsite_shdr['sh_offset'])
callsite_task_local = callsite_true_vaddr - health_text_shdr['sh_addr'] + 0x10000
print(f"callsite: file_off=0x{CALLSITE_FOFF:x} true_vaddr=0x{callsite_true_vaddr:x} "
      f"task_local=0x{callsite_task_local:x} (readme's approximate value: ~0x2604c)")

# Decode NEW_BL_BYTES as an ARM32 B/BL instruction and independently compute
# its real target.
bl_word = struct.unpack('<I', NEW_BL_BYTES)[0]
assert (bl_word >> 25) & 0b111 == 0b101, ("NEW_BL_BYTES is not a B/BL-family instruction", hex(bl_word))
imm24 = bl_word & 0xFFFFFF
if imm24 & 0x800000:
    imm24 -= 0x1000000  # sign-extend the 24-bit field
decoded_target_task_local = (callsite_task_local + 8 + imm24 * 4) & 0xFFFFFFFF
print(f"decoded branch target (task-local): 0x{decoded_target_task_local:x} (intended: 0x{NEW_TASK_LOCAL_BASE:x})")
assert decoded_target_task_local == NEW_TASK_LOCAL_BASE, \
    ("callsite `bl` does NOT decode to the intended handler address -- this is exactly the silent "
     "encode_branch wraparound failure class the readme warns about",
     hex(decoded_target_task_local), hex(NEW_TASK_LOCAL_BASE))

# ---------------------------------------------------------------------------
# 4. perform the single insertion: append the new section's content right
#    before the section header table (lowest-impact insertion point --
#    nothing else has a higher file offset, so only e_shoff shifts).
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
    0,                      # sh_name (reuse empty name at shstrtab[0])
    1,                      # sh_type = SHT_PROGBITS
    6,                      # sh_flags = ALLOC | EXECINSTR (matches .health.elf.text)
    NEW_PHYS_BASE,          # sh_addr
    insertion_offset,       # sh_offset
    new_section_size,       # sh_size
    0, 0, 0, 0)

new_shdr_table_off = new_e_shoff + e_shnum*e_shentsize
new_data[new_shdr_table_off:new_shdr_table_off+40] = new_shdr
new_e_shnum = e_shnum + 1
struct.pack_into('<H', new_data, 0x30, new_e_shnum)

print(f"\ne_shoff: 0x{e_shoff:x} -> 0x{new_e_shoff:x}")
print(f"e_shnum: {e_shnum} -> {new_e_shnum}")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
