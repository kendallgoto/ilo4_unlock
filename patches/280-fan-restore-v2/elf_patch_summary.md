# Exact patch details (2.80 `elf.bin`, pre-sig-bypass, as extracted by `ilo4_extract.py`)

Apply in this order:

1. **Sig-bypass** (identical to `patches/280`): file offset `0x964dfc`,
   4 bytes `1D 00 00 0A` -> `1D 00 00 EA`.

2. **New section**: append one new ELF section header (`sh_type =
   SHT_PROGBITS`, `sh_flags = 6` i.e. `ALLOC|EXECINSTR`, `sh_addr =
   0x4000000`, `sh_name = 0`) and its 17,640-byte content, inserted right
   before the original section header table (so only `e_shoff` shifts, by
   the inserted size; `e_shnum` increments by 1). Content layout, all
   4-byte aligned:
   - offset `0x0000`: `fan_block.bin` (15,548 bytes) -- the relocated 8
     -function `fan` handler closure, built for Health task-local address
     `0x2001000` (see "Relocation" below).
   - offset `0x3cbc`: a new `.secinfo` `SectionInfo` struct (24 bytes:
     `next_ptr=0, name_ptr=<self+24>, text_base_addr=0x4000000,
     text_size=0x3cbc, dw1=1, dw2=0`) followed by the NUL-terminated name
     `.health.fan_restore` (20 bytes) -- 44 bytes total.
   - offset `0x3ce8`: a new 64-entry Health `VirtRange` array (2048 bytes)
     -- the existing 63 entries verbatim, plus one new entry
     `{dw1=1, dw2=5, rbase=0x2001000, rsize=0x4000, mod_id=0x272, dw6=dw7=dw8=0}`.
     `mod_id = size_initial(49) + new_secinfo_index(577) = 626 = 0x272`. Both
     `size_initial` and `new_secinfo_index` were originally trusted as
     one-off manually-confirmed constants; `build_patched_280.py` now
     independently re-derives and asserts both at build time by walking the
     live `.secinfo` linked list (counting its length, and cross-referencing
     `.health.elf.data`'s known `mod_id=0x82` from
     `patches/280-fan-restore/build_patched_280.py`), so a bad assumption
     here raises instead of silently computing a wrong `mod_id`.

3. **`.secinfo` linked-list splice**: the file offset `0x16ece54` is the
   `next_ptr` field of the *previous* tail `SectionInfo` entry (index 576,
   `.secinfo`'s 577th and last entry at the time of patching). Set it to
   the new entry's vaddr, `0x4003cbc` (= `0x4000000 + 0x3cbc`).

4. **Health `TaskInfo` repoint** (within `.boottable`, untouched/unresized):
   file offset `0x16605a0` (`virt_space_size` field) `63 -> 64`; file offset
   `0x16605a4` (`virt_space` field) `0x3e06b98 -> 0x4003ce8` (the new
   64-entry array's vaddr, `0x4000000 + 0x3ce8`).

5. **CLI registration callsite patch**: file offset `0x38e5d8`
   (unaffected by the append-at-end insertion), 4 bytes `1E 49 00 EB` ->
   `EB 6B 7F EB`. Re-points the `fan` trampoline's disabled `bl` to the
   relocated handler at Health task-local address `0x2001000`.

## Relocation

Same 8-function dependency closure as v1
(`patches/280-fan-restore/readme.md`), re-relocated for a new base. Two
coordinate systems matter here and are easy to conflate:

- **Task-local / "in-partition" address**: what the CPU's PC actually holds
  while Health code executes, and what every PC-relative `B`/`BL`/literal
  -pool instruction's offset is computed against. Health's existing
  `VirtRange` entries use task-local addresses up to `0x2000000`; the
  relocated closure uses `0x2001000` as its base (chosen to stay reachable
  from the trampoline at task-local `~0x2604c`, well within ARM's +/-32MB
  branch range -- `0x3000000`, tried first, was ~48MB away and not
  reachable).
- **Physical/true address**: where the generic ELF-section loader actually
  copies the file's bytes into RAM (`sh_addr`/`SectionInfo.text_base_addr`).
  This can be any free value; `0x4000000` was chosen here. A `VirtRange`
  entry is what maps one task-local range to one physical range for the
  MPU; the two numbers need no relationship beyond both being valid and
  unique within their own namespace.

`relocate_fan3.py`'s `NEW_BASE` constant (the task-local placement) is what
must change if this is ever re-targeted; the physical placement is a
separate, independent choice (the new `SectionInfo.text_base_addr` /
section `sh_addr`). All 100 branch instructions in the closure were
explicitly re-checked for ARM's branch-range limit after changing
`NEW_BASE` -- `encode_branch` doesn't raise on overflow, it silently wraps
the immediate, so this must be checked, not assumed, for any new placement.
