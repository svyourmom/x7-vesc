#!/usr/bin/env python3
"""Decode the EBMX/CYC 'Firmware Update' app's boot_loader.json into the on-wire
VESC bootloader-update sequence, and (optionally) rebuild the resident bootloader
image for inspection. Analysis-only: NO Bluetooth, writes nothing to any device.

See ../docs/10-bootloader-over-ble.md. Frame format is standard VESC:
  [start][len][payload][crc16-xmodem:2][0x03]   (start 0x02/0x03/0x04 -> 1/2/3-byte len)
Bootloader-update payloads observed:
  id 73 (0x49) ERASE_BOOTLOADER           payload = [0x49]
  id 81 (0x51) WRITE_NEW_APP_DATA_LZO     payload = [0x51][off:u32 BE][declen:u16 BE][lzo1x]
  id  3 (0x03) WRITE_NEW_APP_DATA (tail)  payload = [0x03][off:u32 BE][raw...]

boot_loader.json is EBMX/VESC copyright and is NOT included here (gitignored);
extract it from your own copy of the app. --rebuild needs liblzo2 (lzokay emits LZO1X).

Usage:
  decode-bootloader-json.py plan    boot_loader.json
  decode-bootloader-json.py rebuild boot_loader.json out_bootloader.bin
"""
import argparse, json, struct, sys, ctypes

def deframe(p):
    b = bytes(p)
    if b[0] == 2: ln = b[1];                         return b[2:2+ln]
    if b[0] == 3: ln = (b[1] << 8) | b[2];           return b[3:3+ln]
    if b[0] == 4: ln = (b[1]<<16)|(b[2]<<8)|b[3];    return b[4:4+ln]
    raise ValueError("bad frame start 0x%02x" % b[0])

def _lzo():
    try:
        lib = ctypes.CDLL("liblzo2.so.2")
    except OSError:
        sys.exit("need liblzo2 for --rebuild (Debian/Ubuntu: apt install liblzo2-2)")
    lib.lzo1x_decompress_safe.restype = ctypes.c_int
    lib.lzo1x_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_ulong,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
    return lib

def walk(doc):
    """yield (index, cmd, offset, declen, data) for each txd write/erase packet."""
    for i, p in enumerate(doc["txd"]):
        pl = deframe(p); cmd = pl[0]
        if cmd == 0x49:
            yield i, cmd, None, None, b""; continue
        off = struct.unpack_from(">I", pl, 1)[0]
        if cmd == 0x51:
            declen = struct.unpack_from(">H", pl, 5)[0]
            yield i, cmd, off, declen, bytes(pl[7:])
        elif cmd == 0x03:
            yield i, cmd, off, None, bytes(pl[5:])
        else:
            yield i, cmd, off, None, bytes(pl[1:])

def cmd_plan(a):
    doc = json.load(open(a.json))
    ntx, nrx = len(doc.get("txd", [])), len(doc.get("rxd", []))
    print(f"transcript: {ntx} txd / {nrx} rxd packets\n")
    names = {0x49: "ERASE_BOOTLOADER(73)", 0x51: "WRITE_NEW_APP_DATA_LZO(81)",
             0x03: "WRITE_NEW_APP_DATA(3,raw)"}
    for i, cmd, off, declen, data in walk(doc):
        if cmd == 0x49:
            print(f"txd[{i:2}] {names[cmd]}")
        else:
            extra = f"declen={declen}" if declen is not None else f"raw={len(data)}"
            print(f"txd[{i:2}] {names.get(cmd,hex(cmd)):26} off=0x{off:06x} (=abs 0x{0x08000000+off:08x}) comp/len={len(data):4} {extra}")

def cmd_rebuild(a):
    doc = json.load(open(a.json)); lzo = _lzo(); chunks = {}
    for i, cmd, off, declen, data in walk(doc):
        if cmd == 0x49: continue
        if cmd == 0x51:
            dst = ctypes.create_string_buffer(declen + 128); dl = ctypes.c_ulong(declen + 128)
            rc = lzo.lzo1x_decompress_safe(data, len(data), dst, ctypes.byref(dl), None)
            if rc != 0: sys.exit(f"lzo decompress failed on txd[{i}] rc={rc}")
            chunks[off] = dst.raw[:dl.value]
        elif cmd == 0x03:
            chunks[off] = data
    if not chunks: sys.exit("no write chunks found")
    mn = min(chunks); mx = max(k + len(v) for k, v in chunks.items())
    buf = bytearray(mx - mn)
    for o, v in chunks.items(): buf[o-mn:o-mn+len(v)] = v
    open(a.out, "wb").write(buf)
    sp, reset = struct.unpack_from("<II", buf, 0)
    import hashlib
    print(f"{len(buf)} bytes -> {a.out}")
    print(f"  staged @ 0x{0x08000000+mn:08x}..0x{0x08000000+mx:08x}")
    print(f"  vec[0] SP=0x{sp:08x}  vec[1] Reset=0x{reset:08x}  (bootloader links @0x080E0000)")
    print(f"  sha256={hashlib.sha256(buf).hexdigest()}")
    print("  NOTE: EBMX/VESC copyright -- keep private, do not commit.")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan");    p.add_argument("json"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("rebuild"); p.add_argument("json"); p.add_argument("out"); p.set_defaults(fn=cmd_rebuild)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
