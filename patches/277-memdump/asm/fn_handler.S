dump:										; base address = 0x18B28
	MOV		R12, SP							; prologue
	PUSH	{R5-R11, R12, LR, PC}
	SUB		R11, R12, #4
	SUB		SP, SP, #0x104					; end prologue
	LDR		R10, grabContext
	BLX		R10								; 4 grab_context(R0)
	MOV		R5, R0							; preserve context
	ADR		R1, handlerStr					; load handler report string
	LDR		R10, nullPtrTest
	BLX		R10								; 7 BL 0x42D74 null_ptr_test(context, handler)
start:
	MOV		R7, R5							; i = 0 / wherever to start dumping
	MOV		R6, R7							; keep a copy of start index
loop:
	ADD		R0, SP, #4						; storage spot SP+4
	ADR		R1, printedString				; formatString
	MOV		R2, R6							; i
	LDRB	R3, [R6], #1					; byte, load byte @ i, R6++
	LDR		R10, sprintf
	BLX		R10								; 14 BL 0x017B407C libc sprintf(storage spot, formatString, i, byte)
	LDR		R0, [R5, #4]					; R0 = context@0x4
	ADR		R1, stringForm					; print sprintf result "%s"
	ADD		R2, SP, #4						; actual sprintf value @ SP+4
	LDR		R10, printToShell
	BLX		R10								; 18 BL 0x00012F68 print to shell (printf-y)
	SUB		R0, R6, R7
	LDR		R1, endPtr						; grab ending size
	CMP		R0, R1							; if we've printed more than ending size bytes
	BLT		loop							; if less than end size, keep going!
end:
	MOV		R0, #0x20
	LDR		R10, endStatus
	BLX		R10								; 24 BL 0x0004C404 report status maybe call(0x20)
	LDMDB	R11, {R5-R11, SP, PC}			; epilogue

printedString:
	.string "%x : %x\r\n\r\n"
handlerStr:
	.string "CLI_helpHandler"
stringForm:
	.string "%s"
endPtr:
	.word	0x0000FFFF
grabContext:
	.word	0x00021F9C
nullPtrTest:
	.word	0x00042D74
sprintf:
	.word	0x017B407C
printToShell:
	.word	0x00012F68
endStatus:
	.word	0x0004C404

	.skip 957, 0x0
