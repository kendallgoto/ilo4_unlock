#!/usr/bin/env bash
#
# Deterministic packaging pipeline for ilo4_unlock diagnostic/patch builds.
#
# Replaces the by-hand sequence this project has repeated for every
# diagnostic build (diag1-8): apply the bootloader/kernel sig-bypass
# patches, run the ELF-level patch script, repack via the vendored
# Python-2-only ilo4_repack.py inside Docker, and verify the result with a
# full compression round-trip. Produces one named, hash-stamped .toflash
# ready to flash.
#
# usage:
#   tools/package_build.sh <build_script.py> <output_name> [extract_dir] [patch_dir]
#
#   build_script.py  an ELF patcher with the same CLI signature as every
#                     patches/280-diagN-*/build_diagN.py: `script.py <in_elf> <out_elf>`.
#                     It must apply its own ELF-internal sig-bypass (every
#                     build_diagN.py does this itself); this script only
#                     handles the separate bootloader.bin/kernel_main.bin
#                     sig-bypass patches.
#   output_name       basename (no extension) for the final .toflash.
#                      Written to the current working directory -- NOT into
#                      the repo, since the output is proprietary HP firmware
#                      and must never be committed.
#   extract_dir       directory with genuine bootloader.bin, kernel_main.bin,
#                      elf.bin, firmware.bin, firmware.map (default:
#                      <repo>/build_extract)
#   patch_dir         directory with patch_bootloader.json and
#                      patch_kernel.json (default: <repo>/patches/280)
#
# Requires Docker (Rancher Desktop) running; will try to start it and wait
# up to ~60s if it isn't.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLBOX="$REPO_ROOT/ilo4_toolbox"

if [ $# -lt 2 ]; then
    echo "usage: $0 <build_script.py> <output_name> [extract_dir] [patch_dir]" >&2
    exit 1
fi

BUILD_SCRIPT="$1"
OUTPUT_NAME="$2"
EXTRACT_DIR="${3:-$REPO_ROOT/build_extract}"
PATCH_DIR="${4:-$REPO_ROOT/patches/280}"

if [ ! -f "$BUILD_SCRIPT" ]; then
    echo "error: build script not found: $BUILD_SCRIPT" >&2
    exit 1
fi
for f in bootloader.bin kernel_main.bin elf.bin firmware.bin firmware.map; do
    if [ ! -f "$EXTRACT_DIR/$f" ]; then
        echo "error: missing genuine artifact: $EXTRACT_DIR/$f" >&2
        exit 1
    fi
done
for f in patch_bootloader.json patch_kernel.json; do
    if [ ! -f "$PATCH_DIR/$f" ]; then
        echo "error: missing sig-bypass patch file: $PATCH_DIR/$f" >&2
        exit 1
    fi
done

if ! docker info >/dev/null 2>&1; then
    echo "[package_build] Docker not responding; attempting to start Rancher Desktop..."
    open -a "Rancher Desktop" >/dev/null 2>&1 || true
    for _ in $(seq 1 30); do
        sleep 2
        if docker info >/dev/null 2>&1; then
            break
        fi
    done
    if ! docker info >/dev/null 2>&1; then
        echo "error: Docker daemon still not available after waiting. Start Rancher Desktop manually and retry." >&2
        exit 1
    fi
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ilo4_package.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
echo "[package_build] work dir: $WORK_DIR"

echo "[package_build] applying bootloader sig-bypass..."
python3 "$REPO_ROOT/tools/apply_json_patch.py" \
    "$EXTRACT_DIR/bootloader.bin" "$PATCH_DIR/patch_bootloader.json" \
    "$WORK_DIR/bootloader.bin"

echo "[package_build] applying kernel sig-bypass..."
python3 "$REPO_ROOT/tools/apply_json_patch.py" \
    "$EXTRACT_DIR/kernel_main.bin" "$PATCH_DIR/patch_kernel.json" \
    "$WORK_DIR/kernel_main.bin"

echo "[package_build] running ELF patch script: $BUILD_SCRIPT"
python3 "$BUILD_SCRIPT" "$EXTRACT_DIR/elf.bin" "$WORK_DIR/elf.bin"

cp "$EXTRACT_DIR/firmware.bin" "$WORK_DIR/firmware.bin"
cp "$EXTRACT_DIR/firmware.map" "$WORK_DIR/firmware.map"

echo "[package_build] repacking via ilo4_repack.py (python:2.7 container)..."
docker run --rm -v "$TOOLBOX":/toolbox -v "$WORK_DIR":/work python:2.7 \
    python /toolbox/scripts/iLO4/ilo4_repack.py \
    /work/firmware.bin /work/firmware.map /work/elf.bin /work/kernel_main.bin /work/bootloader.bin

echo "[package_build] verifying compression round-trip..."
docker run --rm -v "$TOOLBOX":/toolbox -v "$WORK_DIR":/work -v "$REPO_ROOT/tools":/tools python:2.7 \
    python /tools/verify_roundtrip.py /work

OUT_PATH="$(pwd)/${OUTPUT_NAME}.toflash"
cp "$WORK_DIR/firmware.bin.backdoored.toflash" "$OUT_PATH"

echo "[package_build] done."
echo "  output: $OUT_PATH"
echo "  sha1:   $(shasum "$OUT_PATH" | awk '{print $1}')"
echo "  (proprietary HP firmware bytes -- do not commit this file)"
