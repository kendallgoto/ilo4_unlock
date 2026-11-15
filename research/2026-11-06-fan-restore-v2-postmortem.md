# `patches/280-fan-restore` v1 hardware failure, post-mortem, and v2 fix, 2026-11-06

## Symptom

Flashed `patches/280-fan-restore` (the full `fan`-handler backport, see
`research/2026-11-05-278-282-feasibility.md`) to real hardware. Result: iLO
unable to communicate -- matching the exact prior failure signature of
`patches/280-tools` (BIOS POST error 270 "iLO FW Communication Issue",
version reads back `255.255`/`0xFF.0xFF`). Recovered by reflashing the
known-good `ilo4_280-GENUINE-cleanrepack.bin`.

## Adversarial review: root cause

v1 placed the relocated `fan` handler at true vaddr `0xe94000`, reasoning
that it was free because it sat past `.health.elf.data`'s declared on-disk
content (`text_size = 0x2e8c`) but inside that module's `VirtRange`
reservation (`rsize = 0x91000`). That assumption was wrong, and is a
textbook mistake in hindsight: `rsize > text_size` for a data module is
standard ELF semantics for **BSS** (the loader zero-fills the difference at
boot), not spare/unused capacity. The zero-filled remainder is live working
memory for the whole Health task, not scratch space available for new
content.

Confirmed by evidence, not just inference: scanning the *surviving* (i.e.
non-removed, unrelated-to-`fan`) Health `.text` for literal-pool word values
landing inside that "free" region turned up 9 hits -- `0xea0900, 0xeb0900,
0xec0900, ..., 0xf20900` -- evenly spaced by exactly `0x10000`, clearly a
real table of base addresses to distinct structures used by code that has
nothing to do with `fan`. v1's injection (`0xe94000`-`0xe97cbc`) didn't
land exactly on any of those 9 specific addresses, but the pattern is
damning: it proves the region is live, actively-referenced BSS for
unrelated subsystems, not unclaimed space, and growing `.health.elf.data`'s
on-disk size to cover that range almost certainly corrupted whatever
actually lives there at the front of the reservation -- plausibly at or
before boot, well before anyone invokes `fan`, which fits the observed
"total communication failure" symptom far better than a bug confined to
the `fan` handler itself.

Ruled out as the cause: re-disassembled all 8 relocated functions checking
specifically for instruction types the relocator can't handle (jump-table
dispatch via `ldr pc, [...]`, `BLX`, computed `MOV pc, ...`) -- found none.
The ARM32 relocation logic itself (branch/literal/ADR-immediate re-encoding)
remains structurally sound; the bug was purely about *where* the code was
placed, not how it was transformed.

## Fix: v2, a genuinely new memory region

See `patches/280-fan-restore-v2/readme.md` for the full writeup. Summary:
instead of reusing unallocated space inside an *existing* module's declared
`VirtRange`, v2 adds a wholly new ELF section backed by its own new
`.secinfo` entry and a new 64th `VirtRange` entry in Health's own array
(grown from the existing 63), at a physical address (`0x4000000`) confirmed
via an exhaustive scan of all 577 `.secinfo` entries to be above the
highest true-vaddr used by *anything* in the firmware (`0x3e22b18`). Since
nothing existing is resized in address space -- only the ELF section header
*table* moves (append-at-file-end, same trick used for v1's sig-bypass
patch and throughout this project) -- this cannot collide with any other
module's declared or reserved memory.

This surfaced a second, previously-irrelevant constraint: ARM's `B`/`BL`
has a +/-32MB PC-relative reach. The registration trampoline's `bl` to the
restored handler lives at Health task-local address `~0x2604c`; the first
v2 placement attempt (task-local `0x3000000`, chosen without checking
range) was ~48MB away and unreachable. Health's own task-local address
space currently tops out at `0x2000000` (from its existing 63 `VirtRange`
entries), so `0x2001000` was used instead -- ~2.4MB from the trampoline,
comfortably in range. Notably, `relocate_fan3.py`'s `encode_branch` does
**not** raise on overflow, it silently wraps the 24-bit immediate -- so the
"zero unresolved targets" check from the original build (which only
verifies `resolve_target()` doesn't throw) would **not** have caught an
out-of-range branch. All 100 branch instructions in the closure were
explicitly re-checked against the signed-24-bit-word range after fixing the
placement, and the trampoline's own call was separately verified by
round-tripping the computed immediate back through the decode math.

## Status

Static build verification complete for v2 (pyelftools re-parse, `.secinfo`
linked-list integrity, `TaskInfo` repoint, branch-range check, clean
`ilo4_repack.py` run) -- same caveats as v1 apply (this does not prove
runtime correctness, and does not change the standing HPESBHF04134 risk).
**Not yet flashed to hardware.**
