# iLO 2.80 Diagnostic Build #8: reattribute a non-ceiling anonymous entry -- NOT A REAL PATCH

**Follow-up to `patches/280-diag7-alias-existing-modid`, which ALSO bricked
with 270 -- the 4th consecutive brick of the same hypothesis class
(diag1, diag4, diag5, diag6, diag7 all create a new, real `present=1`
link from a VirtRange entry to a module; all five brick).**

## A question raised before building this one

After diag7's result, a sharper question was raised about the test
methodology itself: every one of the five bricked builds reused the
*same* VirtRange entry -- entry 62, the **last** entry in Health's table,
the one whose range ends exactly at the per-task `0x2000000` ceiling.
Two things needed checking before trusting "any new present=1 link is
fatal" as the conclusion:

1. **Is the 270/garbage-version failure signature actually "total iLO
   boot failure," or could it be a narrower "one specific BIOS-comms
   path broke while iLO is otherwise alive"?** Existing (pre-session)
   evidence says the former -- `flash_ilo4` reports success, version
   reads back as garbage, AC power cycle doesn't fix it -- which is the
   signature of the whole RTOS never finishing boot, not a narrow comms
   regression. (Not independently re-verified per diagnostic in this
   session, but consistent with the v1/v2 postmortems.)
2. **Is entry 62 itself a live buffer that Health's own code reads or
   writes** -- i.e. are we bricking because we're clobbering specific
   content, not because of the registration mechanism at all? A
   literal-pool scan of `.health.elf.text`/`.health.elf.data` for word
   values landing in entry 62's address range (tested under both a
   task-local and a true-vaddr-translated hypothesis for what the
   literal pool would actually store) found only **1 isolated hit per
   hypothesis** -- statistically consistent with noise, not a real
   reference. Contrast with the v1 postmortem's smoking gun: 9
   evenly-spaced genuine hits that proved an actual BSS collision.

So Health's own compiled code doesn't appear to reference entry 62's
content directly. But that doesn't rule out the INTEGRITY kernel itself
treating the **last** VirtRange entry specially at task-boot time --
e.g. using whatever's anonymous at the top of the table as generic
heap/stack backing, sized from the entry's `rbase`/`rsize` fields
directly rather than via any hardcoded literal in Health's own code
(which would explain why the literal scan finds nothing, yet corrupting
it is still fatal). If that's the real mechanism, the fatal variable was
never "new mod_id" or "present=1 conversion" in general -- it's
specifically about disturbing the **ceiling** entry.

## This build

Identical in-place re-attribution mechanics to diag6/diag7 (no
relocation, no VirtRange count change, `rbase`/`rsize` unchanged, alias
to the same existing `mod_id=0x81` diag7 used, so mod_id-newness stays a
controlled variable) -- but applied to **entry 11** instead of entry 62.

Entry 11 (task-local `0x1600000`-`0x1780000`, 1.5MB) is anonymous
(`present=0`, `mod_id=0xffffffff`) just like entry 62, but sits in the
middle of the table, 8.5 MiB below the `0x2000000` ceiling, with
unrelated entries both before (entry 10, a 16MB anonymous block) and
after (entry 12, an existing present=1 module) it. A literal-pool scan
of entry 11's range found only 4 hits in `.text` and 0 in `.data` -- the
same noise-floor order of magnitude as entry 62, so it's an equally
"clean" (non-referenced) target. The only variable that changed versus
diag7 is **position in the table**, not size class, not reference
density, not registration mechanics.

## How to read the result

- **If this bricks with 270**: position isn't the differentiator either.
  Reattributing *any* anonymous entry, anywhere in the table, to
  `present=1` is fatal -- not just the ceiling one. The "any
  present=0->1 conversion is fatal" conclusion from diag6/diag7 stands,
  now also ruling out "it's specifically about the ceiling entry" as an
  alternative explanation. This would close out VirtRange re-attribution
  as a restoration mechanism entirely, independent of which entry is
  targeted.
- **If this boots fine**: the ceiling entry (entry 62) specifically is
  special -- almost certainly kernel-managed heap/stack sizing for the
  task, consistent with `research/2026-11-06-v3-fan-restore-strategy.md`'s
  characterization of anonymous regions as "likely live heap/stack/
  scratch." Future registration attempts should target a non-ceiling
  anonymous entry (like entry 11, or others of similar size/position)
  instead of entry 62, and this reframes four of the five prior bricks
  (diag1, diag4, diag5 -- which also only ever manipulated the array
  tail/ceiling region -- plus diag6/diag7) as all having hit the same
  single structural landmine rather than confirming a broader rule.

## Result

**CONFIRMED BROKEN on real hardware, 2026-11-12.** Same 270 "iLO FW
Communication Issue" as every prior registration-variant diagnostic. This
rules out the ceiling-entry hypothesis above: position in the table is not
the differentiator. Combined with diag1/4/5/6/7, this is the 6th
consecutive, independently-isolated hardware-confirmed failure of "convert
an anonymous (`present=0`) VirtRange entry to `present=1`" -- tested across
every variable this project could isolate (new entry vs. reused slot,
relocated array vs. untouched, new `mod_id` vs. existing/aliased, ceiling
entry vs. mid-table entry) with zero survivors. See
`research/2026-11-12-virtrange-reattribution-closed.md` for the full
cumulative analysis and conclusion.

## What was verified (static)

- Entry 1 reconfirmed as Health's own `.health.elf.text` module
  (`mod_id=0x81`, `rights=5`) before reusing its mod_id, same as diag7.
- Entry 11 reconfirmed anonymous (`present=0`, `mod_id=0xffffffff`)
  before the patch, with its range fresh-derived (not hardcoded) and
  checked to immediately follow entry 10 and immediately precede entry
  12 with no gap or overlap, and to sit comfortably (8.5 MiB) below the
  per-task ceiling.
- Full compression round-trip: decompressed ELF and kernel match the
  patched inputs byte-for-byte; bootloader region matches exactly.

## Build

Not committed as a binary artifact (proprietary HP firmware bytes); built
into the session scratchpad only, same pipeline as diag1-7/v4.

This build's result hash (`firmware.bin.backdoored.toflash`), this run:
`24dec3d1c85e30eb047c388607729c177b4abd7a` (SHA1).
