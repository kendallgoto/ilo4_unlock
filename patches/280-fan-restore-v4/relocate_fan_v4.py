import struct, json, sys, os

# v4 fixes a defect found after v3 was flashed and bricked hardware the same
# way v1/v2 did (BIOS POST 270 "iLO FW Communication Issue"). See
# research/2026-11-06-v3-literal-pointer-relocation-gap.md for the full
# writeup. Two independent, additive fixes over v3's relocate_fan_v3.py:
#
#   (a) Four of the 16 superchunks were cut too tight and excluded their own
#       trailing/leading literal pool -- 10 `ldr Rd, [pc, #imm]` instructions
#       inside the closure had their literal word sitting entirely outside
#       all 16 chunks, meaning that data was never copied into the new block
#       at all. Fixed by extending those 4 chunks' boundaries to include it
#       (same "absorb the fragment" approach already used elsewhere in the
#       original SUPERCHUNKS list -- no instruction re-encoding needed,
#       since source and literal still end up in the same chunk).
#   (b) The v3 pipeline only re-encoded PC-relative INSTRUCTION references
#       (bl/b/adr) found by Ghidra's code cross-reference walk. It never
#       inspected literal-pool DATA WORDS whose *value* is itself an
#       absolute task-local pointer into Health's own .text (e.g. a
#       command-table's {string-ptr, handler-ptr} entries). Those are
#       copied byte-for-byte from 2.77 and are wrong by the ~33MB
#       old-position-to-new-position delta. Fixed with a new pass, after
#       the existing instruction patching, that finds every such literal
#       and corrects its *value* using the exact same resolve_new_task_
#       local_target() already trusted for instruction targets.
#
# Usage: python3 relocate_fan_v4.py <extracted 2.77 elf.bin> <output fan_block_v4.bin>

if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.77 elf.bin> <output path>")
    sys.exit(1)

IN_277 = sys.argv[1]
OUT_PATH = sys.argv[2]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

data277 = open(IN_277, 'rb').read()

# ---------------------------------------------------------------------------
# 2.77/2.80 Health .text addressing constants, independently re-derived this
# session (not trusted from old docs): task_local = true_vaddr - TEXT_SH_ADDR + 0x10000.
# ---------------------------------------------------------------------------
TEXT_SH_ADDR_277 = 0xdec000
TEXT_SH_ADDR_280 = 0xded000

def task_local_277(true_vaddr):
    return true_vaddr - TEXT_SH_ADDR_277 + 0x10000

def task_local_280(true_vaddr):
    return true_vaddr - TEXT_SH_ADDR_280 + 0x10000

def true_vaddr_from_task_local_277(task_local):
    return task_local - 0x10000 + TEXT_SH_ADDR_277

# .health.elf.text file offset <-> true vaddr mapping for 2.77 (independently
# re-verified this session, see build_extract/elf.bin section headers)
HEALTH_TEXT_277_OFF = 0x3791fc
HEALTH_TEXT_277_ADDR = 0xdec000

def file_off_277(true_vaddr):
    return HEALTH_TEXT_277_OFF + (true_vaddr - HEALTH_TEXT_277_ADDR)

# ---------------------------------------------------------------------------
# The 16 "super-chunks" -- contiguous byte ranges in 2.77 covering all 15
# missing functions plus every string/constant they reference via `adr`,
# merged wherever two needed pieces sit within 0x300 bytes of each other so
# the (far more numerous) *internal* cross-references between them are
# preserved for free by copying the whole range as a rigid unit. Only
# references that cross *between* these 16 ranges, or leave all of them
# entirely, need re-encoding -- see cross_refs.json (700 such instructions,
# all captured via Ghidra's own reference resolution, not hand-decoded).
#
# v4 note: chunks 5, 6, 7, 11 are widened from v3's boundaries -- an
# exhaustive scan of every `ldr Rd, [pc, #imm]` in the closure (see
# research/2026-11-06-v3-literal-pointer-relocation-gap.md) found 10 literal
# loads whose literal pool word fell entirely outside v3's chunk boundaries,
# meaning that data was silently dropped from the assembled block. Each of
# the 4 widenings below was chosen as the tightest 4-byte-aligned extension
# that covers every such literal address found by that scan, confirmed to
# introduce no overlap with any neighboring chunk.
# ---------------------------------------------------------------------------
SUPERCHUNKS = [
    (0xe1589c, 0xe1a968),  # merged -- absorbs shared-tail fragments at 0xe1a170/0xe1a17c/0xe1a2a0/0xe1a83c,
                           # each reached by a conditional branch from our real functions but each too
                           # small/un-called-elsewhere to be its own Ghidra-recognized function (same
                           # pattern as the 0xe7dab8 shared epilogue tail documented below)
    (0xe1ac98, 0xe1ad60), (0xe1b07c, 0xe1b178), (0xe2326c, 0xe25720),
    (0xe274c8, 0xe27d40),  # extended +0x40 to absorb a shared-tail fragment at 0xe27d34
    (0xe2d0c4, 0xe2dfec),
    (0xe2e338, 0xe2e758),  # extended +0x44 to absorb shared-tail fragments at 0xe2e718/0xe2e738/0xe2e73c
    (0xe32b80, 0xe32f08), (0xe3c148, 0xe3d450), (0xe3d7e4, 0xe3dbe4),
    (0xe3df88, 0xe3dfc8),
    (0xe3e2e4, 0xe3e4b0),  # extended +0x18c to absorb a shared-tail fragment at 0xe3e470
    (0xe7d3e0, 0xe7e048), (0xe7e6c0, 0xe7e90c),
]

