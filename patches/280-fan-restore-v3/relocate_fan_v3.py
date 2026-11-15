import struct, json, sys, os

# Rebuilds the `fan` handler + its full, freshly-re-derived dependency
# closure (see research/2026-11-06-v3-closure-rederivation.md -- this is
# NOT the old v1/v2 closure, which was missing 7 whole functions) from the
# genuine, hash-verified 2.77 elf.bin, and re-encodes every branch/adr/
# literal-load that crosses out of its own chunk for a new load address in
# 2.80's Health task.
#
# Usage: python3 relocate_fan_v3.py <extracted 2.77 elf.bin> <output fan_block_v3.bin>

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
# entirely, need re-encoding -- see cross_refs.json (711 such instructions,
# all captured via Ghidra's own reference resolution, not hand-decoded).
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
# Load the fully-resolved external map (134 stable-helper matches derived
# this session -- see research/2026-11-06-v3-closure-rederivation.md) plus
# the 711 cross-chunk/external instructions actually needing re-encoding.
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

def encode_ldr_literal(old_word, new_src_addr, new_target):
    cond = (old_word >> 28) & 0xF
    rd = (old_word >> 12) & 0xF
    disp = new_target - (new_src_addr + 8)
    u_bit = 1 if disp >= 0 else 0
    magnitude = abs(disp)
    assert magnitude <= 0xFFF, f"LDR-literal offset 0x{magnitude:x} exceeds 12-bit range"
    new_word = (cond << 28) | (0b01 << 26) | (0 << 25) | (1 << 24) | (u_bit << 23) | (0 << 22) | (1 << 20) | (0xF << 16) | (rd << 12) | magnitude
    return new_word

def decode_ldr_literal(word, src_addr):
    u_bit = (word >> 23) & 1
    imm12 = word & 0xFFF
    disp = imm12 if u_bit else -imm12
    return src_addr + 8 + disp

print(f"loaded {len(cross)} cross-chunk/external instructions to re-encode")
print(f"loaded {len(external_map)} resolved external targets")

# ---------------------------------------------------------------------------
# Extract raw bytes for all 16 chunks and assemble the new block.
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
# Final, independent re-verification pass: re-read every one of the 711
# patched instructions back out of the ASSEMBLED OUTPUT bytes (not the
# values computed during patching) and recheck. Catches any bug where the
# patch loop wrote to the wrong offset even if its own math was right.
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

open(OUT_PATH, 'wb').write(assembled)
print(f"\nwrote {OUT_PATH} ({len(assembled)} bytes)")
print(f"NEW_TASK_LOCAL_BASE=0x{NEW_TASK_LOCAL_BASE:x} NEW_TASK_LOCAL_SIZE=0x{TOTAL_SIZE:x}")
print(f"main_handler_new_task_local=0x{main_handler_new_task_local:x}")
