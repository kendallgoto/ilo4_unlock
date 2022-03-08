# Patches
To the best of my ability, I've documented the patched bytes included in the patch_userland.json file below.

## 0xE76184 Logging Patch
This is the only patch I had to change. It makes some calls to relative libraries in memory (libc & VCom Shared), whose positions moved (I guess if the local memory got shifted due to changes of library sizes, etc). I originally didn't notice this and it caused an stdout error (see research/2022-02-19). Our patch is identical to 273, except we move the BL instructions to point to the correct offsets.

Otherwise, I moved around offsets. Here's some Array of Bytes / AoBs I used to track down the pointers:

Check out my documented asm in asm/stdout.S

## Bypass signature check : BEQ XX -> B XX
AOB 02 80 83 E0 87 1E 00 EB 00 20 B0 E1 1D 00 00 0A
one match

## Command Strings (`quit`)
AOB 00 00 00 00 71 75 69 74 00 00 00 00 6F 65 6D 68
one match

(look nearby for the rest of the command strings)

## Function entrypoint
AOB 0D C0 A0 E1 20 D8 2D E9 04 B0 4C E2 8B 13 00 EB 9A
one match

Check out my documented asm in asm/fn_handler.S

## Health Break
AOB 0D C0 A0 E1 0E 00 2D E9 00 D8 2D E9 10 B0 4C E2  08 D0 4D E2
9th match -- it's probably safe-r to use IDA and find the match inside the .health segment

I always struggled to find the actual logging code placement -- it's likely easiest to just go to the breakpoint and scroll down, or patch Health Break above and follow the jump, since the pointer stays correct

## Command Function Calls
All of the function calls have pretty unique AoBs for their actual call pointers; i.e.
74 9E 01 00 -> OCBB (use the second match!)
7C C8 01 00 -> health (use the first match!)
C8 CE 01 00 -> OCSD (use the second match!)
5C D1 01 00 -> Fan (use the last match!)

Just find the match that's within the concli .data -- there's a few duplicates because these methods are duplicates (i.e. exit/quit call the same thing), but you should be able to use the order to figure it out. Command order doesn't change between builds (historically anyway).

## Kernel Patch
AOB 30 10 95 E5 00 00 50 E3 04 00 00 0A 00 00 51 E3
one match