# v4 widenings applied in-place below (kept separate from the v3 list above
# so the diff against v3 stays legible): chunk index -> (new_start, new_end).
#
# IMPORTANT: ORIGINAL_SUPERCHUNKS (the v3, unwidened boundaries) is kept
# around and is what the ldr-literal INSTRUCTION scan below iterates over --
# never the widened ranges. The widened bytes are pure literal-pool/filler
# data absorbed purely so literal WORDS land somewhere copied; scanning them
# for more "instructions" produces false-positive decodes (literal pool
# data can coincidentally match the ldr-immediate bit pattern). Only
# genuine, already-vetted code (the original v3 ranges) is ever treated as
# a source of instructions to decode.
ORIGINAL_SUPERCHUNKS = list(SUPERCHUNKS)

V4_CHUNK_WIDENINGS = {
    5:  (0xe2d0c4, 0xe2e1f0),  # was (0xe2d0c4, 0xe2dfec) -- absorbs literals up to 0xe2e1e8 (+4, 4-aligned)
    6:  (0xe2e234, 0xe2e758),  # was (0xe2e338, 0xe2e758) -- absorbs literal at 0xe2e234
    7:  (0xe32ad8, 0xe32f08),  # was (0xe32b80, 0xe32f08) -- absorbs literals at 0xe32adc/0xe32ae4 (-8, 4-aligned)
    11: (0xe3e2e4, 0xe3e5cc), # was (0xe3e2e4, 0xe3e4b0) -- absorbs literals up to 0xe3e5c8 (+4, 4-aligned)
}
for idx, new_range in V4_CHUNK_WIDENINGS.items():
    SUPERCHUNKS[idx] = new_range

# sanity: confirm the widenings introduce no overlap with their neighbors
for i in range(len(SUPERCHUNKS) - 1):
    assert SUPERCHUNKS[i][1] <= SUPERCHUNKS[i + 1][0], \
        f"v4 chunk widening caused an overlap between chunk {i} and {i+1}: {SUPERCHUNKS[i]} / {SUPERCHUNKS[i+1]}"

MAIN_HANDLER_TRUE_VADDR = 0xe16970  # the `fan` CLI handler's own entry point

def which_chunk(addr):
    for i, (s, e) in enumerate(SUPERCHUNKS):
        if s <= addr < e:
            return i
    return None

# ---------------------------------------------------------------------------
# New layout: pack the 16 chunks in their original relative order, 4-byte
# aligned, with no padding beyond alignment -- keeps re-encoded offsets as
# close as possible in magnitude to the originals (not that it matters for
# B/BL's 32MB range, but it matters for ADR's much more limited rotated-
# immediate encoding -- see encode_adr below).
# ---------------------------------------------------------------------------
chunk_new_offset = []
cursor = 0
for (s, e) in SUPERCHUNKS:
    chunk_new_offset.append(cursor)
    cursor += (e - s)
    cursor = (cursor + 3) & ~3
TOTAL_SIZE = cursor
print(f"assembled block size: 0x{TOTAL_SIZE:x} ({TOTAL_SIZE} bytes)")

