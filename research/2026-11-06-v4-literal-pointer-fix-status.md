# 2026-11-06: v4 fix implementation status -- COMPLETE, build succeeded

**Update: this is now done.** All three pieces below were completed, the
full build (relocate -> patch -> sig-bypass -> repack) succeeded, and the
repack was round-trip verified (decompressed the final flashable image's
embedded ELF/kernel back out and confirmed byte-for-byte match). See
`patches/280-fan-restore-v4/readme.md` for the final writeup and hash. The
rest of this document is kept as the investigation trail that got there --
it is no longer current status, just history.

---

Implementing the fix proposed in
`research/2026-11-06-v3-literal-pointer-relocation-gap.md`. Two of three
planned pieces are done and verified; the third surfaced a deeper, separate
problem that needs real investigation, not a quick patch. **Do not run
`build_patched_280.py` or flash anything from `patches/280-fan-restore-v4`
yet -- it is intentionally incomplete and will refuse to build (fails loudly
on an unresolved pointer) rather than produce a silently-wrong image.**

## Done and verified

1. **Missing literal-pool bytes (10 instructions).** An exhaustive scan of
   every `ldr Rd, [pc, #imm]` in the closure found 10 whose literal pool
   word fell entirely outside v3's 16 chunk boundaries -- that data was
   never copied into the block at all. Fixed by widening chunks 5, 6, 7, 11
   just enough to include it (`V4_CHUNK_WIDENINGS` in
   `relocate_fan_v4.py`), confirmed to introduce no overlaps. Instruction
   *scanning* is still restricted to the original (v3) chunk boundaries so
   the newly-absorbed filler bytes are never misread as more instructions
   (an early attempt at this did exactly that and had to be corrected).
2. **Self/sibling literal pointers (27 confirmed).** Literal-pool words
   whose value resolves to an address inside our own 16 chunks are now
   patched to the corrected post-relocation value using the exact same
   `resolve_new_task_local_target()` already trusted for instruction
   targets, with a full independent re-verification pass (re-derives the
   expected value fresh from the original 2.77 bytes, not from anything
   computed during patching). This part of `relocate_fan_v4.py` runs clean
   end to end.

## Not done -- new finding, more complex than expected

The remaining ~24 literal pointers that resolve to addresses in Health's
`.text` *outside* our 16 chunks are not simply "call a stable helper
function elsewhere in 2.80" the way the equivalent *instruction*-level
external references are. Using Ghidra (headless, both 2.77 and 2.80
`.health.elf.text` imported and auto-analyzed) to check: **none of the 12
addresses checked this way fall inside any function Ghidra recognizes.**
Manual inspection of the actual bytes confirms why -- they're not code at
all. They're inside a large, generic Health sensor/error string-and-data
table (error strings like "General sensor error", "Sensor underflow",
register-name strings like "PCI-E PCI Status Register", field names like
"temp"/"scale"/"count"/"Minimum"/"Maximum") that sits at the tail of
`.health.elf.text` just before `.health.elf.data` begins. This table is
**not fan-specific** -- it's shared infrastructure used across many sensor
types.

Confirmed this table still exists in 2.80 (found "General sensor error"
verbatim via a full-binary search), but it is not merely shifted: **one
leading 4-byte entry in the length-prefix table right before the strings
has been deleted** in 2.80 (2.77 has 9 length values `0x3f,0x5a,0x50,0x46,
0x3c,0x32,0x28,0x1e,0x14` before "General sensor error"; 2.80 has only 8,
missing the `0x3f`). Our candidate pointer `0xe915e8` points at exactly
that deleted entry -- it has no corresponding 2.80 address at all, because
that specific table row is gone, not shifted.

This means:
- A plain address-shift or external_map-style single-address resolution is
  **not sufficient** for this category -- different entries before/after
  the deletion point need different treatment, and at least one entry
  (0xe915e8) has no valid target to resolve to at all.
- Whatever code path in our closure dereferences the now-deleted entry
  needs to be understood semantically (is it for a fan-specific error code
  that's supposed to be gone too? does the surrounding code need to change,
  not just the pointer?) before guessing at a "fix" -- exactly the kind of
  situation where a wrong guess is worse than stopping.
- An earlier, now-**retracted** attempt at this session incorrectly
  "resolved" 4 addresses (`0xe91dc4`, `0xe26798`, `0xe93108`, `0xe3667c`) by
  treating a coincidental exact-byte match elsewhere in 2.80 as confirmation
  -- `0xe91dc4` was directly confirmed to sit inside this same data table
  (not a function), so that match was spurious, not a real resolution. The
  other three were never independently checked against the same risk and
  were retracted for the same reason. `closure_mapping.json` in this
  directory has been restored to the original, pre-session 132 entries only.

