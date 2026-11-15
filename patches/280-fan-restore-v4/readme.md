# iLO 2.80 Patch (signature-bypass + full `fan` command backport, v4) -- EXPERIMENTAL, NOT HARDWARE-TESTED

**Status: static build verified end-to-end through a clean repack, including a
full compression round-trip check. Has NOT been flashed to real hardware.**

Supersedes `patches/280-fan-restore-v3`, which was flashed and bricked iLO
the same way v1 and v2 did (BIOS POST 270 "iLO FW Communication Issue"),
despite fixing both of v1 and v2's previously-diagnosed causes. Root cause:
see `research/2026-11-06-v3-literal-pointer-relocation-gap.md` and
`research/2026-11-06-v4-literal-pointer-fix-status.md` for the full
investigation. v4 fixes it.

## What was actually wrong with v3

v3's relocator (`relocate_fan_v3.py`) only re-encoded PC-relative
**instruction** references (`bl`/`b`/`adr`) found by a Ghidra code
cross-reference walk. It never touched literal-pool **data** words whose
*value* is itself an absolute pointer -- these get copied byte-for-byte from
2.77 and are wrong by the ~33MB delta between the closure's original
in-place position and its new placement near the 32MB ceiling. This kind of
bug is invisible to every check v3 ran (branch-range check, ADR checks, the
700-instruction decode-readback) because all of those inspect instruction
*encodings*, never literal *values*.

## What v4 fixes, concretely

1. **10 literal-pool loads whose literal word was missing entirely.** Four
   of v3's 16 chunk boundaries cut off their own trailing/leading literal
   pool. Fixed by widening those 4 chunks just enough to include it
   (`V4_CHUNK_WIDENINGS` in `relocate_fan_v4.py`) -- instruction *scanning*
   still only looks at the original, Ghidra-vetted code ranges, never the
   newly-absorbed filler bytes, so nothing gets misread as more code.
2. **27 self/sibling literal pointers** -- values that resolve to an address
   inside our own moved block -- corrected via the same
   `resolve_new_task_local_target()` already trusted for instruction
   targets.
3. **15 pointers into Health's generic, non-fan sensor/error string table**
   (error messages like "General sensor error", register names, field names
   like "temp"/"scale"/"count") -- confirmed via Ghidra (none of these
   addresses are inside any recognized function on either side; they're
   data) and resolved via a word-level diff of the whole table between the
   hash-verified 2.77 and 2.80 binaries, anchored on the verbatim string
   "General sensor error" found in both. That diff found exactly two real
   edits in ~40KB of table: a 48-word (192-byte) block of fan-specific name
   strings (`eh_fan`, `fan_tmp`, `fan_tac`, `fan_grp`, `fan_alg`, `fan_pwm`,
   ...) deleted outright -- not referenced by anything in our current
   closure's literal pointers, so no action needed for it -- and one
   single 4-byte length-table entry deleted (see next point). Every other
   difference was a same-count value replacement (i.e. the same structure,
   shifted addresses), resolved exactly via the diff's position mapping.
4. **One pointer with no valid target at all** (`0xe915e8`, the deleted
   length-table entry, value `0x3f` in a 9-entry table that's only 8 entries
   in 2.80). The single load site (`0xe17524` in the main `fan` handler,
   `ldrne r7,[pc,#0x230]`) is conditional, and Ghidra's own decompiler
   independently flags the block it feeds into as **unreachable**
   (`/* WARNING: Removing unreachable block (ram,0x00e17564) */`) for every
   input. Patched defensively to point at the next surviving table entry
   (length `0x5a`) instead of a stale cross-version address, purely so that
   *if* this is somehow reached despite that finding, it reads valid memory
   instead of jumping through garbage -- this is flagged in
   `closure_mapping.json` as a defensive fallback, not a claimed-correct
   resolution.

All patched literal words -- 42 across the whole closure -- are
independently re-verified by re-deriving the expected value fresh from the
original 2.77 bytes (not from anything computed during patching).

## What was verified (static + a new compression round-trip check)

Everything v3 already verified (32MB ceiling, reclaimed-region placement,
branch/ADR re-encoding, VirtRange table), plus:

- **42 literal-pool data pointers**, independently re-verified against the
  original 2.77 bytes (see above).
- **The full repack was round-tripped**: the embedded compressed ELF and
  kernel sections were decompressed back out of the final
  `firmware.bin.backdoored.toflash` and confirmed **byte-for-byte identical**
  to the patched `elf.bin` and `kernel_main.bin` fed into the repack, and
  the raw (uncompressed) bootloader region was confirmed to match
  `bootloader.bin` exactly. This check was not done for v1/v2/v3 -- their
  readmes only claimed the repack "completes without error," which does not
  by itself prove the compressed data decompresses back correctly.
- `ilo4_repack.py` (the unmodified, vendored `ilo4_toolbox` script, which
  needs Python 2) was run inside a `python:2.7` Docker container rather than
  ported, specifically to avoid introducing a translation bug into a
  hand-tuned LZ-style compressor this session didn't write.

## What this does NOT prove

Same standing caveats as v1/v2/v3: static, structural correctness is not
runtime correctness, and the HPESBHF04134 risk (restoring the `fan`
handler's own bugs, if any motivated its removal) is unchanged by any of
this. Specific new residual risk:

- The `0xe915e8` defensive fallback (point 4 above) is believed, not proven,
  unreachable. It's backed by an independent tool's (Ghidra's decompiler)
  own control-flow analysis, not just this session's reasoning, but it is
  still an inference, not a trace of real execution.
- The 48-word fan-specific name-string table that was deleted in 2.80
  (`eh_fan`, `fan_tmp`, etc.) is not referenced by any `ldr`-literal pointer
  *or* `adr` instruction found anywhere in the current 15-function closure
  (721 `adr`s and all `ldr`-literal targets checked, zero hits on that
  address range). It's still possible something reaches it by a mechanism
  neither scan would catch (e.g. a base register loaded far earlier plus a
  runtime-computed arithmetic offset); if so, it would currently read into
  whatever now occupies that space in unmodified 2.80 Health code, since
  this content was not migrated into the new block. No evidence was found
  that anything does this, but it wasn't exhaustively ruled out.

## Build

1. `python3 relocate_fan_v4.py <extracted 2.77 elf.bin> fan_block_v4.bin`
   -- only needs to be re-run if the closure or target address changes;
   `fan_block_v4.bin` is already checked in.
2. `python3 build_patched_280.py <extracted 2.80 elf.bin> <output elf.bin>`
   -- applies sig-bypass + the v4 fan-restore patch.
3. Apply `patches/280/patch_bootloader.json` and `patch_kernel.json` to the
   extracted `bootloader.bin`/`kernel_main.bin` (simple fixed-byte patches).
4. `ilo4_repack.py <genuine 2.80 firmware.bin> firmware.map <patched elf.bin> <patched kernel_main.bin> <patched bootloader.bin>`
   -- needs Python 2; this session ran it via `docker run --rm -v ... python:2.7`.

Result hash (`firmware.bin.backdoored.toflash`), this build:
`f033cd582b6ac5563ec50ef8c4fa528240e25c4a` (SHA1).
