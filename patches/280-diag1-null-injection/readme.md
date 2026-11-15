# iLO 2.80 Diagnostic Build: structural injection only, no fan code -- NOT A REAL PATCH

**Purpose: isolate why v1/v2/v3/v4 all bricked identically (BIOS POST 270
"iLO FW Communication Issue"), despite each fixing a different, real,
previously-undiagnosed bug in the restored fan code's relocation.**

## Why this build exists

v1 through v4 each fixed a distinct, confirmed root cause:
- v1: BSS/live-memory collision
- v2: 32MB per-task address-space ceiling violation
- v3: missing/incomplete dependency closure
- v4: unrelocated literal-pool absolute pointers (see
  `research/2026-11-06-v3-literal-pointer-relocation-gap.md`)

All four were hardware-flashed. All four produced the **identical** BIOS
POST 270 error, during boot, before `fan` could ever be invoked.

Meanwhile, `patches/280/readme.md` documents a sig-bypass-only build
(**hardware-confirmed working** on a real DL380 Gen9, 2026-11-05) that does
none of the fan-restore machinery at all and boots completely normally.

Four different, real fixes to the *content and relocation* of the injected
fan closure, each producing the same symptom, is the signal called out in
this project's own debugging discipline: stop fixing symptoms of one
hypothesis and question whether the shared mechanism -- not the thing that
keeps changing -- is the actual fault. What's common to v1-v4 and absent
from the confirmed-working sig-bypass-only build:

1. A new ELF section appended to the firmware image
2. The Health task's VirtRange table extended from 63 to 64 entries
   (reclaiming the tail of the last anonymous entry)
3. A new `.secinfo` linked-list entry appended
4. The callsite `bl` repointed to jump into the new region

v1-v4 only ever varied #4's target and the content backing it. None of
them tested whether #1-#3 alone -- registering a new module with the RTOS,
regardless of what's in it or whether it's ever reached -- is itself safe.

## What this build does

Exact same structural additions and geometry as v4 (same VirtRange reclaim
math, same `.secinfo` entry shape, same section size -- taken directly from
`fan_block_v4.bin`'s length so the layout is byte-for-byte comparable to
what v4 actually tested) with two deliberate differences:

1. **The injected section's content is all-zero bytes**, not real
   relocated code. If anything walks/validates/executes this region at
   boot, it sees zero bytes.
2. **The callsite `bl` at 0x38e5d8 is left completely untouched** (still
   the original disabled branch from stock 2.80). Nothing can ever branch
   into the new region, manually or automatically.

Build script: `build_diag1.py`, derived directly from
`patches/280-fan-restore-v4/build_patched_280.py` with the content and
callsite-patch steps stripped as described above; every other derivation
(section header parsing, Health TaskInfo/SecInfo/VirtRange discovery,
ceiling/ collision checks) is identical and independently re-verified
against the same genuine 2.80 extraction.

## How to read the result

- **If this still produces BIOS POST 270**: the fault is in the structural
  registration itself -- the new section, the 64-entry VirtRange table, or
  the new `.secinfo` entry -- evaluated at boot before anything related to
  `fan` ever executes. The entire "extend VirtRange / add a .secinfo
  entry / append a section" strategy used by v1-v4 would need to be
  reconsidered from scratch; further relocation-correctness fixes to the
  fan closure's content would not help, because this build has no
  meaningful content at all and still fails the same way.
- **If this boots fine** (no 270, normal boot): the structural registration
  mechanism is sound. The fault is specific to the injected code's content
  or to actually reaching it -- meaning v4's literal-pointer fix direction
  was a real, necessary fix, but something else in the restored closure or
  in how it's invoked remains broken. The next step would be a staged
  follow-up (e.g. point the callsite at a trivial stub instead of v4's
  real closure, to further isolate "is it reaching the new code at all"
  from "is the restored fan code itself still wrong somewhere v4 didn't
  check").

## What was verified (static)

- Same geometry assertions as v4: ceiling respected, no VirtRange overlaps,
  anonymous-region reclaim confirmed safe.
- Full compression round-trip: decompressed ELF and kernel sections pulled
  back out of `firmware.bin.backdoored.toflash` and confirmed byte-for-byte
  identical to the patched inputs; raw bootloader region confirmed to match
  exactly (note for reproducing this check: the bootloader region in the
  final `.toflash` sits at `firmware.map['BOOTLOADER'] -
  firmware.map['BOOTLOADER_HDR']`, not at offset 0 -- and the compressed
  ELF/kernel regions each have a 4-byte little-endian compressed-length
  prefix immediately before the compressed bytes, written by
  `ilo4_repack.py`, which must be skipped before calling
  `ilo4lib.decompress_all`).

## Build

Not flashed yet -- this file is not in the repo's output artifact because
it is proprietary HP firmware content; it was built into the session
scratchpad only, following the same steps as v4:

1. `python3 build_diag1.py <extracted 2.80 elf.bin> <output elf.bin>`
2. Apply `patches/280/patch_bootloader.json` / `patch_kernel.json` to the
   extracted `bootloader.bin` / `kernel_main.bin`.
3. `ilo4_repack.py <genuine 2.80 firmware.bin> firmware.map <patched elf.bin> <patched kernel_main.bin> <patched bootloader.bin>`
   (via `docker run --rm -v ... python:2.7`, same as v4).

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`c8d60efc90e27e1a1dcf717743fdb0eed2dfba87` (SHA1).
