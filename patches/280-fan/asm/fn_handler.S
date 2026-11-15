h:
	MOV		r0, #5		; entrypoint for health (call switch #5)
	B		start

fan:
	MOV		r0, #6		; entrypoint for fan (call switch #6)
	B		start

ocsd:
	MOV		r0, #7		; entrypoint for ocsd (call switch #7)
	B		start

ocbb:
	MOV		r0, #8		; entrypoint for ocbb (call switch #8)

start:
	MOV		R12, SP				; Initialize
	PUSH	{R11, R12, LR, PC}
	SUB		R11, R12, #4
	SUB		SP, SP, #0xA00		; Allocate space on stack for IPC struct
	STR		R0, [SP]			; Store R0 as first value in struct (switch value)
	MOV		R3, #0				; Init R3 to zero
	ADD		R2, SP, #4			; Move R2 to write at 0x4 in IPC struct
	ADD		R0, R7, #0x1000		; Move R0 to start of input arg
loop:							; Parse string char-by-char
	LDRB	R1, [R0], #1		; Load char from string; R0++ (0x1000+i)
	CMP		R1, #0x20			; if loaded == ' '
	STRBEQ	R3, [R2],#1			;	then store \0 into R2, R2++
	STRBNE	R1, [R2],#1			;	else store char in R2, r2++
	CMP		R1, #0				; if char != \0
	BNE		loop				; 	then loop
	STRB	R3, [R2]			; store final \0 onto R2
	MOV		R0, SP				; Setup call
	ADD		R1, SP, #0x500		; Setup call
	BL		0x3e420				; health_ipc_call(SP, SP+500)
	LDR		R0, [SP,#0x500]		; load yielded value to R0
	LDMDB	R11, {R11,SP,PC}	; exit

	.word	0x00000000
	.word	0x00000000
