# 2022-02-15: Initial Findings

## First Glance
I begun my work reading through the iLO4 Toolbox docs & research papers. At first, I didn't actually realize the scripts from iLO4 toolbox existed (would have helped if I read the reddit thread), so I was splitting up binary files into their composite images by hand ... a lot of fun! Unfortunately, since the ELFs were compressed, splitting them by hand doesn't really work.

It took me a while to realize that though - I was pretty confused when the extracted ELF was missing bytes haphazardly within the header. Turns out there isn't some magic special ELF parser they use, they just compress the entire binary.

Here's a snippet of my very confused notes:
```
Genuine firmware starts with signatures:
HP Signed File Header
certificates
HPImage blob
in bytes 0-1b1b
this can be deleted to start with "ILO4 v" text.

After trimming, payload is 1000000(h) long

Inside payload, multiple code sections
the first: 440(h) long (0-43F) (kernel main)
the second: EEFBC0(h) long (440-EEFFFF) (lots to unpack ...) (userland)
the third: 110000(h) long (EF0000-FFFFFF) (few changes here) (kernel recovery)

each payload has a header & is able to be compressed ...

a header:
440h long
	4 bytes: ilo magic string (4 bytes) (always "iLO4")
	28 bytes: build version string (" v 2.73.2 11-Feb-2020"), truncated with 1A00
	2 bytes: uint32 w/ 'type' 0x0800
	2 bytes: uint32 w/ compression_type 0x0010
	4 bytes: unknown field 0x25100000
	4 bytes: unknown field 0xa66a1000
	4 bytes: decompressed size (uint32) = 24026548 (doesn't change / doesn't matter?)
	4 bytes: raw size / compressed size (uint32) = 13761901 (changes 30-33h!) (is the total byte size from header start - start of final pad)
	4 bytes: load address (uint32) = 0xFFFFFFFF
	4 bytes: unknown field 0x00000000
	4 bytes: unknown field 0xFFFFFFFF
	200 bytes: signature (doesn't have to change)
	200 bytes: padding (filled with 0xFF..)


from original 273
compressed size D1FD6D raw size 16E9DB4
D1F92D long from elf start to start of padding
EEF780 with pad
D1FD6D

from fan 273
compressed size D1FCEA raw size 16E9DB4
D1F92D long from start - start of final pad
this value isn't correct for some reason ...? not sure why it was modified...
D1FD6D long


last block
75ED9 long in original

ELF Header:
7F 45 4C 46 01 01 01 60 0F F5 02 00 28 00 50 0D 34 00 03 94 FD 3B 6E 01 00 0C 17 00 0B 20 FF 00 72 02 28 00 74 02 73 B7
	7F 45 4C 46: magic
	01: ei_class (32bit)
	01: ei_data (little-endian)
	01: ei_version (elf 1)
	60: ei_osabi (?? )
	0F: ei_abiversion
	F5: ei_pad (should be zero filled -- seems that we skip 6 bytes here 00 00 00 00 00 00 00 -> F5)
	02 00: e_type (executable file)
	28 00: e_machine (ARM)
	// 50 0D 34 00: e_version entirely omitted? (should just be 1)
	50 0D: e_entry (shortened to 2 byets / should be 4?)
	34 00: e_phoff
```

One thing that stands out in here, however, is that there's some weird behavior from the ilo4_toolbox re-packer:
it doesn't seem to adjust the iLO4 header to contain good values for the uncompressed-size / compressed-size of the binaries. This ended up causing some errors in the extract scripts when I had to retool them to work with the fan-commands repacked binary.


## Getting iLO4 Toolbox Running
If we use the extract tool in iLO toolbox, we get something like this:
```
python scripts/iLO4/ilo4_extract.py ilo4_273_stock.bin extract
bootloader.bin  cert0.x509  elf.bin  elf.sig       kernel_main.bin  kernel_main.sig      kernel_recovery.raw
bootloader.hdr  cert1.x509  elf.hdr  firmware.map  kernel_main.hdr  kernel_recovery.bin  kernel_recovery.sig
bootloader.sig  cert2.x509  elf.raw  hpimage.hdr   kernel_main.raw  kernel_recovery.hdr  sign_params.raw
```
which provides us a pretty good baseline. We're only ever going to deal with kernel_main.bin and elf.bin -- that's the kernel and userland code. We'll have to move around some offsets for these two binaries, but I diff'd the .fancommands payload compared to to the original 273.bin and found the other bytes didn't change. (afterthought: technically, we patch the bootloader too, but it doesn't change in between releases)

We can also use the dissection ruby script to generate IDA configs. This works terrible on Linux but I run Ida on windows anyway:
```
gem install bindata metasm
scripts/iLO4/dissection.rb extract/elf.bin
```
That gives us an individual loader + script + module to prepare the memory perspective as seen by each process. This is extremely useful if we have calls that jump between loaded libraries (for instance, calling libc, etc, whose position might change between releases). However, for general analysis, its not super necessary and its easier to look at a regular Ida disassembly of elf.bin. Just know that some of the function jumps & memory calls are gonna be wrong and require adjustment.

## Disassemble 273.bin.fancommands
I needed to be able to diff the changes made in the fan commands binary in order to start figuring out specific patches. However, the ilo4_extract script isn't really built to handle the packed binaries. It requires a header and signatures and a bunch of other junk. I tweaked the script (/misc/extract-after-compile.py) and I was able to get an extracted elf.bin out of 273.bin.fancommands
_NB: I had to tweak around with the binary a lot to get it to decode correctly ... specifically, I added some bytes to the beginning of the header (01 00 00 00 29 32 EC AE CC 69 D8 43 BD 0E 61 DC 34 06 F7 1B 00 00 00 00) and had to adjust the size right before the ELF and within the iLO4 header. Hopefully nobody will have to replicate this work, but for reference._

Once I had a working elf.bin from fancommands, I was able to start working on figuring out the changes. Here's /u/phoenixdev's notes that helped me understand the changes I was seeing:

```
But the problem as of late is how to get interprocess communication working between the different pieces of the puzzle. The SSH app uses registered service calls to the Command Line Interface (CLI) app, which can simply use standard out (stdout) to send data back to the SSH session (or to some serial connector). The "health" and "fan" commands (along with two other commands which aren't as useful) live in the Health app and are registered as services that any other app can call to. The result of these commands is also printed out via stdout.

That's all background info. Now what has been accomplished so far is that I have renamed one command in the CLI program ("null_cmd", you use it all the time, don't you?) to "fan" and created a function that passed the arguments to the Health app's "fan" service. This enables me to use all of the "fan" command options, with one caveat. I don't get to see the output. I guess that different programs don't tie their stdouts together in iLO; only the CLI app somehow got direct access to writing to SSH.

There are three remaining steps: The first is to create a new service inside of the CLI app so that any app can eventually write to stdout. The second is to hijack the health app's printf function and redirect it to the new service. Finally, hack one more command ("vsp/r" - does the same exact thing as "vsp") and redirect it to the "h" command.
```

Onto [Reproducing v2.73](2022-02-16-reproducing-273.md)!
