# iLO 2.80 Patch (signature-bypass + full `fan` command backport, v2) -- EXPERIMENTAL, NOT HARDWARE-TESTED

**Status: static build verified only. Has NOT been flashed to real hardware.**

This supersedes `patches/280-fan-restore` (v1), which **bricked real hardware**
("iLO FW Communication Issue" / unresponsive iLO -- the same failure mode as
`patches/280-tools`). See "Why v1 failed" below before considering this safe
to flash either.

Like v1, this backports the actual `fan` CLI handler (8-function dependency
closure, 15,548 bytes) from 2.77 into 2.80 and re-enables the disabled CLI
registration call site. What's different in v2 is **where the restored code
lives**.

## Why v1 failed

v1 placed the relocated code at true vaddr `0xe94000`, reasoning that it was
"free" because it sat past `.health.elf.data`'s declared on-disk content but
still inside that module's `VirtRange` reservation (`0x91000` bytes
reserved, only `0x2e8c` bytes initialized from file). That reasoning was
wrong: the reserved-but-uninitialized remainder of a module's `VirtRange` is
standard ELF-style BSS -- zero-filled at boot, then actively used by the
task's own running code for real global state, not idle scratch space. An
adversarial review after the hardware failure found literal-pool references
from *unrelated*, surviving Health code pointing into that same reserved
region (a suspicious table of 9 addresses spaced exactly `0x10000` apart,
well within `.health.elf.data`'s reservation) -- strong evidence the "free"
space was live. Growing `.health.elf.data`'s on-disk size to cover v1's
injection point almost certainly stomped on real BSS used by other,
unrelated Health subsystems at boot, before `fan` was ever invoked --
consistent with the observed failure (total iLO unresponsiveness, not a
narrow "fan command doesn't work" symptom).

## What v2 does differently

v2 never reuses address space already claimed by any existing module.
Instead it adds a **brand new, independent ELF section** (`sh_addr =
0x4000000`, chosen because the highest true-vaddr used by *anything* in the
firmware, per an exhaustive scan of all 577 `.secinfo` entries, is
`0x3e22b18` -- comfortably below it) containing three things back-to-back:

1. The relocated `fan` handler code+data (same 8-function closure as v1,
   re-relocated for its new address).
2. A new `.secinfo` `SectionInfo` entry describing that code (appended to
   the existing linked list by patching the previous tail entry's
   `next_ptr` -- a single in-place 4-byte edit, no resizing of `.secinfo`
   itself).
3. A new, 64-entry copy of Health's `VirtRange` array (the existing 63
   entries, unchanged, plus one new entry mapping Health task-local address
   `0x2001000` to the new section via the new `.secinfo` entry's index).
   Health's `TaskInfo.virt_space`/`virt_space_size` fields (within
   `.boottable`) are repointed to this new array -- again a small in-place
   edit, not a resize of `.boottable`.

Because nothing existing is resized or shifted in *address* space (only the
section header *table* moves, via the usual append-at-file-end trick), this
cannot collide with any other module's declared or reserved memory the way
v1 did.

### A second constraint this surfaced: branch range

The CLI registration trampoline's `bl` to the restored handler is a plain
ARM `B`/`BL`-style PC-relative branch, limited to +/-32MB. The first v2
attempt chose Health task-local address `0x3000000` for the relocated code,
which was ~48MB from the trampoline (task-local ~`0x2604c`) -- unreachable.
Health's own task-local address usage currently tops out at `0x2000000`, so
`0x2001000` was chosen instead (just above existing usage, ~2.4MB from the
trampoline, comfortably in range). All 100 branch instructions inside the
relocated closure, plus the trampoline's own call, were explicitly checked
to fall within the signed 24-bit (word-granularity) immediate range before
this was considered done -- `encode_branch` does **not** itself raise on
overflow, it silently wraps, so this check matters and must be re-run if
the placement ever changes.

## What was verified (static only) -- same caveats as v1

- Independent pyelftools re-parse: 629 sections enumerate correctly, the
  new section's content matches `fan_block.bin` byte-for-byte, the new
  `.secinfo` entry and `VirtRange` array read back with the expected
  values, `.boottable`'s `TaskInfo` for Health correctly points at the new
  array.
- All 100 branch instructions in the relocated closure, plus the
  trampoline's own re-pointed call, verified in-range for ARM's +/-32MB
  `B`/`BL` reach.
- `ilo4_repack.py` completes without error, producing a correctly-sized
  16,777,216-byte flashable image.