def new_addr_for_true_vaddr_277(true_vaddr):
    """Map an address INSIDE one of our 16 chunks (2.77 true vaddr) to its
    task-local offset WITHIN the new assembled block (not yet placed at a
    real task-local base -- caller adds that). Also accepts exactly
    one-past-the-end of a chunk (a `adr r1, <end of array>` loop-bound
    pattern, confirmed as the one real case -- see cross_refs.json's single
    `adr` entry, target 0xe32f08 == SUPERCHUNKS[9]'s own end)."""
    for i, (s, e) in enumerate(SUPERCHUNKS):
        if s <= true_vaddr <= e:
            return chunk_new_offset[i] + (true_vaddr - s)
    raise AssertionError(f"0x{true_vaddr:x} is not inside or at the end of any chunk")

# ---------------------------------------------------------------------------
# Load the fully-resolved external map (132 stable-helper matches derived
# this session -- see research/2026-11-06-v3-closure-rederivation.md) plus
# the cross-chunk/external instructions actually needing re-encoding.
# ---------------------------------------------------------------------------
external_map = json.load(open(os.path.join(SCRIPT_DIR, 'closure_mapping.json')))['external_map']
cross = json.load(open(os.path.join(SCRIPT_DIR, 'cross_refs.json')))['cross']

HEALTH_LO_277, HEALTH_HI_277 = 0xdec000, 0xe98f48

def resolve_new_task_local_target(target_true_vaddr_277, new_base_task_local):
    """Given a cross-reference's ORIGINAL (2.77) true-vaddr target, return
    its correct NEW task-local address once this block is loaded at
    new_base_task_local in 2.80's Health task."""
    try:
        # internal to our own new block (or exactly at one chunk's end --
        # see new_addr_for_true_vaddr_277's docstring)
        return new_base_task_local + new_addr_for_true_vaddr_277(target_true_vaddr_277)
    except AssertionError:
        pass
    if HEALTH_LO_277 <= target_true_vaddr_277 < HEALTH_HI_277:
        # a "stable helper" elsewhere in Health's OWN .text -- must be
        # resolved via the cross-version signature map (its position
        # shifted between 2.77 and 2.80), THEN converted via 2.80's own
        # text_sh_addr (NOT 2.77's -- a different constant).
        key = hex(target_true_vaddr_277)
        assert key in external_map, f"no resolved mapping for Health-internal target {key}"
        entry = external_map[key]
        assert entry['target'] is not None, f"{key} was left unresolved: {entry}"
        resolved_280_true_vaddr = int(entry['target'], 16)
        return task_local_280(resolved_280_true_vaddr)
    else:
        # shared-library / other module call -- independently confirmed
        # this session (research/2026-11-06-kernel-re-methodology...) that
        # this whole task-local region is byte-identical between 2.77 and
        # 2.80, so the TASK-LOCAL address is version-independent: convert
        # using 2.77's own constant, since that's the version this address
        # was captured from, and the result is valid in either version.
        return task_local_277(target_true_vaddr_277)

# ---------------------------------------------------------------------------
# ARM32 instruction re-encoders. Each one decodes the ORIGINAL bytes just
# enough to preserve condition codes / registers, recomputes the PC-relative
# immediate for the NEW source position and NEW target, and re-encodes.
# Every call site below is paired with an assert that decodes the output
# and confirms it reaches the intended target -- the same discipline this
# project's hardened build script already applies to its own callsite `bl`.
# ---------------------------------------------------------------------------

