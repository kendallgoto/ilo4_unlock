/*
# This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
# Derived from Airbus Security Lab @  https://github.com/airbus-seclab/ilo4_toolbox
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
*/

#include "ilo.h"

struct CLI_SESSION {
    u8 pad1[0x164];
    char argv[16][256]; /* 16 256-char-wide command arguments */
    u32 argc;
	u8 pad2[0x204];
	char argstr[256];
};
/* ensure we've got our padding correct */
STATIC_ASSERT(offsetof(struct CLI_SESSION, argv) == 0x164);
STATIC_ASSERT(offsetof(struct CLI_SESSION, argc) == 0x1164);
STATIC_ASSERT(offsetof(struct CLI_SESSION, argstr) == 0x136C);

/* ConAppCLI */
static int (__attribute__((format(printf, 2, 3))) *CLI_printf)(u32 cli_id, const char *fmt, ...) = (const void *)0x12F68;
static struct CLI_SESSION *(*ConAppCLI_get_CLI_session_ptr)(u32 cli_id) = (const void *)0x21F9C;
static int (*ConAppCLI_call_Health)(struct ipc *ref, uint32_t *result) = (const void *)0x5B57C;
static int (*ConAppCLI_getFnIndex)(char *command) = (const void *)0x1832C;
static int (*ConAppCLI_strcasecmp)(char *str1, char *str2) = (const void *)0x7F434;

/* libc.so */
static void *(*malloc)(size_t size) = (const void *)0x017B85E8;
static void (*free)(void *ptr) = (const void *)0x017B86F4;
static size_t (*strlen)(const char *str) = (const void *)0x017B2800;

static DIR *(*opendir)(const char *path) = (const void *)0x017A0CB4;
static void (*closedir)(DIR *dir) = (const void *)0x017A0D70;
static int (*readdir_r)(DIR *dir, struct dirent *entry, struct dirent **result) = (const void *)0x017A0DB4;

static int (*lstat)(const char *pathname, struct stat *statbuf) = (const void *)0x017AC75C;
static int (*ioctl)(int fd, unsigned long request, ...) = (const void *)0x017AD820;
static int (*open)(const char *pathname, int flags, mode_t mode) = (const void *)0x017AE89C;
static ssize_t (*write)(int fd, const void *buf, size_t count) = (const void *)0x017AE9D8;
static ssize_t (*read)(int fd, void *buf, size_t count) = (const void *)0x017AEABC;
static int (*close)(int fd) = (const void *)0x017AEC80;
static off_t (*lseek)(int fd, off_t offset, int whence) = (const void *)0x017AED24;

static int *(*get_errno_ptr)(void) = (const void *)0x017A25A0;

static int (__attribute__((format(printf, 3, 4))) *snprintf)(char *str, size_t size, const char *format, ...) = (const void *)0x017B3FE0;

static int (*libc_RequestResource)(u32 *pRes, const char *szResName, const char *szSystemPassword) = (const void *)0x017A3948;

static int (*AllocateAnyMemoryRegion)(u32 pool, u32 size, u32 *dwMemRegion) = (const void *)0x017A1DB4;

/* libINTEGRITY.so */
static int (*INTEGRITY_CloseConnection)(u32 dwMemIndex) = (const void *)0x017808FC;
static int (*INTEGRITY_MapMemoryRegion)(u32 dwMemIndex, u32 dwMemoryRegion) = (const void *)0x017809AC;
static int (*INTEGRITY_UnMapMemoryRegion)(u32 dwMemIndex, u32 *pResult) = (const void *)0x017826D4;
static int (*INTEGRITY_SetMemoryRegionAttributes)(u32 dwMemoryRegion, u32 dwFlags) = (const void *)0x01782734;
static int (*INTEGRITY_CopyToMemoryRegion)(u32 physMR, u32 physaddr, const void *pInput, size_t ccbInput, u32 unknown_2832) = (const void *)0x1782818;
static int (*INTEGRITY_CopyFromMemoryRegion)(u32 dwPhysMemoryRegion, u32 dwPhysAddr, void *pOutput, u32 dwOutLen, u32 unknown_2049) = (const void *)0x0178284C;
static int (*INTEGRITY_GetMemoryRegionAttributes)(u32 dwMemoryRegion, u32 *pdwFlags) =(const void *) 0x01782964;
static int (*INTEGRITY_GetMemoryRegionAddress)(u32 dwMemIndex, u32 *pVirtAddrStart, u32 *pVirtAddrEnd) = (const void *)0x017829A0;
