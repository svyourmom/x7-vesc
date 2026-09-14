#!/usr/bin/env python3
"""VESC firmware uploader over the X-9000's BLE Nordic UART bridge.

Replicates vesc_tool's app-upload flow (verified against this firmware in Ghidra:
ERASE_NEW_APP=2, WRITE_NEW_APP_DATA=3, JUMP_TO_BOOTLOADER=1; NEW_APP_BASE = flash
sector 8 @0x08080000; header = big-endian [u32 size][u16 crc16-xmodem(fw)] then fw;
the bootloader validates the CRC BEFORE copying staging->app, so a bad/rejected
image fails safe and leaves the running app intact).

    # zero-risk: build the stream and inspect it, NO Bluetooth
    .venv/bin/python src/vesc-fw-upload.py plan  reference/firmware/X9KV3_260714.bin

    # read the current fw id over BLE (no writing)
    .venv/bin/python src/vesc-fw-upload.py preflight

    # ACTUALLY FLASH (requires the bin, --yes, and you present with recovery ready)
    .venv/bin/python src/vesc-fw-upload.py flash reference/firmware/X9KV3_260714.bin --yes

    # same, but LZO-compressed writes (id=81) like the vendor app -- fewer bytes on air
    .venv/bin/python src/vesc-fw-upload.py flash reference/firmware/X9KV3_260714.bin --lzo --yes

`--lzo` streams WRITE_NEW_APP_DATA_LZO(81) blocks (needs liblzo2); the on-wire block format
matches the EBMX app's boot_loader.json. The uncompressed id=3 path stays the default. The LZO
path here is verified host-side (each block is round-tripped through the decompressor) and matches
the vendor stream, but has not been round-tripped on hardware in this repo -- prefer the default
unless you have SWD recovery ready.

DANGER: `flash` erases the new-app staging area and, on JUMP_TO_BOOTLOADER, asks the
bootloader to overwrite the running firmware. Brick recovery = SWD/ST-Link on the board.
"""
import argparse, asyncio, ctypes, struct, sys, time
# bleak is imported lazily inside the BLE commands so `plan` stays truly zero-Bluetooth.

ADDR   = "C5:22:A5:12:A4:9F"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
ERASE_NEW_APP, WRITE_NEW_APP_DATA, JUMP_TO_BOOTLOADER, FW_VERSION = 2, 3, 1, 0
WRITE_NEW_APP_DATA_LZO = 81       # LZO1X variant; payload = [81][off:u32 BE][declen:u16 BE][lzo]
CHUNK   = 240                     # uncompressed: data bytes/packet -> payload 245 <= 255 (short frame)
LZO_BLK = 384                     # LZO: decompressed bytes/block. 384 = the value the vendor app uses
                                  # (seen in boot_loader.json) -- a device-proven, safe block size.

def crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc
assert crc16(b"123456789") == 0x31C3, "CRC-16/XMODEM check value failed"

