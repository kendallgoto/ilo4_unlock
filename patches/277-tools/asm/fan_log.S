start:									; MOV R12, SP (not overwritten)
	PUSH	{R1-R3}						; init
	MOV		R2, SP
	PUSH	{R6, R7, R11, R12, LR, PC}
	SUB		R11, R12, #0x10
	SUB		SP, SP, #0x400				; Allocate space on stack
	MOV		R1, R0						; save first parameter
	ADD		R0, SP, #0x80				; Set R0 to 0x80 in stack struct
	BL		0x1718b34					; libc call (?)
	MOV		R6, #0xD					; R6 = 0xD (\r)
	ADD		R7, SP, #0x80				; Move R7 to 0x80 in stack struct
restart:
	ADD		R3, SP, #0x5C				; Move R3 to 0x5C in stack struct
	ADD		R0, SP, #0x08				; Move R0 to 0x08 in stack struct
charloop:								;
	LDRB	R1, [R7], #1				; Read from 0x80+i
	CMP		R1, #0xA					; if char == \n
	STRBEQ	R6,[R0],#1					;	then store 0xD \r, R0++
	CMP		R1, #0						; if char == \0
	SUBEQ	R7, R7, #1					;	then R7 = R7 - 1 (move one character backwards?)
	CMPNE	R0, R3						;	else if R0 != R3
	STRB	R1, [R0], #1				; always store char @ R0 (why is this here?)
	CMPNE	R0, R3						;		else if R0 != R3
	BNE		charloop					;			break for next char
	MOV		R1, #0x0					; R1 = \0
	STRB	R1, [R0]					; store \0 at end of R0
	MOV		R2, #0x3					; R2 = 0x3
	STR		R2, [SP, #0x4]				; store 3 @ 0x4 in struct
	MOV		R1, #0x1					; R1 = 0x1
	STR		R1, [SP, #0x60]				; store 1 @ 0x60 in struct
	MOV		R0, #0xC					; R0 = #0xC
	STR		R0, [SP]					; store 0xC @ 0x0 in struct
	ADD		R3, SP, #0x64				; R3 = SP + 0x64
	MOV		R2, #0x60					; R2 = 0x60
	ADD		R1, SP, #4					; R1 = SP + 0x4
	ADR		R0, vspLabel				; R0 = VSPCHANNEL Task
	BL		0x17e6cb4					; create IPC call (this is similar to .ConAppCLI's sub_5B57C / health IPC call)
	LDRB	R0, [R7]					; get current character
	CMP		R0, #0						; if != \0
	BNE		restart						;	restart (send another line?)
	LDR		R0, [SP, #0x64]				; end
	LDMDB	R11, {R6, R7, R11, SP, PC}	; end

vspLabel:
	.string	"VSPCHANNEL"

	.word	0x0
	.byte	0x0
