"""Check rtl8159-1.fw the way the kernel does before loading it.

Mirrors rtl8152_check_firmware() and rtl8152_is_fw_phy_speed_up_ok() in
drivers/net/usb/r8152.c, and with --source also re-reads the patch from
r8152.c independently of pack.py and compares it.
"""

import argparse
import hashlib
import struct
import sys

RTL_FW_END = 0
RTL_FW_PHY_SPEED_UP = 13
HEADER = 64
SPEED_UP = 16


def fail(msg):
    sys.exit(f"verify.py: {msg}")


def check(fw):
    if len(fw) < HEADER:
        fail("file too small")
    if hashlib.sha256(fw[32:]).digest() != fw[:32]:
        fail("checksum mismatch")
    if b"\0" not in fw[32:HEADER]:
        fail("header version is not NUL-terminated")

    speed_up = None
    i = HEADER
    while True:
        if i + 8 > len(fw):
            fail(f"no END block before offset {i}")
        kind, length = struct.unpack_from("<II", fw, i)
        if kind == RTL_FW_END:
            if length != 8:
                fail(f"END block length {length}")
            if i + 8 != len(fw):
                fail(f"{len(fw) - i - 8} bytes after the END block")
            break
        if kind != RTL_FW_PHY_SPEED_UP:
            fail(f"unexpected block type {kind} at offset {i}")
        if speed_up is not None:
            fail("multiple PHY speed-up blocks")
        if i + length > len(fw):
            fail("speed-up block runs past the end of the file")
        fw_offset, version, fw_reg = struct.unpack_from("<HHH", fw, i + 8)
        if fw_offset < SPEED_UP or length <= fw_offset:
            fail(f"invalid fw_offset {fw_offset:#x}")
        if (length - fw_offset) & 3:
            fail("patch is not a whole number of 32-bit words")
        if fw_reg != 0x9A00:
            fail(f"fw_reg {fw_reg:#x}, the kernel only accepts 0x9a00")
        info = fw[i + SPEED_UP : i + fw_offset]
        if b"\0" not in info:
            fail("info string is not NUL-terminated")
        speed_up = (version, fw[i + fw_offset : i + length])
        # The kernel steps to the next block on an 8-byte boundary.
        i += (length + 7) & ~7

    if speed_up is None:
        fail("no PHY speed-up block")
    return speed_up


def source_patch(path):
    """Line-wise read of the ram17 array and the code_ver right after it."""
    with open(path, encoding="utf-8") as f:
        lines = iter(f.read().splitlines())
    for line in lines:
        if line.strip() == "static u8 ram17[] = {":
            break
    else:
        fail("no ram17 array in source")
    data = bytearray()
    for line in lines:
        body = line.split("/*")[0].split("//")[0].strip()
        data += bytes(int(b, 16) for b in body.rstrip("};").split(",") if b.strip())
        if body.endswith("};"):
            break
    for line in lines:
        if line.strip():
            name, _, value = line.strip().rstrip(";").partition(" = ")
            if name != "code_ver":
                fail(f"expected code_ver after ram17, got {line.strip()!r}")
            return int(value, 16), bytes(data)
    fail("source ends after ram17")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("firmware")
    ap.add_argument("--source", help="r8152.c the firmware should come from")
    args = ap.parse_args()

    with open(args.firmware, "rb") as f:
        version, patch = check(f.read())
    if args.source:
        code_ver, data = source_patch(args.source)
        if version != code_ver:
            fail(f"block version {version:#06x}, r8152.c code_ver {code_ver:#06x}")
        if patch != data:
            fail("patch differs from r8152.c's ram17")
    print(f"{args.firmware}: ok, PHY patch version {version:#06x}", file=sys.stderr)


if __name__ == "__main__":
    main()
