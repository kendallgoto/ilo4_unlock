import keystone
import paramiko
import argparse
import logging
import sys
import time
import struct
import os
from keystone import *

triggerCommand = b'help'

parser = argparse.ArgumentParser(description="SSH Tools for iLO4_unlock")
parser.add_argument('addr', help="IP of iLO")
parser.add_argument('-u', '--user', type=str, default='Administrator', help="iLO Username")
parser.add_argument('-p', '--password', type=str, default='', help="iLO Password")
parser.add_argument('-P', '--port', type=int, default=22, help="SSH Port")

args = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('ssh')
logger.info("Connecting ...")
client = paramiko.client.SSHClient()
client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy)
client.connect(args.addr, args.port, username=args.user, password=args.password, timeout=30, allow_agent=False, look_for_keys=False)

logger.info("SSH session to %s:%d opened", args.addr, args.port)

channel = client.invoke_shell()
channel.setblocking(0)
def recv_all():
    time.sleep(.05)
    result = b''
    while channel.recv_ready():
            result += channel.recv(4096)
    if result:
        logger.debug("SSH recv: %r", result)
    return result
def recv_force():
    data = recv_all()
    numiter = 0
    while not data:
        numiter += 1
        logger.debug("Waiting ...")
        if numiter <= 10:
                time.sleep(.1)
        elif numiter <= 20:
                time.sleep(1)
        else:
            logger.fatal("Time out")
            sys.exit(1)
        data = recv_all()
    return data

def recv_until_prompt():
    data = recv_force()
    while b'hpiLO' not in data:
        data += recv_force()
    return data
def send(data):
    logger.debug("SSH send: %r", data)
    channel.send(data)
def srp(d):
        send(d)
        return recv_until_prompt()
def run_command(cmd):
    result = srp(cmd + b'\r')
    needle = b'status_tag=COMMAND COMPLETED\r\n'
    idx = result.index(needle)
    return result[idx+len(needle):].split(b'\n', 4)[-1]

recv_until_prompt()
run_command('show')

logger.info("ready")
def hexdump(src, length=16):
    FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
    lines = []
    for c in xrange(0, len(src), length):
        chars = src[c:c+length]
        hex = ' '.join(["%02x" % ord(x) for x in chars])
        printable = ''.join(["%s" % ((ord(x) <= 127 and FILTER[ord(x)]) or '.') for x in chars])
        lines.append("%04x  %-*s  %s\n" % (c, length*3, hex, printable))
    return ''.join(lines)

A16_ENCODING = [c.encode('ascii') for c in 'ABCDEFGHIJKLMNOP']
def a16_u8_encode(val):
    """Encode a u8 in alpha-16 encoding"""
    assert 0 <= val <= 0xff
    return A16_ENCODING[val >> 4] + A16_ENCODING[val & 15]
def a16_data_encode(data):
    return b''.join(a16_u8_encode(struct.unpack('B', data[i:i+1])[0]) for i in range(len(data)))
def a16_u32_encode(val):
    """Encode a u32 in alpha-16 encoding (in Big Endian)"""
    return a16_data_encode(struct.pack('>I', val))

def send_custom(op, arg1, *args):
    arg1 = a16_u32_encode(arg1)
    cmd = triggerCommand + b' ' + op.encode('ascii') + arg1
    if args:
        cmd += b' ' + b' '.join(a.encode('ascii') if isinstance(a, str) else a for a in args)
    logger.debug(hexdump(cmd))
    # cmd = b'uname'
    output = srp(cmd + b'\r')
    cmdindex = output.index(cmd)
    output_prefix = output[:cmdindex].lstrip(b'\r\n')
    output = output_prefix + output[cmdindex + len(cmd):].lstrip(b'\r\n')
    output = output[:output.rindex(b'hpiLO')].rsplit(b'\n', 1)[0]
    return output.strip(b'\r\n')

def exec_read(cmd):
    if len(cmd) < 3:
        print "r [address] [len]"
        return
    addr = int(cmd[1], 0)
    result = send_custom('r', addr, cmd[2])
    print hexdump(result)
    print result
    return result
def exec_write_partial(addr, data):
    if not data:
        return (0, b'')
    size = min(len(data), 100)
    output = send_custom('w', addr, a16_data_encode(data[:size]))
    all_lines = [line.strip() for line in output.decode('ascii').splitlines() if line not in ('', ' ', '> ', '-> ')]
    if len(all_lines) != size:
        logger.error("Unexpected output line number, got %d expected %d", len(all_lines), size)
    assert len(all_lines) == size
    for i, line in enumerate(all_lines):
            logger.debug(line)
            expected = '%#x <- %#x' % (addr + i, bytearray(data[i])[0])
            if expected.endswith(' <- 0x0'):
                expected = '%#x <- 0' % (addr+i)
            if expected != line:
                logger.warning("Unexpected write writing 0x%02x to %#x: got %r instead of %r", data[i], addr+i, line, expected)
    return (size, data[size:])

def exec_write(cmd):
    # w [address] [data]
    if len(cmd) < 3:
        print "w [address] [data]"
        return
    addr = int(cmd[1], 0)
    data = cmd[2]
    while data:
        size, data = exec_write_partial(addr, data)
        addr += size

def exec_exec(cmd):
    # x [address]
    addr = int(cmd[1], 0)
    print send_custom('x', addr)

def exec_alloc(cmd):
    # a [size]
    size = int(cmd[1], 0)
    output = send_custom('a', size)
    if output == b'alloc 0':
        logger.error("OUT OF MEMORY")
    prefix = b'alloc 0x'
    assert output.startswith(prefix)
    print output
    return int(output[len(prefix):], 16)

def exec_free(cmd):
    # f [address]
    addr = int(cmd[1], 0)
    print send_custom('f', addr)
def read_patch(file):
    dir = os.path.dirname(sys.argv[2])
    patch = os.path.join(dir, "asm", file)

    with open(patch, "rb") as f:
        handler = f.read()
        # remove comments ...
        handler_split = handler.split('\n')
        for i in range(len(handler_split)):
            this_line = handler_split[i]
            this_line = this_line.split(";")[0]
            handler_split[i] = this_line
        handler = "\n".join(handler_split)
        print handler
        ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
        try:
            output = ks.asm(handler)
        except KsError as e:
            print "Error with Keystone ", e.message
            if e.get_asm_count() is not None:
                print "asmcount = %u" % e.get_asm_count()
            sys.exit(1)
        return ''.join(chr(x) for x in output[0])
def exec_write_file(cmd):
    # wf [file]
    if len(cmd) < 2:
        print "wf [file]"
        return
    patch = read_patch(cmd[1])
    addr = exec_alloc(['a', str(len(patch)+16)])
    print "allocated 0x%x bytes at 0x%x" % (len(patch)+16, addr)
    exec_write(['w', "0x%x" % addr, patch])
    print "wrote to 0x%x, execute with x 0x%x" % (addr, addr)
while True:
    cmd = raw_input("> ")
    cmd = cmd.split(' ')
    if cmd[0] == 'r':
        exec_read(cmd)
    elif cmd[0] == 'w':
        exec_write(cmd)
    elif cmd[0] == 'x':
        exec_exec(cmd)
    elif cmd[0] == 'a':
        exec_alloc(cmd)
    elif cmd[0] == 'f':
        exec_free(cmd)
    elif cmd[0] == 'wf':
        exec_write_file(cmd)
    elif cmd[0] =='exit':
        break
    else:
        print("????")

if client:
    client.close()
