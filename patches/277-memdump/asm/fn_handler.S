dump:
	MOV		R12, SP						; prologue
	PUSH	{R5, R6, R7, R11, R12, LR, PC}
	SUB		R11, R12, #4
	SUB		SP, SP, #0x104				; end prologue
	.word	0xEB00138A					; BL 0x21F9C grab_context(R0)
	MOV		R5, R0						; preserve context
start:
	MOV		R7, #0						; i = 0 / wherever to start dumping
	MOV		R6, R7						; keep a copy of start index
loop:
	ADD		R0, SP, #4					; storage spot SP+4
	ADR		R1, printedString			; formatString
	MOV		R2, R6						; i
	LDRB	R3, [R6], #1				; byte, load byte @ i, R6++
	.word	0xEB5E5BBA					; BL 0x017B407C libc sprintf(storage spot, formatString, i, byte)
	LDR		R0, [R5, #4]				; R0 = context@0x4
	ADR		R1, stringForm				; print sprintf result "%s"
	ADD		R2, SP, #4					; actual sprintf value @ SP+4
	.word	0xEBFFD771					; BL 0x00012F68 print to shell (printf-y)
	SUB		R0, R6, R7
	LDR		R1, endPtr					; grab ending size
	CMP		R0, R1						; if we've printed more than ending size bytes
	BLT		loop						; if less than end size, keep going!
end:
	MOV		R0, #0x20
	.word	0xEB00BC92					; BL 0x0004C404 report status maybe call(0x20)
	LDMDB	R11, {R5, R6, R7, R11, SP, PC}	; epilogue

printedString:
	.string "%x : %x\r\n\r\n"

stringForm:
	.string "%s"

endPtr:
	.word	0x0000FFFF

	.byte	0x0
