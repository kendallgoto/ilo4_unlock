# iLO 2.80 Patch (signature-bypass + memory-probe tools)

Adds the Airbus Security Lab memory-probe backdoor (from `patches/277-tools`)
on top of the signature-bypass-only patch for this version. Replaces the
CLI's `help` command with a raw memory read/write/execute/alloc/free probe,
reachable over SSH as `help`.

Does NOT attempt to restore fan/health/ocsd/ocbb -- see
research/2026-11-05-278-282-feasibility.md for why, and for how the
addresses reused here (GrabContext, printToShell) were independently
re-verified byte-identical across 2.77-2.82 before reuse. The malloc/free
helper commands reference a fixed address outside this firmware's own
userland image (true for 2.77 too) and could not be statically verified
either way; the core read/write/execute path does not depend on them.

**CONFIRMED BROKEN on real hardware, 2026-11-05.** Flashed to a real HP
DL380 Gen9 running 2.80: iLO failed to come up afterward (BIOS POST error
270 "iLO FW Communication Issue", iLO version read as 255.255/0xFF.0xFF --
indicative of iLO not completing its own boot/init, not necessarily chip
corruption). A full AC power cycle did not resolve it. Recovered by
reflashing a clean (unpatched) repack of the genuine 2.80 image, which
booted normally -- confirming the hardware, flash process, and repack
pipeline are all fine, and narrowing the cause specifically to this patch's
content. The plain signature-bypass-only `patches/280` build was then
separately confirmed working on the same hardware.

Root cause is NOT yet identified -- see
research/2026-11-05-278-282-feasibility.md for the current hypotheses.
**Do not flash this (or 281-tools/282-tools, which share the same
technique) until the cause is understood.**
