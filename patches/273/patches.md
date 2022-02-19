# Patches
To the best of my ability, I've documented the patched bytes included in the patch_userland.json file below.

## Bypass signature check : BEQ XX -> B XX
By patching the signature check in the userland, we're able to upload arbitrary firmware. This is a very similar change to the one we make in the kernel, except this validates the firmware after web upload, where the kernel change validates the firmware at boot. TODO I believe this allows us to upload arbitrary firmware from the web UI.

## Rename `quit` to `OCBB`
In our table of commands, we must remove some known commands to make room for our new commands. Since `quit` is the same as `exit`, we can replace it with OCBB.

## Rename `VSPR` to `h`
Next, since `VSP\R` is the same as `VSP`, we replace it with `h` to call our health utility

## Rename `DEBUG` to `OCSD`
Since `debug` is not very useful, we replace it with `OCSD` to call the option card utility.

## Rename `NULL_CMD` to `FAN`
Finally, Since `null_cmd` is unused, we can replace it with `fan` to call our fan utility

## Add function argument parsing & entry point for new functions
This is a hefty patch and its easier to cover what its doing in the disassembly. In essence, we add the entrypoints
for our 4 new functions and include an argument parser to handle those:
```
05 00 A0 E3                       MOV             R0, #5				-- Entrypoint for health
04 00 00 EA                       B               entrypoint			-- Write immediate 5 to R0

06 00 A0 E3                       MOV             R0, #6				-- Entrypoint for fan
02 00 00 EA                       B               entrypoint			-- Write immediate 6 to R0

07 00 A0 E3                       MOV             R0, #7				-- Entrypoint for OCSD
00 00 00 EA                       B               entrypoint			-- Write immediate 7 to R0

08 00 A0 E3                       MOV             R0, #8				-- Entrypoint for OCBB
																		-- Write immediate 8 to R0
entrypoint
0D C0 A0 E1                       MOV             R12, SP				-- Initialize function
00 D8 2D E9                       PUSH            {R11,R12,LR,PC}		-- init
04 B0 4C E2                       SUB             R11, R12, #4			-- init
0A DC 4D E2                       SUB             SP, SP, #0xA00		-- allocate some space on the stack
00 00 8D E5                       STR             R0, [SP]				-- store R0 on SP (5/6/7/8)
00 30 A0 E3                       MOV             R3, #0				-- start R3 @ 0
04 20 8D E2                       ADD             R2, SP, #4			-- prepare R2 for writing onto stack @ SP+4
01 0A 87 E2                       ADD             R0, R7, #0x1000		-- R0 = R7+0x1000; R0 points at input args?
parseloop																-- start character process loop
01 10 D0 E4                       LDRB            R1, [R0],#1			-- load 1 byte from R0 into R1, incr R0+1
20 00 51 E3                       CMP             R1, #0x20 ; ' '		-- if R1 is space
01 30 C2 04                       STRBEQ          R3, [R2],#1			-- (STRB if EQ) true: store \0 in R2, incr R2
01 10 C2 14                       STRBNE          R1, [R2],#1			-- (STRB if NE) false: store char in R2, incr R2
00 00 51 E3                       CMP             R1, #0				-- if R1 == end of string
F9 FF FF 1A                       BNE             parseloop				-- if not, loop again
00 30 C2 E5                       STRB            R3, [R2]				-- add final \0
0D 00 A0 E1                       MOV             R0, SP				-- call(SP, SP+500)
05 1C 8D E2                       ADD             R1, SP, #0x500		-- call(SP, SP+500)
EE F8 00 EB                       BL              sub_21B157C			-- call appropriate `health` service method
00 05 9D E5                       LDR             R0, [SP,#0x500]		-- load R0 from [SP+500]?
00 A8 1B E9                       LDMDB           R11, {R11,SP,PC}		-- end function

00 00 00 00 00 00+                ALIGN 0x10							-- pad unused bytes w/ 0s
```
This code replace some otherwise unused code that was handling null_cmd, which we removed already.
Roughly, it parses the input arguments into a fat set of strings on the stack, spaced by `\0`, then calls 'sub_21B157C'.  
sub_21B157C fires a call to our health service -- which will in turn call the desired function (there's a jumptable in .health that corresponds to our 5/6/7/8 value on the stack. (.health.elf.text:00E04CB4)

## Immediately Break sub_E75D98 w/ jump to E76184
Bypass default stdout behavior of `health` app and call E76184 instead.

## 0xE76184 Logging Patch
More documentation is needed for this! I don't really understand what the code does - although, its purpose is to redirect logging behavior from the health service back to stdout for the user.

## Add entry jump to OCBB
There's also a separate array of shell command structs. Each element contains a pointer to the name, function, help function, and version function of a shell command. We move the second value, the function pointer, to point to the entrypoint marked previously.

## Add entry jump to health
As above for OCBB, we make the change for `health`.

## Add entry jump to OCSD
As above for OCBB, we make the change for `ocsd`.

## Add entry jump to fan
As above for OCBB, we make the change for `fan`.
