"""Pack the RTL8159 PHY patch from Realtek's r8152.c into rtl_nic/rtl8159-1.fw.

The layout is what the in-kernel r8152 driver loads (struct fw_header,
struct fw_phy_speed_up and enum rtl_fw_type in drivers/net/usb/r8152.c).
"""

import argparse
import hashlib
import re
import struct
import sys

RTL_FW_END = 0
RTL_FW_PHY_SPEED_UP = 13
# The kernel rejects a speed-up block aimed at any other register.
FW_REG = 0x9A00
# Header and info fields are fixed 32-byte, NUL-terminated strings.
FIELD = 32
# sizeof(struct fw_phy_speed_up) plus its info field.
FW_OFFSET = 16 + FIELD

DRIVER_VERSION = re.compile(
    r'#define DRIVER_VERSION "v([0-9.]+)"DRIVER_SUFFIX" \((\d{4})/(\d{2})/(\d{2})\)"'
)
# The RTL8159 branch of rtl_ram_code_speed_up(): the patch, then its version.
RAM17 = re.compile(
    r"static u8 ram17\[\] = \{([^}]*)\};\s*code_ver = (0x[0-9a-fA-F]{4});"
)
BYTE = re.compile(r"0x[0-9a-fA-F]{2}")
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def fail(msg):
    sys.exit(f"pack.py: {msg}")


def extract(src):
    driver = DRIVER_VERSION.findall(src)
    if len(driver) != 1:
        fail(f"expected one DRIVER_VERSION, found {len(driver)}")
    patches = RAM17.findall(src)
    if len(patches) != 1:
        fail(f"expected one ram17 array followed by code_ver, found {len(patches)}")
    body, code_ver = patches[0]
    tokens = [t.strip() for t in COMMENT.sub("", body).split(",") if t.strip()]
    bad = [t for t in tokens if not BYTE.fullmatch(t)]
    if bad:
        fail(f"ram17 holds non-byte tokens: {bad[:5]}")
    ram = bytes(int(t, 16) for t in tokens)
    # The kernel streams the patch in 32-bit words; Realtek ends it with ff ff ff ff.
    if len(ram) % 4 or not ram.endswith(b"\xff" * 4):
        fail("ram17 is not a whole number of words ending in ff ff ff ff")
    return driver[0], ram, int(code_ver, 16)


def field(name, text):
    raw = text.encode("ascii")
    if len(raw) >= FIELD:
        fail(f"{name} {text!r} is longer than {FIELD - 1} characters")
    return raw.ljust(FIELD, b"\0")


def pack(ram, code_ver, version, info):
    block = struct.pack(
        "<IIHHHH",
        RTL_FW_PHY_SPEED_UP,
        FW_OFFSET + len(ram),
        FW_OFFSET,
        code_ver,
        FW_REG,
        0,
    )
    block += field("info", info) + ram
    block += b"\0" * (-len(block) % 8)
    body = field("version", version) + block + struct.pack("<II", RTL_FW_END, 8)
    return hashlib.sha256(body).digest() + body


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="Realtek's r8152.c")
    ap.add_argument("output", help="where to write rtl8159-1.fw")
    ap.add_argument(
        "--driver-version", help="fail unless r8152.c is this release, e.g. 2.22.1"
    )
    ap.add_argument("--version-label", help="override the header version string")
    ap.add_argument("--info", help="override the speed-up block's info string")
    args = ap.parse_args()

    with open(args.source, encoding="utf-8") as f:
        (driver, y, m, d), ram, code_ver = extract(f.read())
    if args.driver_version and args.driver_version != driver:
        fail(f"r8152.c is v{driver}, expected v{args.driver_version}")

    # ethtool -i reports the version string as the adapter's firmware-version.
    version = args.version_label or f"rtl8159-1 v{driver} {y}/{m}/{d}"
    info = args.info or f"tgphy_ramcode_v{code_ver:x}_usb_{y}{m}{d}"
    with open(args.output, "wb") as f:
        f.write(pack(ram, code_ver, version, info))
    print(
        f"r8152 v{driver}: {len(ram)}-byte patch, code_ver {code_ver:#06x}, '{version}'",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
