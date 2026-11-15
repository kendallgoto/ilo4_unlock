# iLO 2.80 Diagnostic Build #2: `.secinfo` list growth only, VirtRange untouched -- NOT A REAL PATCH

**Follow-up to `patches/280-diag1-null-injection`, which bricked with the
identical BIOS POST 270 even with zeroed content and an untouched
callsite -- proving the fault is in the structural registration mechanism
itself, not in any fan-code content or relocation.**

## What diag1 proved, and what's still ambiguous

diag1 bundled two distinct structural changes together:

- (a) Health TaskInfo.virt_space_size `63 -> 64`, VirtRange table extended
  with a new 64th entry (reclaiming the tail of the last anonymous entry)
- (b) the firmware-wide `.secinfo` linked list extended from 577 to 578
  entries (a new tail entry appended)

diag1 did both at once and bricked. This build does **only (b)**: it
appends a new `.secinfo` entry (list grows to 578), but Health's own
`TaskInfo` and `VirtRange` table are **completely untouched** --
`virt_space_size` stays 63, and the `VIRT_SPACE_FOFF` pointer still points
at the original, byte-for-byte unmodified 63-entry array. The new
`.secinfo` entry claims a physical range that nothing in Health's
per-task view maps to.

## How to read the result

- **If this bricks with 270**: merely growing the `.secinfo` list count
  (577 -> 578) is sufficient on its own, independent of VirtRange. That
  would mean something elsewhere in the firmware treats 577 as a fixed,
  expected total -- an integrity/count check, a hardcoded loop bound, or a
  separately-stored total that must agree with the walked list length.
  Notably, every build script in this project (v1 through v4, diag1, this
  one) has independently asserted `total_existing_secinfo_entries == 577`
  as a documented, previously-verified constant -- this test directly
  checks whether 577 is a load-bearing fixed value elsewhere in the
  firmware, not just a derived fact about the current list.
- **If this boots fine**: the fault is isolated to (a), the VirtRange
  63 -> 64 extension -- e.g. a fixed-size 63-slot buffer elsewhere in the
  kernel that a 64th entry overflows, regardless of what's in it. The next
  diagnostic would invert this build: extend VirtRange to 64 while leaving
  `.secinfo` at 577 (reusing an existing, unrelated `.secinfo` entry's
  `mod_id` for the new VirtRange slot, purely to test the table-size change
  in isolation).

## What this build does differently from diag1

- Appends exactly one new `.secinfo` linked-list entry (name
  `.health.diag2_secinfo_only`), same entry-struct shape as diag1/v4.
- Does **not** read or write `HEALTH_TASKINFO_FOFF` (`0x166059c`) or
  either of its two trailing fields (`virt_space_size`, `virt_space`
  pointer) at all -- those bytes are guaranteed byte-identical to stock
  2.80.
- Does **not** build or insert any VirtRange array.
- Callsite `bl` at `0x38e5d8`: left untouched, same as diag1.

Build script: `build_diag2.py`.

## What was verified (static)

- `.secinfo` walk confirms 577 existing entries before the patch (same
  invariant re-checked by every version of this project), new tail
  `next_ptr` correctly repointed to the new entry.
- Full compression round-trip: decompressed ELF and kernel sections pulled
  back out of `firmware.bin.backdoored.toflash` match the patched inputs
  byte-for-byte; raw bootloader region (at `firmware.map['BOOTLOADER'] -
  firmware.map['BOOTLOADER_HDR']`) matches exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same steps as diag1/v4:

1. `python3 build_diag2.py <extracted 2.80 elf.bin> <output elf.bin>`
2. Apply `patches/280/patch_bootloader.json` / `patch_kernel.json`.
3. `ilo4_repack.py <genuine 2.80 firmware.bin> firmware.map <patched elf.bin> <patched kernel_main.bin> <patched bootloader.bin>`
   (via `docker run --rm -v ... python:2.7`).

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`c9ec0db1c6722dc01ed233a91c0c8805c03d43ff` (SHA1).
