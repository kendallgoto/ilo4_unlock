# 2026-11-12: Auditing for an un-bypassed integrity check

Prompted by diag7 bricking (the 4th straight failure of "create a new
present=1 VirtRange link"): before building diag8, and again after it was
flashed, checked whether these bricks could be explained by some integrity
check this project hasn't found and bypassed yet -- separate from the three
RSA signature checks already patched (bootloader `0x38BC`, kernel
`0x1FBB0`, userland ELF `0x964DFC`).

**Conclusion: no additional integrity check was found.** Every lead
investigated either doesn't run for an externally-flashed image, is
demonstrably dead/unreferenced code, or turned out on closer inspection to
be something else entirely. This is written up so a future session doesn't
re-walk the same dead ends.

## Methodology

1. Binary signature scan: searched `kernel_main.bin` (decompressed),
   `bootloader.bin`, and `elf.bin` for the standard zlib CRC32 table (full
   256-entry table, not just a few words), CRC16-CCITT, and MD5/SHA1
   initialization constants.
2. Full-firmware Ghidra analysis (headless, see methodology notes below)
   to find actual code *references* to any hit -- not just literal-pool
   words, but PC-relative `ADR`/`ADD PC,#imm` too, which a plain byte scan
   misses.
3. A broader keyword sweep (`checksum`, `crc`, `sha`, `md5`, `digest`,
   `hash`, `verify`, `valid`, `integrity`, `signature`, `corrupt`,
   `mismatch`, `authenticat`, `trust`, etc.) over every defined string and
   function name in the fully-analyzed firmware, followed by decompiling
   the functions behind the one lead that looked structurally relevant.

## Finding 1: a zlib CRC32 table, embedded but dead

A complete, verified (full 256-entry, not just the first few words) zlib
CRC32 table sits inside `.health.elf.text` itself (true vaddr `0xe8d950`),
next to classic zlib error strings (`"need dictionary"`, `"stream end"`,
`"incompatible version"`, etc.) -- Health links in a static zlib, almost
certainly incidental to whatever library archive its build pulled in, not
because Health's own code uses it.

Checked for *any* reference to this address, three independent ways, all
negative:
- Literal-word scan of the entire firmware (kernel, bootloader, every
  section of `elf.bin`): **0 hits**.
- Ghidra reference analysis (catches `ADR`-style PC-relative addressing
  too) scoped to just `.health.elf.text` (1,214 functions): **0
  references**, none within +/-1KB of the table either.
- Ghidra reference analysis over the **entire** `elf.bin` (every task, not
  just Health) -- confirmed twice, once with the slow decompiler-based
  analyzers disabled (38,953 functions, 192s) and once with every default
  analyzer enabled including Decompiler Switch Analysis and Decompiler
  Parameter ID (40,470 functions, 320s, 20GB heap): **0 references** both
  times.
- Ghidra reference analysis over the kernel (`kernel_main.bin`, loaded at
  its documented base `0x20001000`, 2,565 functions, matching the function
  count this project's own earlier kernel RE session got): **0
  references**.

This table is dead, unreferenced linked-in library data. Not a check.

## Finding 2: `dvcrcv` -- a promising name that wasn't

A keyword sweep over the fully-analyzed firmware's strings surfaced a real
RTOS task literally named `dvcrcv`, created via
`CommonCreateTask(127, (Address)dvcrcv_main, 0x3000, "dvcrcv", &dvcrcv_task)`,
with nearby strings referencing `GetMemoryRegionAddresses` and
`crcStart`/`crcEnd` -- looked, before decompiling anything, like it could be
a memory-region CRC watchdog.

Decompiling every function that actually references `dvcrcv*` (`src\
dvcrcv.c`, `src\dvcrc4sw.c`) shows it is the **USB keyboard/mouse receive
queue for the Integrated Remote Console** (remote KVM): the code handles
USB HID keyboard scancodes (`"key command = [%x %x %x...]"`), mouse/power
commands, and is explicitly labeled `"USB_KB_Mouse_Queue"` at its creation
site. `crcv` is "**r**e**c**ei**v**e", not "CRC verify" -- a coincidental
substring match. This is the same class of trap this project's own
`2026-11-06-kernel-re-methodology-and-pitfalls.md` already flagged once
(the `FUN_20031d24` SHA-256-that-turned-out-irrelevant incident): **a
needle match on a hash/crc-sounding name is not evidence by itself, it has
to be read in the decompiled context.**

The two actual `...Crc...` strings near it (`GetMemoryRegionAddresses
(dviPhys, &divPhysCrcStart, &divPhysCrcEnd)` and the `dviVirt` variant)
have **zero references anywhere** in the 40,470-function full-firmware
analysis -- dead debug/assertion text, never called. Most likely an unused
helper for video-frame-change detection in screen redirection, unrelated
to firmware or boot integrity either way.

## Finding 3: a complete embedded OpenSSL, but for the wrong thing

The keyword sweep's ~2,876 matching strings are overwhelmingly one thing: a
statically-linked **OpenSSL 1.0.2x-fips** (`"MD5 part of OpenSSL
1.0.2x-fips  8 Dec 2020"` confirms the exact version) -- full MD5/SHA
family/RSA/DSA, X.509 certificate validation, FIPS self-test strings, TLS
handshake state strings. This backs HTTPS, LDAP, SSO, and the web UI's TLS
stack. None of it is wired to firmware image or boot-table validation;
Ghidra's own function-name matching found **zero** functions named with any
integrity/validation keyword (the matches are all plain string data, mostly
inside this OpenSSL blob).

The remaining non-OpenSSL hits (`NVRAM_CRC_ERROR`, `MEM_DIMM_SPD_CHECKSUM`,
`Memory SPD CRC failure`, `MEM_DIMM_TYPE_MISMATCH`, etc.) are iLO's own
hardware health **event log message strings** -- what Health reports about
DIMMs/NVRAM/power supplies to the admin, not something that validates the
firmware image itself.

## Finding 4: the one genuine boot-time validator doesn't apply here

`FUN_2000b16c` (identified in `2026-11-06-kernel-re-methodology-and-pitfalls.md`
as the kernel's `.boottable` relocation/fit-check pass -- confirmed, not
guessed, via decompilation) is reached only from `FUN_2000dc40`, the
**network firmware-download command dispatcher** (confirmed by its own
embedded strings: `"Download succeeded!"`, `"Bad boottable!"`). It is a
flash-time OTA-upload validator, not a per-boot check. Since every build in
this project is flashed externally (never through iLO's own live web/network
update path), this function most likely never executes against our images
at all, and doesn't explain any of diag1-8's bricks.

## Bottom line

No integrity check beyond the three already-bypassed RSA signature checks
was found, across binary signature scanning, two independent full-firmware
Ghidra reference-analysis passes (with and without the decompiler-heavy
analyzers), and a full keyword/string sweep with manual decompilation of
the one structurally-plausible lead. The diag1-8 brick pattern needs a
different explanation than "we missed a check" -- see
`patches/280-diag8-nonceiling-anon-entry/readme.md` for the current leading
theory (the kernel treating the last/ceiling VirtRange entry specially,
likely as heap/stack backing).

## Ghidra headless methodology notes (new, building on `2026-11-06-kernel-re-methodology-and-pitfalls.md`)

- **Default headless heap (2GB) is far too small** for a 24MB multi-task
  firmware image. A full `elf.bin` import+analyze aborted with
  `OutOfMemoryError` at 2GB; bumping to `GHIDRA_HEADLESS_MAXMEM=16G` (and
  later `20G` with every analyzer enabled) let it complete in 190-320s on
  a 24GB-RAM machine. Set this env var before calling `analyzeHeadless`,
  not as a CLI flag.
- **A whole-firmware import produces many "function body repair failed due
  to overlap" errors** -- dozens, concentrated in specific unrelated
  tasks' address ranges, not Health's. These are noisy but not fatal to
  the overall analysis; the disassembly and reference analyzers still
  complete and still find real cross-references. Don't mistake this for
  the import having failed.
- **For a scoped/fast check of one component, extract it as a raw binary
  and import via `BinaryLoader`** rather than importing the whole ELF --
  e.g. just `.health.elf.text` (669KB) analyzed cleanly in ~10 seconds
  with zero errors and found a sane function count (1,214), versus the
  whole-firmware import's multi-minute run and overlap noise.
- `-processor` for `BinaryLoader` takes the bare language ID only (e.g.
  `ARM:LE:32:v8`) -- passing the full `ARM:LE:32:v8:default` string (as
  Ghidra's own log output displays it, language:compiler combined) fails
  with `Unsupported language`. Use `-cspec default` separately if needed,
  though it's often not required.
- To disable the expensive decompiler-based analyzers (Decompiler Switch
  Analysis, Decompiler Parameter ID, Call Convention ID) for a faster
  first pass, use a `-preScript` that calls
  `currentProgram.getOptions(Program.ANALYSIS_PROPERTIES).setBoolean("<analyzer name>", false)`
  before the default analysis runs -- there's no direct
  `analyzeHeadless` CLI flag for this.
- `currentProgram.getImageBase()` for a `BinaryLoader` import can print
  `00000000` even when `-loader-baseAddr` was correctly applied -- it's a
  separate, mostly-cosmetic relocation-base property. Verify the *actual*
  load address via the program's memory blocks
  (`currentProgram.getMemory().getBlocks()`), not `getImageBase()`.
- Reusing an already-analyzed project (`-process <file> -noanalysis`) for
  a new query script is fast (seconds) and avoids re-running the whole
  import+analyze pipeline for every follow-up question.
