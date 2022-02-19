# iLO 2.73 Patch

This patch patches the signature checking in the kernel + bootloader (just like 250/), as well as applies modifications
to the iLO to unlock the iLO's locked fan controller, etc methods.

The generated patch has the checksums:
06e572e9de5926208bfc52998abdc44410672a79	build/ilo4_273.bin.patched
a773d99a5e1d9aee0915fcb3cd746d5c			build/ilo4_273.bin.patched

which are identical to the ilo4_273.bin.fancommands provided by /u/phoenixdev in their 2.73 release.
