# Patches (2.80)

## Signature bypass
Same mechanism as 2.77-2.79 (bootloader + kernel identical bytes/offsets
across all six firmwares verified 2.77-2.82; userland signature-check AOB
`02 80 83 E0 87 1E 00 EB 00 20 B0 E1 1D 00 00 0A` located uniquely at file
offset 0x964df0, bypass applied 12 bytes in at
0x964dfc).

No fan/health/ocsd/ocbb patches are included in this version pending
further research (see research/ directory).
