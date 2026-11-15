# iLO 2.80 Patch (signature-bypass only)

**Hardware-confirmed working on a real HP DL380 Gen9, 2026-11-05.** Boots
normally, iLO reports its correct version, SSH access confirmed (see SSH
client note below), all 6 fans report `OperationalStatus=Ok`/
`HealthState=Ok` and were observed dynamically adjusting speed downward
(40-50% -> 15-27%) as the system settled post-boot -- normal, healthy
automatic thermal control, no anomaly. This is the first version beyond
2.77 confirmed on real hardware.

**SSH client note:** a modern OpenSSH client (10.x) will fail to connect
with "no matching key exchange method found" -- this embedded SSH server
(`mpSSH_0.2.1`) only offers legacy `diffie-hellman-group14-sha1`/
`diffie-hellman-group1-sha1` KEX and `ssh-rsa`/`ssh-dss` host keys. Even
after forcing those via `-o KexAlgorithms=+diffie-hellman-group14-sha1 -o
HostKeyAlgorithms=+ssh-rsa`, a very new client (observed: OpenSSH 10.5)
still gets disconnected by the server during the key exchange reply itself
-- a deeper incompatibility than just the deprecated algorithm list. An
older client (observed working: OpenSSH 8.4p1) completes the handshake
fine with the same flags. If SSH connections "immediately terminate," try
an older ssh client before assuming the firmware is broken.

This patch ONLY patches the bootloader/kernel/userland signature checks
(identical mechanism to 2.77-2.79), allowing custom/unsigned firmware to be
flashed and basic SSH access confirmed.

It does NOT attempt to restore fan/health/ocsd/ocbb CLI commands. Research
into whether that's possible on this version is ongoing -- see
research/ for findings. HPE's own firmware-side `.health` task code shrank by
roughly 38KB between 2.77 and 2.78 and stayed roughly stable through 2.82,
so the old CLI-rewiring approach used for 2.77 is NOT assumed to work here
without further verification.
