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
#pragma once

typedef unsigned char u8, uint8_t, bool;
typedef unsigned short u16, uint16_t;
typedef unsigned int u32, uint32_t, mode_t, off_t, size_t;
typedef unsigned long long u64, uint64_t;
typedef int ssize_t;

typedef uint32_t dev_t, ino_t, nlink_t, uid_t, gid_t, dev_t, blksize_t, blkcnt_t, time_t;

#define false (0U)
#define true (1U)

/* From Linux:include/stddef.h */
#define offsetof(TYPE, MEMBER) ((size_t)&((TYPE *)0)->MEMBER)

#define STATIC_ASSERT(cond) _Static_assert(cond, #cond)
STATIC_ASSERT(sizeof(uint8_t) == 1);
STATIC_ASSERT(sizeof(uint16_t) == 2);
STATIC_ASSERT(sizeof(uint32_t) == 4);
STATIC_ASSERT(sizeof(uint64_t) == 8);

typedef struct DIR_s {
    u32 unknown;
} DIR;
enum {
    DT_UNKNOWN = 0,
    DT_FIFO = 1,
    DT_CHR = 2,
    DT_DIR = 4,
    DT_BLK = 6,
    DT_REG = 8,
    DT_LNK = 10,
    DT_SOCK = 12,
};
struct dirent {
    uint32_t d_ino; /* Inode number (2 for /, 3 for /mnt, 4 for /tmp) */
    uint16_t d_reclen; /* Size of the record in the directory inode */
    uint8_t d_type; /* DT_... */
    uint8_t d_namelen; /* Length of name */
    char d_name[256];
};
struct ipc {
    uint32_t call;
    char params[256];
};
STATIC_ASSERT(offsetof(struct ipc, call) == 0x0);
STATIC_ASSERT(offsetof(struct ipc, params) == 0x4);

struct timespec {
    time_t tv_sec;
    long tv_nsec;
};
struct stat {
    dev_t     st_dev;         /* ID of device containing file */
    ino_t     st_ino;         /* Inode number */
    mode_t    st_mode;        /* File type and mode */
    nlink_t   st_nlink;       /* Number of hard links */
    uid_t     st_uid;         /* User ID of owner */
    gid_t     st_gid;         /* Group ID of owner */
    dev_t     st_rdev;        /* Device ID (if special file) */
    off_t     st_size;        /* Total size, in bytes */
    blksize_t st_blksize;     /* Block size for filesystem I/O */
    blkcnt_t  st_blocks;      /* Number of 512B blocks allocated */

    struct timespec st_atim;  /* Time of last access */
    struct timespec st_mtim;  /* Time of last modification */
    struct timespec st_ctim;  /* Time of last status change */
};

#define errno (*(int *)get_errno_ptr())

#if HPILO_VER == 0x277
#include "ilo_277.h"
#else
#error Unknown iLO Version
#endif
