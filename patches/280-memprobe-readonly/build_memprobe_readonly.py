import json, struct, subprocess, sys, os, tempfile

# Minimal, read-only-only memory probe for iLO 2.80.
#
# Replaces the "help" CLI command's handler with a trimmed-down variant
# of patches/277-tools' memory probe (see asm/tools_readonly.S for the
# full rationale) -- read-only memory access only, dropping write,
# execute, and the malloc/free commands entirely. Same injection
# mechanism and same exact offset as patches/280-tools (which bricked on
# real hardware for a still-unidentified reason -- see
# research/2026-11-05-278-282-feasibility.md). This build exists to test
# whether the brick is specific to one of the removed capabilities
# (write, execute, or the two unverifiable external malloc/free
# references) or whether it's something else entirely (in which case
# this will brick too, and the mystery remains open).
#
# This patch does NOT touch VirtRange, .secinfo, or any task-local
# address-space structure at all -- it overwrites the content of an
# already-present, already-executable, already-correctly-permissioned
# module (the stock "help" command's own declared code slot), the exact
# same technique as patches/277-tools, which has strong (though not
# airtight) evidence of being sound on real hardware -- see
# research/2026-11-12-documentation-audit-untested-items.md.
#
# usage: python3 build_memprobe_readonly.py <extracted 2.80 elf.bin> <output path>
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))

data = bytearray(open(IN_PATH, 'rb').read())

# ---------------------------------------------------------------------------
# 0. sig-bypass (identical to every prior patch/diagnostic)
# ---------------------------------------------------------------------------
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass applied @0x{SIGBYPASS_OFFSET:x}")

# ---------------------------------------------------------------------------
# 1. the "help" command handler injection point -- same exact offset and
#    size as patches/280-tools. The genuine original content is derived
#    here from patches/280-tools/patch_userland.json's own recorded
#    prev_data (already committed to this repo as hex text, not a binary
#    blob) rather than stored as a separate proprietary .bin file in this
#    patch's own directory.
# ---------------------------------------------------------------------------
HELP_HANDLER_OFFSET = 0xaed07c
HELP_HANDLER_SIZE = 1136

TOOLS_280_PATCH = os.path.join(HERE, '..', '280-tools', 'patch_userland.json')
userland_patches = json.load(open(TOOLS_280_PATCH))
help_patch = next(p for p in userland_patches if p['remark'] == 'replace help with tools')
assert int(help_patch['offset'], 0) == HELP_HANDLER_OFFSET
assert help_patch['size'] == HELP_HANDLER_SIZE
expected_prev = bytes.fromhex(''.join(help_patch['prev_data'].split()))
assert len(expected_prev) == HELP_HANDLER_SIZE

actual_prev = bytes(data[HELP_HANDLER_OFFSET:HELP_HANDLER_OFFSET+HELP_HANDLER_SIZE])
assert actual_prev == expected_prev, \
    "genuine 'help' handler content at 0x%x does not match the recorded original -- " \
    "wrong input file, or this offset has changed" % HELP_HANDLER_OFFSET
print(f"genuine 'help' handler content @0x{HELP_HANDLER_OFFSET:x} ({HELP_HANDLER_SIZE} bytes) confirmed before patching")

# ---------------------------------------------------------------------------
# 2. the new, trimmed, read-only-only probe -- assembled fresh from
#    asm/tools_readonly.S every build, via the GNU ARM toolchain
#    (arm-none-eabi-as/objcopy). Every instruction, branch target, and
#    literal in this blob was independently verified once, by hand, by
#    disassembling the assembled output and confirming every branch/ADR
#    computation lands on its intended label -- not just trusted from the
#    assembler, and not just trusted to stay correct silently: this
#    rebuilds it from source every time rather than shipping a prebuilt
#    binary, so the committed source is always what actually gets flashed.
# ---------------------------------------------------------------------------
asm_src = os.path.join(HERE, 'asm', 'tools_readonly.S')
with tempfile.TemporaryDirectory() as tmpdir:
    obj_path = os.path.join(tmpdir, 'tools_readonly.o')
    bin_path = os.path.join(tmpdir, 'tools_readonly.bin')
    subprocess.run(['arm-none-eabi-as', '-o', obj_path, asm_src], check=True)
    subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', obj_path, bin_path], check=True)
    new_code = open(bin_path, 'rb').read()

assert len(new_code) <= HELP_HANDLER_SIZE, \
    f"assembled probe ({len(new_code)} bytes) does not fit in the available {HELP_HANDLER_SIZE}-byte slot"
print(f"new read-only probe: {len(new_code)} bytes (available: {HELP_HANDLER_SIZE})")

# content beyond what the new probe occupies is left as the genuine,
# untouched original bytes -- not zero-padded -- matching every prior
# diagnostic's discipline of touching the minimum possible.
new_content = new_code + expected_prev[len(new_code):]
assert len(new_content) == HELP_HANDLER_SIZE

data[HELP_HANDLER_OFFSET:HELP_HANDLER_OFFSET+HELP_HANDLER_SIZE] = new_content
print(f"wrote {len(new_code)} bytes of new code @0x{HELP_HANDLER_OFFSET:x}, "
      f"remaining {HELP_HANDLER_SIZE-len(new_code)} bytes left as genuine original content")

# ---------------------------------------------------------------------------
# 3. no VirtRange, .secinfo, or TaskInfo change of any kind -- this is a
#    pure content overwrite of an already-present, already-correctly-
#    permissioned module. Confirm that explicitly.
# ---------------------------------------------------------------------------
HEALTH_TASKINFO_FOFF = 0x166059c
task_type, virt_space_size, virt_space = struct.unpack_from('<III', data, HEALTH_TASKINFO_FOFF)
assert virt_space_size == 63, virt_space_size
print(f"Health TaskInfo: virt_space_size={virt_space_size} (UNTOUCHED, irrelevant to this patch -- "
      f"this patch is entirely within ConAppCLI's existing, already-present code, not Health's)")

open(OUT_PATH, 'wb').write(data)
print(f"\nWrote {OUT_PATH} ({len(data)} bytes, same size as input -- no insertion, no growth)")
