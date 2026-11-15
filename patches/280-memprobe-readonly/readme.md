# iLO 2.80 minimal read-only memory probe

**Result: CONFIRMED WORKING on real hardware, 2026-11-14.** First
hardware-confirmed live memory read on 2.80+. See
`research/2026-11-14-memprobe-readonly-confirmed-working.md` for the full
writeup, including an important command-syntax correction and a hardware
false-alarm from the first attempt that turned out to be user-input
related, not a firmware defect. Short version if you just want to use it:
see "Usage" below -- the original usage line here was wrong.

Tests whether `patches/280-tools`'s still-unidentified brick cause is
specific to one of its removed capabilities, by flashing a much smaller
version of the same technique that only implements read-only memory
access.

## Background

`patches/280-tools` (the full port of `patches/277-tools`'s Airbus
Security Lab memory probe) bricked on real hardware on 2026-11-05, for a
cause that was never identified -- ruled out as "the technique is broken
in general" (strong evidence 277-tools itself is sound, see
`research/2026-11-12-documentation-audit-untested-items.md`) and ruled
out as "the literal addresses were mis-ported" (independently verified
byte-identical function prologues across all six shipped firmware
versions, 2.77-2.82). Something else about that specific 1136-byte
payload is the cause, and nobody has isolated what.

## This build

Replaces the exact same injection point (`help` command handler, file
offset `0xaed07c`, same 1136-byte slot `patches/280-tools` used) with a
hand-trimmed 208-byte variant (`asm/tools_readonly.S`) that keeps only
the `r` (read memory) command and drops:

- **`w` (write memory)**: the single riskiest primitive in the original,
  never needed to answer this question.
- **`x` (execute)**: `blx` to an arbitrary, unvalidated user-supplied
  address -- the second-riskiest primitive.
- **`a`/`f` (malloc/free)**: the *only* code paths in the original that
  call external helpers (`libc_malloc_fn`/`libc_free_fn`) whose targets
  research flagged as unverifiable -- "reference an address outside this
  firmware image's own file bounds entirely... can't be statically
  verified either way for any version"
  (`research/2026-11-05-278-282-feasibility.md`). Removing them means
  every external reference this build makes (`GrabContext_fn`,
  `printToShell_fn`) is one this session independently re-verified as a
  real function prologue in the genuine stock firmware (not just trusted
  from prior research).
- **The `sprintf` trampoline**: confirmed, via a full Ghidra instruction
  scan this session, to be dead code in the original -- never called by
  anything, so dropping it changes nothing behaviorally.

Everything kept (prologue, `GrabContext` bootstrap, the hex-digit
address-parsing loop, the single-command dispatch, the default/fallback
echo, `cmd_read`) is structurally identical to the original, just
re-assembled without the removed pieces.

Assembled fresh every build (not shipped as a prebuilt binary) with
`arm-none-eabi-as`/`objcopy` (GNU ARM toolchain, not keystone --
keystone-engine's Python bindings failed to load on this machine and
failed to build from source in a Linux container; the GNU toolchain
produces equivalent machine code). Every instruction, branch target, and
literal in the assembled 208-byte blob was independently verified once,
by hand, by disassembling the output and confirming every branch/`ADR`
computation lands exactly on its intended label -- not just trusted from
the assembler.

The remaining 928 bytes of the 1136-byte slot are left as the genuine,
untouched original "help" handler content (not zero-padded), matching
the minimal-footprint discipline of every diagnostic in this project.

This patch makes **no** change to VirtRange, `.secinfo`, or any
task-local address-space structure. It overwrites the content of an
already-present, already-executable, already-correctly-permissioned
module -- the same technique as `patches/277-tools`, entirely unrelated
to the now-closed VirtRange re-attribution investigation.

## Result (2026-11-14)

Boots clean (full `diag9` checklist passed: no POST 270, correct version
readback, ping, SSH, web UI). **Confirmed isolated to one of the removed
capabilities** -- read-only at this exact slot is safe, so `280-tools`'s
still-unexplained brick is narrowed specifically to write, execute, or the
malloc/free references, not the slot or the bootstrap mechanism. This is
also the project's first confirmed live memory-read capability on 2.80+.
Full narrative, including a hardware false-alarm from a user-input mistake
on the first attempt (not a firmware defect) and independent verification
of the read data against an ARM disassembly: see
`research/2026-11-14-memprobe-readonly-confirmed-working.md`.

## Usage (corrected 2026-11-14 -- the original wording below was wrong)

`help r<ADDR> <N>` where:

- **`<ADDR>` is NOT standard hex.** Each nibble is encoded as a letter
  `A`-`P` (A=0, B=1, ... P=15), inherited unchanged from the original
  Airbus/phoenixdev `tools.S`. Typing ordinary hex digits (`0`-`9`/`a`-`f`)
  will silently resolve to address `0` instead of erroring -- which is
  exactly what happened on this build's first hardware test and hung that
  SSH session (see the research note for why: a null-pointer read, not a
  general firmware brick -- new connections were unaffected). Example:
  `0x21F9C` -> nibbles `2,1,F,9,C` -> `CBPJM`.
- **`<N>` is a separate, space-separated argument, and its first raw byte
  (not parsed as a number) is the read count.** E.g. a literal `0`
  character (ASCII `0x30`) requests 48 bytes. This was never a
  user-settable "count field" in the way earlier readmes (including this
  one) assumed -- see the research note for how this was finally pinned
  down, resolving a question open since `research/2022-02-17-docs.md`.
- **The printed address for each byte is off by one** (prints
  `byte_address + 1`, not the byte's own address) -- subtract 1 from every
  line before using it.
- **Scope**: this reads memory inside the **ConAppCLI** (SSH/CLI shell)
  task's own address partition only, not Health's -- see the research note
  for why that matters for this project's actual `fan`-restoration goal.

Full example that produces real, verifiable output: `help rCBPJM 0` reads
48 bytes starting at `GrabContext_fn`'s own address, which decodes as a
textbook ARM function prologue -- see the research note for the byte-level
verification.

## What was verified (static)

- Genuine "help" handler content at the injection offset reconfirmed,
  byte-for-byte, against the recorded original before patching.
- Both external function addresses (`GrabContext_fn`, `printToShell_fn`)
  independently disassembled from the genuine stock firmware and
  confirmed to be real ARM function prologues (`mov ip,sp; push {...};
  sub fp,ip,#N`), not just trusted from prior research.
- Every branch target and `ADR` computation in the assembled 208-byte
  blob manually verified against its intended label.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region matches exactly.
- Built via the deterministic `tools/package_build.sh` pipeline.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes). Only
`asm/tools_readonly.S` (this session's own assembly source) is committed
-- the build script assembles it fresh every run and derives the genuine
original "help" handler content it replaces from
`patches/280-tools/patch_userland.json`'s own already-committed
`prev_data` field, so no proprietary firmware bytes are stored anywhere
in this patch's own directory.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`cade45d436bda777c6d85b79b0470462b93f7159` (SHA1) -- confirmed identical
before and after the build script was refactored to assemble on the fly
instead of reading a prebuilt binary.
