@ Minimal, read-only-only variant of patches/277-tools/asm/tools.S.
@
@ Replaces the help-command CLI handler, same injection point and
@ mechanism as patches/277-tools / patches/280-tools. Deliberately drops
@ everything except the "r" (read memory) command:
@   - cmd_write (w): removed. Arbitrary memory write is the single
@     riskiest primitive in the original tool and was never needed to
@     answer the open "is 280-tools's brick a technique problem or
@     something else" question.
@   - cmd_execute (x): removed. `blx` to an arbitrary, user-supplied
@     address with no validation is the second-riskiest primitive.
@   - cmd_alloc (a) / cmd_free (f): removed. These are the ONLY code
@     paths in the original tools.S that call external helpers
@     (libc_malloc_fn / libc_free_fn) whose targets research flagged as
@     unverifiable -- "reference an address outside this firmware
@     image's own file bounds entirely... can't be statically verified
@     either way for any version" (research/2026-11-05-278-282-
@     feasibility.md). Removing them means every external reference this
@     build makes (GrabContext_fn, printToShell_fn) has been
@     independently, byte-for-byte verified identical across all six
@     shipped firmware versions (2.77-2.82) -- see
@     research/2026-11-12-entry2-literal-table-re-examined.md's
@     companion verification work this same session.
@   - sprintf trampoline: removed. Confirmed in this session (via a
@     full Ghidra instruction scan) to be dead code in the original --
@     never called by anything -- so dropping it changes nothing
@     behaviorally.
@
@ What's kept, byte-for-byte identical in structure to the original:
@ the prologue, the GrabContext bootstrap, the hex-digit address-parsing
@ loop (builds r8 from arg[1]'s leading hex digits), the single-command
@ dispatch, the default/fallback echo (useful as a live sanity check:
@ typing "help" with no valid subcommand should echo arg[1] and r8),
@ and cmd_read unmodified.
@
@ Usage over SSH, identical to the original: `help r<ADDR> <N>`, where
@ ADDR is NOT standard hex -- each nibble is a letter A-P (A=0 ... P=15),
@ per the _addr_loop decode below -- and <N> is a second, space-separated
@ argument whose first raw byte (stored at task-local offset 0x364 by the
@ CLI's own argument-splitting, confirmed 2026-11-14 hardware-tested; see
@ research/2026-11-14-memprobe-readonly-confirmed-working.md) becomes the
@ read count, unparsed. E.g. `help rCBPJM 0` reads 0x30=48 bytes starting
@ at task-local 0x21F9C. The printed address for each byte is off by one
@ (prints byte_address+1); subtract 1 when reading a dump.

.syntax unified
.arm

.global _start
_start:
	MOV		R12, SP
	STMFD	SP!, {R5-R11, R12, LR, PC}
	SUB		R11, R12, #4

	MOV		R6, R0
	BL		GrabContext
	MOV		R5, R0
	MOV		R8, #0
	ADD		R1, R5, #0x264
_addr_loop:
	LDRB	R2, [R1, #1]!
	SUB		R2, R2, #0x41		@ r2 = r2 - 'A'
	CMP		R2, #0x10
	LSLLO	R8, R8, #4			@ left shift #4 if below 0x10
	ADDLO	R8, R8, R2			@ r8 = r8 + r2 if below 0x10
	BLO		_addr_loop			@ loop again if below 0x10

	LDRB	R0, [R5, #0x264]
	CMP		R0, #0x72			@ 'r'
	BEQ		cmd_read

	MOV		R3, R8
	ADD		R2, R5, #0x264
	ADR		R1, _message
	MOV		R0, R6
	BL		printToShell
return:
	LDMDB	R11, {R5-R11, SP, PC}		@ epilogue

cmd_read:					@ rADDR -- read bytes starting at R8
	ADD		R1, R5, #0x364		@ r1 is the reading-size value's location
	LDRB	R9, [R1], #1
	MOV		R2, R8			@ r2 has start address
_cmdr_data_loop:
	LDRB	R8, [R2], #1		@ grab from r2, incrementing r2, into r8 to print
	SUB		R9, R9, #1
	CMP		R9, #0
	BLT		return

	PUSH	{R0, R1, R2, R3}
	ADR		R1, _cmdr_addr_fmt
	MOV		R3, R8
	MOV		R0, R6
	BL		printToShell
	POP		{R0, R1, R2, R3}

	B		_cmdr_data_loop

GrabContext:
	LDR		R10, GrabContext_fn
	BX		R10
GrabContext_fn:
	.word	0x00021F9C

printToShell:
	LDR		R10, printToShell_fn
	BX		R10
printToShell_fn:
	.word	0x00012F68

_message:
	.ascii	"arg[1]=%.256s, r8=%#x\r\n\0"
	.align	2

_cmdr_addr_fmt:
	.ascii	"%#x : %#x\r\n\0"
	.align	2
