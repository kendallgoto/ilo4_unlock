start:
	PUSH {R1-R3}
	MOV R2, SP
	PUSH {R6, R7, R11, R12, LR, PC}
	SUB R11, R12, #0x10
	SUB SP, SP, $0x400
	MOV R1, R0
	ADD R0, SP, #0x80
	BL 0x1718b34
	MOV R6, #0xD
	ADD R7, SP, #0x80
restart:
	ADD R3, SP, #0x5C
	ADD R0, SP, #0x08
charloop:
	LDRB R1, [R7], #1
	CMP R1, #0xA
	STRBEQ R6,[R0],#1
	CMP R1, #0
	SUBEQ R7, R7, #1
	CMPNE R0, R3
	STRB R1, [R0], #1
	CMPNE R0, R3
	BNE charloop
	MOV R1, #0x0
	STRB R1, [R0]
	MOV R2, #0x3
	STR R2, [SP, #0x4]
	MOV R1, #0x1
	STR R1, [SP, #0x60]
	MOV R0, #0xC
	STR R0, [SP]
	ADD R3, SP, #0x64
	MOV R2, #0x60
	ADD R1, SP, #4
	ADR R0, vspLabel
	BL 0x17e6cb4
	LDRB R0, [R7]
	CMP R0, #0
	BNE restart
	LDR R0, [SP, #0x64]
	LDMDB R11, {R6, R7, R11, SP, PC}
vspLabel: .string "VSPCHANNEL"

.word 0x0
.byte 0x0