**None of this proves runtime correctness.** The address-collision class of
bug that broke v1 is specifically addressed, but this does not rule out
other classes of bug (a subtle literal/branch fixup error elsewhere in the
closure, the open structural question of whether any other code reads
Health's `TaskInfo`/`.secinfo` metadata in a way sensitive to array growth
from 63 to 64 entries, etc.), and it does not change the standing,
separately-acknowledged risk around HPESBHF04134 (see `patches/280-fan-restore/readme.md`).

## Additional pre-flight checks added after an adversarial review, 2026-11-06

`build_patched_280.py` originally trusted `NEW_SECINFO_INDEX=577` and
`SIZE_INITIAL=49` as bare constants from a one-off manual scan, and trusted
`NEW_PHYS_BASE`/`NEW_TASK_LOCAL_BASE`'s collision-freedom from the
postmortem's one-off summary claims rather than re-checking the live binary
-- exactly the class of mistake that bricked v1. After three consecutive
hardware round-trips (`280-tools`, `280-fan`, this patch's own v1) each
surfaced something static checks hadn't caught, and given each hardware test
costs ~20 minutes against instant static checks, the build script now
self-verifies, against the actual input binary, every time it runs:

- **`NEW_SECINFO_INDEX`/`SIZE_INITIAL`**: re-derived by walking the live
  `.secinfo` linked list from its head (bounds-checked against the section's
  own extent at every step -- `struct.unpack_from` silently wraps on a
  negative offset instead of raising, so an un-bounds-checked walk would NOT
  reliably fail loudly on a wrong assumption) and cross-checked against a
  direct scan of the 63 existing Health `VirtRange` entries for the one
  whose `rsize` matches `.health.elf.data`'s hardware-confirmed `0x91000`
  (see "Why v1 failed" above), rather than trusting `patches/280-fan-restore`
  v1's unverified `mod_id=0x82` comment on its own.
- **`NEW_PHYS_BASE` collision-freedom**: the same `.secinfo` walk now also
  tracks the highest `text_base_addr+text_size` across all existing entries
  and asserts the new physical placement is above it -- re-run against the
  live binary every build, not trusted as a one-off "exhaustive scan"
  result from `research/2026-11-06-fan-restore-v2-postmortem.md` that can no
  longer be independently reproduced (the script that did it wasn't
  committed).
- **`NEW_TASK_LOCAL_BASE` collision-freedom**: checked against each of the
  63 existing Health `VirtRange` entries' own `[rbase, rbase+rsize)` ranges
  individually, not just the "existing entries top out at `0x2000000`"
  summary claim (a max-value summary wouldn't by itself rule out a smaller,
  out-of-order existing entry overlapping the new one).
- **The callsite `bl` itself, decoded and round-tripped**: this patch's own
  `encode_branch` tooling silently wraps a too-large 24-bit immediate
  instead of raising, so the only real test is to decode the actual patched
  bytes and independently compute where they branch to. The script now
  resolves the callsite's own task-local address from scratch (finds its
  owning `.secinfo` entry by true-vaddr range, predicts that entry's
  `mod_id` using the same `SIZE_INITIAL + secinfo_index` formula relied on
  for the new entry, and confirms a real Health `VirtRange` entry has that
  `mod_id`), decodes `NEW_BL_BYTES` as an ARM32 `B`/`BL` instruction, and
  asserts the computed target equals `NEW_TASK_LOCAL_BASE` exactly. Decoding
  `NEW_BL_BYTES` against this readme's own previously-approximate `~0x2604c`
  callsite value independently lands on exactly `0x2001000` with zero
  discrepancy -- the "~" was just prose hedging, not real imprecision.

All of the above were exercised against synthetic (non-firmware) data
covering both the intended-good path and deliberately corrupted inputs
(a `next_ptr` pointing before/after the section, duplicate matches, a
mod_id formula that doesn't generalize, forward/backward branch encoding)
before being relied on here, since no real extracted `elf.bin` exists in
this repo to test against end-to-end. These checks make a wrong assumption
**fail loudly during the build** instead of **silently producing a
wrong-but-plausible image** -- they raise confidence, they do not replace a
hardware test.

## Build

`build_patched_280.py` in this directory is self-contained: given a freshly
extracted 2.80 `elf.bin` (via `ilo4_extract.py`), it applies the sig-bypass
patch and the full v2 fan-restore patch, and writes the result for feeding
into `ilo4_repack.py`. `fan_block.bin` is the final 15,548-byte relocated
code+data blob. See `elf_patch_summary.md` for exact offsets, for anyone
re-deriving this without re-running the script.

Result sha1 (`ilo4_280.bin.backdoored.toflash` after repack):
`a3bee3cf3f35dcd9617484b326239b178dd0ebf7`
