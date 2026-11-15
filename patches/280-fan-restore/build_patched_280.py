import struct, pickle, sys, os

# usage: python3 build_patched_280.py <extracted-280-elf.bin> <output-path>
# (produces an elf.bin with both the sig-bypass patch AND the fan-restore
# patch applied; feed the result to ilo4_repack.py as the patched userland)
if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <extracted 2.80 elf.bin> <output path>")
    sys.exit(1)

IN_PATH = sys.argv[1]
OUT_PATH = sys.argv[2]
FAN_BLOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fan_block.bin')

data = bytearray(open(IN_PATH, 'rb').read())

# --- apply the proven-working sig-bypass patch first (patches/280/patch_userland.json),
# while file offsets are still in their ORIGINAL (unshifted) positions ---
SIGBYPASS_OFFSET = 0x964dfc
old = bytes(data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4])
assert old == bytes.fromhex('1D00000A'.replace(' ', '')), old.hex()
data[SIGBYPASS_OFFSET:SIGBYPASS_OFFSET+4] = bytes.fromhex('1D0000EA')
print(f"sig-bypass patch applied @0x{SIGBYPASS_OFFSET:x}: {old.hex()} -> 1d0000ea")

e_shoff = struct.unpack_from('<I', data, 0x20)[0]
e_shentsize = struct.unpack_from('<H', data, 0x2e)[0]
e_shnum = struct.unpack_from('<H', data, 0x30)[0]
shstrtab_idx = struct.unpack_from('<H', data, 0x32)[0]
assert e_shentsize == 40

def read_shdr(i):
    off = e_shoff + i*e_shentsize
    fields = struct.unpack_from('<IIIIIIIIII', data, off)
    keys = ['sh_name','sh_type','sh_flags','sh_addr','sh_offset','sh_size','sh_link','sh_info','sh_addralign','sh_entsize']
    return dict(zip(keys, fields))

shdrs = [read_shdr(i) for i in range(e_shnum)]
shstrtab_off = shdrs[shstrtab_idx]['sh_offset']

def name_of(i):
    n = shdrs[i]['sh_name']
    end = data.index(b'\x00', shstrtab_off+n)
    return data[shstrtab_off+n:end].decode('latin1')

hdata_idx = next(i for i in range(e_shnum) if name_of(i) == '.health.elf.data')
secinfo_idx = next(i for i in range(e_shnum) if name_of(i) == '.secinfo')

hdata = shdrs[hdata_idx]
secinfo = shdrs[secinfo_idx]

insertion_offset = hdata['sh_offset'] + hdata['sh_size']
assert insertion_offset == 0x41ebc0, hex(insertion_offset)

TARGET_VADDR = 0xe94000
zero_pad_len = TARGET_VADDR - hdata['sh_addr'] - hdata['sh_size']
assert zero_pad_len >= 0, zero_pad_len

fan_block = open(FAN_BLOCK_PATH, 'rb').read()
assert len(fan_block) == 15548

insertion_bytes = (b'\x00' * zero_pad_len) + fan_block
delta = len(insertion_bytes)
print(f"insertion_offset=0x{insertion_offset:x} zero_pad_len={zero_pad_len} fan_block_len={len(fan_block)} delta=0x{delta:x}")

new_text_size = hdata['sh_size'] + delta
print(f"new .health.elf.data text_size (sh_size) = 0x{new_text_size:x}")

# --- sanity check callsite patch target before we touch anything ---
CALLSITE_FOFF = 0x38e5d8
NEW_BL_BYTES = b'\xebC\x02\xeb'
old_bytes_at_callsite = bytes(data[CALLSITE_FOFF:CALLSITE_FOFF+4])
print(f"callsite current bytes @0x{CALLSITE_FOFF:x}: {old_bytes_at_callsite.hex()}")
assert old_bytes_at_callsite == bytes.fromhex('1e4900eb'), old_bytes_at_callsite.hex()
assert CALLSITE_FOFF < insertion_offset  # unaffected by insertion

# --- perform insertion ---
new_data = bytearray(data[:insertion_offset]) + bytearray(insertion_bytes) + bytearray(data[insertion_offset:])

# --- apply callsite patch (file offset unchanged, before insertion point) ---
new_data[CALLSITE_FOFF:CALLSITE_FOFF+4] = NEW_BL_BYTES

# --- fix up e_shoff ---
new_e_shoff = e_shoff + delta if e_shoff >= insertion_offset else e_shoff
struct.pack_into('<I', new_data, 0x20, new_e_shoff)
print(f"e_shoff: 0x{e_shoff:x} -> 0x{new_e_shoff:x}")

# --- fix up every section header's sh_offset (and hdata's sh_size) ---
SHDR_FIELD_OFFSETS = {'sh_name':0,'sh_type':4,'sh_flags':8,'sh_addr':12,'sh_offset':16,'sh_size':20,'sh_link':24,'sh_info':28,'sh_addralign':32,'sh_entsize':36}

shifted_count = 0
for i in range(e_shnum):
    hdr_off = new_e_shoff + i*e_shentsize
    sh = shdrs[i]
    old_off = sh['sh_offset']
    if old_off >= insertion_offset:
        new_off = old_off + delta
        shifted_count += 1
    else:
        new_off = old_off
    struct.pack_into('<I', new_data, hdr_off + SHDR_FIELD_OFFSETS['sh_offset'], new_off)
    if i == hdata_idx:
        struct.pack_into('<I', new_data, hdr_off + SHDR_FIELD_OFFSETS['sh_size'], new_text_size)

print(f"shifted sh_offset for {shifted_count} of {e_shnum} sections")

# --- fix up .secinfo entry for mod_id 0x82 (.health.elf.data) text_size field ---
new_secinfo_off = secinfo['sh_offset'] + delta if secinfo['sh_offset'] >= insertion_offset else secinfo['sh_offset']
SECINFO_ENTRY_OFF_IN_SECTION = 0xde0  # entry idx 81, confirmed via parse_boottable.py / direct scan
text_size_field_off = new_secinfo_off + SECINFO_ENTRY_OFF_IN_SECTION + 12  # next_ptr,name_ptr,text_base_addr,text_size

# sanity check: confirm text_base_addr field at this entry matches 0xe91000 before editing
check_text_base = struct.unpack_from('<I', new_data, new_secinfo_off + SECINFO_ENTRY_OFF_IN_SECTION + 8)[0]
assert check_text_base == 0xe91000, hex(check_text_base)
check_old_text_size = struct.unpack_from('<I', new_data, text_size_field_off)[0]
assert check_old_text_size == 0x2e8c, hex(check_old_text_size)

struct.pack_into('<I', new_data, text_size_field_off, new_text_size)
print(f".secinfo text_size for .health.elf.data: 0x{check_old_text_size:x} -> 0x{new_text_size:x} (at file offset 0x{text_size_field_off:x})")

open(OUT_PATH, 'wb').write(new_data)
print(f"\nWrote {OUT_PATH} ({len(new_data)} bytes, was {len(data)} bytes, grew by {len(new_data)-len(data)})")
