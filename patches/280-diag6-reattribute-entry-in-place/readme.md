# iLO 2.80 Diagnostic Build #6: re-attribute an existing VirtRange entry in place -- NOT A REAL PATCH

**Follow-up to `patches/280-diag4-relocate-virtrange-only` and
`patches/280-diag5-relocate-tight-address`, which BOTH bricked with the
identical 270 error.**

## Taking stock

| Build | virt_space touched? | Array relocated? | Count changed? | Result |
|---|---|---|---|---|
| diag2 (`.secinfo` growth only) | no | no | no | **booted fine** |
| diag3 (in-place rsize shrink) | no | no | no | **booted fine** |
| diag1 (full relocation, address 0x4000000) | yes | yes | 63->64 | bricked |
| diag4 (relocate only, address 0x4000000) | yes | yes | no | bricked |
| diag5 (relocate only, tight address 0x3e22b18) | yes | yes | no | bricked |

diag4 and diag5 used *different* addresses for the exact same relocation
and both bricked identically, which falsifies the "image_end fit-check /
wrong address" hypothesis from diag5. The clean, three-times-replicated
common denominator across every bricking build (diag1, diag4, diag5) vs.
every clean one (diag2, diag3): **changing `TaskInfo.virt_space` to
anything other than its stock address bricks, no matter where the new
value points.** The array has to stay exactly where stock 2.80 put it,
inside `.boottable`.

## This build

Tests whether an **existing** VirtRange entry can instead be
re-attributed, in place, to reference a new module -- with **no**
relocation of the array at all:

- `TaskInfo.virt_space` and `virt_space_size`: **completely untouched**
  (still the original address, still 63)
- the VirtRange array itself **does not move** -- stays at its original
  file location inside `.boottable`
- the only VirtRange change: entry 62 (the last, previously anonymous,
  ceiling-ending entry) has its `dw1` (present), `dw2` (rights), and
  `mod_id` fields patched **in place**, at their original file offsets,
  from `(present=0, rights=7, mod_id=0xffffffff)` [anonymous] to
  `(present=1, rights=5, mod_id=0x272)` [owned by the new module] --
  the same convention v1-v4/diag1 used for a brand-new entry, applied to
  the *existing* entry instead
- `rbase`/`rsize` for entry 62: **unchanged**, full original range --
  this isolates "can an entry's ownership be reattributed" from "does
  abandoning part of its range matter" (diag3 already answered the
  latter: yes, abandoning is safe)
- one new `.secinfo` entry is appended (diag2 already proved `.secinfo`
  growth alone is safe) describing an inert (zeroed, like diag1) content
  block positioned at the top of entry 62's existing range
- the callsite `bl` is left untouched, same as diag1/diag2/diag4/diag5 --
  nothing can ever branch into the new region, so this stays a pure
  structural-registration test, content-blind

## How to read the result

- **If this bricks with 270**: re-attributing an existing entry's
  ownership (`dw1`/`dw2`/`mod_id`) is itself unsafe, independent of any
  relocation -- pointing at something that validates entry 62
  specifically, or treats non-anonymous entries differently at boot in a
  way this session hasn't characterized yet.
- **If this boots fine**: the VirtRange array can safely describe a new
  module through an existing, unmoved entry. That opens a real path to
  restoring `fan` without ever touching `TaskInfo.virt_space` or growing
  the array past 63 entries -- the next step would be wiring real fan
  code into this same structural shape (content + callsite), instead of
  the zeroed/unreachable stub used here.

## What was verified (static)

- `.secinfo` walk reconfirms 577 existing entries and the
  `mod_id = secinfo_index + SIZE_INITIAL` convention (`SIZE_INITIAL=49`,
  matching every prior version).
- Entry 62 confirmed anonymous (`present=0`, `mod_id=0xffffffff`) before
  the patch, with its full original range verified to reach exactly the
  `0x2000000` ceiling.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region matches exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1-5/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`9c2129dd90f284dc29e9cc890149f6398c82e20c` (SHA1).
