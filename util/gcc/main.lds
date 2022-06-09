OUTPUT_FORMAT("elf32-littlearm")
ENTRY(_entrypoint)

SECTIONS
{
    . = 0;
    .shcode : {
        *(.entry)
        . = ALIGN(4);
        *(.text)
        . = ALIGN(4);
        *(.data .data.*)
        . = ALIGN(4);
        *(.rodata *.rodata.*)
    }
}
