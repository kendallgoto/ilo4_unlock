# 2026-11-12: Audit of previously-documented, never-tested items

Prompted after the `var_array` investigation showed this project has, more
than once, documented a structural detail or a recommended next step
without ever actually following up on it. Re-read every file in
`research/*.md` (14 files) and every `patches/*/readme.md` (25 files) in
full, specifically looking for claims/leads flagged as untested,
unverified, assumed, or "not yet done" that were never subsequently
revisited.

## Actionable: still worth doing

1. ~~`patches/277-tools` has never been hardware-tested~~ -- **revised
   after checking upstream provenance, 2026-11-12.** This repo is a fork
   of `kendallgoto/ilo4_unlock`. Confirmed every file in this fork's
   `patches/277-tools/` (`tools.S`, all three patch JSONs, `config`,
   `readme.md`) is byte-for-byte identical to the upstream copy -- no
   divergence. The upstream maintainer's own merged PR
   (`kendallgoto/ilo4_unlock#2`, merged 2022-03-08) describes the feature
   in confident, present-tense functional language: *"these tools allow
   for reading and modifying the iLO's memory while it is running... This
   also features a python REPL to interact directly with the iLO and
   inject & execute firmware on a running system."* This is strong,
   though not 100% explicit (no dedicated "I flashed this and it booted"
   research note or issue comment exists in either repo), evidence the
   base `help`-hijack/memory-probe technique is sound on 2.77 -- it is a
   real, working, maintained feature in the upstream project, not
   speculative code this project invented.

   **Revised conclusion:** flashing `277-tools` to independently
   re-confirm the base technique is very likely low-information-gain and
   not worth the flash-brick risk. More importantly, this narrows the
   still-open `patches/280-tools` mystery: it's now unlikely to be "the
   technique is broken in general" (good upstream evidence against) *and*
   it was already shown not to be "the 5 re-derived literal addresses are
   wrong for 2.80" (`research/2026-11-05-278-282-feasibility.md` --
   verified byte-identical function prologues across all six versions).
   Something else, specific to the 2.80 port or environment, remains
   genuinely unidentified. Chasing it further would need to look beyond
   both of those two already-substantially-ruled-out explanations.

2. **Existing, stock, read-only telemetry surfaces were never checked for
   live memory exposure**, independent of the broken `280-tools` memory
   probe. From `research/2026-11-06-v3-fan-restore-strategy.md`: *"any
   existing, stock, read-only iLO diagnostic surface that happens to
   expose memory contents (AHS log export, a SMASH-CLP target not yet
   explored, a RedFish diagnostics endpoint) would be worth checking
   before writing this option off. Not yet investigated this session."*
   This is zero-flash-risk (works against the already-confirmed-working
   plain `patches/280` image) and could directly validate or refute the
   "INTEGRITY Address Space is fixed at build time" explanation this
   project is currently relying on for why VirtRange re-attribution
   bricks -- instead of inferring it from boot-failure patterns alone.

3. **Whether `/system1` or an aggregate thermal target supports `set` for
   finer-grained fan control via Redfish/CLP was never tried.** From the
   same feasibility doc: *"Doesn't rule out `set` working on a different
   target... untested, and not attempted without deliberate decision given
   it'd be a write operation on live hardware."* This is a completely
   different path to the user's actual goal (quieter/more controllable
   fans) that doesn't touch firmware at all -- it was set aside out of
   caution about a live write, not because it was ruled out.

4. ~~`tools.S`'s `sprintf_fn`/`libc_malloc_fn`/`libc_free_fn` reference an
   address outside the firmware image and were never verified~~ --
   **struck after re-checking the source, 2026-11-12, then adversarially
   re-checked a second time against `tools.S` itself (not just prose
   summaries of it).** Confirmed directly by reading
   `patches/277-tools/asm/tools.S` (byte-identical to this project's 2.80
   port's logic): `libc_malloc`/`libc_free` are called only inside
   `cmd_alloc`/`cmd_free`, reached by comparing the user-supplied
   argument's first byte against `'a'`/`'f'` -- unreachable without a
   live, interactively-typed command. `sprintf` is defined as a trampoline
   but **never called anywhere in the file** (`grep -n "bl sprintf"`
   returns nothing) -- it's simply dead code, not merely hard to reach.

   The one claim worth being honest about: "280-tools bricks before SSH
   is ever reachable" is the *original research's own characterization*
   (`research/2026-11-05-278-282-feasibility.md`), not something
   independently reachability-confirmed for that specific brick the way
   diag7's unreachability was later confirmed this session. It's inferred
   from the garbage version readback (`255.255`) and BIOS POST 270 on the
   very next boot after flashing -- a sequence that leaves no window for
   anyone to have interactively run `help a`/`help f` before the first
   boot's POST check already failed. That inference is solid on its own
   terms; it just isn't the same thing as a directly-tested fact.

   Net: this candidate is ruled out, more confidently than the first
   correction stated, but the "before SSH reachable" premise it leans on
   is inherited, not independently re-verified. Keeping this
   struck-through rather than deleted so the correction is visible.

5. **2.81 and 2.82's plain signature-bypass-only builds were never
   separately hardware-tested** -- only 2.80 was confirmed working. Low
   urgency unless the target hardware is actually running 2.81/2.82.

## Lower-priority / likely moot given the VirtRange closure

- 87 "other-module" literal-pointer candidates from the v3/v4
  closure-relocation work were assumed benign for data-word references but
  never specifically re-verified that way (`2026-11-06-v3-literal-pointer-relocation-gap.md`).
- v4's two residual unproven assumptions (the `0xe915e8` fallback believed
  but not proven unreachable; the deleted fan-name string table not
  exhaustively ruled out as reachable some other way) --
  `patches/280-fan-restore-v4/readme.md`.
- 9 externally-referenced removed functions from the "106 removed
  functions" count were never individually traced for exact purpose
  (`2026-11-05-278-282-feasibility.md`).

All three of the above only matter if a safe module-registration mechanism
is found later; with VirtRange re-attribution closed
(`2026-11-12-virtrange-reattribution-closed.md`), none of this content has
anywhere to be placed right now.

## Historical, already closed out

- Early 2.77-only CLI wishlist items and internal `ConnectionRecord`/`r7`
  register speculation (`2022-02-17-docs.md`, `2022-02-19-onto-277.md`) --
  no bearing on 2.80+ or the fan/integrity investigations.
- `patches/250`'s "isn't intended for use, nor has it been tested" --
  intentionally untested scaffold, by design.
- The Health service-ID 5/6/7/8 dispatch table was "never reliably
  located" -- superseded by the later direct hardware test confirming the
  fan service is simply dead on 2.80 regardless of dispatch-table detail.
- `patches/280-fan-restore` v1/v2/v3's in-file "not yet done" framing is
  stale; each was superseded by the next version after its own hardware
  brick.
