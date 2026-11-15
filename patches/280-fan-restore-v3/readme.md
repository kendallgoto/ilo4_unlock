# iLO 2.80 Patch (signature-bypass + full `fan` command backport, v3) -- EXPERIMENTAL, NOT HARDWARE-TESTED

**Status: static build verified end-to-end through a clean repack. Has NOT been flashed to real hardware.**

Supersedes `patches/280-fan-restore-v2`, which almost certainly bricked
hardware by placing the restored code past a hard, universal 32MB per-task
Address Space ceiling (see `research/2026-11-06-kernel-re-methodology-and-
pitfalls.md`). v1 bricked hardware for a different, earlier-identified
reason (reused live BSS inside an existing module).

v3 changes two things, independently, from v2:

1. **Placement.** Instead of appending a new VirtRange entry past the
   confirmed ceiling, v3 reclaims the last `0xbe54` bytes from the *tail*
   of Health's final VirtRange entry -- a large (`0xe0000`-byte), anonymous
   (no file backing), reference-free region, confirmed byte-identical
   between 2.77 and 2.80 and never directly addressed by any literal in
   Health's own compiled code (`research/2026-11-06-v3-fan-restore-
   strategy.md`). The 64-entry table still ends at exactly `0x2000000`,
   never past it.
2. **The dependency closure itself was completely re-derived**, not
   trusted from v1/v2. The old closure (8 functions, 15,128 bytes) was
   missing 7 whole functions; the real transitive closure from the `fan`
   handler's own entry point is **15 functions, 28,596 bytes**, plus
   ~20KB of help-text/format-string data the handler and its helpers
   reference -- see `research/2026-11-06-v3-closure-rederivation.md` for
   the full methodology (Ghidra-based call-graph walk, cross-version
   signature matching, literal-pool-value disambiguation).

## What was verified (static only, same caveats as v1/v2)

- The confirmed 32MB ceiling: re-verified live against this exact 2.80
  `elf.bin`, not trusted as a constant. The build **fails loudly** if a
  future extraction doesn't match (`build_patched_280.py`'s own
  assertions).
- The reclaimed region really is the last entry, really is anonymous
  (`present=0`, `mod_id=0xffffffff`), and really ends exactly at the
  ceiling -- checked generically (by scanning, not by hardcoded index)
  every build.
- The relocated closure (`fan_block_v3.bin`, built by `relocate_fan_v3.py`
  from the genuine, hash-verified 2.77 `elf.bin`): every one of 700
  re-encoded branch/adr instructions was decode-verified twice -- once
  during patching, once by independently re-reading the final assembled
  bytes -- to confirm it reaches its intended target. This is the same
  external-reference set this session spent most of its effort resolving
  correctly (124 stable cross-version matches via exact signature,
  remainder via literal-pool-value comparison, call-target correlation, or
  position-in-family matching -- never guessed).
- The new 64-entry VirtRange table: no overlaps, ends exactly at
  `0x2000000` (one pre-existing 4KB gap elsewhere in the *original*
  63-entry table was found and is reported, but is not something this
  patch introduces or needs to fix).
- The callsite `bl`: independently decoded from the patched output file
  (not trusted from the build script's own in-memory state) and confirmed
  to land exactly on the new handler's task-local entry point
  (`0x1ff5280`), itself confirmed within ARM's +/-32MB branch range of the
  callsite with ~195KB of margin.
- `ilo4_repack.py` completes without error against the genuine 2.80
  firmware container, the sig-bypassed bootloader/kernel (patched directly
  in Python from `patches/280`'s own JSON patch files -- no `keystone`
  dependency needed for these, just fixed byte replacements), producing a
  correctly-sized `16,777,216`-byte flashable image.

## What this does NOT prove

Exactly the same caveat as v1 and v2: static, structural correctness is
not runtime correctness. The specific new risk v3 carries, beyond the
general "we've never run this code" caveat every version shares:

- The reclaimed tail region's "no direct literal reference from Health's
  own code" finding is real but not airtight -- a generic heap/pool region
  accessed only via an indirect, runtime-computed pointer (set up once at
  task init) would show the same "zero direct references" signature while
  still being live. This is meaningfully better evidence than v1 had for
  its mistake, not proof.
- The standing, separately-acknowledged risk around HPESBHF04134 is
  unchanged by any of this -- restoring the `fan` handler's actual code is
  still restoring whatever that handler's own bugs were, if any motivated
  its removal.

## Build

1. `python3 relocate_fan_v3.py <extracted 2.77 elf.bin> fan_block_v3.bin`
   -- only needs to be re-run if the closure or target address changes;
   `fan_block_v3.bin` is already checked in.
2. `python3 build_patched_280.py <extracted 2.80 elf.bin> <output elf.bin>`
   -- applies sig-bypass + the v3 fan-restore patch.
3. Apply `patches/280/patch_bootloader.json` and `patch_kernel.json` to the
   extracted `bootloader.bin`/`kernel_main.bin` (simple fixed-byte
   patches, no assembler needed -- see `apply_patches` logic used to build
   and verify this).
4. `ilo4_repack.py <genuine 2.80 firmware.bin> firmware.map <patched elf.bin> <patched kernel_main.bin> <patched bootloader.bin>`.

Result hash (`firmware.bin.backdoored.toflash`), this build:
`b2ff08f5a7076773d4dcc7fe9d8b3af871ddd341` (SHA1).
