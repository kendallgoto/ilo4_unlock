# Exact patch offsets (2.80 `elf.bin`, pre-sig-bypass, as extracted by `ilo4_extract.py`)

Apply in this order (order matters -- see research doc):

1. **Sig-bypass** (identical to `patches/280`): file offset `0x964dfc`,
   4 bytes `1D 00 00 0A` -> `1D 00 00 EA`.

2. **Insertion**: at file offset `0x41ebc0` (= end of `.health.elf.data`'s
   on-disk content at that point, `sh_offset 0x41bd34 + sh_size 0x2e8c`),
   insert 15,920 bytes: 372 zero-padding bytes, then the 15,548 bytes of
   `fan_block.bin` (this directory). This places `fan_block.bin`'s first
   byte at true vaddr `0xe94000`.

3. **Section header fixups** (for every one of the 628 section headers
   whose original `sh_offset >= 0x41ebc0`): add `0x3e30` (15,920) to
   `sh_offset`. For the `.health.elf.data` header specifically, also set
   `sh_size = 0x6cbc` (was `0x2e8c`).

4. **`e_shoff`** (ELF header, file offset `0x20`): add `0x3e30`.

5. **`.secinfo` fixup**: the `SectionInfo` linked-list entry for
   `.health.elf.data` (list index 81, `text_base_addr == 0xe91000`) has its
   `text_size` field (byte offset `0xde0 + 12` within the *post-shift*
   `.secinfo` section) changed from `0x2e8c` to `0x6cbc`.

6. **CLI registration callsite patch**: file offset `0x38e5d8`
   (unaffected by the insertion -- it's before the insertion point),
   4 bytes `1E 49 00 EB` -> `EB 43 02 EB`. This re-points the `fan`
   trampoline's disabled `bl` to the relocated handler at in-partition
   address `0xb7000` (true vaddr `0xe94000`).

No `.boottable`, `TaskInfo`, or `VirtRange` changes were needed: true vaddr
`0xe94000` already falls inside the existing `.health.elf.data` module's
`VirtRange` (`0xe91000`-`0xf22000`, flags `0x7` = read+write+execute), which
reserves far more address space than its on-disk content used -- the
in-RAM loader zero-fills the unused reservation at boot, so growing the
on-disk content up to that point is sufficient to get the new code loaded
and executable with no new memory-map entries.

See `research/2026-11-05-278-282-feasibility.md` for full derivation of
`fan_block.bin`'s contents (the relocated 8-function dependency closure +
format strings, each branch/literal/ADR instruction re-encoded for its new
load address).