## What's needed before this can build

1. Map out the *entire* extent of this generic data table in both versions
   (where it starts/ends in 2.77 and 2.80) and diff it properly -- not just
   spot-check a few addresses -- to find every point where an entry was
   added, removed, or reordered, not just the one found so far.
2. For each of our ~24 literal pointers into this table, determine which
   side of which edit it falls on, and what the correct 2.80 address (or
   "there is no valid target, the caller needs to change") actually is.
3. For any pointer whose target is confirmed gone (like `0xe915e8`),
   understand what the *code* that loads it was going to do with it, and
   decide -- with the project owner, not by guessing -- whether that call
   path is still needed for the `fan` functionality being restored, or
   whether it's dead weight from a feature that's supposed to be gone.

This is real, separate investigative work, not a mechanical follow-on to
the pointer-relocation fix. Hardware has already been bricked three times;
nothing from `280-fan-restore-v4` should be built or flashed until this is
resolved on the merits, not on a deadline.

---

## How it actually resolved

Per-address Ghidra function lookups don't scale to a whole table, so this
used a word-level diff instead: extracted the full tail region in both
versions (2.77 `0xe8f284-0xe98f48`, 2.80 the equivalent span), anchored on
the verbatim string "General sensor error" (confirmed present in both, same
relative structure), and ran `difflib.SequenceMatcher` on 4-byte words.
Across ~40KB, there were exactly two structural edits (not dozens): the
192-byte fan-name-string block (`eh_fan`, `fan_tmp`, etc.) deleted outright,
and the single `0x3f` length-table entry deleted. Everything else was a
same-count value replacement -- i.e. the same table, same structure, just
shifted addresses -- resolved by walking the diff's own position mapping,
not by guessing a constant shift (an early, wrong instinct: the shift is
*not* constant across the whole region, because of those two edits).

This resolved 14 of the 16 originally-stuck addresses outright, confirmed
2 more (`0xe26798`, `0xe3667c`) via unique longer-string searches elsewhere
in the file, and turned up one more previously-missed address
(`0xe94644`, inside the same tail region, caught by a from-scratch
enumeration of every literal value in the whole closure rather than trusting
the earlier hand-picked sample list). Net: the earlier 4 "retracted,
spurious-looking" resolutions (`0xe91dc4`, `0xe26798`, `0xe93108`,
`0xe3667c`) turned out to have been correct after all -- re-derived here via
real evidence instead of a coincidental byte match, which is why retracting
them first and re-deriving them properly was the right call rather than
trusting the earlier guess.

The one truly-unresolvable address (`0xe915e8`) was handled by decompiling
its containing function (the main `fan` handler itself, `FUN_00e16970`)
with Ghidra: the decompiler's own output opens with
`/* WARNING: Removing unreachable block (ram,0x00e17564) */`, independent
confirmation (not just this session's reasoning) that the conditional block
feeding on this load is dead code. Patched defensively to the next
surviving table entry rather than left unresolved indefinitely.

Final build: `relocate_fan_v4.py` -> `build_patched_280.py` -> sig-bypass
patches on bootloader/kernel -> `ilo4_repack.py` (run via
`docker run --rm -v ... python:2.7`, since the vendored tool needs Python 2
and this session chose not to risk a hand-port of its LZ-style compressor).
New step beyond anything v1/v2/v3 did: decompressed the final image's
embedded ELF and kernel back out and confirmed byte-for-byte match against
the patched inputs, and confirmed the raw bootloader region matches too.
Final hash: `f033cd582b6ac5563ec50ef8c4fa528240e25c4a`.

## One more check: does anything reach the deleted fan-name table via `adr`?

The literal-pointer scan only catches absolute pointers loaded via
`ldr Rd, [pc, #imm]`. Before calling the deleted 48-word fan-name-string
block (`eh_fan`, `fan_tmp`, etc., see above) definitely unreferenced, also
decoded every `adr`-style (`ADD`/`SUB Rd, PC, #imm`) instruction across all
14 original closure chunks -- 721 of them -- and checked each one's target
against the table's address range (`0xe8f568-0xe8f628`). None hit. Combined
with the `ldr`-literal scan (which also found none) and `cross_refs.json`
having zero cross-chunk `adr` entries to begin with, this is now a
reasonably thorough (not exhaustive -- doesn't cover e.g. a base-register
loaded far earlier plus a runtime-computed arithmetic offset) check that
nothing in the restored closure depends on that deleted table.
