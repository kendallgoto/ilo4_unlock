# 2026-11-06: Kernel reverse-engineering methodology, errors made, and pitfalls to avoid

This documents an attempt to statically confirm (or refute) the root cause of
`patches/280-fan-restore-v2` still bricking real hardware after static
pre-flight checks passed. It records real mistakes made along the way so a
future session doesn't repeat them, and the methodology that eventually
worked.

## Mistake 1: disassembling the wrong file (`.raw` vs `.bin`)

`ilo4_toolbox/scripts/iLO4/ilo4_extract.py` writes **two** files per embedded
image (`elf`, `kernel_main`, `kernel_recovery`):

```python
with open(outdir + "/%s.raw" % IMG_LIST[ilo_num], "wb") as fff:
    fff.write(data1)                              # STILL COMPRESSED
output_size = decompress_all(data1, outdir + "/%s.bin" % IMG_LIST[ilo_num])
```

**`.raw` is the still-compressed payload. `.bin` is the actual decompressed
code.** This is the opposite of what the names suggest at a glance ("raw"
sounds like "plain bytes", "bin" sounds like "some processed blob"). For
`kernel_main`: `.raw` is 486,335 bytes (LZMA-compressed, entropy ~7.24
bits/byte), `.bin` is 794,624 bytes (real ARM code, entropy ~5.47
bits/byte, matching the header's own `decompressed_size: 0xc2000` field
exactly).

An entire session's worth of disassembly attempts (capstone, radare2, and
the first two Ghidra runs) targeted `kernel_main.raw` and produced nothing
but incoherent, partly-"invalid" decodes, misidentified "MEMORY_REGION"
struct false positives, and (correctly, in hindsight!) **zero** functions
found by Ghidra's auto-analysis -- all symptoms of trying to disassemble
compressed data as if it were code. None of this was a tooling bug; the
input was simply wrong.

**Lesson: before disassembling any extracted firmware blob, read the
extraction script itself to confirm which output file is the real
decompressed code, don't infer it from the filename.** A quick sanity check
that would have caught this immediately: compare file size against the
image header's own `decompressed_size` field (`ilo_header`/`ImgHeader`), or
just measure entropy (compressed/encrypted data sits close to 8.0
bits/byte; real ARM code is usually 5-6.5).

## Mistake 2: assuming a disassembly result is meaningful without this check

Related meta-lesson: capstone and radare2 will *always* produce some output
for any byte sequence, even pure noise -- there is no built-in "this isn't
code" signal from a linear disassembler. Ghidra's **zero functions found**
result was actually the one honest signal available, and it was initially
misread as "the tool failed" rather than "the input isn't executable code."
When a disassembler finds nothing recognizable, check the input's provenance
before concluding the tool or the base address is wrong.

## Ghidra headless CLI pitfalls (free tooling, installed via `brew install ghidra`)

1. The base-address flag for `BinaryLoader` is **`-loader-baseAddr`**, not
   `-loaderBaseAddr`. General form from `analyzeHeadless -help`:
   `-loader-<loader argument name> <value>`. The loader's actual option name
   (`baseAddr`) has to be found from the loader's own source/class file if
   it's not obvious; for `BinaryLoader` specifically it's `baseAddr`
   ("Base Address" is just the display label).
2. Headless Python (`.py`) scripts require **PyGhidra**, which is not
   enabled by default in a plain `brew install ghidra` -- attempting one
   fails with `Ghidra was not started with PyGhidra. Python is not
   available`. Writing the same script in **Java** (a `.java` file whose
   public class extends `GhidraScript`, filename matching the class name)
   works with zero extra setup and is the reliable default for headless
   scripting on a fresh install.
3. `JAVA_HOME` must point at a real JDK (`brew install openjdk@25` installs
   one) and be exported before calling `analyzeHeadless`, or it fails with
   "Unable to locate a Java Runtime" in a non-interactive shell (no TTY to
   prompt for a path).
