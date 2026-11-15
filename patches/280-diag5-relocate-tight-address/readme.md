# iLO 2.80 Diagnostic Build #5: relocate VirtRange, tight address -- NOT A REAL PATCH

**Follow-up to `patches/280-diag4-relocate-virtrange-only` (BRICKED with
270 -- proved relocating the VirtRange array out of `.boottable` into a
new section is, by itself, sufficient to brick, independent of entry
count or content).**

## The key lead: `FUN_2000b16c`

After diag4 bricked, `research/2026-11-06-kernel-re-methodology-and-
pitfalls.md` was consulted. It documents a real, Ghidra-decompiled
boot-time/flash-validation routine, `FUN_2000b16c`, which for every task
does:

```c
virtspace_ptr = relocate(TaskInfo + 8);
if (image_end < virtspace_ptr + virt_space_size * 0x20)
    goto fail;
```

This is a **structural fit-inside-the-loaded-image check on the pointer
value itself** -- independent of what's actually stored at that address.
It would reject *any* relocation of `virt_space` to an address beyond the
image's real extent, regardless of entry count or content.

## What the real firmware's own layout shows

Measuring the genuine, unmodified 2.80 `elf.bin` directly:

- the highest `sh_addr + sh_size` across every real section is
  `0x3e22b18` (~62.14 MB) -- `.secinfo` itself, the highest-addressed
  thing in the genuine firmware.
- v1 through v4, diag1, and diag4 all anchored their newly-appended
  section at `NEW_PHYS_BASE = 0x4000000` (exactly 64 MB) -- a round
  number chosen only because it was checked against a *lower* bound
  (past everything currently used, `>= max_existing_secinfo_end`),
  never checked against the image's real *upper* bound. `0x4000000`
  sits **~1.86 MB beyond** the real image's highest address.
- every build that repointed `TaskInfo.virt_space` into that
  `0x4000000`-anchored section bricked (v1, v2, v3, v4, diag1, diag4).
  Every build that left `virt_space` untouched (diag2, diag3) booted
  fine. This is exactly the pattern `FUN_2000b16c`'s fit-check predicts
  -- and it would mean the actual root cause of every 270 brick in this
  entire investigation was simply **the address chosen for the new
  section**, not any relocation-math error, entry-count change, or
  Address-Space ceiling.

## This build

Diag4's exact test (relocate the unchanged 63-entry VirtRange array,
byte-for-byte identical, into a new section; count, content, `.secinfo`,
and callsite all untouched) with **one change**: the new section is
anchored immediately after the real end of the existing image
(`0x3e22b18`, 4-byte aligned -- already aligned, so `NEW_PHYS_BASE` is
exactly `0x3e22b18`) instead of the arbitrary `0x4000000`.

## How to read the result

- **If this boots fine**: the image_end/address-choice hypothesis is
  confirmed. The real root cause of every 270 brick in this whole
  investigation was an improperly chosen insertion address -- not
  relocation mechanics, not entry count, not an Address-Space ceiling.
  A genuine fan-restore patch would need to anchor its new section
  tightly against the real image end rather than a round placeholder.
- **If this still bricks with 270**: relocation out of `.boottable` is
  broken for a different or additional reason, and `FUN_2000b16c`'s
  fit-check is not the (or not the only) culprit -- the next diagnostic
  would need to dig further into why relocating `virt_space` itself,
  independent of address value, is unsafe.

## What was verified (static)

- Existing 63-entry VirtRange table confirmed intact and still reaches
  exactly the confirmed `0x2000000` per-task ceiling before relocation.
- Real image end independently recomputed directly from the genuine
  `elf.bin`'s own section headers: `0x3e22b18`.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region matches exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1-4/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`ec075555fd75903397167a90b1e10285758836f5` (SHA1).
