# iLO 2.80 Diagnostic Build #3: shrink the last VirtRange entry's size only -- NOT A REAL PATCH

**Follow-up to `patches/280-diag1-null-injection` (bricked -- fault is in
the structural registration mechanism, not fan code) and
`patches/280-diag2-secinfo-only-growth` (BOOTED FINE -- cleared `.secinfo`
list growth, 577 -> 578, as a cause on its own).**

## Narrowing further

With diag2 clearing `.secinfo` growth, the fault is isolated to the
VirtRange side of diag1's change -- which itself bundled two things:

- (a) shrinking the pre-existing LAST anonymous VirtRange entry's `rsize`
  field in place (reclaiming its tail)
- (b) bumping Health `TaskInfo.virt_space_size` `63 -> 64` and appending a
  brand-new 64th VirtRange entry (which requires relocating the whole
  63-entry array to a new file location, since the original array has no
  room to grow in place)

This build tests **(a) alone**, as minimally as possible: it patches
**only the 4-byte `rsize` field** of the existing last anonymous VirtRange
entry, in place, at its original file offset. Nothing else in the file
changes:

- `TaskInfo.virt_space_size` stays 63 (byte-identical, untouched)
- the pointer to the VirtRange array (`VIRT_SPACE_FOFF`) stays untouched,
  still pointing at the **original** array location (not relocated)
- no new ELF section is inserted -- **the file does not even grow**
- no new `.secinfo` entry is added
- the callsite `bl` is untouched

The reclaimed tail space (`0xc320` bytes, same amount as v3/v4/diag1, for
apples-to-apples comparison) is left completely unregistered: nothing
claims it, nothing points at it.

## How to read the result

- **If this bricks with 270**: merely shrinking that one pre-existing
  entry's size value is sufficient on its own, independent of the count
  bump or the new entry. That would point at something that validates
  this specific entry's size elsewhere (a checksum over the VirtRange
  table, or a cross-reference expecting the original `0xe0000` `rsize`
  value).
- **If this boots fine**: the fault is isolated to (b) -- bumping
  `virt_space_size` to 64, and/or appending the new 64th entry, and/or
  relocating the array to a new file location. The next diagnostic would
  split those further (e.g. relocate the array to a new location with the
  SAME 63 entries and count, vs. actually bump the count to 64 with an
  inert/unused 64th entry).

## What was verified (static)

- Same ceiling/anonymous-entry derivation and assertions as every prior
  version.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region (at
  `firmware.map['BOOTLOADER'] - firmware.map['BOOTLOADER_HDR']`) matches
  exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1/diag2/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`c76326009bde11317ff9864349878b28a67e29d6` (SHA1).
