/*
# This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
# Copyright (c) 2022 Kendall Goto
# with some code derived from https://github.com/airbus-seclab/ilo4_toolbox
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
__asm__ (
"	.section .entry, \"ax\", %progbits\n"
"	.arm\n"
"	.globl _entrypoint\n"
"	.hidden _entrypoint\n"
"	.type _entrypoint, %function\n"
"_entrypoint:\n"
"	b payload_start\n"
);
/*
void dump_registers(u32 cli_id) {
	//struct CLI_SESSION *pCli;

	//pCli = ConAppCLI_get_CLI_session_ptr(cli_id);

	uint32_t r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10;
	asm (
		"STR %%r0, %[a0] ;"
		"STR %%r1, %[a1] ;"
		"STR %%r2, %[a2] ;"
		"STR %%r3, %[a3] ;"
		"STR %%r4, %[a4] ;"
		"STR %%r5, %[a5] ;"
		"STR %%r6, %[a6] ;"
		"STR %%r7, %[a7] ;"
		"STR %%r8, %[a7] ;"
		"STR %%r9, %[a7] ;"
		"STR %%r10, %[a10] ;"
		:
		[a0] "=m" (r0), [a1] "=m" (r1), [a2] "=m" (r2), [a3] "=m" (r3),
		[a4] "=m" (r4), [a5] "=m" (r5), [a6] "=m" (r6), [a7] "=m" (r7),
		[a8] "=m" (r8), [a9] "=m" (r9), [a10] "=m" (r10)
	);
	CLI_printf(cli_id, "r0=%08x\n", r0);
	CLI_printf(cli_id, "r1=%08x\n", r1);
	CLI_printf(cli_id, "r2=%08x\n", r2);
	CLI_printf(cli_id, "r3=%08x\n", r3);
	CLI_printf(cli_id, "r4=%08x\n", r4);
	CLI_printf(cli_id, "r5=%08x\n", r5);
	CLI_printf(cli_id, "r6=%08x\n", r6);
	CLI_printf(cli_id, "r7=%08x\n", r7);
	CLI_printf(cli_id, "r8=%08x\n", r8);
	CLI_printf(cli_id, "r9=%08x\n", r9);
	CLI_printf(cli_id, "r10=%08x\n", r10);
}
*/
void dump_vmemory(u32 cli_id, uint32_t startAddr, uint32_t len) {
	uint32_t i;
	char buff[17];
	char *pc = (char *)startAddr;
	for(i = 0; i < len; i++) {
		if((i % 16) == 0) {
			if(i != 0)
				CLI_printf(cli_id, "\t%s\n", buff);
			CLI_printf(cli_id, "%04x\t%04x ", i, i+startAddr);
		}

		CLI_printf(cli_id, " %02x", pc[i]);

		if((pc[i] < 0x20) || (pc[i] > 0x7e)) {
			buff[i % 16] = '.';
		} else {
			buff[i % 16] = pc[i];
		}
		buff[(i % 16) + 1] = '\0';
	}
	while((i%16) != 0) {
		CLI_printf(cli_id, "\t");
		i++;
	}
	CLI_printf(cli_id, "\t%s\n\n\n", buff);
}

void health_handler(u32 cli_id) {
	struct CLI_SESSION *pCli;
	pCli = ConAppCLI_get_CLI_session_ptr(cli_id);
	CLI_printf(cli_id, "%s", pCli->argstr);
	char *args = pCli->argstr;
	struct ipc testFan;
	uint32_t mode;
	uint32_t base = strlen(pCli->argv[0]) + 1;
	if(ConAppCLI_strcasecmp(pCli->argv[1], "h") == 0) {
		mode = 5;
	} else if(ConAppCLI_strcasecmp(pCli->argv[1], "fan") == 0){
		mode = 6;
	} else if(ConAppCLI_strcasecmp(pCli->argv[1], "ocsd") == 0) {
		mode = 7;
	} else if((ConAppCLI_strcasecmp(pCli->argv[1], "ocbb") == 0)) {
		mode = 8;
	} else {
		CLI_printf(cli_id, "must call fan/ocsd/ocbb/h\n");
		return;
	}
	testFan.call = mode;
	for(int i = 0; i < 255; i++) {
		char thisChar = args[i+base];
		if(thisChar == ' ') {
			testFan.params[i] = '\0';
		}
		else if(thisChar == '\0') {
			testFan.params[i] = '\0';
			break;
		} else {
			testFan.params[i] = thisChar;
		}
	}
	dump_vmemory(cli_id, (int)&testFan, sizeof(testFan));

	uint32_t *result = malloc(0x500);
	uint32_t rescode = ConAppCLI_call_Health(&testFan, result);
	CLI_printf(cli_id, "Done, result %d\n", rescode);
	dump_vmemory(cli_id, (uint32_t)result, 0x500);
	free(result);

}

static __attribute__((used))
void payload_start(u32 cli_id) {
	health_handler(cli_id);
}
