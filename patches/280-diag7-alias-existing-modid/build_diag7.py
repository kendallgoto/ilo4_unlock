import struct, sys

# DIAGNOSTIC BUILD #7 -- not a real patch. Follow-up to
# patches/280-diag6-reattribute-entry-in-place, which ALSO bricked with
# 270, even though it never relocated the array, never changed
# virt_space/virt_space_size, never changed entry count, and never moved
# entry 62's rbase/rsize -- it only flipped entry 62's dw1/dw2/mod_id
# from anonymous to a BRAND-NEW module (mod_id=0x272, backed by a
# freshly-appended .secinfo entry that did not exist in stock 2.80).
#
# Cumulative picture across every diagnostic so far:
#   - diag2 (.secinfo list grows, but NOTHING in VirtRange references the
#     new entry): booted fine
#   - diag3 (existing anonymous entry's rsize shrunk in place, stays
#     anonymous): booted fine
#   - diag1 (new 64th VirtRange entry + array relocation, new mod_id,
#     new secinfo entry): bricked
#   - diag4 (relocate virt_space only, same 63 entries, address 0x4000000): bricked
#   - diag5 (relocate virt_space only, same 63 entries, tight address): bricked
#   - diag6 (reuse entry 62's slot in place, new mod_id, new secinfo
#     entry, NO relocation, NO count change): bricked
#
# The two clean builds never create a NEW, real (present=1) link between
# a VirtRange entry and a module. Every bricked build does -- regardless
# of registration mechanism (new entry vs. reused slot, relocated array
# vs. untouched array). This build isolates the one variable common to
# every bricked attempt that's never been tested in isolation: is it
# specifically that the *module id itself* (mod_id) is BRAND NEW --
# i.e. never present in stock 2.80's own module table at all -- or is it
# simply "any anonymous entry becoming present=1" regardless of which
# module it names?
#
# This build re-attributes entry 62 EXACTLY like diag6 (same in-place
# patch, no relocation, no count change, rbase/rsize UNCHANGED), but
# instead of inventing a new module, it points entry 62 at mod_id=0x81 --
# the SAME, pre-existing, already-valid module Health's own main
# `.health.elf.text` (entry 1) already uses. No new `.secinfo` entry is
# added at all (none is needed -- mod_id=0x81 already has one, at index
# 80, describing `.health.elf.text` itself). This is a pure alias: the
# same already-registered module, now also mapped at a second task-local
# address. The file does not even grow.
#
# If THIS bricks with 270: the problem isn't "is this mod_id new" --
# converting ANY anonymous entry to present=1 is fatal regardless of
# which module it names, even one that's already fully valid and
# load-bearing elsewhere. That would close out the entire "register a
# new module via VirtRange re-attribution" direction conclusively.
# If THIS boots fine: the module table itself tolerates a *duplicate*
# reference to an already-known mod_id, and the real constraint is
# specifically that mod_id must already exist in the system's own
# build-time module table -- meaning no mechanism that invents a NEW
# mod_id (new secinfo entry) can ever work here, structurally, no matter
# how it's wired into VirtRange.
#
# usage: python3 build_diag7.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1-6, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1-6)
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
VIRT_SPACE_SIZE_FOFF = HEALTH_TASKINFO_FOFF + 4
VIRT_SPACE_FOFF = HEALTH_TASKINFO_FOFF + 8

task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} virt_space=0x{virt_space:x} "
      f"(BOTH LEFT COMPLETELY UNTOUCHED -- the array does not move)")

existing_vr_off = boottable['sh_offset'] + (virt_space - boottable['sh_addr'])
existing_vr_bytes = bytearray(data[existing_vr_off:existing_vr_off + 63*0x20])
assert len(existing_vr_bytes) == 63*0x20

VR_ENTRY_SIZE = 0x20

# confirm entry 1 is Health's own main .health.elf.text module (mod_id=0x81,
# dw2=5 executable) -- the EXISTING, already-valid mod_id this build will
# alias, re-derived fresh rather than hardcoded.
e1_dw1, e1_dw2, e1_rbase, e1_rsize, e1_mod_id, _d6, _d7, _d8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, 1 * VR_ENTRY_SIZE)
assert e1_dw1 == 1 and e1_mod_id == 0x81, \
    ("entry 1 is not the expected Health .text module", e1_dw1, hex(e1_mod_id))
EXISTING_MOD_ID = e1_mod_id
EXISTING_RIGHTS = e1_dw2
print(f"entry 1 confirmed: mod_id=0x{EXISTING_MOD_ID:x} (Health's own .health.elf.text), "
      f"rights={EXISTING_RIGHTS} rbase=0x{e1_rbase:x} rsize=0x{e1_rsize:x}")

# ---------------------------------------------------------------------------
# 2. find the last (anonymous, ceiling-ending) entry -- identical
#    derivation to diag3/diag4/diag5/diag6.
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
#    mod_id IN PLACE -- identical mechanics to diag6 -- but point mod_id
#    at the EXISTING, already-valid module (0x81) instead of inventing a
#    new one. rbase/rsize UNCHANGED (full original range). No new
#    .secinfo entry is added at all -- none is needed, since mod_id=0x81
#    already has one (index 80, describing .health.elf.text). The file
#    does not grow by even one byte.
# ---------------------------------------------------------------------------
entry_62_file_off = existing_vr_off + last_entry_idx * VR_ENTRY_SIZE
cur_dw1, cur_dw2 = struct.unpack_from('<II', data, entry_62_file_off)
assert cur_dw1 == last_dw1 and cur_dw2 == last_dw2
cur_mod_id = struct.unpack_from('<I', data, entry_62_file_off + 16)[0]
assert cur_mod_id == last_mod_id

struct.pack_into('<I', data, entry_62_file_off + 0, 1)                # present
struct.pack_into('<I', data, entry_62_file_off + 4, EXISTING_RIGHTS)   # rights, matching entry 1
struct.pack_into('<I', data, entry_62_file_off + 16, EXISTING_MOD_ID)  # mod_id -- EXISTING, not new
print(f"patched entry 62 IN PLACE @0x{entry_62_file_off:x}: "
      f"dw1 {last_dw1}->1, dw2 {last_dw2}->{EXISTING_RIGHTS}, "
      f"mod_id 0x{last_mod_id:x}->0x{EXISTING_MOD_ID:x} (ALIAS of entry 1's module, not new)")
print("rbase/rsize for entry 62: UNCHANGED (still full original range)")
print("TaskInfo.virt_space / virt_space_size: UNTOUCHED -- array does not move, count stays 63")
print(".secinfo: UNTOUCHED -- no new entry added, mod_id=0x81 already has one")

# ---------------------------------------------------------------------------
# 4. callsite: NOT TOUCHED (same as diag1/diag2/diag4/diag5/diag6) --
#    content-blind structural test, nothing can ever branch into the
#    aliased region differently than it already could via entry 1.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 5. no insertion at all this time -- entry 62's bytes were patched
#    directly in `data` above; the file is otherwise byte-for-byte
#    identical to stock 2.80 (plus the sig-bypass from step 0). No
#    e_shoff/e_shnum changes, no new section.
# ---------------------------------------------------------------------------
open(OUT_PATH, 'wb').write(data)
print(f"\nWrote {OUT_PATH} ({len(data)} bytes, same size as input -- no insertion, no growth)")