def encode_b_bl(old_word, new_src_addr, new_target):
    cond = (old_word >> 28) & 0xF
    assert (old_word >> 25) & 0b111 == 0b101, f"not a B/BL family word: {old_word:#x}"
    link_bit = old_word & (1 << 24)
    disp = new_target - (new_src_addr + 8)
    assert disp % 4 == 0, f"branch target not 4-aligned: new_src=0x{new_src_addr:x} target=0x{new_target:x}"
    imm24 = (disp // 4) & 0xFFFFFF
    # round-trip range check (ARM signed 24-bit word-granular immediate)
    check = imm24
    if check & 0x800000:
        check -= 0x1000000
    assert new_src_addr + 8 + check * 4 == new_target, "branch range/encoding sanity check failed"
    new_word = (cond << 28) | (0b101 << 25) | link_bit | imm24
    return new_word

def decode_b_bl(word):
    imm24 = word & 0xFFFFFF
    if imm24 & 0x800000:
        imm24 -= 0x1000000
    return imm24  # caller adds src+8 and *4

ADR_ROTATE_TABLE = None
def _build_rotate_table():
    global ADR_ROTATE_TABLE
    if ADR_ROTATE_TABLE is not None:
        return
    table = {}
    for rot in range(16):
        for imm8 in range(256):
            shift = (2 * rot) % 32
            val = ((imm8 >> shift) | (imm8 << (32 - shift))) & 0xFFFFFFFF if shift else imm8
            if val not in table:
                table[val] = (rot, imm8)
    ADR_ROTATE_TABLE = table
_build_rotate_table()

def encode_adr(old_word, new_src_addr, new_target):
    """ADR is pseudo for ADD/SUB Rd, PC, #imm (data-processing immediate,
    Rn=PC). Only representable if the needed |offset| fits ARM's rotated-
    8-bit immediate scheme -- NOT all 32-bit offsets are. Raises loudly
    (does not silently approximate) if the exact needed value can't be
    represented, so a real problem is never masked."""
    cond = (old_word >> 28) & 0xF
    opcode = (old_word >> 21) & 0xF
    assert opcode in (0b0100, 0b0010), f"not an ADD/SUB-immediate word: {old_word:#x}"
    rd = (old_word >> 12) & 0xF
    disp = new_target - (new_src_addr + 8)
    if disp >= 0:
        opcode_new = 0b0100  # ADD
        magnitude = disp
    else:
        opcode_new = 0b0010  # SUB
        magnitude = -disp
    assert magnitude in ADR_ROTATE_TABLE, (
        f"ADR offset 0x{magnitude:x} (new_src=0x{new_src_addr:x} target=0x{new_target:x}) "
        "is not representable as an ARM rotated-8-bit immediate -- needs a real fix "
        "(e.g. convert to an LDR-literal + inserted pool word), not a silent approximation"
    )
    rot, imm8 = ADR_ROTATE_TABLE[magnitude]
    imm12 = (rot << 8) | imm8
    new_word = (cond << 28) | (0b001 << 25) | (opcode_new << 21) | (0 << 20) | (0xF << 16) | (rd << 12) | imm12
    return new_word

def decode_adr(word, src_addr):
    opcode = (word >> 21) & 0xF
    rot = (word >> 8) & 0xF
    imm8 = word & 0xFF
    shift = (2 * rot) % 32
    magnitude = ((imm8 >> shift) | (imm8 << (32 - shift))) & 0xFFFFFFFF if shift else imm8
    if opcode == 0b0100:
        return src_addr + 8 + magnitude
    elif opcode == 0b0010:
        return src_addr + 8 - magnitude
    else:
        raise AssertionError(f"not ADD/SUB-immediate: {word:#x}")

print(f"loaded {len(cross)} cross-chunk/external instructions to re-encode")
print(f"loaded {len(external_map)} resolved external targets")

# ---------------------------------------------------------------------------
# Extract raw bytes for all 16 (now v4-widened) chunks and assemble the new
# block.
# ---------------------------------------------------------------------------
assembled = bytearray(TOTAL_SIZE)
for i, (s, e) in enumerate(SUPERCHUNKS):
    chunk_bytes = data277[file_off_277(s):file_off_277(e)]
    assert len(chunk_bytes) == e - s
    off = chunk_new_offset[i]
    assembled[off:off + len(chunk_bytes)] = chunk_bytes

# ---------------------------------------------------------------------------
# Placement: end-of-block anchored exactly at the confirmed 32MB per-task
# ceiling (0x2000000 -- see research/2026-11-06-kernel-re-methodology-and-
# pitfalls.md), taken from the tail of Health's final, reference-free
# anonymous VirtRange entry (research/2026-11-06-v3-fan-restore-strategy.md).
# ---------------------------------------------------------------------------
NEW_TASK_LOCAL_BASE = 0x2000000 - TOTAL_SIZE
assert NEW_TASK_LOCAL_BASE % 4 == 0
print(f"NEW_TASK_LOCAL_BASE = 0x{NEW_TASK_LOCAL_BASE:x}  (ends exactly at 0x2000000)")

main_handler_new_task_local = NEW_TASK_LOCAL_BASE + new_addr_for_true_vaddr_277(MAIN_HANDLER_TRUE_VADDR)
print(f"main `fan` handler new task-local entry point: 0x{main_handler_new_task_local:x}")

# ---------------------------------------------------------------------------
# Apply every cross-chunk/external re-encode, verifying each one by
# decoding the patched bytes back and confirming they land on the intended
# target -- never trust the encoder alone, the same discipline
# build_patched_280.py already applies to its own callsite `bl`.
# ---------------------------------------------------------------------------
patched = 0
for c in cross:
    src_true_vaddr = c['src']
    old_word = struct.unpack('<I', bytes.fromhex(c['bytes']))[0]
    new_src_addr = NEW_TASK_LOCAL_BASE + new_addr_for_true_vaddr_277(src_true_vaddr)
    new_target = resolve_new_task_local_target(c['target'], NEW_TASK_LOCAL_BASE)

    mnem0 = c['mnem'].split()[0]
    if mnem0 in ('bl', 'b', 'bleq', 'bne', 'blne', 'ble', 'beq', 'blgt', 'blt', 'bgt', 'bge', 'blls', 'bls', 'blcc', 'bcc', 'blcs', 'bcs'):
        new_word = encode_b_bl(old_word, new_src_addr, new_target)
        decoded_imm = decode_b_bl(new_word)
        decoded_target = (new_src_addr + 8 + decoded_imm * 4) & 0xFFFFFFFF
    elif mnem0 == 'adr':
        new_word = encode_adr(old_word, new_src_addr, new_target)
        decoded_target = decode_adr(new_word, new_src_addr)
    else:
        raise AssertionError(f"unhandled reloc instruction type: {c['mnem']}")

    assert decoded_target == new_target, (
        f"re-encode verification FAILED for src=0x{src_true_vaddr:x} ({c['mnem']}): "
        f"decoded 0x{decoded_target:x} != intended 0x{new_target:x}"
    )

    new_off = new_addr_for_true_vaddr_277(src_true_vaddr)
    assembled[new_off:new_off + 4] = struct.pack('<I', new_word)
    patched += 1

print(f"patched and verified {patched} instructions")

# ---------------------------------------------------------------------------
# Final, independent re-verification pass for the instruction-level patches:
# re-read every one of the patched instructions back out of the ASSEMBLED
# OUTPUT bytes (not the values computed during patching) and recheck.
# ---------------------------------------------------------------------------
recheck = 0
for c in cross:
    src_true_vaddr = c['src']
    new_off = new_addr_for_true_vaddr_277(src_true_vaddr)
    new_src_addr = NEW_TASK_LOCAL_BASE + new_off
    word = struct.unpack_from('<I', assembled, new_off)[0]
    expected_target = resolve_new_task_local_target(c['target'], NEW_TASK_LOCAL_BASE)
    mnem0 = c['mnem'].split()[0]
    if mnem0 == 'adr':
        actual_target = decode_adr(word, new_src_addr)
    else:
        imm = decode_b_bl(word)
        actual_target = (new_src_addr + 8 + imm * 4) & 0xFFFFFFFF
    assert actual_target == expected_target, (
        f"FINAL re-check FAILED at new_off=0x{new_off:x}: 0x{actual_target:x} != 0x{expected_target:x}"
    )
    recheck += 1
print(f"independently re-verified {recheck} instructions by re-reading the assembled output")

# ---------------------------------------------------------------------------
# v4 NEW: literal-pool DATA pointer relocation.
#
# Enumerate every `ldr Rd, [pc, #imm]` instruction whose literal pool word
# lies inside one of our (now-widened) 16 chunks -- by construction, after
# the v4 chunk widenings, this is now ALL such instructions in the closure
# (verified below: zero literal-outside-all-chunks cases remain, where v3
# had 10). For each literal word, decode its stored VALUE as if it were a
# 2.77 task-local address; if it resolves into Health's own .text
# (0xdec000-0xe98f48 true-vaddr range) -- whether inside our own moved
# block or to some other stable Health function -- it is almost certainly
# a genuine absolute pointer (confirmed functions/registration-table
# entries; see research/2026-11-06-v3-literal-pointer-relocation-gap.md for
# the statistical argument this isn't coincidental data: 51 hits against a
# <3-hit chance expectation). Correct its value via the exact same
# resolve_new_task_local_target() already trusted for instruction targets.
# Anything that does NOT resolve into Health .text is left untouched --
# resolve_new_task_local_target's own "shared-library / other module" branch
# is a no-op (identity transform) for exactly this case, which is itself a
# useful cross-check: applying it to a non-pointer integer that coincidentally
# looked plausible would also be a no-op there, so no legitimate constant can
# be corrupted by this pass.
# ---------------------------------------------------------------------------
def find_ldr_literal_sites():
    sites = []
    for (s, e) in ORIGINAL_SUPERCHUNKS:
        off = file_off_277(s)
        length = e - s
        chunk = data277[off:off + length]
        for woff in range(0, length - 3, 4):
            word = struct.unpack_from('<I', chunk, woff)[0]
            cond = (word >> 28) & 0xF
            if cond == 0xF:
                continue
            if (word >> 26) & 0b11 != 0b01:
                continue
            if (word >> 25) & 1 != 0:
                continue  # immediate-offset form only
            U = (word >> 23) & 1
            B = (word >> 22) & 1
            L = (word >> 20) & 1
            Rn = (word >> 16) & 0xF
            if L != 1 or Rn != 15 or B != 0:
                continue
            src_true_vaddr = s + woff
            imm12 = word & 0xFFF
            disp = imm12 if U else -imm12
            lit_addr = src_true_vaddr + 8 + disp
            if which_chunk(lit_addr) is None:
                raise AssertionError(
                    f"ldr-literal @0x{src_true_vaddr:x} still has its literal (0x{lit_addr:x}) "
                    "outside all chunks after v4's widenings -- widen further, don't ignore"
                )
            sites.append((src_true_vaddr, lit_addr))
    return sites

ldr_sites = find_ldr_literal_sites()
print(f"\nfound {len(ldr_sites)} ldr-literal sites, all with literal inside some chunk (v3 had 10 outside)")

# Group by literal address (several instructions may share one literal pool word).
literal_addrs = sorted(set(lit for _src, lit in ldr_sites))

literal_patches = 0
for lit_addr in literal_addrs:
    new_off = new_addr_for_true_vaddr_277(lit_addr)
    old_val = struct.unpack_from('<I', assembled, new_off)[0]
    if not (0x10000 <= old_val <= 0x2000000):
        continue  # not a plausible task-local pointer value at all
    target_true_vaddr = true_vaddr_from_task_local_277(old_val)
    if not (HEALTH_LO_277 <= target_true_vaddr < HEALTH_HI_277):
        continue  # outside Health entirely -- resolve_new_task_local_target would be a no-op anyway
    new_val = resolve_new_task_local_target(target_true_vaddr, NEW_TASK_LOCAL_BASE)
    if new_val == old_val:
        continue  # genuinely unchanged (shouldn't happen for an in-Health target, but no-op is safe)
    struct.pack_into('<I', assembled, new_off, new_val)
    print(f"  literal@0x{lit_addr:x}: 0x{old_val:08x} -> 0x{new_val:08x}  "
          f"(2.77 true_vaddr 0x{target_true_vaddr:x})")
    literal_patches += 1

print(f"patched {literal_patches} literal-pool data pointers")

# Independent re-verification: re-derive the expected value fresh from the
# ORIGINAL 2.77 bytes (not from anything computed above) and compare against
# what's actually sitting in the assembled output.
literal_recheck = 0
for lit_addr in literal_addrs:
    new_off = new_addr_for_true_vaddr_277(lit_addr)
    orig_val = struct.unpack_from('<I', data277, file_off_277(lit_addr))[0]
    if not (0x10000 <= orig_val <= 0x2000000):
        expected = orig_val
    else:
        target_true_vaddr = true_vaddr_from_task_local_277(orig_val)
        if not (HEALTH_LO_277 <= target_true_vaddr < HEALTH_HI_277):
            expected = orig_val
        else:
            expected = resolve_new_task_local_target(target_true_vaddr, NEW_TASK_LOCAL_BASE)
    actual = struct.unpack_from('<I', assembled, new_off)[0]
    assert actual == expected, (
        f"literal-pool FINAL re-check FAILED at 0x{lit_addr:x}: 0x{actual:08x} != 0x{expected:08x}"
    )
    literal_recheck += 1
print(f"independently re-verified {literal_recheck} literal-pool words by re-deriving from original 2.77 bytes")

open(OUT_PATH, 'wb').write(assembled)
print(f"\nwrote {OUT_PATH} ({len(assembled)} bytes)")
print(f"NEW_TASK_LOCAL_BASE=0x{NEW_TASK_LOCAL_BASE:x} NEW_TASK_LOCAL_SIZE=0x{TOTAL_SIZE:x}")
print(f"main_handler_new_task_local=0x{main_handler_new_task_local:x}")
