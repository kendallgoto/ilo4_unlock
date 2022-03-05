# Patches
To the best of my ability, I've documented the patched bytes included in the patch_userland.json file below.

## Bypass signature check : BEQ XX -> B XX
By patching the signature check in the userland, we're able to upload arbitrary firmware. This is a very similar change to the one we make in the kernel, except this validates the firmware after web upload, where the kernel change validates the firmware at boot. I'm not sure what the purpose of this code is - maybe to make it easier for /u/phoenixdev to work on changes? But the signature bypass didn't work in practice for me & I don't see this bypass in Airbus' research ... I might remove it in the future.

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
for our 4 new functions and include an argument parser to handle those. See the documented asm patch [here](/patches/277/asm/fn_handler.S).

This code replace some otherwise unused code that was handling null_cmd, which we removed already.
Roughly, it parses the input arguments into a fat set of strings on the stack, spaced by `\0`, then calls 'sub_21B157C'.  
sub_21B157C fires a call to our health service -- which will in turn call the desired function (there's a jumptable in .health that corresponds to our 5/6/7/8 value on the stack. (.health.elf.text:00E04CB4)

## Immediately Break sub_E75D98 w/ jump to E76184
Bypass default stdout behavior of `health` app and call E76184 instead.

## 0xE76184 Logging Patch
The original piece of code here looks to be dead, so we replace it with our custom logging code that is entered from sub_E75D98. The previous function seems to serve as the general handler for all output from the health service; so we subvert all the output back into here instead.
This replicates an IPC call from .ConAppCLI, calling the VSPChannel task to log data to the stdout. See the documented asm patch [here](/patches/277/asm/stdout.S).

## Add entry jump to OCBB
There's also a separate array of shell command structs. Each element contains a pointer to the name, function, help function, and version function of a shell command. We move the second value, the function pointer, to point to the entrypoint marked previously.

## Add entry jump to health
As above for OCBB, we make the change for `health`.

## Add entry jump to OCSD
As above for OCBB, we make the change for `ocsd`.

## Add entry jump to fan
As above for OCBB, we make the change for `fan`.
