# iLO 2.80 Diagnostic Build #7: alias entry 62 to an existing mod_id -- NOT A REAL PATCH

**Follow-up to `patches/280-diag6-reattribute-entry-in-place`, which ALSO
bricked with 270 -- even though it never relocated the array, never
changed `virt_space`/`virt_space_size`, never changed entry count, and
never moved entry 62's `rbase`/`rsize`. It only flipped entry 62's
`dw1`/`dw2`/`mod_id` from anonymous to a BRAND-NEW module.**

## Cumulative picture

| Build | New present=1 link to a module? | New mod_id? | Result |
|---|---|---|---|
| diag2 (`.secinfo` growth, unreferenced) | no | n/a | booted fine |
| diag3 (in-place rsize shrink, stays anonymous) | no | n/a | booted fine |
| diag1 (new 64th entry + array relocation) | yes | yes | bricked |
| diag4 (relocate virt_space, 0x4000000) | yes | yes | bricked |
| diag5 (relocate virt_space, tight address) | yes | yes | bricked |
| diag6 (reuse entry 62, new module) | yes | yes | bricked |

Every bricked build creates a brand-new, real (`present=1`) link between a
VirtRange entry and a module that didn't exist in stock 2.80's own module
table. Every clean build never does. This isolates the one variable never
tested alone: is it specifically **a module id that never existed in stock
firmware**, or **any anonymous entry becoming present=1**, regardless of
which module it names?

## This build

Re-attributes entry 62 exactly like diag6 (same in-place patch, no
relocation, no count change, `rbase`/`rsize` unchanged) -- but instead of
inventing a new module, points entry 62 at `mod_id=0x81`, the same,
pre-existing, already-valid module Health's own `.health.elf.text` (entry
1) already uses. No new `.secinfo` entry is added at all -- none is
needed, since `mod_id=0x81` already has one. This is a pure alias: the
same already-registered module, now also mapped at a second task-local
address. The file does not grow by even one byte.

## How to read the result

- **If this bricks with 270**: the problem isn't "is this mod_id new" --
  converting *any* anonymous entry to `present=1` is fatal regardless of
  which module it names, even one that's already fully valid and
  load-bearing elsewhere. This would close out the entire "register a new
  module via VirtRange re-attribution" direction conclusively, pointing at
  something structural about `present=0`-to-`present=1` conversion itself
  (e.g. these regions may be load-bearing live heap/stack, consistent with
  `research/2026-11-06-v3-fan-restore-strategy.md`'s own characterization).
- **If this boots fine**: the module table tolerates a duplicate reference
  to an already-known mod_id. The real constraint is specifically that
  `mod_id` must already exist in the system's own build-time module table
  -- meaning no mechanism that invents a *new* mod_id can ever work here,
  structurally, no matter how it's wired into VirtRange.

## What was verified (static)

- Entry 1 reconfirmed as Health's own `.health.elf.text` module
  (`mod_id=0x81`, `rights=5`) before reusing its mod_id.
- Entry 62 reconfirmed anonymous (`present=0`, `mod_id=0xffffffff`) before
  the patch, full original range reaching exactly the `0x2000000` ceiling.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region matches exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1-6/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`1a9ecbd7b73eccb3f0e0cbaf4701af85ba298bcc` (SHA1).
