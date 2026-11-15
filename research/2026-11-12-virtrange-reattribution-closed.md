# 2026-11-12: VirtRange re-attribution is closed -- 6/6 hardware-confirmed failures

## Verdict

**Converting any anonymous (`present=0`) `VirtRange` entry in Health's
`.boottable` to `present=1` is fatal, unconditionally.** Six diagnostic
builds hardware-tested this across every structurally distinct variable
this project could isolate, with zero survivors. This closes out "register
a new or existing module via VirtRange re-attribution" as a restoration
mechanism for `fan` entirely -- not one variant of it, the whole technique.

## Cumulative results

| Build | New `present=1` link? | New `mod_id`? | Array relocated? | Entry position | Result |
|---|---|---|---|---|---|
| diag2 (`.secinfo` growth, unreferenced) | no | n/a | no | n/a | booted fine |
| diag3 (in-place `rsize` shrink, stays anonymous) | no | n/a | no | n/a | booted fine |
| diag1 (new 64th entry + array relocation, new module) | yes | yes | yes | new entry, past ceiling | **bricked** |
| diag4 (relocate `virt_space` only, address `0x4000000`) | n/a (no new module) | n/a | yes | n/a | **bricked** |
| diag5 (relocate `virt_space` only, tight address) | n/a (no new module) | n/a | yes | n/a | **bricked** |
| diag6 (reuse entry 62 in place, new module) | yes | yes | no | ceiling (entry 62) | **bricked** |
| diag7 (reuse entry 62 in place, alias existing module) | yes | no | no | ceiling (entry 62) | **bricked** |
| diag8 (reuse entry 11 in place, alias existing module) | yes | no | no | mid-table (entry 11) | **bricked** |

Every variable that could plausibly have been the real culprit was tested
in isolation and shown **not** to matter:

- **Registration mechanism**: new array entry + relocation (diag1) vs.
  in-place slot reuse with no relocation at all (diag6/7/8) -- both fail
  identically.
- **`mod_id` newness**: a brand-new `mod_id` backed by a freshly-appended
  `.secinfo` entry (diag1, diag6) vs. aliasing an existing, already-valid,
  completely unmodified module (diag7, diag8) -- both fail identically.
  This rules out a per-module content hash/checksum as the mechanism:
  diag7/8 touch zero bytes of the aliased module's actual content.
- **Array relocation address**: `0x4000000` (diag4) vs. a tight,
  purpose-computed address (diag5) -- both fail identically, ruling out
  the `FUN_2000b16c` image-end fit-check as the (sole) explanation.
- **Entry position**: the ceiling-ending entry, entry 62 (diag6, diag7)
  vs. a mid-table entry 8.5 MiB below the ceiling, entry 11 (diag8) --
  both fail identically, ruling out "the kernel treats the last/ceiling
  entry specially" as the explanation.
- **Content**: diag7/diag8 patch zero content bytes (pure structural
  alias); diag6/diag1 do add inert zeroed content. No difference in
  outcome.

The only thing every bricked build shares, and the only thing every clean
build (diag2, diag3) avoids, is: **a VirtRange entry's `present` field
flips from 0 to 1.** That is now the full extent of what's provable by
black-box hardware testing from this side.

## Why, probably (not confirmed -- would need a live debugger or vendor docs)

Per `research/2026-11-06-kernel-re-methodology-and-pitfalls.md`, this
firmware runs Green Hills INTEGRITY RTOS, whose Address Space model is
documented (independently, by Perigaud/Gazet/Czarny's 2018 REcon research
on this exact product) to be **fixed at system-integration/build time, not
dynamically extensible**, with `AddressSpaceLimitExceeded` as a real, named
OS error. The leading explanation, consistent with every result above: an
anonymous (`present=0`) `VirtRange`/`MEM_RANGE` entry is not simply "a
memory range nobody's using yet that you can claim" -- it's a *descriptor*
for a region whose actual MMU page-table backing (or lack of it) was
decided by the System Builder tool when the image was integrated, outside
anything this project can edit by patching the shipped binary. Flipping
`present` to 1 in the descriptor doesn't grant the underlying hardware
mapping; it just makes the kernel's own task-setup code try to use a
mapping that was never built, which fails immediately and totally,
independent of which entry, which module, or how the registration is
wired -- exactly the uniform, total-boot-failure signature observed six
times in a row.

This is "very likely," not proven: nothing here caught the exact
instruction/trap that fires, and that would need either a live debugger
on real hardware or vendor documentation this project doesn't have access
to.

## What this doesn't rule out

- **Runtime safety was never actually tested.** No diagnostic in this
  series ever wired a callsite to branch into the registered region --
  every one was a content-blind structural test. If a mechanism had
  survived boot, it still wouldn't have proven safety under sustained
  operation.
