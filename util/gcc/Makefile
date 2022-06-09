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

VERSION ?= 277

ARM_OBJDUMP ?= arm-none-eabi-objdump
ARM_GCC ?= arm-none-eabi-gcc
HPILO_VER := $(shell printf "0x%d" $(VERSION))
CPPFLAGS += -DHPILO_VER=$(HPILO_VER)
WARNINGS := -Wall -Wextra
WARNINGS += -Wno-unused-parameter
WARNINGS += -Wno-unused-variable
WARNINGS += -Wno-unused-function
WARNINGS += -Werror

all: main.bin

clean:
	$(RM) ./*.bin ./*.o ./.*.d

main.bin: main.linked.o
	if $(ARM_OBJDUMP) -r $< | grep -i shcode ; then \
		echo "Fatal error: relocations exist!" ; \
		$(ARM_OBJDUMP) -r $< ; \
		false ; \
	fi
	arm-none-eabi-objcopy -j .shcode -O binary $< $@
	chmod -x $@
	stat -c '%s %n' $@

main.linked.o: main.o
	@
	arm-none-eabi-ld -nostdlib -O1 -T main.lds -shared -Bsymbolic -as-needed -no-undefined -warn-common -fatal-warnings $^ -o $@

main.o: main.c
	$(ARM_GCC) $(WARNINGS) $(CPPFLAGS) -Wp,-MT,$@ -Wp,-MD,$(dir $@).$(notdir $@).d \
		-O2 -c -fPIC -nostdlib -ffreestanding -mpic-register=r4 $< -o $@

-include .*.d

dump: main.bin
	$(ARM_OBJDUMP) -D -bbinary -marm $<

.PHONY: all clean dump dumplinked dumplinkedd
.PRECIOUS: main.linked.o main.o
