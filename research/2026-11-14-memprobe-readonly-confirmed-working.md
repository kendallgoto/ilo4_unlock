# 2026-11-14: `patches/280-memprobe-readonly` confirmed working on real hardware

## Background

`patches/280-memprobe-readonly` (built 2026-11-12, see its own readme) was
built to answer the still-open question from
`research/2026-11-05-278-282-feasibility.md`: `patches/280-tools` (the full
read/write/execute/malloc/free memory probe) bricked on real hardware for a
cause never identified. This build strips the probe down to just the `r`
(read) command, at the identical injection point, to test whether the brick
is specific to the removed, riskier capabilities (write/execute/malloc/free)
or something about the slot/technique itself. It had been built and
statically verified but not yet flashed.

## Hardware test, attempt 1: `help r00000000` -- hung the SSH session

Flashed and booted clean (no POST 270, correct version readback, SSH/web/ping
all normal -- the full checklist from `CLAUDE.md` passed before any command
was run). Running `help r00000000` hung that SSH session permanently (no
output, no prompt returned). Critically, this was **not** a whole-device
brick: a new SSH connection could still be established immediately after,
and ping/web continued working throughout. Only the one task servicing that
command got stuck.

**Root cause, read directly from the assembly (not guessed):** the
address-parsing loop in both this build's `tools_readonly.S` and the
original `patches/277-tools/asm/tools.S` it descends from computes
`byte - 0x41` and only accepts the result as a hex nibble if it's `< 0x10`.
That means the only characters it recognizes as hex digits are **uppercase
`A`-`P`** (A=0, B=1, ... P=15) -- not `0`-`9`/`a`-`f`. This isn't something
this project's trimming introduced; it's inherited unchanged from the
original Airbus/phoenixdev code. Typing `00000000` (ordinary hex digits)
means every character falls outside the accepted range, so the loop exits
on the very first character having accumulated nothing -- the target
address silently resolves to `0`. `cmd_read` then dereferences task-local
address `0`, which is unmapped, triggering a data abort inside the task
handling that connection. This matches the observed symptom exactly: one
task wedges, nothing else does.

The readme's own usage line ("`help r<hex-address>`") was actively
misleading here -- fixed below to document the real A-P-per-nibble
encoding, so this isn't re-discovered the hard way again.

## Hardware test, attempt 2: `help rCBPJM` -- clean return, no output

Re-ran with the address correctly A-P-encoded, targeting `GrabContext_fn`'s
own literal (`0x21F9C`, nibbles `2,1,F,9,C` -> letters `C,B,P,J,M`) --
chosen specifically because it has to be mapped, since the running code
just branched to it. This returned cleanly to the prompt with **no**
output and no hang.

**This resolves a question this project has had open since its very first
research session.** `cmd_read`'s byte count is read from task-local
`r5+0x364`:
```
add r1, r5, #0x364
LDRB r9, [r1], #1
```
`research/2022-02-17-docs.md` (2022-02-17) already speculated about this
exact offset, from tracing a completely different command (`oemhp_ping`):
*"`sub_3908800(connectionRecord[0x364]) -> strlen` ... `if(length = 0) ->
jumps down` ... Could connectionRecord contain the last inputted string,
already spaced out? i.e. first argument @ `[0x264]`, second argument @
`[0x364]`? ... it wasn't used in phoenixdev's code so I tried my best to
ignore it."` That speculation was correct and is now confirmed: `0x364` is
not a settable "count" field at all, it's **the start of the command's
second, space-separated argument string**, and `cmd_read` just takes that
string's first raw byte as the count with no decoding. `help rCBPJM` has no
second argument, so that field is an empty string (first byte `0`) --
count `0`, loop exits on its first comparison, nothing printed. Exactly
consistent with the 2022 note's own "if length==0, jumps down" finding.

## Hardware test, attempt 3: `help rCBPJM 0` -- confirmed working read