def frame(payload: bytes) -> bytes:
    n = len(payload)
    if n <= 255:      hdr = bytes([2, n])
    elif n <= 65535:  hdr = bytes([3, n >> 8, n & 0xFF])
    else:             hdr = bytes([4, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    c = crc16(payload)
    return hdr + payload + bytes([c >> 8, c & 0xFF, 3])

class Unframer:
    def __init__(self): self.buf = bytearray()
    def feed(self, chunk: bytes):
        self.buf += chunk; out = []
        while True:
            while self.buf and self.buf[0] not in (2, 3, 4): self.buf.pop(0)
            if not self.buf: break
            s = self.buf[0]; nlen = s - 1
            if len(self.buf) < 1 + nlen: break
            n = int.from_bytes(self.buf[1:1 + nlen], "big")
            total = 1 + nlen + n + 3
            if len(self.buf) < total: break
            pl = bytes(self.buf[1 + nlen:1 + nlen + n])
            rx = int.from_bytes(self.buf[1 + nlen + n:1 + nlen + n + 2], "big")
            if self.buf[total - 1] == 3 and rx == crc16(pl):
                out.append(pl); del self.buf[:total]
            else:
                self.buf.pop(0)
        return out

def build_image(fw: bytes) -> bytes:
    """[u32 size BE][u16 crc16(fw) BE][fw]  -- exactly what vesc_tool stages."""
    return struct.pack(">IH", len(fw), crc16(fw)) + fw

# --- LZO1X (optional, --lzo). Matches the vendor app's WRITE_NEW_APP_DATA_LZO(81) stream:
#     per block  [81][off:u32 BE][declen:u16 BE][lzo1x-bytes] , off = decompressed offset.
# Compression is host-side via liblzo2; each block is round-tripped through the decompressor
# here so we never put a stream on the wire that would not decode on the device (same LZO1X). ---
class _Lzo:
    def __init__(self):
        try:
            self.l = ctypes.CDLL("liblzo2.so.2")
        except OSError:
            sys.exit("--lzo needs liblzo2 (Debian/Ubuntu: apt install liblzo2-2)")
        self.l.lzo1x_1_compress.restype = ctypes.c_int
        self.l.lzo1x_1_compress.argtypes = [ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p,
                                            ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        self.l.lzo1x_decompress_safe.restype = ctypes.c_int
        self.l.lzo1x_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p,
                                                 ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        self.wrk = ctypes.create_string_buffer(1 << 18)   # >= LZO1X_1_MEM_COMPRESS on 64-bit
    def compress(self, block: bytes) -> bytes:
        dst = ctypes.create_string_buffer(len(block) + len(block)//16 + 64 + 3)
        dl = ctypes.c_ulong(len(dst))
        if self.l.lzo1x_1_compress(block, len(block), dst, ctypes.byref(dl), self.wrk) != 0:
            sys.exit("lzo compress failed")
        comp = dst.raw[:dl.value]
        chk = ctypes.create_string_buffer(len(block) + 64); cl = ctypes.c_ulong(len(chk))
        if self.l.lzo1x_decompress_safe(comp, len(comp), chk, ctypes.byref(cl), None) != 0 \
           or chk.raw[:cl.value] != block:
            sys.exit("lzo self-check failed -- refusing to send an undecodable block")
        return comp

def lzo_packets(img: bytes, blk: int):
    """yield (offset, declen, payload) WRITE_NEW_APP_DATA_LZO packets for the staged image."""
    z = _Lzo()
    for off in range(0, len(img), blk):
        block = img[off:off+blk]
        comp = z.compress(block)
        yield off, len(block), bytes([WRITE_NEW_APP_DATA_LZO]) + struct.pack(">IH", off, len(block)) + comp

def decode_fw(pl: bytes):
    if len(pl) < 3: return None
    hw = pl[3:].split(b"\x00")[0].decode("utf-8", "replace")
    return {"fw": f"{pl[1]}.{pl[2]}", "hw": hw}

def cmd_plan(args):
    fw = open(args.bin, "rb").read()
    img = build_image(fw)
    print(f"firmware file : {args.bin}")
    print(f"fw size       : {len(fw)} bytes")
    print(f"crc16(fw)     : 0x{crc16(fw):04X}")
    print(f"staged image  : {len(img)} bytes  (6-byte header + fw)")
    print(f"header (hex)   : {img[:6].hex()}   = size={struct.unpack('>I',img[:4])[0]} crc=0x{struct.unpack('>H',img[4:6])[0]:04X}")
    print(f"ERASE_NEW_APP  : 02 {len(img):08x}  (payload id=2 + u32 image size)")
    if args.lzo:
        pkts = list(lzo_packets(img, args.lzo_block))
        comp_total = sum(len(p) for _, _, p in pkts)
        print(f"mode           : LZO (id=81), block={args.lzo_block} decompressed bytes")
        print(f"WRITE packets  : {len(pkts)} x [81][u32 off][u16 declen][lzo]  "
              f"(compressed payload {comp_total} B, {100*comp_total/max(len(img),1):.0f}% of raw)")
        print(f"first WRITE pl : {pkts[0][2][:24].hex()} ...")
    else:
        nchunks = (len(img) + CHUNK - 1) // CHUNK
        print(f"mode           : uncompressed (id=3)")
        print(f"WRITE packets  : {nchunks} x (id=3 + u32 offset + <=240 data)")
        print(f"first WRITE pl : {(bytes([WRITE_NEW_APP_DATA])+struct.pack('>I',0)+img[:16]).hex()} ...")
    print(f"JUMP_TO_BOOTLOADER: 01")
    print("\n(plan only -- no Bluetooth was used)")

async def _connect():
    from bleak import BleakScanner
    dev = await BleakScanner.find_device_by_address(ADDR, timeout=25.0)
    if dev is None: sys.exit(f"{ADDR} not advertising -- powered on and in range?")
    return dev

def cmd_preflight(args):
    async def run():
        from bleak import BleakClient
        dev = await _connect(); un = Unframer(); got = []
        def on(_, d):
            for pl in un.feed(bytes(d)):
                if pl and pl[0] == FW_VERSION: got.append(decode_fw(pl))
        async with BleakClient(dev, timeout=30.0) as c:
            print(f"connected to {dev.name} [{dev.address}]")
            await c.start_notify(NUS_TX, on)
            pkt = frame(bytes([FW_VERSION]))
            for i in range(0, len(pkt), 20):
                await c.write_gatt_char(NUS_RX, pkt[i:i+20], response=False); await asyncio.sleep(0.02)
            await asyncio.sleep(2.0); await c.stop_notify(NUS_TX)
        print("FW_VERSION:", got[-1] if got else "(no reply)")
    asyncio.run(run())

def cmd_flash(args):
    fw = open(args.bin, "rb").read()
    img = build_image(fw)
    pkts = list(lzo_packets(img, args.lzo_block)) if args.lzo else None
    nchunks = len(pkts) if args.lzo else (len(img) + CHUNK - 1) // CHUNK
    mode = f"LZO id=81 blk={args.lzo_block}" if args.lzo else "uncompressed id=3"
    print(f"about to FLASH {args.bin}: fw={len(fw)}B crc=0x{crc16(fw):04X} image={len(img)}B "
          f"({nchunks} write packets, {mode})")
    if not args.yes:
        sys.exit("refusing to flash without --yes")
    if input('type "FLASH" to proceed: ').strip() != "FLASH":
        sys.exit("aborted")

    async def run():
        from bleak import BleakClient
        dev = await _connect(); un = Unframer()
        acks = asyncio.Queue()
        def on(_, d):
            for pl in un.feed(bytes(d)):
                if pl: acks.put_nowait(pl)
        async def send(client, payload):
            pkt = frame(payload)
            for i in range(0, len(pkt), 20):
                await client.write_gatt_char(NUS_RX, pkt[i:i+20], response=False)
                await asyncio.sleep(0.006)
        async def wait_ack(cmd_id, timeout):
            end = time.time() + timeout
            while time.time() < end:
                try:
                    pl = await asyncio.wait_for(acks.get(), timeout=max(end - time.time(), 0.01))
                except asyncio.TimeoutError:
                    break
                if pl and pl[0] == cmd_id: return pl
            return None
        async with BleakClient(dev, timeout=30.0) as client:
            print(f"connected to {dev.name} [{dev.address}]")
            await client.start_notify(NUS_TX, on)
            # pre-flight fw id
            await send(client, bytes([FW_VERSION])); pl = await wait_ack(FW_VERSION, 3)
            print("  before:", decode_fw(pl) if pl else "(no fw reply)")
            # erase
            print("  ERASE_NEW_APP ...")
            await send(client, bytes([ERASE_NEW_APP]) + struct.pack(">I", len(img)))
            pl = await wait_ack(ERASE_NEW_APP, 15)
            if pl is None: sys.exit("  ERASE ack timeout -- aborting (nothing copied yet)")
            print(f"  erase ack: {pl.hex()}")
            # write chunks. Both id=3 and id=81 are handled by the same firmware routine and
            # reply with id=3 (WRITE_NEW_APP_DATA) -- confirmed by the vendor transcript acks.
            t0 = time.time()
            for k in range(nchunks):
                if args.lzo:
                    off, _declen, payload = pkts[k]
                else:
                    off = k * CHUNK
                    payload = bytes([WRITE_NEW_APP_DATA]) + struct.pack(">I", off) + img[off:off+CHUNK]
                await send(client, payload)
                pl = await wait_ack(WRITE_NEW_APP_DATA, 4)
                if pl is None: sys.exit(f"\n  WRITE ack timeout at offset {off} -- aborting (no jump sent; running app intact)")
                if k % 25 == 0 or k == nchunks-1:
                    pct = 100*(k+1)/nchunks; rate=(off+LZO_BLK if args.lzo else off+CHUNK)/max(time.time()-t0,1e-3)
                    print(f"\r  writing {k+1}/{nchunks} ({pct:4.1f}%)  {rate/1024:5.1f} KiB/s", end="", flush=True)
            print("\n  all chunks acked.")
            if args.no_jump:
                print("  --no-jump: staged but NOT jumping. Send JUMP_TO_BOOTLOADER later to apply.")
            else:
                print("  JUMP_TO_BOOTLOADER (device will reboot & bootloader validates+copies) ...")
                await send(client, bytes([JUMP_TO_BOOTLOADER]))
                await asyncio.sleep(1.0)
            await client.stop_notify(NUS_TX)
        print("done. If it took: reconnect and check fw id. If not: running app was kept (CRC-validated copy).")
    asyncio.run(run())

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    def add_lzo(pp):
        pp.add_argument("--lzo", action="store_true",
                        help="compress writes with LZO1X (id=81), as the vendor app does; needs liblzo2")
        pp.add_argument("--lzo-block", type=int, default=LZO_BLK, metavar="N",
                        help=f"LZO decompressed bytes/block (default {LZO_BLK}, the vendor-observed size)")
    p = sub.add_parser("plan"); p.add_argument("bin"); add_lzo(p); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("preflight"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("flash"); p.add_argument("bin"); p.add_argument("--yes", action="store_true")
    p.add_argument("--no-jump", action="store_true", help="stage only, do not JUMP_TO_BOOTLOADER")
    add_lzo(p); p.set_defaults(fn=cmd_flash)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
