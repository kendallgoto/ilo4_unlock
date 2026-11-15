# iLO 2.82 Patch (signature-bypass + memory-probe tools)

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

**Not yet hardware-tested. NOTE: the identical technique failed on real 2.80 hardware (patches/280-tools) -- do not flash this until that is understood, see research/2026-11-05-278-282-feasibility.md.**