Added a second argument. `'0'` is ASCII `0x30` = 48 decimal, so this should
request 48 bytes if the above is right. Result: **48 lines of real memory
dump**, starting at `0x21f9c`:
```
0x21f9d : 0xd
0x21f9e : 0xc0
0x21f9f : 0xa0
0x21fa0 : 0xe1
0x21fa1 : 0
0x21fa2 : 0xd8
0x21fa3 : 0x2d
0x21fa4 : 0xe9
... (48 lines total)
```

**Independent verification, not just "it returned a line count":**
decoding the first 12 bytes as little-endian ARM32 words gives
`0xE1A0C00D` (`MOV IP, SP`), `0xE92DD800` (`STMFD SP!, {fp, ip, lr, pc}`),
`0xE24CB004` (`SUB FP, IP, #4`) -- the canonical ARM AAPCS function
prologue, and specifically the *exact* prologue shape
`research/2026-11-05-278-282-feasibility.md` already predicted would be
here ("byte-for-byte identical function prologues in all six firmware
versions"), based on static analysis of the *extracted firmware image*.
Getting the identical bytes back from a live read on real running hardware
is real, independent confirmation that both the address resolution and the
read primitive are correct -- not just "the device didn't crash."

**Verdict: the read-only memory probe works correctly on 2.80 real
hardware**, at the same injection point (`help` command slot) that
`patches/280-tools`'s full read/write/execute/malloc/free version bricked
on. This narrows the still-unidentified `280-tools` brick cause specifically
to the write, execute, or malloc/free paths -- not the slot, not the
bootstrap mechanism, not the read primitive itself.

## Two things to get right reading any future dump from this probe

1. **Off-by-one in the printed address.** `cmdr_data_loop` prints `r2`
   *after* the `LDRB r8, [r2], #1` post-increment, so every printed address
   is actually `(byte's real address) + 1`. E.g. the line `0x21f9d : 0xd`
   is really byte `0xd` at address `0x21f9c`. To read a dump correctly,
   subtract 1 from every printed address before interpreting it.
2. **Task-scope limit.** `GrabContext_fn`/`printToShell_fn` resolve as
   task-local addresses within **ConAppCLI** (the SSH/CLI shell task) --
   confirmed in `research/2026-11-05-278-282-feasibility.md`'s original
   porting work. This probe therefore only sees ConAppCLI's own address
   partition. It **cannot** read Health-task memory (e.g. the entry-2
   bootstrap pointer at Health-task-local `0xb7058` from
   `research/2026-11-12-entry2-literal-table-re-examined.md`) -- that's a
   different task's separate address space, and the `diag1`-`diag9` series
   already demonstrated this hardware enforces per-task address-space
   boundaries strictly (see
   `research/2026-11-12-virtrange-reattribution-closed.md`). Reading
   Health's memory would need an equivalent probe injected at a point that
   actually runs inside the Health task -- new work, not a reuse of this
   one.

## Why this matters for the actual goal (restoring `fan` on 2.78+)

The VirtRange closure work left exactly one mechanism open: *"overwriting
the content of an already-present, already-correctly-permissioned module
in place"* (`research/2026-11-12-virtrange-reattribution-closed.md`). This
is the first real hardware confirmation that an in-place content overwrite
at an executable, already-present slot is safe and behaves exactly as
predicted -- it just happened to land in the wrong task (ConAppCLI) to
directly help with Health's `fan` restoration. The natural next step is
the same technique, same discipline, but injected at a point that executes
inside the **Health** task instead -- e.g. reusing the already-proven-safe
`NULL_CMD`/`fan` slot wiring from `patches/280-fan` (which already calls
into Health via IPC) as the injection point for a Health-side read probe,
rather than another IPC call into the now-confirmed-dead fan service. That
would finally give this project live, ground-truth visibility into Health's
own memory -- enough to directly verify the entry-2 bootstrap-pointer
finding and go looking for a genuinely free present+executable region to
host the v4 `fan`-handler closure via in-place overwrite, instead of the
now-closed "create a new VirtRange entry" approach.