- **An integrity-check gap was separately audited and ruled out** (see
  `research/2026-11-12-integrity-check-audit.md`) -- the bricks are not
  explained by a missed checksum/signature check.
- This doesn't bear on non-VirtRange approaches (e.g. a task that already
  has spare, *present* capacity in its own declared module, or a
  completely different restoration path like direct I2C/GPIO access,
  which `research/2026-11-05-278-282-feasibility.md` already flagged as
  unexplored).

## Addendum, 2026-11-12: checked for a nuanced/undetected breakage before accepting the verdict above

Before trusting "closed," checked two things a plain round-trip/structural
verification wouldn't catch:

1. **Full byte-diff, stock vs. diag8-patched `elf.bin`.** Exactly 4
   contiguous differing byte-runs: the 1-byte ELF sig-bypass patch, and
   the 3 fields actually intended to change (`present`, `rights`,
   `mod_id`). Nothing else in the 24MB file differs -- the build script
   isn't silently touching anything adjacent.
2. **Decoded `TaskInfo`'s second array** (documented but never actually
   read, at `TaskInfo+0x14`, count at `+0x10`, see
   `2026-11-06-kernel-re-methodology-and-pitfalls.md`) for Health
   specifically, to check whether it's a parallel/shadow structure that
   also needs updating when a `VirtRange` entry's `present` bit flips --
   something none of the 8 diagnostics ever touched or checked.
   - 270 entries, not 63 -- **not** a 1:1 shadow of the `VirtRange` array.
   - Entry-type distribution: `{1: 218, 3: 49, 7: 2, 4: 1}`.
   - Checked every field of all 270 entries against entry 62's and entry
     11's address ranges (both task-local and true-vaddr hypotheses):
     **zero matches**.
   - The two pointer-bearing (`type=7`) entries point ~0x70/0x63 bytes
     *before* `.secinfo`'s own start -- consistent with this being
     INTEGRITY's "Variable" kernel object declarations (a lightweight
     IPC/sync primitive the task declares), not a memory-region shadow
     table.

Neither check found evidence of a subtler breakage mechanism. This doesn't
prove none exists -- only that the two most concrete, checkable
"what else could be inconsistent" candidates came back clean -- but it
raises confidence that the verdict above isn't an artifact of an
undetected scripting bug or an unexamined parallel structure.

## Addendum, 2026-11-12 (diag9): permission bits are also fixed at build time

A follow-up question this closure didn't address: every bricked build
above changed `present` (dw1) from 0 to 1. Does the kernel's build-time
immutability extend to an **already-present** entry's permission bits
(`rights`, dw2: 5=executable, 7=data), or is only *presence* fixed, with
permission free to change on a region the kernel already has real MMU
backing for?

`patches/280-diag9-rights-flip-existing-entry` tested this directly: took
an existing, already-`present=1`, `rights=7` (data) VirtRange entry and
flipped only its `rights` field to 5 (executable), in place --
`present`/`rbase`/`rsize`/`mod_id`/content/callsite all untouched. This is
a different variable than every build in the table above (which all
toggled `present`), so it isn't folded into the "6/6" count, but it is the
same investigation's natural next question.

**Result: bricked with error 270**, the identical signature. Permission
bits are *also* fixed at build time, not just presence. The INTEGRITY
Address Space model enforces the entire `MEM_RANGE` descriptor -- presence
and permission together -- as immutable once the image is built.

This closes "reuse an existing module's slot with different permissions"
as a mechanism too. Combined with the entry-2 dead-space investigation
(confirmed live in all 6 shipped firmware versions,
`research/2026-11-12-entry2-literal-table-re-examined.md`), every axis of
"edit a VirtRange descriptor to carve out room for `fan`" that this
project could isolate has now been hardware-tested: presence (6/6
bricked), permission (1/1 bricked), and "is there free space in an
existing present module at all" (no -- entry 2, the only one large
enough, is live). The only mechanism not ruled out by this entire family
is overwriting the *content* of an already-present, already-correctly-
permissioned module in place -- the injection technique
`patches/277-tools`/`patches/280-tools`/`patches/280-memprobe-readonly`
use, which never touches VirtRange at all.

## Recommendation

Per this project's own systematic-debugging discipline (3+ failures of the
same hypothesis class means question the architecture, not the next
variant of it) -- already raised once after diag6, continued per explicit
user direction, and now at 6 consecutive, maximally-diversified failures --
**VirtRange re-attribution should be considered closed.** Continuing to
test further variants of "flip an anonymous entry to present" is very
unlikely to produce a different result; every axis of variation available
within this technique has now been exhausted. The live, unresolved paths
forward are the ones `research/2026-11-05-278-282-feasibility.md` already
named: direct I2C/GPIO hardware-level fan control research, or accepting
that fine-grained PWM control is not achievable through this software layer
on 2.80+.
