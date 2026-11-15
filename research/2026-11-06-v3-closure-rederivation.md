# 2026-11-06: Re-deriving the `fan` dependency closure from scratch (v3)

Per instruction: don't trust v1/v2's closure data (it predates everything
learned this session), rebuild it properly using Ghidra against the real,
hash-verified 2.77 and 2.80 `elf.bin`s. This documents the result and the
methodology, since it's a substantial amount of re-derived ground truth
that shouldn't need repeating.

## Headline result: the old closure was genuinely incomplete

The old closure (`research/2026-11-05-278-282-feasibility.md`): **8
functions, 15,128 bytes** (+ ~420 bytes of data = `fan_block.bin`'s
15,548).

Re-derived via a full transitive call-graph walk from the `fan` handler's
entry (true vaddr `0xe16970`, task-local `0x3a970`) in 2.77 -- following
**both** `bl`/`blx` calls and plain `b`/`b<cc>` jumps (an initial pass that
only followed calls missed a 12-byte shared epilogue tail reached by a
plain `b`, the exact class of gap being guarded against here). The walk
reaches **163 functions total**. Checking every one against 2.80 by
normalized instruction-mnemonic signature:

- **124 already exist, unchanged, in 2.80** (genuinely stable -- safe to
  call directly from the new block, no need to carry them).
- **14 do not exist in 2.80 at all** and must be included in the new
  block:

| addr (true vaddr) | size |
|---|---|
| 0xe1589c | 700 |
| 0xe16970 | 13424 (the main handler) |
| 0xe2326c | 4836 |
| 0xe274c8 | 1008 |
| 0xe2d0c4 | 1668 |
| 0xe2e338 | 988 |
| 0xe32b80 | 320 |
| 0xe3c148 | 4264 |
| 0xe7d3e0 | 756 |
| 0xe7dab8 | 12 (shared epilogue tail) |
| 0xe7dac4 | 120 |
| 0xe7db3c | 316 |
| 0xe7e6c0 | 80 |
| 0xe7e710 | 80 |

**Total: 28,572 bytes of code alone** -- nearly double the old estimate,
before any string/constant data these functions reference is even added
(at least one confirmed `adr`-referenced string/data blob exists past the
epilogue tail at true vaddr `0xe7dc94`, not yet catalogued). This directly
explains the project's own earlier, separate finding of "106 removed
functions, ~41KB" -- the old fan-closure walk simply didn't reach 6 of the
functions it actually depends on; this walk, cross-checked three different
ways (see below), does.

## External reference resolution

Of the 76 distinct addresses the 14 functions call/reference outside
themselves, matching by normalized instruction signature alone leaves 124
of the *overall* 163 uniquely resolved and 25 ambiguous (multiple
identical-looking candidates in 2.80 -- short, templated-looking
accessor stubs). Narrowing to just the ambiguous targets actually used by
the 14 missing functions leaves **8** that matter. Disambiguated by, in
order of preference:

1. **Call-target correlation**: if the ambiguous function's own internal
   `bl` target is itself uniquely resolved, the correct candidate is
   whichever one calls that same resolved target. Resolved `0xe2713c` and
   `0xe79e18` this way.
2. **Literal-pool constant comparison**: several of these are generic
   "load a small integer field-offset from a literal pool, add it to a
   shared base" accessors -- the literal pool *value* (not its address,
   which is version-dependent) is a small integer (e.g. `0x1f4e`,
   `0x1f8a`) that doesn't change between firmware versions. Resolved
   `0xe79fb0`, `0xe7a040`, `0xe7a63c`, `0xe7a664` this way, each an exact,
   unambiguous numeric match.
3. **Ordinal-family matching**: when a whole family of near-identical
   stub functions has the *same count* in both 2.77 and 2.80 (sorted by
   address), position-in-family is a reliable match (compiler/linker
   preserves declaration order even when absolute addresses shift).
   Resolved `0xe74374` this way (family of 2 in both versions).

**One remains genuinely unresolved**: `0xe2dfd4` (a 9-member family in
2.77, only 8 in 2.80 -- one sibling was dropped, and which one determines
how the remaining 8 realign). Needs caller-tracing on the dropped member
to resolve properly; not yet done. This is a real gap, explicitly flagged
rather than guessed at.

Full address-level mapping: `patches/280-fan-restore-v3/closure_mapping.json`.

## Tooling notes (building on `2026-11-06-kernel-re-methodology-and-pitfalls.md`)

- Ghidra's own auto-analysis (`-import` without `-noanalysis`) works well
  on a real, uncompressed ELF code section extracted at its true load
  address -- no seeding needed, unlike the compressed-kernel case.
- A `GhidraScript` can do real iterative worklist algorithms (not just
  one-shot dumps) -- the transitive-closure walk is a plain Java
  `ArrayDeque` worklist over `getReferencesFrom()`/`getFunctionAt()`,
  nothing exotic.
- Normalized-signature matching (mnemonic sequence only) is necessary
  (raw bytes differ because branch/literal immediates get re-encoded by
  the linker even for functionally-identical code) but **not sufficient**
  for short, templated functions -- several families of near-identical
  accessor stubs required literal-pool *value* comparison or ordinal
  position to disambiguate.
- Hand-decoding ARM branch immediates is error-prone even after doing it
  correctly earlier in this same session -- a manual decode of one
  instruction came out wrong by 16 bytes; re-deriving the same value via
  Ghidra's own reference info caught it immediately. Prefer the tool's
  decode over redoing it by hand once it's available.

## What's left before this is usable

1. Resolve `0xe2dfd4` properly (don't guess).
2. Catalogue the string/constant data the 14 functions reference via
   `adr` (at least one confirmed, likely more -- old docs mention "21
   format strings + 2 pointer-indirection words").
3. Extract real bytes for all 14 functions + data from 2.77, build the
   actual byte-level relocator (re-encode every branch/literal that's
   internal-to-the-new-block or crosses into one of the resolved external
   targets, for the new load address chosen in
   `research/2026-11-06-v3-fan-restore-strategy.md`).
4. Exhaustively verify every re-encoded branch by decoding the output
   bytes and confirming the computed target, the same discipline already
   applied to the callsite trampoline in `build_patched_280.py`.
