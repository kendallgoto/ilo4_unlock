import struct, sys

# DIAGNOSTIC BUILD #8 -- not a real patch. Follow-up to
# patches/280-diag7-alias-existing-modid, which ALSO bricked with 270 --
# the 4th consecutive brick of the exact same hypothesis class (diag1,
# diag4, diag5, diag6, diag7 all create a new, real present=1 link from a
# VirtRange entry to a module; all five brick).
#
# After diag7's result, a sharper question was raised: every one of these
# five tests reused the SAME VirtRange entry -- entry 62, the LAST entry in
# Health's table, the one whose range ends exactly at the per-task ceiling
# (0x2000000). A literal-pool scan of Health's own .health.elf.text/.data
# for references into entry 62's address range (both as a task-local value
# and as a true-vaddr-translated value) found only 1 isolated hit per
# hypothesis -- statistically consistent with noise, not a real reference
# (contrast with the v1 postmortem's 9 evenly-spaced genuine hits that
# proved an actual BSS collision). So Health's own compiled code doesn't
# appear to read/write fixed addresses there.
#
# But that doesn't rule out the INTEGRITY kernel itself treating the LAST
# VirtRange entry specially at task-boot time -- e.g. using whatever's left
# anonymous at the top of the table as the task's heap/stack backing,
# sized generically from the entry's rbase/rsize fields rather than via any
# hardcoded literal in Health's own code (which would explain why a literal
# scan finds nothing, yet corrupting it is still fatal). If that's the real
# mechanism, the fatal variable was never "new mod_id" or "present=1
# conversion" in general -- it's specifically about disturbing the ceiling
# entry.
#
# This build tests that directly: identical in-place re-attribution
# mechanics to diag6/diag7 (no relocation, no count change, rbase/rsize
# unchanged, alias to the SAME existing mod_id=0x81 diag7 used so the
# mod_id-newness variable stays controlled) -- but applied to entry 11
# instead of entry 62. Entry 11 is anonymous (present=0, mod_id=0xffffffff)
# like entry 62, but sits in the middle of the table (task-local
# 0x1600000-0x1780000, 1.5MB) with entries both before and after it still
# anonymous/present on either side -- nowhere near the 0x2000000 ceiling.
# A literal-pool scan of entry 11's range found only 4 hits in .text and 0
# in .data -- the same noise-floor order of magnitude as entry 62, so it's
# an equally "clean" (non-referenced) target, isolating position
# (ceiling vs. mid-table) as the only changed variable versus diag7.
#
# If THIS bricks with 270: position isn't the differentiator either --
# reattributing ANY anonymous entry anywhere in the table is fatal, not
# just the ceiling one. The "any present=0->1 conversion is fatal"
# conclusion from diag6/diag7 stands, now independent of position too.
# If THIS boots fine: the ceiling entry specifically is special (almost
# certainly kernel-managed heap/stack sizing), and future registration
# attempts should target a non-ceiling anonymous entry like this one
# instead of entry 62.
#
# usage: python3 build_diag8.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to v1-v4, diag1-7, and confirmed-working
#    patches/280)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# parse section header table (identical to v4/diag1-7)
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
# alias, re-derived fresh rather than hardcoded (identical to diag7).
e1_dw1, e1_dw2, e1_rbase, e1_rsize, e1_mod_id, _d6, _d7, _d8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, 1 * VR_ENTRY_SIZE)
assert e1_dw1 == 1 and e1_mod_id == 0x81, \
    ("entry 1 is not the expected Health .text module", e1_dw1, hex(e1_mod_id))
EXISTING_MOD_ID = e1_mod_id
EXISTING_RIGHTS = e1_dw2
print(f"entry 1 confirmed: mod_id=0x{EXISTING_MOD_ID:x} (Health's own .health.elf.text), "
      f"rights={EXISTING_RIGHTS} rbase=0x{e1_rbase:x} rsize=0x{e1_rsize:x}")

# ---------------------------------------------------------------------------
# 2. target entry: 11 -- anonymous, mid-table, nowhere near the 0x2000000
#    ceiling (unlike entry 62, which every prior diagnostic touched).
#    Confirm its position/content fresh rather than trusting prior notes.
# ---------------------------------------------------------------------------
TARGET_IDX = 11
CEILING = 0x2000000

t_dw1, t_dw2, t_rbase, t_rsize, t_mod_id, t_dw6, t_dw7, t_dw8 = \
    struct.unpack_from('<IIIIIIII', existing_vr_bytes, TARGET_IDX * VR_ENTRY_SIZE)
assert t_dw1 == 0 and t_mod_id == 0xffffffff, \
    ("entry 11 is not anonymous as expected", t_dw1, hex(t_mod_id))