4. A raw-binary import with no entry point found zero functions even once
   given the *correct* decompressed file, until a `-preScript` explicitly
   called `disassemble(currentProgram.getImageBase())` to seed the first
   instruction. Once seeded, the default analysis passes (`-postScript`
   runs after the standard analysis pipeline) found **2,565** real
   functions from that single seed, via normal call/branch propagation.

## What the real kernel code confirmed

With the correct file (`kernel_main.bin`), correct load address (`0x20001000`,
read directly from the image's own header -- not guessed), and working
decompilation, `FUN_2000b16c` was identified as the kernel's boot-time
`.boottable` relocation/integrity-check pass:

```c
for (task = 0; task < task_count; task++) {
    TaskInfo = task_array + task * 0x40;              // TaskInfo is 0x40 bytes
    virtspace_ptr      = relocate(TaskInfo + 8);       // VirtRange array (already known)
    second_array_ptr   = relocate(TaskInfo + 0x14);    // a second, previously unidentified array
    if (image_end < virtspace_ptr    + *(TaskInfo+4)  * 0x20 ||   // must fit inside the loaded image
        image_end < second_array_ptr + *(TaskInfo+0xc)* 0x20)
        goto fail;
    for (i = 0; i < *(uint*)(TaskInfo + 0x10); i++) {
        entry = second_array_ptr + i * 0x20;
        if (entry->type == 7 || entry->type == 8)
            entry->field4 = relocate(entry->field4);
    }
}
```

This is a genuine, verified (not inferred) fact about `TaskInfo`'s real
layout: it is 0x40 bytes, not the 12 bytes (`task_type`, `virt_space_size`,
`virt_space`) that `build_patched_280.py` and this session's earlier
analysis only ever read. There is a second 0x20-byte-stride array at
`TaskInfo+0x14` (count at `+0xc`) whose entries carry a type byte (7/8
trigger a secondary pointer fixup at entry `+4`) that has not yet been
characterized.

**Important caveat:** this function checks that each task's arrays *fit
inside the loaded firmware image blob* -- a structural/integrity check, not
a check on the actual `rbase`/`rsize` *values* inside `VirtRange` entries.
It does not, by itself, confirm or refute whether `0x2000000` is an
enforced per-task virtual-address ceiling. That enforcement, if it exists,
is almost certainly in a *different* function -- most likely called later,
at actual task creation/dispatch, not during this one-time boot relocation
pass. That function has not yet been located.

## Where this leaves the open question

Separately (see `research/2026-11-05-278-282-feasibility.md` and
`research/2026-11-06-fan-restore-v2-postmortem.md`), real kernel code
(`FUN_2001f0e4`, `FUN_2001ee08`) confirmed this SoC uses a real ARM MMU
with 1MB section-granularity L1 page tables (`addr >> 0x14` indexing,
`| 0x412`/`| 0x41e` section-descriptor attribute bits), set up at boot for
the *global* system address space (DRAM/peripherals from `0x20000000`
upward in a completely separate numbering scheme from the userland
"true vaddr" addresses used by `.secinfo`/`VirtRange`). This confirms the
hardware mechanism that *could* enforce a per-task ceiling exists, but does
not yet pinpoint the specific code that applies it per-task, if any.

## The actual breakthrough: identifying the RTOS, not disassembling it

After `FUN_2000b16c` turned out to be a **flash-time upload validator**
(reached from `FUN_2000dc40`, the network firmware-download command
dispatcher -- confirmed by its embedded strings: `"Download succeeded!"`,
`"Bad boottable!"`, `"LoadError: No .boottable section"`), it became clear
`kernel_main.bin` is primarily an OTA-update agent, not the code that
manages tasks during normal runtime. Continuing to hunt blindly through its
2,565 functions for a per-task MMU-mapping routine was hitting diminishing
returns (one promising double-hit, `FUN_20031d24`, turned out to be an
unrelated SHA-256 implementation -- recognizable from the classic `Ch`/
`sigma` rotate-and-xor pattern, a reminder that a needle match on a bare hex
constant like `0x2000000` is not evidence by itself, it has to be read in
context).

**A much higher-leverage move: `strings`-level identification of the
underlying RTOS**, done directly in `elf.bin` rather than the kernel blob:

```
INTEGRITY occurrences: 113
AddressSpace occurrences: 110
ghs occurrences: 99
```

This firmware runs **Green Hills INTEGRITY RTOS**. That single fact
reframes everything this session had been reconstructing from scratch
(`.boottable`, `.secinfo`, `VirtRange`/`TaskInfo`, per-task `0x10000`-based
addressing) as INTEGRITY's own native, documented concepts: Address Spaces
(INTEGRITY's process/task isolation unit), Memory Regions, and a kernel
that manages them via the MMU. And INTEGRITY's own linked-in `libc.so`
carries its real error vocabulary as plain strings, including, extracted
directly and unambiguously:

```
AddressSpaceLimitExceeded
MemoryRegionMustBeFromAddressSpace
NewVirtualAddressSpaceRequired
PageTooSmallForAddressSpace
TheAddressSpaceCannotHaveATaskRunningInIt
```

`AddressSpaceLimitExceeded` is **the OS's own named error for exactly the
failure mode this session had been building circumstantial evidence for**:
an Address Space (Health's own 32MB task-local range) has a hard,
enforced limit, and something can exceed it. This is not an inference from
a byte pattern anymore -- it's the literal error constant the OS ships with.
Consistent with INTEGRITY's known architecture (Address Spaces are sized at
system-integration/build time, not dynamically grown at runtime), this also
explains *why* no explicit "if (addr > ceiling) reject" instruction was
ever found by disassembly: there likely isn't one as a single dynamic
check. The limit is structural -- a fixed-size region established once at
system build/boot -- so "exceeding" it doesn't take a branch, it simply
runs out of room in a page table that was never sized to hold a 64th entry.

(The string was not found to be referenced by a bare absolute pointer
anywhere in the file -- consistent with INTEGRITY's common pattern of
indexing error strings by numeric code through a lookup table rather than
storing individual pointers to each one, not evidence that it's unused.)

**Lesson for next time: when reverse-engineering an unfamiliar embedded
firmware blob, search for plain-text strings and identify the underlying
OS/toolchain *before* investing heavily in blind disassembly.** A `strings`
pass costs nothing and can turn "guess what this custom-looking scheme
does" into "look up what this named, documented subsystem does." This
should have been one of the first things tried, not one of the last.

## Independent confirmation: public research on this exact firmware already exists

Once INTEGRITY was identified, a web search for `HP iLO4 Green Hills
INTEGRITY RTOS AddressSpace` turned up that this exact firmware has already
been the subject of public security research: Perigaud/Gazet/Czarny
(Synacktiv/Airbus Security Lab), "Subverting your server through its BMC:
the HPE iLO4 case", presented at REcon Brussels 2018, with slides and a
paper freely hosted at `airbus-seclab.github.io/ilo/`. The `ilo4_toolbox`
submodule already cloned into this repo is these same researchers' tooling
-- the project had the pointer to this research the whole time, via the
toolbox's own `README.rst`.

Fetching the REcon slide deck (`pdftotext -layout` on the saved PDF, after
`WebFetch` alone couldn't decompress the PDF's internal streams -- see
below) gave the **actual, official struct definitions**, independently
written by researchers who never saw this session's work:

```c
struct SECTION_INFO { SECTION_INFO *next; void *name; int section_offset;
                       int section_size; int rights; int field_14; };

struct TASK_INFO { int type; int vmem_space_count; void *vmem_space_array;
                    int field_C; int var_count; void *var_array;
                    int field_18 .. field_3C; };   // 0x40 bytes, 16 fields

struct MEM_RANGE { int present; int rights; int range_base; int range_size;
                    int id; int field_14; int field_18; int field_1C; };
```

This **exactly matches**, field-for-field, what this session independently
reverse-engineered from raw bytes with no prior knowledge of this paper:
`SECTION_INFO` = our `.secinfo` entry, `TASK_INFO` = our `TaskInfo` (0x40
bytes, confirmed separately by Ghidra decompilation of `FUN_2000b16c`), and
`MEM_RANGE` = what we'd been calling `VirtRange`. Specific details this
session inferred and the slides independently confirm verbatim:

- `rights` (our "dw2"): "5 for executable range, 7 for data" -- exactly the
  5/7 split this session found by pattern-matching real entries.
- `id` (our "mod_id"): "shifted index of the ELF section, shift = number of
  modules" -- exactly the `mod_id = secinfo_index + SIZE_INITIAL` relation
  this session derived and verified (`SIZE_INITIAL` = the module count).
- Tasks' base address is always task-local `0x10000` -- matches the
  `research/2022-02-17-docs.md` convention this project already had.

**Lesson: before spending hours reverse-engineering a vendor's custom-looking
on-disk format from scratch, search for public research on that exact
product.** This firmware had already been presented at a major security
conference, by name, with slides covering precisely the sections being
re-derived here -- and the pointer to it was sitting in this repo's own
`ilo4_toolbox` submodule README the entire time.

This also surfaced two near-mistakes worth recording:

1. The companion "MRDOWNLOAD" BSP memory region in the slides
   (`low 0x207ba000 / high 0x221ba000`) is **26MB** (`0x1A00000`), not 32MB
   -- an arithmetic slip was made and caught before stating it to the user
   as corroborating evidence. It would have been a coincidental, wrong
   claim. Always redo the subtraction before citing a number as
   corroboration.
2. `WebFetch` cannot read text out of a real PDF's compressed internal
   streams -- it returns the raw container bytes, and a model-generated
   "summary" of binary PDF bytes is not trustworthy (the subagent correctly
   flagged this itself rather than guessing). The reliable path: let
   `WebFetch`/the fetch agent save the file, then run a real extractor
   (`brew install poppler`, then `pdftotext -layout <file> <out.txt>`) and
   grep the result.

## Honest status, not to be overstated

- The `280-tools`/v1/v2 bricks are very likely **three separate bugs**, not
  one shared root cause (see `research/2026-11-06-fan-restore-v2-postmortem.md`
  adversarial-review addendum for the `280-tools` shell-table measurement
  that ruled out one hypothesis for it).
- The "`0x2000000` is a hard per-task ceiling" theory for v2 is now
  supported by four independent lines of evidence: (1) a strong,
  independently-reproduced *structural* pattern (checked across both 2.77
  and 2.80, 60+ sibling tasks, zero exceptions), (2) identification of the
  underlying OS as Green Hills INTEGRITY RTOS, whose Address Space model is
  documented (publicly, by independent researchers) to be fixed-size at
  build time, not dynamically extensible, (3) the OS's own linked-in error
  vocabulary literally contains `AddressSpaceLimitExceeded` as a named,
  real error condition, and (4) this session's own reverse-engineered
  `MEM_RANGE`/`TASK_INFO` struct layouts turned out to match, field for
  field, the struct layouts independently published by Perigaud/Gazet/
  Czarny's 2018 REcon research on this exact firmware -- strong validation
  that the rest of this session's analysis methodology was sound. This is
  strong, well-corroborated evidence, but it still falls short of catching
  the exact instruction/trap that fires for this specific patch on this
  specific hardware -- that would need a live debugger or vendor
  documentation, and the public research itself doesn't print a full
  enough `MEM_RANGE` table for any one task to directly verify a 32MB
  total. Treat the conclusion as "very likely," not "proven beyond doubt."
- The v1 postmortem's "9-address table" evidence was independently
  re-verified against the real binary and is solid; its causal leap
  ("this is why the whole system failed before `fan` was ever invoked") is
  plausible but not independently demonstrated.
