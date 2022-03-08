prologue:
	MOV		R12, SP
	STMFD	SP!, {R5-R11, R12, LR, PC}
	SUB		R11, R12, #4
	SUB		SP, SP, #0x104
	MOV		R6, R0
start:
	BL		GrabContext						; grab_context(R0)
	MOV		R5, R0							; preserve context
	MOV		R7, R5							; i = 0 / wherever to start dumping
	MOV		R6, R7							; keep a copy of start index
loop:
	ADD		R0, SP, #4						; storage spot SP+4
	ADR		R1, printedString				; formatString
	MOV		R2, R6							; i
	LDRB	R3, [R6], #1					; byte, load byte @ i, R6++
	BL		sprintf							; libc sprintf(storage spot, formatString, i, byte)
	LDR		R0, [R5, #4]					; R0 = context@0x4
	ADR		R1, stringForm					; print sprintf result "%s"
	ADD		R2, SP, #4						; actual sprintf value @ SP+4
	BL		printToShell					; print to shell (printf-y)
	SUB		R0, R6, R7
	LDR		R1, endPtr						; grab ending size
	CMP		R0, R1							; if we've printed more than ending size bytes
	BLT		loop							; if less than end size, keep going!
end:
	LDMDB	R11, {R5-R11, SP, PC}			; epilogue

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

printedString:
	.string "%x : %x\r\n\r\n"
stringForm:
	.string "%s"
endPtr:
	.word	0x0000FFFF

	.skip 989, 0x0
