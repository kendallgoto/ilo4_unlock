# Patches (2.82-tools)

Signature bypass: identical to patches/282 (userland bypass at
0x96a240).

`replace help with tools`: the `help`-handler function this overwrites was
independently confirmed byte-identical (280/281) or differing by only 2
bytes inside an internal call target (282, harmless/unrelated to this
patch) compared to 2.77's known-good copy, at new offset
0xaf279c. `tools.S` is reused unmodified from
`patches/277-tools/asm/tools.S`: its two load-bearing external targets
(`GrabContext_fn` = 0x21F9C, `printToShell_fn` = 0x12F68, both per-task
"in-partition" addresses) were disassembled at the correctly-resolved
offset for this version and found byte-identical to 2.77's. `libc_malloc_fn`
/`libc_free_fn`/`sprintf_fn` reference an address outside this firmware
image's own bounds and could not be verified by static analysis for ANY
version including 2.77 -- this is a pre-existing property of the original
patch, not something introduced by porting it here.
