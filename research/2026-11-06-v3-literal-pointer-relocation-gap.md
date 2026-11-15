# 2026-11-06: v3 hardware failure -- likely root cause found (unrelocated data pointers)

## Symptom

`patches/280-fan-restore-v3` flashed to real hardware. Result: identical
failure signature to v1 and v2 -- BIOS POST error 270 "iLO FW Communication
Issue", occurring during the BIOS boot process itself (iLO never comes up
far enough to answer BIOS, well before anyone could invoke `fan`).

v3 fixed the two previously-diagnosed causes (v1's BSS collision, v2's
32MB ceiling violation) yet produced the exact same generic symptom. That
symptom is not diagnostic of a specific bug -- `patches/280-tools` hit the
identical 270/255.255 signature for an unrelated reason years ago -- it is
simply what "iLO crashed during its own boot" looks like from BIOS's side.
So the fact that v3 still shows it does not mean the two known fixes were
wrong; it means a *third*, independent defect is still present.

## Root cause hypothesis: literal-pool data pointers are never relocated

`relocate_fan_v3.py` copies 16 contiguous "superchunks" of raw bytes from
2.77's Health `.text` verbatim, then re-encodes only the **instruction**
references that cross chunk boundaries -- `bl`/`b`/`b<cc>` (700 instances,
`cross_refs.json`) and `adr` (0 instances needed, the one known case is
intra-chunk). This list was built entirely from Ghidra's own **code**
cross-reference walk.

What it does not do, anywhere in the pipeline: inspect or patch raw **data**
words -- specifically, 32-bit literal-pool constants loaded via
`ldr rX, [pc, #imm]` whose *value* is itself an absolute task-local address
(as opposed to a small integer, which is the only literal-pool pattern this
session's external-reference disambiguation work ever looked at). A
dead-but-written `encode_ldr_literal`/`decode_ldr_literal` pair exists in
`relocate_fan_v3.py` (never called) -- evidence this was anticipated as a
*possible* need and then not followed through on.

This matters because v3 moves the whole closure by roughly 33MB (from its
original in-place task-local position, ~0x39890-0xa2910, to the new
placement at the top of the 32MB ceiling, ~0x1ff5280-0x2000000). An
instruction's PC-relative encoding survives this move for free as long as
both ends of the reference are in the same chunk (the chunk moves as one
rigid unit). A raw absolute-address **value** sitting in a literal pool has
no such protection -- it's copied byte-for-byte, so it still contains the
*old* address after the block lands 33MB away.

## Verified against the real, hash-identified 2.77 `elf.bin`

Scanned all 16 superchunks for `ldr Rd, [pc, #imm]` instructions whose
literal pool word also lies inside a superchunk, then checked whether the
*value* stored there looks like a task-local-277 address (0x10000-0x2000000)
and where it resolves:

- **27 confirmed self/sibling pointers**: the loaded value resolves to a
  true-vaddr *inside one of our own 16 chunks* -- e.g. `0xe3d83c` (in chunk
  9) holds `0x00060f7c`, which as a task-local-277 address is true-vaddr
  `0xe3cf7c`, itself inside chunk 8. Three separate load sites
  (`0xe3d8f8`, `0xe3d938`, `0xe3d990`) all fetch this same stale pointer.
  These are guaranteed wrong post-relocation -- the delta between old and
  new chunk positions is never applied to them.
- **24 more** resolve to true-vaddrs elsewhere in Health's own `.text`
  (e.g. `0xe91dc4`, `0xe93108`, `0xe3667c`) -- stable helpers that would
  need the same kind of resolution `external_map` already provides for
  branch targets, but currently never receive it because nothing in the
  pipeline looks for data-word pointers at all.
- A further 87 resolve outside Health entirely (other modules); per this
  session's own already-established finding that shared/other-module
  task-local addressing is version- and position-independent, these are
  *probably* benign as-is, but that assumption hasn't been specifically
  re-verified for data-word (as opposed to instruction-level) references.

Traced representative usage of several of the 27 (e.g. loads at `0xe3d8f8`,
`0xe3d938`, `0xe3d97c`, `0xe3d9c4`, all within the tight ~0x400-byte chunk
9, `0xe3d7e4-0xe3dbe4`): the loaded values are immediately assembled in
pairs onto the stack (`add rX, sp, #n` / `stm sp, {r0, r1}`) and then fed
into a call shortly after -- the shape of code building `{pointer, pointer}`
table entries and registering them, consistent with (and apparently far
larger than) the old pre-session docs' noted "2 pointer-indirection words"
for the `fan` handler's subcommand table. That estimate looks like a
significant undercount; this session's hash-verified scan alone finds at
least 27 definite and 24 probable candidates.

None of this is caught by any verification step already run (branch-range
check, ADR rotation check, the double decode-readback of the 700 patched
instructions) -- all of those inspect instruction *encodings* only, never
literal-pool *values*. This defect class would have been present in v1 and
v2 too, just masked by the grosser, already-identified bugs in each.

## Confidence

High but not proven by full decompilation -- the pointer-resolution and
stack-assembly pattern is strong, structural, repeatable evidence, not a
confirmed trace of an indirect branch through one of these registers. No
further hardware testing should happen until this is either disproven more
rigorously or fixed; this is the most credible lead by a wide margin given
it's the one class of reference the entire pipeline provably never
inspects.

## What a fix would need

1. Exhaustively enumerate every `ldr`-literal in all 16 chunks whose value
   plausibly encodes a task-local-277 pointer (not just the ones sampled
   above), classifying each the same three ways as above.
2. For the self/sibling class: patch the literal *value* (not an
   instruction encoding) by the same chunk-delta logic `resolve_new_task_
   local_target` already uses for cross-chunk instructions.
3. For the Health-internal-but-external-chunk class: resolve via
   `external_map` (extending it if any of these 24 targets aren't already
   keys) and write the corrected `task_local_280(...)` value.
4. Re-verify the "version/position-independent" assumption for the 87
   other-module candidates specifically for data words, not just
   instructions, before trusting them unmodified.
5. Add a dedicated verification pass for literal-pool data words, mirroring
   the existing double-decode-readback discipline for instructions.
