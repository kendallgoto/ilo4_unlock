# iLO 2.81 Patch (signature-bypass only)

This patch ONLY patches the bootloader/kernel/userland signature checks
(identical mechanism to 2.77-2.79), allowing custom/unsigned firmware to be
flashed and basic SSH access confirmed.

It does NOT attempt to restore fan/health/ocsd/ocbb CLI commands. Research
into whether that's possible on this version is ongoing -- see
research/ for findings. HPE's own firmware-side `.health` task code shrank by
roughly 38KB between 2.77 and 2.78 and stayed roughly stable through 2.82,
so the old CLI-rewiring approach used for 2.77 is NOT assumed to work here
without further verification.
