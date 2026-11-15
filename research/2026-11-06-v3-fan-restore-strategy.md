# 2026-11-06: `fan` restore v3 strategy

v1 and v2 of `patches/280-fan-restore` both bricked real hardware (see
`research/2026-11-06-fan-restore-v2-postmortem.md` and
`research/2026-11-06-kernel-re-methodology-and-pitfalls.md`), by two
different mechanisms that converge on the same underlying constraint. This
document lays out that constraint precisely, rules out approaches that can't
work, and ranks what's actually left.

## The constraint, stated precisely

This firmware runs Green Hills INTEGRITY RTOS (confirmed by strings in the
image itself, and independently by public 2018 REcon research on this exact
product). Every userland task gets a fixed-size virtual **Address Space**,
established at system-build time, not grown at runtime.

Checked directly against the real, hash-verified `elf.bin` for both 2.77 and
2.80: **every single userland task in the firmware** -- not just Health --
independently ends its own `VirtRange`/`MEM_RANGE` table at exactly
`0x2000000` (32MB), despite wildly different module counts (54-72 entries
per task, 31 tasks in 2.80, 32 in 2.77). This appears to be a single,
global, per-task Address Space size baked into this build, not something
tunable per task or per firmware version from inside the ELF file.

Separately and already established: Health's entire 32MB is **already
100% claimed** -- every byte belongs either to a real, file-backed module
(`present=1`) or to anonymous, zero-filled memory (`present=0`, likely
live heap/stack/scratch for the running task). There is currently no known
byte of Health's address space that is both (a) inside the ceiling and
(b) not already spoken for.

## Why v1 and v2 both failed, restated against this constraint

- **v1** reused a `present=0` (anonymous/BSS-style) region inside an
  *existing* module's declared reservation, inside the ceiling. Confirmed
  root cause: that memory is live, actively-referenced scratch, not idle
  space -- ELF-style "reserved but not file-backed" is standard notation
  for BSS, not a hint that it's free to reuse.
- **v2** added a brand-new region entirely, at a task-local address just
  past the ceiling. Leading hypothesis (strong circumstantial support,
  not proven by kernel disassembly): this falls outside the task's actual
  allocated Address Space and is simply never mapped.

Both failures are instances of the same unsolved problem: **there is no
currently-known safe place, inside Health's Address Space, for ~15.5KB of
new code.**

## Options, ranked

### 1. Find genuinely free bytes via live telemetry (best if achievable, currently blocked)

If we could observe *actual running* Health task memory on hardware we
already trust (the plain, hash-verified, SSH-reachable `patches/280` --
sig-bypass only, confirmed working, nothing fan-related changed), we could
directly tell which `present=0` regions are truly idle (e.g. over-sized,
never-touched heap headroom) versus actively written. This is categorically
safer than guessing, because it requires **no new flash** at all to gather
the evidence.

**Blocker:** there is no known safe, already-shipped way to read arbitrary
task memory over SSH/CLI on stock 2.80. The one tool that could do this
(`patches/280-tools`'s memory-probe) is the one already **confirmed broken**
on real hardware, for a still-unidentified reason unrelated to this
session's findings -- re-flashing it to get telemetry would trade a known
brick risk for the information needed to avoid a different one, which is
not an acceptable trade.

**What would unblock this:** any existing, stock, read-only iLO diagnostic
surface that happens to expose memory contents (AHS log export, a
SMASH-CLP target not yet explored, a RedFish diagnostics endpoint) would be
worth checking before writing this option off. Not yet investigated this
session.

### 2. Shrink the problem instead of solving it (needs fresh hardware-level research)

The ~15.5KB dependency closure restores the *original* `fan` implementation
faithfully. A hand-written, minimal replacement that talks directly to the
fan-control hardware (there are `.i2c`/`.gpio` modules already loaded in
Health's own task, per `elf.bin`'s section list) could plausibly be a few
hundred bytes instead of 15.5KB -- small enough that a much smaller "is
there really nowhere safe" problem might become tractable, or small enough
to reconsider option 1 with a far lower bar.

**Blocker:** this requires hardware-level research this session hasn't
done at all -- which I2C bus/address the fan controller is actually on,
what protocol it expects, and confirming that information independent of
the removed binary code (since we can't trust removed proprietary logic as
a spec). This is a real, separate research effort, not a quick patch.

### 3. Host the new code in a different, roomier task (ruled out)

Checked directly: **every** userland task shares the same fixed 32MB
ceiling, and the ones sampled are all similarly packed. There is no
"spare" task with meaningfully more headroom to borrow from, and routing
through INTEGRITY's own IPC (`rsrc_mgr`, as documented in the REcon slides)
to call cross-task would be a materially bigger architecture change than
anything tried so far, introducing new failure surface for a benefit that
doesn't exist (no task actually has more room). Not recommended.

### 4. Grow the Address Space itself (ruled out, not achievable from here)

If the 32MB figure is a single fixed constant in INTEGRITY's own kernel
code or system-build configuration (consistent with everything found this
session), changing it would require Green Hills' own proprietary build
toolchain (the "Integrate" IDE and board support package build), not
something reachable by patching a shipped ELF file. Not pursued further.

## Recommendation

Do not attempt another hardware flash of a `fan`-restore patch yet. The
build script (`patches/280-fan-restore-v2/build_patched_280.py`) now
asserts the confirmed ceiling explicitly, so this specific mistake can't
recur silently -- but that assertion only prevents repeating v2's error, it
doesn't locate a safe address to use instead.

Next concrete step, in order of preference:
1. Check whether any existing, stock iLO4 diagnostic feature (AHS log,
   RedFish endpoints, other SMASH-CLP targets) can serve as a legitimate,
   zero-new-risk window into live Health task memory, before concluding
   option 1 is fully blocked.
2. If not, scope out option 2 (direct I2C/GPIO fan control) as its own
   research task -- it needs hardware documentation research, not more
   static analysis of this firmware.
3. Keep `patches/280-fan` (confirmed boots, SSH-reachable, `fan` command is
   simply inert) as the safe, documented baseline while either of the above
   is pursued.