assert t_rbase + t_rsize < CEILING - 0x400000, \
    ("entry 11 is suspiciously close to the ceiling -- not a clean non-ceiling test", hex(t_rbase+t_rsize))
print(f"target entry {TARGET_IDX}: rbase=0x{t_rbase:x} rsize=0x{t_rsize:x} "
      f"end=0x{t_rbase+t_rsize:x} (ceiling is 0x{CEILING:x} -- "
      f"{(CEILING - (t_rbase+t_rsize))/1024/1024:.1f} MiB below it) dw1={t_dw1} dw2={t_dw2}")

# sanity: entries immediately before/after entry 11 are untouched by this
# patch and still describe their own stock ranges (no overlap introduced).
prev_dw1, prev_dw2, prev_rbase, prev_rsize, prev_mod_id = \
    struct.unpack_from('<IIIII', existing_vr_bytes, (TARGET_IDX-1) * VR_ENTRY_SIZE)
next_dw1, next_dw2, next_rbase, next_rsize, next_mod_id = \
    struct.unpack_from('<IIIII', existing_vr_bytes, (TARGET_IDX+1) * VR_ENTRY_SIZE)
print(f"entry {TARGET_IDX-1} (untouched): rbase=0x{prev_rbase:x} rsize=0x{prev_rsize:x} end=0x{prev_rbase+prev_rsize:x}")
print(f"entry {TARGET_IDX+1} (untouched): rbase=0x{next_rbase:x} rsize=0x{next_rsize:x} mod_id=0x{next_mod_id:x}")
assert prev_rbase + prev_rsize == t_rbase, "entry 11 does not immediately follow entry 10 as expected"
assert t_rbase + t_rsize == next_rbase, "entry 12 does not immediately follow entry 11 as expected"

# ---------------------------------------------------------------------------
# 3. THE ONLY VirtRange change in this build: patch entry 11's dw1/dw2/
#    mod_id IN PLACE -- identical mechanics to diag6/diag7. rbase/rsize
#    UNCHANGED (full original range). No new .secinfo entry needed --
#    mod_id=0x81 already has one. The file does not grow by even one byte.
# ---------------------------------------------------------------------------
entry_11_file_off = existing_vr_off + TARGET_IDX * VR_ENTRY_SIZE
cur_dw1, cur_dw2 = struct.unpack_from('<II', data, entry_11_file_off)
assert cur_dw1 == t_dw1 and cur_dw2 == t_dw2
cur_mod_id = struct.unpack_from('<I', data, entry_11_file_off + 16)[0]
assert cur_mod_id == t_mod_id

struct.pack_into('<I', data, entry_11_file_off + 0, 1)                # present
struct.pack_into('<I', data, entry_11_file_off + 4, EXISTING_RIGHTS)   # rights, matching entry 1
struct.pack_into('<I', data, entry_11_file_off + 16, EXISTING_MOD_ID)  # mod_id -- EXISTING, not new
print(f"patched entry {TARGET_IDX} IN PLACE @0x{entry_11_file_off:x}: "
      f"dw1 {t_dw1}->1, dw2 {t_dw2}->{EXISTING_RIGHTS}, "
      f"mod_id 0x{t_mod_id:x}->0x{EXISTING_MOD_ID:x} (ALIAS of entry 1's module, not new)")
print("rbase/rsize for entry 11: UNCHANGED (still full original range)")
print("TaskInfo.virt_space / virt_space_size: UNTOUCHED -- array does not move, count stays 63")
print(".secinfo: UNTOUCHED -- no new entry added, mod_id=0x81 already has one")

# ---------------------------------------------------------------------------
# 4. callsite: NOT TOUCHED (same as every prior diagnostic) -- content-blind
#    structural test, nothing can ever branch into the aliased region
#    differently than it already could via entry 1.
# ---------------------------------------------------------------------------
CALLSITE_FOFF = 0x38e5d8
old_bl = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
assert old_bl == bytes.fromhex('1e4900eb'), old_bl.hex()
print(f"callsite @0x{CALLSITE_FOFF:x} left UNTOUCHED (still {old_bl.hex()})")

# ---------------------------------------------------------------------------
# 5. no insertion at all -- entry 11's bytes were patched directly in
#    `data` above; the file is otherwise byte-for-byte identical to stock
#    2.80 (plus the sig-bypass from step 0). No e_shoff/e_shnum changes,
#    no new section.
# ---------------------------------------------------------------------------
open(OUT_PATH, 'wb').write(data)
print(f"\nWrote {OUT_PATH} ({len(data)} bytes, same size as input -- no insertion, no growth)")
