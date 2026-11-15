# iLO 2.80 Patch (signature-bypass + full `fan` command backport) -- EXPERIMENTAL, NOT HARDWARE-TESTED

**Status: static build verified only. Has NOT been flashed to real hardware.**
Do not flash this to a production/relied-upon iLO without understanding the
risk below and accepting that a bad outcome may require physical chip
reprogramming to recover from.

This is a from-scratch binary backport of the `fan` CLI command's actual
handler code (not just a cosmetic rename like `patches/280-fan`) from 2.77
into 2.80. It relocates the full dependency closure of the removed `fan`
handler (8 functions, 15,128 bytes of code, plus ~420 bytes of format
strings/constants -- 15,548 bytes total) into previously-unused-but-already
-mapped RWX memory inside the Health task's address space, re-links every
branch/literal/ADR reference in the relocated code for its new address, and
re-enables the CLI registration call site that HPE's 2.78 build disabled.

See `research/2026-11-05-278-282-feasibility.md` (section "Backporting the
`fan` handler cluster into 2.80") for the full methodology: dependency
closure discovery, the ARM32 relocation approach (no decompiler, no
assembler -- direct instruction bit-manipulation), why no new
`.secinfo`/`.boottable` entries were needed, and exactly what was verified
and what was not.

## Why this might still be a bad idea

HPE's iLO4 2.78 security bulletin (HPESBHF04134) documents a local buffer
overflow fix in the same release where this code was removed. There is no
confirmed causal link between that fix and this specific code path, but it
is circumstantial evidence that restoring this exact code could reintroduce
a real vulnerability. This patch was built anyway, at the explicit request
of (and accepted risk by) the repo maintainer testing on their own
hardware, for personal/homelab fan-noise-reduction use -- **not** recommended
for wider distribution until/unless hardware-verified and the security
question is better understood.

## What was verified (static only)

- Independent re-parse with pyelftools: all 628 ELF sections enumerate
  correctly, `.health.elf.data`'s grown size (`0x2e8c` -> `0x6cbc`) is
  consistent between the ELF section header and the `.secinfo` entry, the
  injected code lands at exactly the intended vaddr (`0xe94000`).
- Zero unresolved branch/literal targets across all 100 branch
  instructions in the relocated closure.
- `ilo4_repack.py` completes without error and produces a
  16,777,216-byte flashable image, the same size as the known
  hardware-confirmed-working 2.80 sig-bypass-only build.

## What was NOT verified

- Whether the relocated code actually behaves correctly at runtime (a
  single incorrect fixup could silently corrupt Health-task memory,
  crash the task, or cause a reboot loop -- none of this would be caught
  by the static checks above).
- Whether this reintroduces the vulnerability the 2.78 bulletin may have
  fixed.

## Build

Produced via a one-off Python script
(`~/ilo-work/build_patched_280.py`, not checked into this repo --
see the research doc for the full derivation), not the JSON-patch-list
mechanism used by other patches in this repo, because it performs a
byte-insertion + section-header/`.secinfo` fixup rather than a fixed-offset
overwrite. The final 15,548-byte relocated code+data blob is
`fan_block.bin` in this directory; `elf_patch_summary.md` in this
directory records the exact offsets involved for reproducibility.

Result: `ilo4_280.bin.fan_restore.patched`
sha1: `5e2f2649c6e782ff6798f4eb032887a85a666f53`
