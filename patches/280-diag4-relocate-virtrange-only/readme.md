# iLO 2.80 Diagnostic Build #4: relocate the VirtRange array only -- NOT A REAL PATCH

**Follow-up to `patches/280-diag2-secinfo-only-growth` (BOOTED FINE --
cleared `.secinfo` list growth, 577 -> 578, as a cause on its own) and
`patches/280-diag3-shrink-only` (BOOTED FINE -- cleared shrinking the
pre-existing last anonymous VirtRange entry's `rsize` in place, as a
cause on its own).**

## Narrowing further

With diag2 and diag3 both clean, the fault is narrowed to what's left of
diag1's VirtRange-side change:

- (b1) relocating the 63-entry VirtRange array out of its original
  location inside `.boottable` into a brand-new, freshly-appended ELF
  section (required because the original array has no room to grow in
  place once a 64th entry is added)
- (b2) bumping Health `TaskInfo.virt_space_size` `63 -> 64`
- (b3) appending a new, real 64th VirtRange entry

This build tests **(b1) alone**, as minimally as possible: it copies the
existing 63 VirtRange entries **byte-for-byte unchanged** (no shrink, no
new entry) into a brand-new section appended to the file, and repoints
`TaskInfo.virt_space` (the pointer only) at the new location:

- `TaskInfo.virt_space_size` stays 63 (byte-identical, untouched)
- no new VirtRange entry is added -- the copied array is exactly the
  same 63 entries, same bytes, same order
- no new `.secinfo` entry is added (diag2 already cleared `.secinfo`
  growth as a cause, so this build doesn't re-exercise it)
- the callsite `bl` is untouched
- the only field touched anywhere in TaskInfo is the `virt_space`
  pointer value itself

## How to read the result

- **If this bricks with 270**: merely moving the VirtRange array's
  storage location -- independent of entry count or content -- is
  sufficient on its own. That would point at something that only works
  when `TaskInfo.virt_space` resolves through the original static
  `.boottable` mapping (e.g. a boot-time path that locates the table
  structurally relative to `.boottable` rather than through the same
  resolution used for other relocatable/appended regions).
- **If this boots fine**: relocation itself is safe. The fault is
  isolated to (b2) and/or (b3) -- bumping `virt_space_size` to 64
  and/or the new 64th entry's presence/content. The next diagnostic
  would test bumping the count to 64 with a new entry that's a
  harmless duplicate of an existing one, vs. a genuinely new entry
  claiming fresh address space.

## What was verified (static)

- Existing 63-entry VirtRange table confirmed intact and still reaches
  exactly the confirmed `0x2000000` per-task ceiling before relocation.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region (at
  `firmware.map['BOOTLOADER'] - firmware.map['BOOTLOADER_HDR']`) matches
  exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1/diag2/diag3/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`ae10bb8bcc8de730e23566f23c52f423b84d59a2` (SHA1).
